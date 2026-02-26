"""Unit tests for _extract_raise_statements.

Validates Requirement 2.3 — AST detection of raise statements with exception
class and triggering condition extraction.
"""

from __future__ import annotations

import ast

from app.pipeline.bce.extractor import (
    _extract_raise_statements,
    _extract_function_info,
    extract_all_function_infos,
)


def _parse_first_func(source: str):
    tree = ast.parse(source)
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    raise ValueError("No function found")


# ---------------------------------------------------------------------------
# Tests for _extract_raise_statements
# ---------------------------------------------------------------------------


class TestExtractRaiseStatements:
    def test_simple_raise_with_call(self):
        src = '''\
def validate(x):
    if x < 0:
        raise ValueError("must be non-negative")
'''
        node = _parse_first_func(src)
        results = _extract_raise_statements(node)
        assert len(results) == 1
        assert results[0]["exception_class"] == "ValueError"
        assert results[0]["condition"] == "x < 0"
        assert results[0]["lineno"] == 3

    def test_raise_without_condition(self):
        src = '''\
def fail():
    raise RuntimeError("always fails")
'''
        node = _parse_first_func(src)
        results = _extract_raise_statements(node)
        assert len(results) == 1
        assert results[0]["exception_class"] == "RuntimeError"
        assert results[0]["condition"] is None

    def test_bare_raise(self):
        """A bare ``raise`` (re-raise) has no exc node."""
        src = '''\
def reraise():
    try:
        pass
    except Exception:
        raise
'''
        node = _parse_first_func(src)
        results = _extract_raise_statements(node)
        assert len(results) == 1
        assert results[0]["exception_class"] == "Exception"
        assert results[0]["condition"] is None

    def test_raise_name_without_call(self):
        """``raise ValueError`` without calling it."""
        src = '''\
def check(data):
    if not data:
        raise ValueError
'''
        node = _parse_first_func(src)
        results = _extract_raise_statements(node)
        assert len(results) == 1
        assert results[0]["exception_class"] == "ValueError"
        assert results[0]["condition"] == "not data"

    def test_multiple_raises(self):
        src = '''\
def process(x, y):
    if x is None:
        raise TypeError("x required")
    if y < 0:
        raise ValueError("y must be positive")
'''
        node = _parse_first_func(src)
        results = _extract_raise_statements(node)
        assert len(results) == 2
        classes = {r["exception_class"] for r in results}
        assert classes == {"TypeError", "ValueError"}

    def test_no_raise_statements(self):
        src = '''\
def add(a, b):
    return a + b
'''
        node = _parse_first_func(src)
        results = _extract_raise_statements(node)
        assert results == []

    def test_attribute_exception_class(self):
        """``raise module.CustomError(...)`` extracts the attribute name."""
        src = '''\
def check():
    raise errors.NotFoundError("missing")
'''
        node = _parse_first_func(src)
        results = _extract_raise_statements(node)
        assert len(results) == 1
        assert results[0]["exception_class"] == "NotFoundError"

    def test_nested_if_picks_innermost(self):
        """When raise is inside nested ifs, the innermost enclosing if is used."""
        src = '''\
def check(x, y):
    if x > 0:
        if y < 0:
            raise ValueError("bad y")
'''
        node = _parse_first_func(src)
        results = _extract_raise_statements(node)
        assert len(results) == 1
        assert results[0]["condition"] == "y < 0"


# ---------------------------------------------------------------------------
# Integration: raise_statements populated in FunctionInfo
# ---------------------------------------------------------------------------


class TestRaiseStatementsInFunctionInfo:
    def test_function_info_has_raise_statements(self):
        src = '''\
def divide(a, b):
    """Divide a by b."""
    if b == 0:
        raise ZeroDivisionError("cannot divide by zero")
    return a / b
'''
        infos = extract_all_function_infos(src)
        assert len(infos) == 1
        rs = infos[0].raise_statements
        assert len(rs) == 1
        assert rs[0]["exception_class"] == "ZeroDivisionError"
        assert rs[0]["condition"] == "b == 0"

    def test_function_without_raises_has_empty_list(self):
        src = '''\
def add(a, b):
    """Add two numbers."""
    return a + b
'''
        infos = extract_all_function_infos(src)
        assert len(infos) == 1
        assert infos[0].raise_statements == []
