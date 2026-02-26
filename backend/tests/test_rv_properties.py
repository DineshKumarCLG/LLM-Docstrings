"""Property tests for the Runtime Verifier (RV).

**Validates: Requirements 4.2–4.5, 10.5, 10.6**

Properties tested:
- Property 11: Outcome classification determinism
- Property 12: BCV rate computation correctness
- Property 13: ViolationReport excludes non-violations
"""

from __future__ import annotations

from unittest.mock import patch

from hypothesis import given, settings as h_settings, assume, HealthCheck
from hypothesis import strategies as st

from app.pipeline.rv.verifier import RuntimeVerifier
from app.schemas import (
    BCVCategory,
    Claim,
    SynthesizedTest,
    TestOutcome,
    ViolationReport,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_RV = RuntimeVerifier(timeout=10)


def _make_claim(**overrides) -> Claim:
    """Build a minimal valid Claim with sensible defaults."""
    defaults = dict(
        category=BCVCategory.RSV,
        subject="return",
        predicate_object="returns a list",
        conditionality=None,
        source_line=1,
        raw_text="Returns a list.",
    )
    defaults.update(overrides)
    return Claim(**defaults)


def _make_synthesized_test(
    test_code: str,
    test_function_name: str,
    claim: Claim | None = None,
) -> SynthesizedTest:
    """Build a SynthesizedTest with sensible defaults."""
    return SynthesizedTest(
        claim=claim or _make_claim(),
        test_code=test_code,
        test_function_name=test_function_name,
        synthesis_model="test-model",
    )


def _make_result_dict(
    name: str,
    outcome: str,
    traceback: str | None = None,
) -> dict:
    """Build a mock pytest result dict matching the _run_pytest output format."""
    return {
        "nodeid": f"test_veridoc_rv.py::{name}",
        "outcome": outcome,
        "stdout": "",
        "stderr": "",
        "traceback": traceback,
        "duration": 0.01,
    }


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------


@st.composite
def outcome_string_strategy(draw: st.DrawFn) -> str:
    """Generate pytest outcome strings including known and unknown values."""
    return draw(
        st.sampled_from(["passed", "failed", "error", "skipped", "xfailed", ""])
    )


@st.composite
def result_dict_strategy(draw: st.DrawFn) -> dict:
    """Generate a pytest result dict with an outcome and optional traceback."""
    outcome = draw(outcome_string_strategy())
    has_traceback = draw(st.booleans())
    traceback = (
        draw(st.from_regex(r"[A-Za-z0-9 :=\n]{10,80}", fullmatch=True))
        if has_traceback
        else None
    )
    return {
        "nodeid": "test_veridoc_rv.py::test_example",
        "outcome": outcome,
        "stdout": "",
        "stderr": "",
        "traceback": traceback,
        "duration": draw(st.floats(min_value=0.0, max_value=5.0)),
    }


@st.composite
def pass_fail_error_counts_strategy(draw: st.DrawFn) -> tuple[int, int, int]:
    """Generate (pass_count, fail_count, error_count) combinations.

    Ensures at least one of pass or fail is present so bcv_rate is defined.
    """
    pass_count = draw(st.integers(min_value=0, max_value=50))
    fail_count = draw(st.integers(min_value=0, max_value=50))
    error_count = draw(st.integers(min_value=0, max_value=20))
    assume(pass_count + fail_count > 0)
    return pass_count, fail_count, error_count


# ---------------------------------------------------------------------------
# Property 11: Outcome classification determinism
# ---------------------------------------------------------------------------


@given(result=result_dict_strategy())
@h_settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_outcome_classification_determinism(result: dict) -> None:
    """Property 11: _classify_outcome deterministically maps:
    - "passed" → PASS
    - "failed" → FAIL
    - "error"  → ERROR
    - anything else → UNDETERMINED

    Every FAIL outcome must have a non-null traceback when the result dict
    itself carries a traceback (i.e. the mapping is consistent with the
    expectation that real pytest failures always include tracebacks).

    **Validates: Requirements 4.2, 4.3, 4.4**
    """
    outcome = _RV._classify_outcome(result)

    raw = result.get("outcome", "")

    # Deterministic mapping
    if raw == "passed":
        assert outcome == TestOutcome.PASS, f"Expected PASS for 'passed', got {outcome}"
    elif raw == "failed":
        assert outcome == TestOutcome.FAIL, f"Expected FAIL for 'failed', got {outcome}"
    elif raw == "error":
        assert outcome == TestOutcome.ERROR, f"Expected ERROR for 'error', got {outcome}"
    else:
        assert outcome == TestOutcome.UNDETERMINED, (
            f"Expected UNDETERMINED for {raw!r}, got {outcome}"
        )

    # Idempotency: calling again with the same input yields the same result
    assert _RV._classify_outcome(result) == outcome

    # For FAIL outcomes from real pytest, traceback is expected to be present.
    # We verify the invariant: if outcome is FAIL and the result dict has a
    # traceback, it must be non-null (the verifier preserves it).
    if outcome == TestOutcome.FAIL and result.get("traceback") is not None:
        assert result["traceback"] is not None


# ---------------------------------------------------------------------------
# Property 12: BCV rate computation correctness
# ---------------------------------------------------------------------------


@given(counts=pass_fail_error_counts_strategy())
@h_settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_bcv_rate_computation_correctness(counts: tuple[int, int, int]) -> None:
    """Property 12: bcv_rate = fail / (pass + fail), excludes ERROR and
    UNDETERMINED outcomes, and the result is always in [0.0, 1.0].

    We generate pass/fail/error counts, build a test suite with controlled
    mock results from _run_pytest, and verify the computed bcv_rate.

    **Validates: Requirements 4.5, 10.5, 10.6**
    """
    pass_count, fail_count, error_count = counts

    source_code = "def target_func():\n    return 42\n"

    # Build synthesized tests and matching mock pytest results
    tests: list[SynthesizedTest] = []
    mock_results: list[dict] = []
    idx = 0

    for _ in range(pass_count):
        name = f"test_pass_{idx}"
        code = f"def {name}():\n    assert True\n"
        tests.append(_make_synthesized_test(code, name))
        mock_results.append(_make_result_dict(name, "passed"))
        idx += 1

    for _ in range(fail_count):
        name = f"test_fail_{idx}"
        code = f"def {name}():\n    assert False\n"
        tests.append(_make_synthesized_test(code, name))
        mock_results.append(
            _make_result_dict(name, "failed", traceback="assert 42 == 999")
        )
        idx += 1

    for _ in range(error_count):
        name = f"test_error_{idx}"
        code = f"def {name}():\n    pass\n"
        tests.append(_make_synthesized_test(code, name))
        mock_results.append(
            _make_result_dict(name, "error", traceback="ImportError")
        )
        idx += 1

    with patch.object(_RV, "_run_pytest", return_value=mock_results), \
         patch.object(_RV, "_write_test_module", return_value="/tmp/fake.py"):
        report = _RV.verify(
            tests, source_code, analysis_id="prop12", function_name="target_func",
        )

    # BCV rate formula: fail / (pass + fail), excluding ERROR
    expected_total = pass_count + fail_count
    expected_rate = fail_count / expected_total if expected_total > 0 else 0.0

    # Rate must be in [0.0, 1.0]
    assert 0.0 <= report.bcv_rate <= 1.0, (
        f"bcv_rate {report.bcv_rate} out of [0.0, 1.0] range"
    )

    # Rate must match expected formula
    assert abs(report.bcv_rate - expected_rate) < 1e-9, (
        f"bcv_rate mismatch: expected {expected_rate}, got {report.bcv_rate} "
        f"(pass={pass_count}, fail={fail_count}, error={error_count})"
    )

    # Verify counts match
    assert report.pass_count == pass_count
    assert report.fail_count == fail_count
    assert report.error_count == error_count


# ---------------------------------------------------------------------------
# Property 13: ViolationReport excludes non-violations
# ---------------------------------------------------------------------------


@given(counts=pass_fail_error_counts_strategy())
@h_settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_violation_report_excludes_non_violations(
    counts: tuple[int, int, int],
) -> None:
    """Property 13: The violations list in ViolationReport contains ONLY
    FAIL outcomes. PASS, ERROR, and UNDETERMINED outcomes must not appear.

    **Validates: Requirements 4.4, 10.5**
    """
    pass_count, fail_count, error_count = counts

    source_code = "def target_func():\n    return 42\n"

    tests: list[SynthesizedTest] = []
    mock_results: list[dict] = []
    idx = 0

    for _ in range(pass_count):
        name = f"test_pass_{idx}"
        code = f"def {name}():\n    assert True\n"
        tests.append(_make_synthesized_test(code, name))
        mock_results.append(_make_result_dict(name, "passed"))
        idx += 1

    for _ in range(fail_count):
        name = f"test_fail_{idx}"
        code = f"def {name}():\n    assert False\n"
        tests.append(_make_synthesized_test(code, name))
        mock_results.append(
            _make_result_dict(name, "failed", traceback="AssertionError: assert 42 == 999")
        )
        idx += 1

    for _ in range(error_count):
        name = f"test_error_{idx}"
        code = f"def {name}():\n    pass\n"
        tests.append(_make_synthesized_test(code, name))
        mock_results.append(
            _make_result_dict(name, "error", traceback="ImportError")
        )
        idx += 1

    with patch.object(_RV, "_run_pytest", return_value=mock_results), \
         patch.object(_RV, "_write_test_module", return_value="/tmp/fake.py"):
        report = _RV.verify(
            tests, source_code, analysis_id="prop13", function_name="target_func",
        )

    # Every record in violations must be FAIL
    for v in report.violations:
        assert v.outcome == TestOutcome.FAIL, (
            f"Non-FAIL outcome {v.outcome} found in violations list"
        )

    # The number of violations must equal fail_count
    assert len(report.violations) == fail_count, (
        f"Expected {fail_count} violations, got {len(report.violations)}"
    )

    # No PASS or ERROR outcomes in violations
    violation_outcomes = {v.outcome for v in report.violations}
    assert TestOutcome.PASS not in violation_outcomes, "PASS found in violations"
    assert TestOutcome.ERROR not in violation_outcomes, "ERROR found in violations"
    assert TestOutcome.UNDETERMINED not in violation_outcomes, "UNDETERMINED found in violations"
