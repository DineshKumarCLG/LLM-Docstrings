"""Java RuntimeAdapter — compiles and executes tests via JUnit subprocess.

Compiles Java source and test files with ``javac``, then runs the tests
using the JUnit Platform Console Launcher.  Parses the console output
into per-test result dicts compatible with the RV stage.

Requirements: 4.4
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from typing import Any

from app.pipeline.runtimes import RuntimeAdapter
from app.pipeline.runtimes.registry import RuntimeRegistry

logger = logging.getLogger(__name__)

# JUnit Platform Console Standalone JAR — expected to be available on the
# system classpath or at a well-known location.  The adapter first checks
# the ``JUNIT_PLATFORM_JAR`` environment variable, then falls back to
# searching common locations.
_DEFAULT_JUNIT_JAR_PATHS = [
    "/usr/share/java/junit-platform-console-standalone.jar",
    "/opt/junit/junit-platform-console-standalone.jar",
]


def _find_junit_jar() -> str | None:
    """Locate the JUnit Platform Console Standalone JAR.

    Checks ``JUNIT_PLATFORM_JAR`` env var first, then well-known paths.
    """
    env_jar = os.environ.get("JUNIT_PLATFORM_JAR")
    if env_jar and os.path.isfile(env_jar):
        return env_jar

    for path in _DEFAULT_JUNIT_JAR_PATHS:
        if os.path.isfile(path):
            return path

    return None


class JavaRuntimeAdapter(RuntimeAdapter):
    """Compiles and executes Java JUnit 5 tests via subprocess."""

    def write_test_module(
        self, tests: list, source_code: str, tmpdir: str
    ) -> str:
        """Write source ``.java`` and test ``.java`` files to *tmpdir*.

        Creates:
        - ``Source.java`` — the target source code
        - ``SourceTest.java`` — synthesized JUnit 5 test code

        Returns the path to the test file.
        """
        # Detect the public class name from source code, default to "Source"
        source_class = _extract_public_class_name(source_code) or "Source"
        source_path = os.path.join(tmpdir, f"{source_class}.java")
        with open(source_path, "w", encoding="utf-8") as fh:
            fh.write(source_code)

        # Build the test file from synthesized tests
        lines: list[str] = []
        for test in tests:
            code = (
                test.test_code
                if hasattr(test, "test_code")
                else test.get("test_code", "")
            )
            lines.append(code.rstrip())
            lines.append("")

        test_content = "\n".join(lines)

        # Detect the test class name from the test code
        test_class = _extract_public_class_name(test_content) or f"{source_class}Test"
        test_path = os.path.join(tmpdir, f"{test_class}.java")

        with open(test_path, "w", encoding="utf-8") as fh:
            fh.write(test_content)

        logger.debug(
            "Wrote Java test module to %s (%d bytes)", test_path, len(test_content)
        )
        return test_path

    def execute(
        self, test_path: str, timeout: int
    ) -> list[dict[str, Any]]:
        """Compile with ``javac`` and run with JUnit ConsoleLauncher.

        Returns a list of dicts with keys:
        ``nodeid``, ``outcome``, ``stdout``, ``stderr``, ``traceback``, ``duration``.
        """
        test_dir = os.path.dirname(test_path)

        # --- Locate JUnit JAR ---
        junit_jar = _find_junit_jar()
        if not junit_jar:
            logger.error("JUnit Platform Console Standalone JAR not found")
            return [{
                "nodeid": "compilation",
                "outcome": "error",
                "stdout": "",
                "stderr": "JUnit Platform Console Standalone JAR not found. "
                          "Set JUNIT_PLATFORM_JAR environment variable.",
                "traceback": None,
                "duration": 0.0,
            }]

        # --- Compile ---
        java_files = [
            os.path.join(test_dir, f)
            for f in os.listdir(test_dir)
            if f.endswith(".java")
        ]

        classpath = junit_jar
        compile_cmd = [
            "javac",
            "-cp", classpath,
            *java_files,
        ]

        try:
            compile_proc = subprocess.run(
                compile_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=test_dir,
            )
        except subprocess.TimeoutExpired:
            logger.warning("javac timed out after %ds", timeout)
            return []

        if compile_proc.returncode != 0:
            logger.warning(
                "javac compilation failed:\nstdout:\n%s\nstderr:\n%s",
                compile_proc.stdout[:2000],
                compile_proc.stderr[:2000],
            )
            return [{
                "nodeid": "compilation",
                "outcome": "error",
                "stdout": compile_proc.stdout,
                "stderr": compile_proc.stderr,
                "traceback": compile_proc.stderr,
                "duration": 0.0,
            }]

        # --- Run tests via JUnit ConsoleLauncher ---
        test_class_name = os.path.splitext(os.path.basename(test_path))[0]

        run_cmd = [
            "java",
            "-cp", f"{test_dir}{os.pathsep}{classpath}",
            "org.junit.platform.console.ConsoleLauncher",
            "--select-class", test_class_name,
            "--details", "verbose",
        ]

        start_time = time.monotonic()
        try:
            run_proc = subprocess.run(
                run_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=test_dir,
            )
            elapsed = time.monotonic() - start_time
            logger.debug(
                "JUnit exited with code %d in %.2fs\nstdout:\n%s\nstderr:\n%s",
                run_proc.returncode,
                elapsed,
                run_proc.stdout[:2000],
                run_proc.stderr[:2000],
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "JUnit subprocess timed out after %ds for %s", timeout, test_path
            )
            return []

        return _parse_junit_output(run_proc.stdout, run_proc.stderr)

    def is_available(self) -> bool:
        """Check if ``javac`` and ``java`` are available via ``shutil.which``."""
        return (
            shutil.which("javac") is not None
            and shutil.which("java") is not None
        )


def _extract_public_class_name(source: str) -> str | None:
    """Extract the public class name from Java source code."""
    match = re.search(r"\bpublic\s+class\s+(\w+)", source)
    if match:
        return match.group(1)
    # Fall back to any class declaration
    match = re.search(r"\bclass\s+(\w+)", source)
    return match.group(1) if match else None


def _parse_junit_output(
    stdout: str, stderr: str
) -> list[dict[str, Any]]:
    """Parse JUnit ConsoleLauncher verbose output into per-test result dicts.

    The ``--details verbose`` output contains lines like::

        ├─ JUnit Jupiter ✔
        │  └─ SourceTest ✔
        │     ├─ testAdd() ✔
        │     └─ testSubtract() ✘

    We look for test method lines with ✔ (passed) or ✘ (failed) markers,
    as well as ``SUCCESSFUL`` / ``FAILED`` / ``ABORTED`` text patterns.
    """
    results: list[dict[str, Any]] = []

    # Pattern for verbose tree output with checkmark/cross symbols
    # Matches lines like: "│     ├─ testAdd() ✔" or "│     └─ testSubtract() ✘"
    tree_pattern = re.compile(
        r"[│├└─\s]+(\w+\([^)]*\))\s+(✔|✘|✓|✗)"
    )

    # Alternative pattern for text-based output
    # Matches lines like: "[         1 tests successful      ]"
    text_pass_pattern = re.compile(
        r"^\s*\[?\s*(\w+(?:\([^)]*\))?)\s*\]?\s*(?:SUCCESSFUL|PASSED)",
        re.IGNORECASE,
    )
    text_fail_pattern = re.compile(
        r"^\s*\[?\s*(\w+(?:\([^)]*\))?)\s*\]?\s*(?:FAILED|ABORTED)",
        re.IGNORECASE,
    )

    # Also parse the detailed per-test lines from JUnit verbose output
    # e.g. "testMethodName() -- SUCCESSFUL" or "testMethodName() -- FAILED"
    detail_pattern = re.compile(
        r"[│├└─\s]+(\w+\([^)]*\))\s+(.+)"
    )

    combined_output = stdout + "\n" + stderr

    for line in combined_output.splitlines():
        # Try tree-style output first (most common with --details verbose)
        m = tree_pattern.search(line)
        if m:
            method_name = m.group(1)
            symbol = m.group(2)
            outcome = "passed" if symbol in ("✔", "✓") else "failed"
            results.append({
                "nodeid": method_name,
                "outcome": outcome,
                "stdout": "",
                "stderr": "",
                "traceback": None if outcome == "passed" else _extract_traceback(combined_output, method_name),
                "duration": 0.0,
            })
            continue

        # Try detail pattern with text status
        m = detail_pattern.search(line)
        if m:
            method_name = m.group(1)
            status_text = m.group(2).strip()
            if "SUCCESSFUL" in status_text or "PASSED" in status_text:
                outcome = "passed"
            elif "FAILED" in status_text or "ABORTED" in status_text:
                outcome = "failed"
            else:
                continue
            results.append({
                "nodeid": method_name,
                "outcome": outcome,
                "stdout": "",
                "stderr": "",
                "traceback": None if outcome == "passed" else _extract_traceback(combined_output, method_name),
                "duration": 0.0,
            })

    # If no results were parsed from tree output, try summary-based parsing
    if not results:
        results = _parse_junit_summary(combined_output)

    return results


def _extract_traceback(output: str, method_name: str) -> str | None:
    """Try to extract a traceback/failure message for a specific test method."""
    # Look for exception/assertion messages near the method name
    clean_name = method_name.replace("()", "")
    lines = output.splitlines()
    traceback_lines: list[str] = []
    capturing = False

    for line in lines:
        if clean_name in line and ("FAILED" in line or "✘" in line or "✗" in line):
            capturing = True
            continue
        if capturing:
            # Stop capturing at the next test result or blank section
            if re.search(r"[├└]─\s+\w+\(", line) or line.strip() == "":
                if traceback_lines:
                    break
            else:
                traceback_lines.append(line.rstrip())

    return "\n".join(traceback_lines) if traceback_lines else None


def _parse_junit_summary(output: str) -> list[dict[str, Any]]:
    """Fallback parser using JUnit summary counts.

    When individual test lines can't be parsed, extract summary counts
    like ``[ 3 tests successful ]`` and ``[ 1 tests failed ]``.
    """
    results: list[dict[str, Any]] = []

    success_match = re.search(r"\[\s*(\d+)\s+tests?\s+successful\s*\]", output, re.IGNORECASE)
    failed_match = re.search(r"\[\s*(\d+)\s+tests?\s+failed\s*\]", output, re.IGNORECASE)

    success_count = int(success_match.group(1)) if success_match else 0
    failed_count = int(failed_match.group(1)) if failed_match else 0

    for i in range(success_count):
        results.append({
            "nodeid": f"test_{i + 1}",
            "outcome": "passed",
            "stdout": "",
            "stderr": "",
            "traceback": None,
            "duration": 0.0,
        })

    for i in range(failed_count):
        results.append({
            "nodeid": f"test_failed_{i + 1}",
            "outcome": "failed",
            "stdout": "",
            "stderr": "",
            "traceback": output,
            "duration": 0.0,
        })

    return results


# Register with RuntimeRegistry for language "java"
RuntimeRegistry.register("java", JavaRuntimeAdapter)
