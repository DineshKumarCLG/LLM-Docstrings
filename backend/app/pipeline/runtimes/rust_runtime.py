"""Rust RuntimeAdapter — executes Rust tests via ``cargo test`` subprocess.

Runs tests using ``cargo test`` with verbose output and parses the
standard test output into per-test result dicts compatible with the RV stage.

Requirements: 4.6
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from typing import Any

from app.pipeline.runtimes import RuntimeAdapter
from app.pipeline.runtimes.registry import RuntimeRegistry

logger = logging.getLogger(__name__)

# Regex for parsing standard ``cargo test`` verbose output lines like:
#   test tests::test_example ... ok
#   test tests::test_example ... FAILED
_TEST_LINE_RE = re.compile(
    r"^test\s+(?P<name>\S+)\s+\.\.\.\s+(?P<result>\S+)$"
)

# Regex for extracting per-test failure details from the failures section.
# Cargo prints:
#   ---- tests::test_example stdout ----
_FAILURE_HEADER_RE = re.compile(
    r"^---- (?P<name>\S+) stdout ----$"
)


class RustRuntimeAdapter(RuntimeAdapter):
    """Executes Rust tests via ``cargo test`` subprocess."""

    def write_test_module(
        self, tests: list, source_code: str, tmpdir: str
    ) -> str:
        """Write source and test Rust files to a Cargo project in *tmpdir*.

        Creates:
        - ``Cargo.toml`` — minimal package manifest
        - ``src/lib.rs``  — target source code followed by ``#[cfg(test)]``
                            module containing synthesized tests
        """
        src_dir = os.path.join(tmpdir, "src")
        os.makedirs(src_dir, exist_ok=True)

        cargo_toml_path = os.path.join(tmpdir, "Cargo.toml")
        lib_rs_path = os.path.join(src_dir, "lib.rs")

        # Write a minimal Cargo.toml
        with open(cargo_toml_path, "w", encoding="utf-8") as fh:
            fh.write(
                "[package]\n"
                'name = "veridoc_test"\n'
                'version = "0.1.0"\n'
                'edition = "2021"\n'
            )

        # Build lib.rs: source code + test module
        lines: list[str] = []
        lines.append("// --- Target source code ---")
        lines.append(source_code.rstrip())
        lines.append("")
        lines.append("")
        lines.append("// --- Synthesized tests ---")
        for test in tests:
            code = (
                test.test_code
                if hasattr(test, "test_code")
                else test.get("test_code", "")
            )
            lines.append(code.rstrip())
            lines.append("")

        content = "\n".join(lines)

        with open(lib_rs_path, "w", encoding="utf-8") as fh:
            fh.write(content)

        logger.debug(
            "Wrote Rust test module to %s (%d bytes)", lib_rs_path, len(content)
        )
        return lib_rs_path

    def execute(
        self, test_path: str, timeout: int
    ) -> list[dict[str, Any]]:
        """Run ``cargo test`` via subprocess, parse results.

        Attempts ``cargo test -- --format=json -Z unstable-options`` first.
        If that fails (requires nightly), falls back to parsing the standard
        verbose output from ``cargo test -- --nocapture``.

        Returns a list of dicts with keys:
        ``nodeid``, ``outcome``, ``stdout``, ``stderr``, ``traceback``, ``duration``.
        """
        # The Cargo project root is the parent of the src/ directory
        project_dir = os.path.dirname(test_path)
        if os.path.basename(project_dir) == "src":
            project_dir = os.path.dirname(project_dir)

        # Use standard verbose output (works on stable Rust)
        cmd = ["cargo", "test", "--", "--nocapture"]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=project_dir,
            )
            logger.debug(
                "cargo test exited with code %d\nstdout:\n%s\nstderr:\n%s",
                proc.returncode,
                proc.stdout[:2000],
                proc.stderr[:2000],
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "cargo test subprocess timed out after %ds for %s",
                timeout,
                test_path,
            )
            return []

        return self._parse_cargo_test_output(proc.stdout, proc.stderr)

    @staticmethod
    def _parse_cargo_test_output(
        stdout: str, stderr: str
    ) -> list[dict[str, Any]]:
        """Parse standard ``cargo test`` verbose output into per-test results.

        Cargo test verbose output contains lines like:
            test tests::test_add ... ok
            test tests::test_sub ... FAILED

        And a failures section:
            failures:

            ---- tests::test_sub stdout ----
            thread 'tests::test_sub' panicked at ...
            ...

            failures:
                tests::test_sub
        """
        results: list[dict[str, Any]] = []
        test_outcomes: dict[str, str] = {}

        # Combined output for parsing
        combined = stdout + "\n" + stderr

        # Pass 1: extract test names and outcomes from result lines
        for line in combined.splitlines():
            line = line.strip()
            m = _TEST_LINE_RE.match(line)
            if m:
                name = m.group("name")
                result = m.group("result").lower()
                test_outcomes[name] = result

        # Pass 2: extract failure details (stdout captured between headers)
        failure_outputs: dict[str, str] = {}
        current_failure_name: str | None = None
        current_lines: list[str] = []

        for line in combined.splitlines():
            header_match = _FAILURE_HEADER_RE.match(line.strip())
            if header_match:
                # Save previous failure block
                if current_failure_name is not None:
                    failure_outputs[current_failure_name] = "\n".join(
                        current_lines
                    )
                current_failure_name = header_match.group("name")
                current_lines = []
            elif current_failure_name is not None:
                # End of failure block: blank line or next section header
                if line.strip().startswith("failures:") or line.strip().startswith("test result:"):
                    failure_outputs[current_failure_name] = "\n".join(
                        current_lines
                    )
                    current_failure_name = None
                    current_lines = []
                else:
                    current_lines.append(line)

        # Flush last failure block
        if current_failure_name is not None:
            failure_outputs[current_failure_name] = "\n".join(current_lines)

        # Build result dicts
        for name, outcome_raw in test_outcomes.items():
            if outcome_raw == "ok":
                outcome = "passed"
            elif outcome_raw == "ignored":
                outcome = "skipped"
            else:
                outcome = "failed"

            traceback = failure_outputs.get(name, "").strip() or None
            test_stderr = stderr.strip() if outcome == "failed" else ""

            results.append({
                "nodeid": name,
                "outcome": outcome,
                "stdout": failure_outputs.get(name, ""),
                "stderr": test_stderr,
                "traceback": traceback,
                "duration": 0.0,
            })

        return results

    def is_available(self) -> bool:
        """Check if ``cargo`` and ``rustc`` are available via ``shutil.which``."""
        return (
            shutil.which("cargo") is not None
            and shutil.which("rustc") is not None
        )


# Register with RuntimeRegistry for language "rust"
RuntimeRegistry.register("rust", RustRuntimeAdapter)
