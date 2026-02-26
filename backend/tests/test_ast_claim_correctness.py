"""Property test for AST-derived claim correctness.

**Validates: Requirements 2.3, 2.4**

Property 3: AST-derived claim correctness — For any Python function containing
raise statements or in-place mutation patterns on parameters, the BCE AST track
should produce ECV claims for each raise statement and SEV claims for each
detected mutation, with the correct exception class, parameter name, and
mutation method.
"""

from __future__ import annotations

import ast
from collections import Counter

from hypothesis import given, settings as h_settings, HealthCheck, assume
from hypothesis import strategies as st

from app.pipeline.bce.extractor import (
    _extract_raise_statements,
    detect_mutations,
)


# ---------------------------------------------------------------------------
# Exception classes used in generated raise statements
# ---------------------------------------------------------------------------

EXCEPTION_CLASSES = [
    "ValueError",
    "TypeError",
    "KeyError",
    "IndexError",
    "RuntimeError",
    "AttributeError",
    "ZeroDivisionError",
    "FileNotFoundError",
    "OverflowError",
    "StopIteration",
]

# Conditions that can guard a raise statement
IF_CONDITIONS = [
    "x < 0",
    "not data",
    "len(items) == 0",
    "value is None",
    "idx >= len(arr)",
]

# Mutation methods mapped to the code pattern that triggers them
MUTATION_METHOD_TEMPLATES: dict[str, str] = {
    "sort": "{param}.sort()",
    "append": "{param}.append(1)",
    "extend": "{param}.extend([1])",
    "insert": "{param}.insert(0, 1)",
    "remove": "{param}.remove(1)",
    "pop": "{param}.pop()",
    "clear": "{param}.clear()",
    "reverse": "{param}.reverse()",
    "update": "{param}.update({{}})",
    "setdefault": '{param}.setdefault("k", 0)',
    "add": "{param}.add(1)",
    "discard": "{param}.discard(1)",
    "item_assignment": "{param}[0] = 99",
    "slice_assignment": "{param}[0:1] = [99]",
    "attribute_assignment": "{param}.attr = 99",
    "augmented_assignment": "{param} += [1]",
}

PARAM_NAMES = ["data", "items", "values", "config", "mapping", "arr", "seq"]


# ---------------------------------------------------------------------------
# Hypothesis composite strategies
# ---------------------------------------------------------------------------


@st.composite
def raise_function_source(draw: st.DrawFn):
    """Generate a Python function containing 1-4 raise statements.

    Each raise is placed in its own independent block so that ordering
    within ``ast.walk`` does not affect correctness checks.

    Returns ``(source_code, expected_raises)`` where *expected_raises* is a
    list of dicts with ``exception_class`` keys.
    """
    n_raises = draw(st.integers(min_value=1, max_value=4))
    exc_classes = draw(
        st.lists(
            st.sampled_from(EXCEPTION_CLASSES),
            min_size=n_raises,
            max_size=n_raises,
        )
    )
    use_conditions = draw(
        st.lists(st.booleans(), min_size=n_raises, max_size=n_raises)
    )
    conditions = draw(
        st.lists(
            st.sampled_from(IF_CONDITIONS),
            min_size=n_raises,
            max_size=n_raises,
        )
    )

    body_lines: list[str] = []
    expected: list[dict] = []

    for i in range(n_raises):
        exc = exc_classes[i]
        if use_conditions[i]:
            cond = conditions[i]
            body_lines.append(f"    if {cond}:")
            body_lines.append(f'        raise {exc}("error {i}")')
            expected.append({"exception_class": exc, "has_condition": True})
        else:
            body_lines.append(f'    raise {exc}("error {i}")')
            expected.append({"exception_class": exc, "has_condition": False})

    source = "def func(x, data, items, value, idx, arr, key, mapping):\n"
    source += "\n".join(body_lines)

    try:
        ast.parse(source)
    except SyntaxError:
        assume(False)

    return source, expected


@st.composite
def mutation_function_source(draw: st.DrawFn):
    """Generate a Python function containing 1-4 mutation patterns.

    Returns ``(source_code, expected_mutations)`` where *expected_mutations*
    is a list of dicts with ``target`` and ``method`` keys.
    """
    n_mutations = draw(st.integers(min_value=1, max_value=4))
    param_name = draw(st.sampled_from(PARAM_NAMES))
    methods = draw(
        st.lists(
            st.sampled_from(list(MUTATION_METHOD_TEMPLATES.keys())),
            min_size=n_mutations,
            max_size=n_mutations,
        )
    )

    body_lines: list[str] = []
    expected: list[dict] = []

    for method in methods:
        template = MUTATION_METHOD_TEMPLATES[method]
        line = "    " + template.format(param=param_name)
        body_lines.append(line)
        expected.append({"target": param_name, "method": method})

    source = f"def func({param_name}):\n"
    source += "\n".join(body_lines)

    try:
        ast.parse(source)
    except SyntaxError:
        assume(False)

    return source, expected


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _parse_first_func(source: str):
    tree = ast.parse(source)
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    raise ValueError("No function found in source")


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(data=raise_function_source())
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_extract_raise_statements_correctness(
    data: tuple[str, list[dict]],
) -> None:
    """Property 3 (raise statements): For any function with raise statements,
    _extract_raise_statements produces the correct number of entries with the
    correct exception classes.

    **Validates: Requirements 2.3**
    """
    source, expected_raises = data
    node = _parse_first_func(source)
    results = _extract_raise_statements(node)

    # --- Correct total count ---
    assert len(results) == len(expected_raises), (
        f"Expected {len(expected_raises)} raise(s), got {len(results)}"
    )

    # --- Exception class multiset matches ---
    # ast.walk order is not guaranteed to match source order, so we compare
    # as unordered multisets.
    expected_classes = Counter(e["exception_class"] for e in expected_raises)
    actual_classes = Counter(r["exception_class"] for r in results)
    assert actual_classes == expected_classes, (
        f"Exception class mismatch: expected {expected_classes}, "
        f"got {actual_classes}"
    )

    # --- Structural invariants on every result ---
    for result in results:
        assert "exception_class" in result
        assert "condition" in result
        assert "lineno" in result
        assert isinstance(result["exception_class"], str)
        assert len(result["exception_class"]) > 0
        assert isinstance(result["lineno"], int)
        assert result["lineno"] > 0

    # --- Conditional raises have non-None condition ---
    # Count how many conditional raises we expect vs how many results have
    # a non-None condition.  Because ordering may differ, we verify the
    # *count* of conditional results matches.
    expected_conditional_count = sum(
        1 for e in expected_raises if e["has_condition"]
    )
    actual_conditional_count = sum(
        1 for r in results if r["condition"] is not None
    )
    assert actual_conditional_count >= expected_conditional_count, (
        f"Expected at least {expected_conditional_count} conditional raise(s), "
        f"got {actual_conditional_count}"
    )


@given(data=mutation_function_source())
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_detect_mutations_correctness(
    data: tuple[str, list[dict]],
) -> None:
    """Property 3 (mutations): For any function with mutation patterns on
    parameters, detect_mutations produces the correct number of entries with
    the correct target parameter and mutation method.

    **Validates: Requirements 2.4**
    """
    source, expected_mutations = data
    node = _parse_first_func(source)
    results = detect_mutations(node)

    # --- Correct total count ---
    assert len(results) == len(expected_mutations), (
        f"Expected {len(expected_mutations)} mutation(s), got {len(results)}"
    )

    # --- (target, method) multiset matches ---
    expected_pairs = Counter(
        (e["target"], e["method"]) for e in expected_mutations
    )
    actual_pairs = Counter(
        (r["target"], r["method"]) for r in results
    )
    assert actual_pairs == expected_pairs, (
        f"Mutation mismatch: expected {expected_pairs}, got {actual_pairs}"
    )

    # --- Structural invariants on every result ---
    for result in results:
        assert "target" in result
        assert "method" in result
        assert "line" in result
        assert isinstance(result["target"], str)
        assert len(result["target"]) > 0
        assert isinstance(result["method"], str)
        assert len(result["method"]) > 0
        assert isinstance(result["line"], int)
        assert result["line"] > 0
