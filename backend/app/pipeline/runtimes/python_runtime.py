"""Python RuntimeAdapter — wraps existing pytest execution logic.

Preserves the behavior from ``backend/app/pipeline/rv/verifier.py`` by
delegating to pytest in an isolated subprocess with a ResultCollector
plugin that writes per-test results to a JSON sidecar file.

Requirements: 4.2
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

from app.pipeline.runtimes import RuntimeAdapter
from app.pipeline.runtimes.registry import RuntimeRegistry

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


class PythonRuntimeAdapter(RuntimeAdapter):
    """Executes Python tests via pytest subprocess.

    Wraps the existing pytest execution logic from
    ``RuntimeVerifier._write_test_module`` and ``RuntimeVerifier._run_pytest``
    into the ``RuntimeAdapter`` interface.
    """

    def write_test_module(
        self, tests: list, source_code: str, tmpdir: str
    ) -> str:
        """Write test code and source code to *tmpdir*, return the test file path.

        Creates:
        - ``conftest.py`` — ResultCollector plugin for capturing results
        - ``test_veridoc_rv.py`` — target source code + synthesized tests
        """
        test_path = os.path.join(tmpdir, "test_veridoc_rv.py")
        conftest_path = os.path.join(tmpdir, "conftest.py")

        # Write conftest.py with the ResultCollector plugin
        with open(conftest_path, "w", encoding="utf-8") as fh:
            fh.write(_CONFTEST_CONTENT)

        # Build the test module
        lines: list[str] = []
        lines.append("# --- Target source code ---")
        lines.append(source_code.rstrip())
        lines.append("")
        lines.append("")
        lines.append("# --- Synthesized tests ---")
        for test in tests:
            # Support both SynthesizedTest objects and plain dicts
            code = test.test_code if hasattr(test, "test_code") else test.get("test_code", "")
            lines.append(code.rstrip())
            lines.append("")
            lines.append("")

        content = "\n".join(lines)

        with open(test_path, "w", encoding="utf-8") as fh:
            fh.write(content)

        logger.debug("Wrote RV test module to %s (%d bytes)", test_path, len(content))
        return test_path

    def execute(
        self, test_path: str, timeout: int
    ) -> list[dict[str, Any]]:
        """Run pytest via subprocess with JSON output, parse results.

        Returns a list of dicts with keys:
        ``nodeid``, ``outcome``, ``stdout``, ``stderr``, ``traceback``, ``duration``.
        """
        test_dir = os.path.dirname(test_path)
        results_path = os.path.join(test_dir, "_veridoc_results.json")

        env = os.environ.copy()
        env["_VERIDOC_RESULTS_PATH"] = results_path

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            test_path,
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
                timeout=timeout,
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
                timeout,
                test_path,
            )
            return []

        # Read structured results from the JSON sidecar
        results: list[dict[str, Any]] = []
        try:
            with open(results_path, "r", encoding="utf-8") as fh:
                results = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            logger.warning(
                "Could not read results sidecar %s: %s", results_path, exc,
            )

        return results

    def is_available(self) -> bool:
        """Check if python and pytest are available."""
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return proc.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False


# Register with RuntimeRegistry for language "python"
RuntimeRegistry.register("python", PythonRuntimeAdapter)
