"""Runtime Verifier — executes synthesized pytest suites and captures results.

Implements Algorithm 5 from the design document.  The verifier:
1. Writes a temporary test module containing the target source code and
   synthesized test functions, plus a companion conftest.py with a
   ResultCollector plugin.
2. Runs pytest in an isolated subprocess with a configurable timeout
   (default 30 s) to capture per-test stdout, stderr, tracebacks, and
   durations.
3. Returns a list of result dicts keyed by nodeid, outcome, stdout,
   stderr, traceback, and duration.

Requirements: 4.1, 4.6, 11.1
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from typing import Any

import re

from app.config import settings
from app.schemas import SynthesizedTest, TestOutcome, ViolationRecord, ViolationReport

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conftest content — written as a companion file so pytest auto-discovers
# the ResultCollector plugin in the subprocess.
# ---------------------------------------------------------------------------

_CONFTEST_CONTENT = textwrap.dedent("""\
    \"\"\"Auto-generated conftest.py for VeriDoc Runtime Verifier.\"\"\"
    import json as _json
    import os as _os

    class _ResultCollector:
        \"\"\"Custom pytest plugin to collect per-test results.\"\"\"

        def __init__(self):
            self.results = []

        def pytest_runtest_logreport(self, report):
            if report.when == "call":
                self.results.append({
                    "nodeid": report.nodeid,
                    "outcome": report.outcome,
                    "stdout": report.capstdout or "",
                    "stderr": report.capstderr or "",
                    "traceback": str(report.longrepr) if report.longrepr else None,
                    "duration": report.duration,
                })
            elif report.when == "setup" and report.outcome != "passed":
                self.results.append({
                    "nodeid": report.nodeid,
                    "outcome": "error",
                    "stdout": report.capstdout or "",
                    "stderr": report.capstderr or "",
                    "traceback": str(report.longrepr) if report.longrepr else None,
                    "duration": report.duration,
                })

    _collector = _ResultCollector()

    def pytest_configure(config):
        config.pluginmanager.register(_collector, "_result_collector")

    def pytest_unconfigure(config):
        results_path = _os.environ.get("_VERIDOC_RESULTS_PATH", "")
        if results_path:
            with open(results_path, "w") as f:
                _json.dump(_collector.results, f)
""")


class RuntimeVerifier:
    """Executes synthesized pytest test suites against target functions.

    Parameters
    ----------
    timeout : int
        Maximum wall-clock seconds for the subprocess (default from
        ``settings.test_timeout``, which defaults to 30).
    """

    def __init__(self, timeout: int | None = None) -> None:
        self.timeout = timeout if timeout is not None else settings.test_timeout

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def _write_test_module(
        self,
        tests: list[SynthesizedTest],
        source_code: str,
    ) -> str:
        """Write a temporary test file containing source + synthesized tests.

        Creates a dedicated temp directory with:
        - ``conftest.py`` — ResultCollector plugin for capturing results
        - ``test_veridoc_rv.py`` — target source code + synthesized tests

        Parameters
        ----------
        tests : list[SynthesizedTest]
            Synthesized test objects whose ``test_code`` will be appended.
        source_code : str
            The Python source containing the functions under test.

        Returns
        -------
        str
            Absolute path to the temporary test ``.py`` file.
        """
        tmpdir = tempfile.mkdtemp(prefix="veridoc_rv_")

        test_path = os.path.join(tmpdir, "test_veridoc_rv.py")
        conftest_path = os.path.join(tmpdir, "conftest.py")

        # 1. Write conftest.py with the ResultCollector plugin
        with open(conftest_path, "w", encoding="utf-8") as fh:
            fh.write(_CONFTEST_CONTENT)

        # 2. Build the test module
        lines: list[str] = []

        lines.append("# --- Target source code ---")
        lines.append(source_code.rstrip())
        lines.append("")
        lines.append("")

        lines.append("# --- Synthesized tests ---")
        for test in tests:
            lines.append(test.test_code.rstrip())
            lines.append("")
            lines.append("")

        content = "\n".join(lines)

        with open(test_path, "w", encoding="utf-8") as fh:
            fh.write(content)

        logger.debug("Wrote RV test module to %s (%d bytes)", test_path, len(content))
        return test_path

    # ------------------------------------------------------------------
    # Outcome classification
    # ------------------------------------------------------------------

    _OUTCOME_MAP: dict[str, TestOutcome] = {
        "passed": TestOutcome.PASS,
        "failed": TestOutcome.FAIL,
        "error": TestOutcome.ERROR,
    }

    def _classify_outcome(self, result: dict[str, Any]) -> TestOutcome:
        """Deterministically map a pytest outcome string to a TestOutcome enum.

        Mapping:
        - ``"passed"`` → :attr:`TestOutcome.PASS`
        - ``"failed"`` → :attr:`TestOutcome.FAIL`
        - ``"error"``  → :attr:`TestOutcome.ERROR`
        - anything else → :attr:`TestOutcome.UNDETERMINED`

        Requirements: 4.2, 4.3, 4.4
        """
        return self._OUTCOME_MAP.get(result.get("outcome", ""), TestOutcome.UNDETERMINED)

    # ------------------------------------------------------------------
    # Expected / actual extraction
    # ------------------------------------------------------------------

    _ASSERT_PATTERN = re.compile(
        r"assert\s+(.+?)\s*==\s*(.+?)(?:\s*$|\s*,)",
        re.MULTILINE,
    )

    def _extract_expected_actual(
        self, traceback: str | None,
    ) -> tuple[str | None, str | None]:
        """Extract expected and actual values from a failure traceback.

        Looks for ``assert <actual> == <expected>`` patterns in the
        traceback text.  Returns ``(expected, actual)`` or ``(None, None)``
        if no pattern is found.
        """
        if not traceback:
            return None, None
        m = self._ASSERT_PATTERN.search(traceback)
        if m:
            actual = m.group(1).strip()
            expected = m.group(2).strip()
            return expected, actual
        return None, None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify(
        self,
        test_suite: list[SynthesizedTest],
        source_code: str,
        analysis_id: str = "",
        function_name: str = "",
    ) -> ViolationReport:
        """Execute all synthesized tests and produce a ViolationReport.

        Steps:
        1. Write a temporary test module with *source_code* + test functions.
        2. Run pytest in an isolated subprocess.
        3. Classify each outcome and extract expected/actual from tracebacks.
        4. Compute ``bcv_rate = fail_count / (pass_count + fail_count)``,
           excluding ERROR and UNDETERMINED outcomes.
        5. Return a :class:`ViolationReport` whose ``violations`` list
           contains only FAIL outcomes.

        Requirements: 4.2, 4.3, 4.4, 4.5, 4.7, 10.5, 10.6
        """
        if not test_suite:
            return ViolationReport(
                analysis_id=analysis_id,
                function_name=function_name,
                total_claims=0,
            )

        # 1. Write temp test module
        test_file = self._write_test_module(test_suite, source_code)

        # 2. Run pytest
        raw_results = self._run_pytest(test_file)

        # Build a nodeid → result lookup for matching back to tests
        result_by_name: dict[str, dict[str, Any]] = {}
        for r in raw_results:
            # nodeid looks like "test_veridoc_rv.py::test_foo"
            name = r["nodeid"].split("::")[-1] if "::" in r["nodeid"] else r["nodeid"]
            result_by_name[name] = r

        # 3. Classify outcomes and build records
        all_records: list[ViolationRecord] = []
        pass_count = 0
        fail_count = 0
        error_count = 0

        for test in test_suite:
            result = result_by_name.get(test.test_function_name)

            if result is None:
                # Test didn't produce a result (e.g. timeout killed subprocess)
                outcome = TestOutcome.UNDETERMINED
                record = ViolationRecord(
                    function_id=test.claim.subject,
                    claim=test.claim,
                    test_code=test.test_code,
                    outcome=outcome,
                    stdout="",
                    stderr="",
                    traceback=None,
                    expected=None,
                    actual=None,
                    execution_time_ms=0.0,
                )
            else:
                outcome = self._classify_outcome(result)
                tb = result.get("traceback")
                expected, actual = self._extract_expected_actual(tb)

                record = ViolationRecord(
                    function_id=test.claim.subject,
                    claim=test.claim,
                    test_code=test.test_code,
                    outcome=outcome,
                    stdout=result.get("stdout", ""),
                    stderr=result.get("stderr", ""),
                    traceback=tb,
                    expected=expected,
                    actual=actual,
                    execution_time_ms=result.get("duration", 0.0) * 1000,
                )

            all_records.append(record)

            if outcome == TestOutcome.PASS:
                pass_count += 1
            elif outcome == TestOutcome.FAIL:
                fail_count += 1
            elif outcome == TestOutcome.ERROR:
                error_count += 1
            # UNDETERMINED is excluded from all counts used in bcv_rate

        # 4. Compute BCV rate (exclude ERROR and UNDETERMINED)
        total = pass_count + fail_count
        bcv_rate = fail_count / total if total > 0 else 0.0

        # 5. Build report — violations list contains only FAIL outcomes
        return ViolationReport(
            analysis_id=analysis_id,
            function_name=function_name,
            total_claims=len(test_suite),
            violations=[r for r in all_records if r.outcome == TestOutcome.FAIL],
            pass_count=pass_count,
            fail_count=fail_count,
            error_count=error_count,
            bcv_rate=bcv_rate,
        )

    def _run_pytest(self, test_file: str) -> list[dict[str, Any]]:
        """Run pytest in an isolated subprocess and collect results.

        The subprocess executes ``python -m pytest <test_file>`` with the
        ``_ResultCollector`` plugin loaded via the companion conftest.py.
        Results are communicated back via a JSON sidecar file whose path
        is passed through the ``_VERIDOC_RESULTS_PATH`` environment variable.

        Parameters
        ----------
        test_file : str
            Absolute path to the temporary test module written by
            :meth:`_write_test_module`.

        Returns
        -------
        list[dict]
            One dict per test with keys: ``nodeid``, ``outcome``,
            ``stdout``, ``stderr``, ``traceback``, ``duration``.
        """
        test_dir = os.path.dirname(test_file)
        results_path = os.path.join(test_dir, "_veridoc_results.json")

        env = os.environ.copy()
        env["_VERIDOC_RESULTS_PATH"] = results_path

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            test_file,
            "-v",
            "--tb=long",
            "--no-header",
            "-q",
            "-p",
            "no:cacheprovider",
            f"--rootdir={test_dir}",
            "--override-ini=addopts=",
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
                cwd=test_dir,
            )
            logger.debug(
                "pytest exited with code %d\nstdout:\n%s\nstderr:\n%s",
                proc.returncode,
                proc.stdout[:2000],
                proc.stderr[:2000],
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "pytest subprocess timed out after %ds for %s",
                self.timeout,
                test_file,
            )
            self._safe_remove_dir(test_dir)
            return []

        # Read structured results from the sidecar
        results: list[dict[str, Any]] = []
        try:
            with open(results_path, "r", encoding="utf-8") as fh:
                results = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            logger.warning(
                "Could not read results sidecar %s: %s", results_path, exc,
            )
        finally:
            self._safe_remove_dir(test_dir)

        return results


    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_remove(path: str) -> None:
        """Remove a file, ignoring errors if it doesn't exist."""
        try:
            os.unlink(path)
        except OSError:
            pass

    @staticmethod
    def _safe_remove_dir(dirpath: str) -> None:
        """Remove a directory tree, ignoring errors."""
        try:
            shutil.rmtree(dirpath, ignore_errors=True)
        except OSError:
            pass
