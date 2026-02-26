"""Property tests for pre-commit hook exit codes.

**Validates: Requirements 9.2, 9.3**

Properties tested:
- Property 18: Pre-commit exit code correctness — exit 1 iff strictness="high"
  and high-confidence violations are present; otherwise exit 0.
"""

from __future__ import annotations

from unittest.mock import patch

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from app.cli.precommit import PreCommitHook
from app.schemas import (
    BCVCategory,
    Claim,
    TestOutcome,
    ViolationRecord,
    ViolationReport,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

strictness_strategy = st.sampled_from(["high", "low"])

claim_strategy = st.builds(
    Claim,
    category=st.sampled_from(list(BCVCategory)),
    subject=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L",))),
    predicate_object=st.text(min_size=1, max_size=40, alphabet=st.characters(whitelist_categories=("L",))),
    source_line=st.integers(min_value=1, max_value=500),
    raw_text=st.text(min_size=1, max_size=60, alphabet=st.characters(whitelist_categories=("L",))),
)

violation_record_strategy = st.builds(
    ViolationRecord,
    function_id=st.just("func_1"),
    claim=claim_strategy,
    test_code=st.just("def test_x(): pass"),
    outcome=st.sampled_from([TestOutcome.FAIL, TestOutcome.ERROR]),
    stdout=st.just(""),
    stderr=st.just(""),
    traceback=st.just(None),
    expected=st.just(None),
    actual=st.just(None),
    execution_time_ms=st.just(0.0),
)

violation_report_strategy = st.builds(
    ViolationReport,
    analysis_id=st.just("pre-commit"),
    function_name=st.just("some_func"),
    total_claims=st.integers(min_value=0, max_value=20),
    violations=st.lists(violation_record_strategy, min_size=0, max_size=5),
    pass_count=st.integers(min_value=0, max_value=20),
    fail_count=st.integers(min_value=0, max_value=20),
    error_count=st.integers(min_value=0, max_value=20),
    bcv_rate=st.floats(min_value=0.0, max_value=1.0),
)


# ---------------------------------------------------------------------------
# Property 18: Pre-commit exit code correctness
# ---------------------------------------------------------------------------


@given(
    strictness=strictness_strategy,
    report=violation_report_strategy,
)
@h_settings(max_examples=200, deadline=None)
def test_precommit_exit_code_correctness(
    strictness: str,
    report: ViolationReport,
) -> None:
    """Property 18: exit_code == 1 iff strictness='high' AND violations present.

    **Validates: Requirements 9.2, 9.3**

    We mock ``_get_staged_python_files`` to return one file and
    ``_run_pipeline_local`` to return the generated report, then verify
    the exit code matches the expected property.
    """
    hook = PreCommitHook(strictness=strictness)

    with (
        patch.object(hook, "_get_staged_python_files", return_value=["staged.py"]),
        patch.object(hook, "_run_pipeline_local", return_value=report),
    ):
        exit_code = hook.run()

    has_violations = len(report.violations) > 0
    expected_exit = 1 if (strictness == "high" and has_violations) else 0

    assert exit_code == expected_exit, (
        f"Expected exit {expected_exit} for strictness={strictness!r}, "
        f"violations={len(report.violations)}, got {exit_code}"
    )


@given(strictness=strictness_strategy)
@h_settings(max_examples=50, deadline=None)
def test_precommit_exit_zero_when_no_staged_files(strictness: str) -> None:
    """Exit code is always 0 when there are no staged Python files.

    **Validates: Requirements 9.2, 9.3**
    """
    hook = PreCommitHook(strictness=strictness)

    with patch.object(hook, "_get_staged_python_files", return_value=[]):
        exit_code = hook.run()

    assert exit_code == 0, (
        f"Expected exit 0 when no staged files, got {exit_code}"
    )


@given(strictness=strictness_strategy)
@h_settings(max_examples=50, deadline=None)
def test_precommit_exit_zero_when_pipeline_returns_none(strictness: str) -> None:
    """Exit code is always 0 when the pipeline returns None for every file.

    **Validates: Requirements 9.2, 9.3**
    """
    hook = PreCommitHook(strictness=strictness)

    with (
        patch.object(hook, "_get_staged_python_files", return_value=["a.py"]),
        patch.object(hook, "_run_pipeline_local", return_value=None),
    ):
        exit_code = hook.run()

    assert exit_code == 0, (
        f"Expected exit 0 when pipeline returns None, got {exit_code}"
    )
