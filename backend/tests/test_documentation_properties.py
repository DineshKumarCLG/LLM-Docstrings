"""Property tests for ``build_documentation_tree``.

**Validates: Requirements 8.4, 8.5, 8.6**

Properties tested:
- Property 12: Documentation Tree Completeness — one root node per top-level
               function/class, child nodes for all methods
- Property 13: Documentation Node Line Number Positivity — all lineno values
               are positive integers (> 0)
"""

from __future__ import annotations

import ast
import uuid
from typing import Any

from hypothesis import given, settings as h_settings, assume, HealthCheck
from hypothesis import strategies as st

from app.api.documentation import build_documentation_tree


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_nodes(nodes: list[dict]) -> list[dict]:
    """Recursively collect every node in the tree (depth-first)."""
    result: list[dict] = []
    for node in nodes:
        result.append(node)
        result.extend(_all_nodes(node.get("children", [])))
    return result


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------


@st.composite
def identifier(draw: st.DrawFn) -> str:
    """Generate a valid Python identifier."""
    first = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz"))
    rest = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_", max_size=10))
    name = first + rest
    # Avoid Python keywords
    keywords = {
        "and", "as", "assert", "async", "await", "break", "class", "continue",
        "def", "del", "elif", "else", "except", "finally", "for", "from",
        "global", "if", "import", "in", "is", "lambda", "nonlocal", "not",
        "or", "pass", "raise", "return", "try", "while", "with", "yield",
        "None", "True", "False",
    }
    assume(name not in keywords)
    return name


@st.composite
def method_def(draw: st.DrawFn) -> tuple[str, str]:
    """Generate a method definition string and its name."""
    name = draw(identifier())
    is_async = draw(st.booleans())
    prefix = "async " if is_async else ""
    src = f"    {prefix}def {name}(self):\n        pass\n"
    return src, name


@st.composite
def class_def(draw: st.DrawFn) -> tuple[str, str, list[str]]:
    """Generate a class definition with 0–4 methods.

    Returns (source, class_name, [method_names]).
    """
    class_name = draw(identifier())
    n_methods = draw(st.integers(min_value=0, max_value=4))
    method_sources_and_names = draw(
        st.lists(method_def(), min_size=n_methods, max_size=n_methods, unique_by=lambda x: x[1])
    )
    method_src = "".join(src for src, _ in method_sources_and_names)
    method_names = [name for _, name in method_sources_and_names]

    if method_src:
        body = method_src
    else:
        body = "    pass\n"

    src = f"class {class_name}:\n{body}\n"
    return src, class_name, method_names


@st.composite
def function_def(draw: st.DrawFn) -> tuple[str, str]:
    """Generate a top-level function definition string and its name."""
    name = draw(identifier())
    is_async = draw(st.booleans())
    prefix = "async " if is_async else ""
    src = f"{prefix}def {name}():\n    pass\n\n"
    return src, name


@st.composite
def python_module(draw: st.DrawFn) -> tuple[str, list[str], dict[str, list[str]]]:
    """Generate a Python module with top-level functions and classes.

    Returns:
        (source_code, top_level_names, {class_name: [method_names]})
    """
    n_funcs = draw(st.integers(min_value=0, max_value=4))
    n_classes = draw(st.integers(min_value=0, max_value=4))

    # Ensure at least one top-level item so the tree is non-trivial
    assume(n_funcs + n_classes > 0)

    func_data = draw(
        st.lists(function_def(), min_size=n_funcs, max_size=n_funcs, unique_by=lambda t: t[1])
    )
    class_data = draw(
        st.lists(class_def(), min_size=n_classes, max_size=n_classes, unique_by=lambda t: t[1])
    )

    # Ensure no name collision between functions and classes
    func_names = [fn for _, fn in func_data]
    class_names = [cn for _, cn, _ in class_data]
    assume(len(set(func_names + class_names)) == len(func_names) + len(class_names))

    # Build source: functions first, then classes
    parts: list[str] = []
    for src, _ in func_data:
        parts.append(src)
    for src, _, _ in class_data:
        parts.append(src)

    source = "\n".join(parts)

    # Verify it parses (defensive — strategies should always produce valid Python)
    try:
        ast.parse(source)
    except SyntaxError:
        assume(False)

    top_level_names = func_names + class_names
    class_methods: dict[str, list[str]] = {
        cn: methods for _, cn, methods in class_data
    }

    return source, top_level_names, class_methods


# ---------------------------------------------------------------------------
# Property 12: Documentation Tree Completeness
# ---------------------------------------------------------------------------


@given(module=python_module())
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_documentation_tree_completeness(
    module: tuple[str, list[str], dict[str, list[str]]]
) -> None:
    """Property 12: For any valid Python source, ``build_documentation_tree``
    produces one root node per top-level function/class, and each class node
    has child nodes for all its methods.

    **Validates: Requirements 8.4, 8.5**
    """
    source, top_level_names, class_methods = module

    analysis_id = str(uuid.uuid4())
    result = build_documentation_tree(source, analysis_id)

    root_nodes: list[dict] = result["rootNodes"]

    # One root node per top-level function or class
    root_names = [node["name"] for node in root_nodes]
    assert sorted(root_names) == sorted(top_level_names), (
        f"Root node names {root_names!r} do not match expected "
        f"top-level names {top_level_names!r}"
    )

    # Each class node must have child nodes for all its methods
    for node in root_nodes:
        if node["type"] == "class":
            class_name = node["name"]
            expected_methods = class_methods.get(class_name, [])
            child_names = [child["name"] for child in node["children"]]
            assert sorted(child_names) == sorted(expected_methods), (
                f"Class {class_name!r} children {child_names!r} do not match "
                f"expected methods {expected_methods!r}"
            )
            # All children must have type "method"
            for child in node["children"]:
                assert child["type"] == "method", (
                    f"Expected child type 'method', got {child['type']!r} "
                    f"for {child['name']!r} in class {class_name!r}"
                )

    # Top-level functions must have no children
    for node in root_nodes:
        if node["type"] == "function":
            assert node["children"] == [], (
                f"Top-level function {node['name']!r} should have no children, "
                f"got {node['children']!r}"
            )


# ---------------------------------------------------------------------------
# Property 13: Documentation Node Line Number Positivity
# ---------------------------------------------------------------------------


@given(module=python_module())
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_documentation_node_line_number_positivity(
    module: tuple[str, list[str], dict[str, list[str]]]
) -> None:
    """Property 13: For all DocumentationNodes in any documentation tree,
    the ``lineno`` field is a positive integer (> 0).

    **Validates: Requirement 8.6**
    """
    source, _, _ = module

    analysis_id = str(uuid.uuid4())
    result = build_documentation_tree(source, analysis_id)

    all_nodes = _all_nodes(result["rootNodes"])

    # Every node must have a positive lineno
    for node in all_nodes:
        lineno = node["lineno"]
        assert isinstance(lineno, int), (
            f"lineno must be an int, got {type(lineno).__name__!r} "
            f"for node {node['name']!r}"
        )
        assert lineno > 0, (
            f"lineno must be > 0, got {lineno} for node {node['name']!r}"
        )
