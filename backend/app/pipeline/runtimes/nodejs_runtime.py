"""Node.js RuntimeAdapter — executes JS/TS tests via vitest subprocess.

Runs tests using ``npx vitest run --reporter=json`` and parses the JSON
output into per-test result dicts compatible with the RV stage.

Requirements: 4.3
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


class NodeJSRuntimeAdapter(RuntimeAdapter):
    """Executes JavaScript/TypeScript tests via vitest subprocess."""

    def write_test_module(
        self, tests: list, source_code: str, tmpdir: str
    ) -> str:
        """Write test code and source code to *tmpdir*, return the test file path.

        Creates:
        - ``source.js`` — the target source code
        - ``source.test.js`` — synthesized test code importing from source
        """
        source_path = os.path.join(tmpdir, "source.js")
        test_path = os.path.join(tmpdir, "source.test.js")

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
            "Wrote Node.js test module to %s (%d bytes)", test_path, len(content)
        )
        return test_path

    def execute(
        self, test_path: str, timeout: int
    ) -> list[dict[str, Any]]:
        """Run vitest via subprocess with JSON reporter, parse results.

        Returns a list of dicts with keys:
        ``nodeid``, ``outcome``, ``stdout``, ``stderr``, ``traceback``, ``duration``.
        """
        test_dir = os.path.dirname(test_path)

        # Create a minimal vitest config so it doesn't search for a project config
        vitest_config_path = os.path.join(test_dir, "vitest.config.js")
        with open(vitest_config_path, "w", encoding="utf-8") as fh:
            fh.write(
                "import { defineConfig } from 'vitest/config';\n"
                "export default defineConfig({ test: { globals: true } });\n"
            )

        # Create a minimal package.json so npx resolves correctly
        pkg_json_path = os.path.join(test_dir, "package.json")
        with open(pkg_json_path, "w", encoding="utf-8") as fh:
            fh.write('{"type": "module"}\n')

        cmd = [
            "npx",
            "vitest",
            "run",
            test_path,
            "--reporter=json",
            f"--config={vitest_config_path}",
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=test_dir,
            )
            logger.debug(
                "vitest exited with code %d\nstdout:\n%s\nstderr:\n%s",
                proc.returncode,
                proc.stdout[:2000],
                proc.stderr[:2000],
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "vitest subprocess timed out after %ds for %s",
                timeout,
                test_path,
            )
            return []

        return self._parse_vitest_json(proc.stdout)

    @staticmethod
    def _parse_vitest_json(stdout: str) -> list[dict[str, Any]]:
        """Parse vitest JSON reporter output into per-test result dicts."""
        results: list[dict[str, Any]] = []

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            # vitest may prefix non-JSON output before the JSON blob;
            # try to find the JSON object in the output
            start = stdout.find("{")
            if start == -1:
                logger.warning("Could not find JSON in vitest output")
                return results
            try:
                data = json.loads(stdout[start:])
            except json.JSONDecodeError:
                logger.warning("Failed to parse vitest JSON output")
                return results

        # vitest JSON reporter structure:
        # { "testResults": [ { "name": "...", "assertionResults": [ ... ] } ] }
        for test_file in data.get("testResults", []):
            for assertion in test_file.get("assertionResults", []):
                status = assertion.get("status", "failed")
                outcome = "passed" if status == "passed" else "failed"

                # Build a readable nodeid from the ancestor titles + test title
                ancestors = assertion.get("ancestorTitles", [])
                title = assertion.get("title", "unknown")
                nodeid = " > ".join([*ancestors, title])

                # Duration is in milliseconds from vitest
                duration_ms = assertion.get("duration", 0) or 0
                duration = duration_ms / 1000.0

                failure_messages = assertion.get("failureMessages", [])
                traceback = "\n".join(failure_messages) if failure_messages else None

                results.append({
                    "nodeid": nodeid,
                    "outcome": outcome,
                    "stdout": "",
                    "stderr": "",
                    "traceback": traceback,
                    "duration": duration,
                })

        return results

    def is_available(self) -> bool:
        """Check if node and npx are available via shutil.which."""
        return shutil.which("node") is not None and shutil.which("npx") is not None


# Register with RuntimeRegistry for both JavaScript and TypeScript
RuntimeRegistry.register("javascript", NodeJSRuntimeAdapter)
RuntimeRegistry.register("typescript", NodeJSRuntimeAdapter)
