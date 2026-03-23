"""Go RuntimeAdapter — executes Go tests via ``go test`` subprocess.

Runs tests using ``go test -v -json`` and parses the line-delimited JSON
output into per-test result dicts compatible with the RV stage.

Requirements: 4.5
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from typing import Any

from app.pipeline.runtimes import RuntimeAdapter
from app.pipeline.runtimes.registry import RuntimeRegistry

logger = logging.getLogger(__name__)


class GoRuntimeAdapter(RuntimeAdapter):
    """Executes Go tests via ``go test -v -json`` subprocess."""

    def write_test_module(
        self, tests: list, source_code: str, tmpdir: str
    ) -> str:
        """Write source and test Go files to *tmpdir*, return the test file path.

        Creates:
        - ``go.mod``   — minimal module file so ``go test`` can resolve the package
        - ``source.go`` — the target source code
        - ``source_test.go`` — synthesized test code
        """
        go_mod_path = os.path.join(tmpdir, "go.mod")
        source_path = os.path.join(tmpdir, "source.go")
        test_path = os.path.join(tmpdir, "source_test.go")

        # Write a minimal go.mod so `go test` treats tmpdir as a module
        with open(go_mod_path, "w", encoding="utf-8") as fh:
            fh.write("module veridoc_test\n\ngo 1.21\n")

        with open(source_path, "w", encoding="utf-8") as fh:
            fh.write(source_code)

        lines: list[str] = []
        for test in tests:
            code = (
                test.test_code
                if hasattr(test, "test_code")
                else test.get("test_code", "")
            )
            lines.append(code.rstrip())
            lines.append("")

        content = "\n".join(lines)

        with open(test_path, "w", encoding="utf-8") as fh:
            fh.write(content)

        logger.debug(
            "Wrote Go test module to %s (%d bytes)", test_path, len(content)
        )
        return test_path

    def execute(
        self, test_path: str, timeout: int
    ) -> list[dict[str, Any]]:
        """Run ``go test -v -json`` via subprocess, parse results.

        The ``go test -json`` output emits one JSON object per line with fields:
        ``Time``, ``Action``, ``Package``, ``Test``, ``Output``, ``Elapsed``.

        Actions include ``run``, ``output``, ``pass``, ``fail``, ``skip``.

        Returns a list of dicts with keys:
        ``nodeid``, ``outcome``, ``stdout``, ``stderr``, ``traceback``, ``duration``.
        """
        test_dir = os.path.dirname(test_path)

        cmd = ["go", "test", "-v", "-json", "./..."]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=test_dir,
            )
            logger.debug(
                "go test exited with code %d\nstdout:\n%s\nstderr:\n%s",
                proc.returncode,
                proc.stdout[:2000],
                proc.stderr[:2000],
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "go test subprocess timed out after %ds for %s",
                timeout,
                test_path,
            )
            return []

        return self._parse_go_test_json(proc.stdout, proc.stderr)

    @staticmethod
    def _parse_go_test_json(
        stdout: str, stderr: str
    ) -> list[dict[str, Any]]:
        """Parse ``go test -json`` line-delimited JSON into per-test results."""
        # Accumulate output lines and final status per test function.
        # Key: test name (str), Value: dict with collected info
        test_data: dict[str, dict[str, Any]] = {}
        results: list[dict[str, Any]] = []

        for raw_line in stdout.splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            action = event.get("Action", "")
            test_name = event.get("Test", "")

            # Skip package-level events (no Test field)
            if not test_name:
                continue

            if test_name not in test_data:
                test_data[test_name] = {
                    "output_lines": [],
                    "outcome": None,
                    "elapsed": 0.0,
                }

            entry = test_data[test_name]

            if action == "output":
                output_text = event.get("Output", "")
                entry["output_lines"].append(output_text)
            elif action in ("pass", "fail", "skip"):
                entry["outcome"] = action
                entry["elapsed"] = event.get("Elapsed", 0.0)

        # Convert accumulated data into result dicts
        for test_name, data in test_data.items():
            outcome_raw = data["outcome"]
            if outcome_raw == "pass":
                outcome = "passed"
            elif outcome_raw == "skip":
                outcome = "skipped"
            else:
                outcome = "failed"

            full_output = "".join(data["output_lines"])

            # Extract traceback: for failed tests, the output contains the
            # failure messages (file:line and error text)
            traceback = full_output.strip() if outcome == "failed" else None

            results.append({
                "nodeid": test_name,
                "outcome": outcome,
                "stdout": full_output,
                "stderr": stderr if outcome == "failed" else "",
                "traceback": traceback,
                "duration": data["elapsed"],
            })

        return results

    def is_available(self) -> bool:
        """Check if the ``go`` binary is available via ``shutil.which``."""
        return shutil.which("go") is not None


# Register with RuntimeRegistry for language "go"
RuntimeRegistry.register("go", GoRuntimeAdapter)
