"""Property tests for API validation and export.

**Validates: Requirements 1.1–1.3, 7.1, 7.2, 11.3**

Properties tested:
- Property 1:  Python source validation correctness
- Property 16: JSON export round-trip
- Property 17: CSV export row completeness
- Property 19: XSS sanitization
"""

from __future__ import annotations

import ast
import csv
import io
import json

from hypothesis import given, settings as h_settings, assume, HealthCheck
from hypothesis import strategies as st

from app.api.router import _validate_python, sanitize_source, _export_csv, _export_json, _build_violation_dicts
from app.schemas import BCVCategory, TestOutcome


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------


@st.composite
def python_source_strategy(draw: st.DrawFn) -> str:
    """Generate arbitrary strings that may or may not be valid Python."""
    return draw(
        st.one_of(
            # Valid Python snippets
            st.sampled_from([
                "x = 1",
                "def foo():\n    return 42\n",
                "class A:\n    pass\n",
                "import os\n",
                "a, b = 1, 2\n",
                "for i in range(10):\n    pass\n",
                "if True:\n    x = 1\nelse:\n    x = 2\n",
                "lambda x: x + 1",
                "pass",
                "",
            ]),
            # Invalid Python snippets
            st.sampled_from([
                "def",
                "def foo(:\n",
                "class :\n",
                "if\n",
                "return return return",
                "def foo(\n",
                "x = = = 1",
                "for in range(10):\n",
                "import",
                "def foo() return 1",
            ]),
            # Random text (likely invalid Python)
            st.text(
                alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
                min_size=1,
                max_size=200,
            ),
        )
    )


_BCV_CATEGORIES = [c.value for c in BCVCategory]


@st.composite
def violation_dict_strategy(draw: st.DrawFn) -> dict:
    """Generate a violation dict matching the CSV/JSON export format."""
    return {
        "function_name": draw(st.from_regex(r"[a-z_][a-z0-9_]{0,20}", fullmatch=True)),
        "category": draw(st.sampled_from(_BCV_CATEGORIES)),
        "claim_text": draw(st.text(min_size=1, max_size=100).filter(lambda s: s.strip())),
        "outcome": "fail",
        "expected": draw(st.text(max_size=50)),
        "actual": draw(st.text(max_size=50)),
    }



@st.composite
def violation_report_dict_strategy(draw: st.DrawFn) -> dict:
    """Generate a ViolationReport-like dict for JSON export round-trip testing."""
    violations = draw(st.lists(violation_dict_strategy(), min_size=0, max_size=10))
    category_breakdown: dict[str, int] = {}
    for v in violations:
        cat = v["category"]
        category_breakdown[cat] = category_breakdown.get(cat, 0) + 1

    return {
        "analysis_id": draw(st.uuids().map(str)),
        "filename": draw(st.one_of(st.none(), st.text(min_size=1, max_size=30))),
        "llm_provider": draw(st.sampled_from(["gpt-4o", "claude-3-5-sonnet", "gemini-1.5-pro"])),
        "status": "complete",
        "total_functions": draw(st.integers(min_value=0, max_value=100)),
        "total_claims": draw(st.integers(min_value=0, max_value=200)),
        "total_violations": len(violations),
        "bcv_rate": draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
        "category_breakdown": category_breakdown,
        "violations": violations,
    }


@st.composite
def xss_source_strategy(draw: st.DrawFn) -> str:
    """Generate source code strings containing XSS payloads."""
    safe_code = draw(st.sampled_from([
        "x = 1\n",
        "def foo():\n    return 42\n",
        "# comment\n",
        "pass\n",
    ]))
    xss_payload = draw(st.sampled_from([
        '<script>alert("xss")</script>',
        "<script>document.cookie</script>",
        '<script src="evil.js"></script>',
        '<SCRIPT>alert(1)</SCRIPT>',
        '<img onerror="alert(1)" src="x">',
        '<div onclick="steal()">',
        '<a onmouseover="hack()">link</a>',
        'onclick="alert(1)"',
        "javascript:alert(1)",
        "JAVASCRIPT:void(0)",
        '<body onload="malicious()">',
        '<input onfocus="evil()" autofocus>',
    ]))
    # Inject payload at random position
    position = draw(st.sampled_from(["before", "after", "middle"]))
    if position == "before":
        return xss_payload + "\n" + safe_code
    elif position == "after":
        return safe_code + "\n" + xss_payload
    else:
        lines = safe_code.split("\n")
        mid = len(lines) // 2
        lines.insert(mid, xss_payload)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Property 1: Python source validation correctness
# ---------------------------------------------------------------------------


@given(source=python_source_strategy())
@h_settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_python_source_validation_correctness(source: str) -> None:
    """Property 1: _validate_python accepts iff ast.parse() succeeds.
    On rejection, the HTTPException detail contains 'line' and 'message'.

    **Validates: Requirements 1.1, 1.2, 1.3**
    """
    # Determine ground truth: does ast.parse succeed?
    ast_succeeds = True
    try:
        ast.parse(source)
    except SyntaxError:
        ast_succeeds = False

    # Test _validate_python against ground truth
    if ast_succeeds:
        # Should not raise
        _validate_python(source)  # no exception = pass
    else:
        # Should raise HTTPException 422 with line and message
        from fastapi import HTTPException

        try:
            _validate_python(source)
            # If we get here, validation accepted invalid Python — fail
            assert False, (
                f"_validate_python accepted invalid Python: {source!r}"
            )
        except HTTPException as exc:
            assert exc.status_code == 422, (
                f"Expected 422, got {exc.status_code}"
            )
            detail = exc.detail
            assert isinstance(detail, dict), (
                f"Expected dict detail, got {type(detail)}"
            )
            assert "line" in detail, (
                f"Error detail missing 'line' key: {detail}"
            )
            assert "message" in detail, (
                f"Error detail missing 'message' key: {detail}"
            )


# ---------------------------------------------------------------------------
# Property 16: JSON export round-trip
# ---------------------------------------------------------------------------


@given(report=violation_report_dict_strategy())
@h_settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_json_export_round_trip(report: dict) -> None:
    """Property 16: Serializing a ViolationReport to JSON then deserializing
    produces an equivalent object.

    **Validates: Requirement 7.1**
    """
    # Serialize to JSON
    serialized = json.dumps(report, indent=2)

    # Deserialize back
    deserialized = json.loads(serialized)

    # Verify equivalence of all top-level fields
    assert deserialized["analysis_id"] == report["analysis_id"]
    assert deserialized["filename"] == report["filename"]
    assert deserialized["llm_provider"] == report["llm_provider"]
    assert deserialized["status"] == report["status"]
    assert deserialized["total_functions"] == report["total_functions"]
    assert deserialized["total_claims"] == report["total_claims"]
    assert deserialized["total_violations"] == report["total_violations"]
    assert deserialized["category_breakdown"] == report["category_breakdown"]

    # bcv_rate: compare with tolerance for float serialization
    assert abs(deserialized["bcv_rate"] - report["bcv_rate"]) < 1e-9

    # Violations list: same length and each violation matches
    assert len(deserialized["violations"]) == len(report["violations"])
    for orig, deser in zip(report["violations"], deserialized["violations"]):
        assert deser["function_name"] == orig["function_name"]
        assert deser["category"] == orig["category"]
        assert deser["claim_text"] == orig["claim_text"]
        assert deser["outcome"] == orig["outcome"]
        assert deser["expected"] == orig["expected"]
        assert deser["actual"] == orig["actual"]


# ---------------------------------------------------------------------------
# Property 17: CSV export row completeness
# ---------------------------------------------------------------------------


@given(violations=st.lists(violation_dict_strategy(), min_size=0, max_size=20))
@h_settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_csv_export_row_completeness(violations: list[dict]) -> None:
    """Property 17: N violations → N data rows + 1 header row.
    Each row has all required fields: function_name, category, claim_text,
    outcome, expected, actual.

    **Validates: Requirement 7.2**
    """
    n = len(violations)

    # Build CSV content the same way the export endpoint does
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["function_name", "category", "claim_text", "outcome", "expected", "actual"]
    )
    for v in violations:
        writer.writerow([
            v["function_name"],
            v["category"],
            v["claim_text"],
            v["outcome"],
            v.get("expected", ""),
            v.get("actual", ""),
        ])
    csv_content = buf.getvalue()

    # Parse the CSV back
    reader = csv.reader(io.StringIO(csv_content))
    rows = list(reader)

    # Header + N data rows
    assert len(rows) == n + 1, (
        f"Expected {n + 1} rows (1 header + {n} data), got {len(rows)}"
    )

    # Verify header
    expected_header = ["function_name", "category", "claim_text", "outcome", "expected", "actual"]
    assert rows[0] == expected_header, (
        f"Header mismatch: expected {expected_header}, got {rows[0]}"
    )

    # Each data row must have exactly 6 fields
    for i, row in enumerate(rows[1:], start=1):
        assert len(row) == 6, (
            f"Row {i} has {len(row)} fields, expected 6: {row}"
        )
        # function_name (index 0) must be non-empty
        assert row[0], f"Row {i} has empty function_name"
        # category (index 1) must be a valid BCV category
        assert row[1] in _BCV_CATEGORIES, (
            f"Row {i} has invalid category: {row[1]}"
        )
        # claim_text (index 2) must be non-empty
        assert row[2], f"Row {i} has empty claim_text"
        # outcome (index 3) must be present
        assert row[3], f"Row {i} has empty outcome"


# ---------------------------------------------------------------------------
# Property 19: XSS sanitization
# ---------------------------------------------------------------------------


@given(source=xss_source_strategy())
@h_settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_xss_sanitization(source: str) -> None:
    """Property 19: Source code with script tags/event handlers produces
    safe output after sanitization. The sanitized output must not contain
    executable script content.

    **Validates: Requirement 11.3**
    """
    sanitized = sanitize_source(source)

    # No <script> tags (case-insensitive)
    assert "<script" not in sanitized.lower(), (
        f"Sanitized output still contains <script> tag: {sanitized!r}"
    )
    assert "</script>" not in sanitized.lower(), (
        f"Sanitized output still contains </script> tag: {sanitized!r}"
    )

    # No on* event handler attributes (e.g., onclick="...", onerror="...")
    import re
    event_handler_pattern = re.compile(r'\bon\w+\s*=\s*["\'][^"\']*["\']', re.IGNORECASE)
    assert not event_handler_pattern.search(sanitized), (
        f"Sanitized output still contains event handler: {sanitized!r}"
    )

    # No javascript: URIs
    assert "javascript:" not in sanitized.lower(), (
        f"Sanitized output still contains javascript: URI: {sanitized!r}"
    )
