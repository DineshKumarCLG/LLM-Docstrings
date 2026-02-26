"""Pre-commit hook entry point for VeriDoc BCV detection.

Runs the BCE → DTS → RV pipeline locally (no Celery) on staged Python files
and blocks the commit when strictness="high" and violations are found.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Optional

from app.pipeline.bce.extractor import BehavioralClaimExtractor
from app.pipeline.dts.synthesizer import DynamicTestSynthesizer
from app.pipeline.rv.verifier import RuntimeVerifier
from app.schemas import LLMProvider, ViolationReport


# ---------------------------------------------------------------------------
# ANSI colour helpers (gracefully degrade when not supported)
# ---------------------------------------------------------------------------

def _supports_color() -> bool:
    """Return *True* when stderr is a TTY that likely supports ANSI codes."""
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()


_RED = "\033[91m"
_YELLOW = "\033[93m"
_GREEN = "\033[92m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _c(code: str, text: str, color: bool) -> str:
    """Wrap *text* in ANSI *code* when *color* is enabled."""
    return f"{code}{text}{_RESET}" if color else text


# ---------------------------------------------------------------------------
# PreCommitHook
# ---------------------------------------------------------------------------


class PreCommitHook:
    """Run the VeriDoc pipeline locally as a git pre-commit hook.

    Parameters
    ----------
    strictness : str
        ``"high"`` blocks the commit on any violation (exit 1).
        ``"low"`` prints warnings but allows the commit (exit 0).
    llm_provider : str
        LLM provider identifier (must match an ``LLMProvider`` value).
    """

    def __init__(
        self,
        strictness: str = "high",
        llm_provider: str = "gemini-3-flash-preview",
    ) -> None:
        self.strictness = strictness
        self.llm_provider = llm_provider

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> int:
        """Main entry point — returns an exit code (0 or 1).

        * Gets staged Python files via ``git diff --cached``.
        * Runs the full pipeline on each file locally (no Celery).
        * Prints a formatted report to *stderr*.
        * Returns **1** when ``strictness="high"`` and violations exist,
          **0** otherwise.

        Requirements: 9.1, 9.2, 9.3, 9.4
        """
        staged_files = self._get_staged_python_files()
        if not staged_files:
            return 0

        has_violations = False

        for filepath in staged_files:
            report = self._run_pipeline_local(filepath)
            if report is None:
                continue

            formatted = self._format_report(report, filepath)
            print(formatted, file=sys.stderr)

            if report.violations:
                has_violations = True

        if has_violations and self.strictness == "high":
            return 1

        return 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_staged_python_files(self) -> list[str]:
        """Return staged ``.py`` files (added, copied, or modified).

        Runs ``git diff --cached --name-only --diff-filter=ACM`` and
        filters the output to paths ending with ``.py``.

        Requirement: 9.1
        """
        try:
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                capture_output=True,
                text=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []

        return [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip().endswith(".py")
        ]

    def _run_pipeline_local(self, filepath: str) -> Optional[ViolationReport]:
        """Run BCE → DTS → RV locally without Celery.

        Requirement: 9.5
        """
        path = Path(filepath)
        if not path.exists():
            return None

        source_code = path.read_text(encoding="utf-8")

        # Stage 1 — BCE
        bce = BehavioralClaimExtractor()
        claim_schemas = bce.extract(source_code)
        if not claim_schemas:
            return None

        # Stage 2 — DTS (async, so we run in an event loop)
        provider = LLMProvider(self.llm_provider)
        dts = DynamicTestSynthesizer(llm_provider=provider)

        all_tests = []
        for cs in claim_schemas:
            tests = asyncio.run(dts.synthesize(cs))
            all_tests.extend(tests)

        if not all_tests:
            return None

        # Stage 3 — RV
        rv = RuntimeVerifier()
        report = rv.verify(
            test_suite=all_tests,
            source_code=source_code,
            analysis_id="pre-commit",
            function_name=claim_schemas[0].function.name if claim_schemas else "",
        )

        return report

    @staticmethod
    def _format_report(report: ViolationReport, filepath: str = "") -> str:
        """Format a ViolationReport for terminal output (coloured if possible).

        Requirement: 9.2, 9.3
        """
        color = _supports_color()
        lines: list[str] = []

        header = f"VeriDoc: {filepath or report.function_name}"
        lines.append(_c(_BOLD, header, color))
        lines.append(
            f"  Claims: {report.total_claims}  "
            f"Pass: {report.pass_count}  "
            f"Fail: {report.fail_count}  "
            f"Error: {report.error_count}  "
            f"BCV Rate: {report.bcv_rate:.1%}"
        )

        if not report.violations:
            lines.append(_c(_GREEN, "  ✓ No violations detected.", color))
            return "\n".join(lines)

        lines.append(
            _c(_RED, f"  ✗ {len(report.violations)} violation(s) found:", color)
        )

        for v in report.violations:
            cat = v.claim.category.value
            subj = v.claim.subject
            pred = v.claim.predicate_object
            line_info = f"line {v.claim.source_line}"

            violation_line = f"    [{cat}] {subj}: {pred} ({line_info})"
            lines.append(_c(_YELLOW, violation_line, color))

            if v.traceback:
                # Show first two lines of the traceback for brevity
                tb_lines = v.traceback.strip().splitlines()
                for tb_line in tb_lines[:3]:
                    lines.append(f"      {tb_line}")
                if len(tb_lines) > 3:
                    lines.append(f"      ... ({len(tb_lines) - 3} more lines)")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point (referenced by pyproject.toml console_scripts)
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the ``veridoc-check`` console script."""
    hook = PreCommitHook()
    sys.exit(hook.run())
