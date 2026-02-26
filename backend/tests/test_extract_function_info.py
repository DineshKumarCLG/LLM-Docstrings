"""Unit tests for _extract_function_info and related helpers.

Validates Requirement 2.1 — AST-based extraction of function signatures,
return annotations, params, and docstrings.
"""

from __future__ import annotations

import ast

from app.pipeline.bce.extractor import (
    _extract_function_info,
    _extract_params,
    _build_signature,
    extract_all_function_infos,
)


# ---------------------------------------------------------------------------
# Fixtures / sample source
# ---------------------------------------------------------------------------

SAMPLE_SOURCE = '''\
def normalize_list(data: list[float], scale: float = 1.0) -> list[float]:
    """Normalize values to unit range.

    Returns a new list with values scaled to [0, 1].
    """
    min_val = min(data)
    max_val = max(data)
    rng = max_val - min_val
    return [(v - min_val) / rng * scale for v in data]
'''

ASYNC_SOURCE = '''\
async def fetch(url: str, *, timeout: int = 30) -> bytes:
    """Fetch content from a URL."""
    pass
'''

NO_DOCSTRING_SOURCE = '''\
def add(a: int, b: int) -> int:
    return a + b
'''

BARE_FUNCTION_SOURCE = '''\
def greet(name):
    """Say hello."""
    return f"Hello, {name}"
'''

COMPLEX_PARAMS_SOURCE = '''\
def complex(a, b: int, *args: str, key: bool = True, **kwargs: float) -> None:
    """Complex signature."""
    pass
'''


# ---------------------------------------------------------------------------
# Tests for _extract_function_info
# ---------------------------------------------------------------------------


class TestExtractFunctionInfo:
    def _parse_first(self, source: str):
        tree = ast.parse(source)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return node
        raise ValueError("No function found")

    def test_basic_function(self):
        node = self._parse_first(SAMPLE_SOURCE)
        info = _extract_function_info(node, SAMPLE_SOURCE, SAMPLE_SOURCE.splitlines())

        assert info.name == "normalize_list"
        assert info.qualified_name == "normalize_list"
        assert info.lineno == 1
        assert info.return_annotation == "list[float]"
        assert info.docstring == "Normalize values to unit range.\n\nReturns a new list with values scaled to [0, 1]."
        assert len(info.params) == 2
        assert info.params[0] == {"name": "data", "annotation": "list[float]", "default": None}
        assert info.params[1] == {"name": "scale", "annotation": "float", "default": "1.0"}
        assert info.raise_statements == []
        assert info.mutation_patterns == []

    def test_qualified_name_with_module(self):
        node = self._parse_first(SAMPLE_SOURCE)
        info = _extract_function_info(
            node, SAMPLE_SOURCE, SAMPLE_SOURCE.splitlines(), module_name="utils"
        )
        assert info.qualified_name == "utils.normalize_list"

    def test_async_function(self):
        node = self._parse_first(ASYNC_SOURCE)
        info = _extract_function_info(node, ASYNC_SOURCE, ASYNC_SOURCE.splitlines())

        assert info.name == "fetch"
        assert info.return_annotation == "bytes"
        assert info.docstring == "Fetch content from a URL."
        assert "async def" in info.signature
        # params: url (positional), timeout (keyword-only with default)
        assert info.params[0] == {"name": "url", "annotation": "str", "default": None}
        assert info.params[1] == {"name": "timeout", "annotation": "int", "default": "30"}

    def test_no_docstring(self):
        node = self._parse_first(NO_DOCSTRING_SOURCE)
        info = _extract_function_info(
            node, NO_DOCSTRING_SOURCE, NO_DOCSTRING_SOURCE.splitlines()
        )
        assert info.docstring is None

    def test_no_annotations(self):
        node = self._parse_first(BARE_FUNCTION_SOURCE)
        info = _extract_function_info(
            node, BARE_FUNCTION_SOURCE, BARE_FUNCTION_SOURCE.splitlines()
        )
        assert info.return_annotation is None
        assert info.params[0] == {"name": "name", "annotation": None, "default": None}

    def test_source_captured(self):
        node = self._parse_first(SAMPLE_SOURCE)
        info = _extract_function_info(node, SAMPLE_SOURCE, SAMPLE_SOURCE.splitlines())
        assert "def normalize_list" in info.source
        assert "return" in info.source

    def test_complex_params(self):
        node = self._parse_first(COMPLEX_PARAMS_SOURCE)
        info = _extract_function_info(
            node, COMPLEX_PARAMS_SOURCE, COMPLEX_PARAMS_SOURCE.splitlines()
        )
        names = [p["name"] for p in info.params]
        assert names == ["a", "b", "*args", "key", "**kwargs"]
        assert info.params[2] == {"name": "*args", "annotation": "str", "default": None}
        assert info.params[3] == {"name": "key", "annotation": "bool", "default": "True"}
        assert info.params[4] == {"name": "**kwargs", "annotation": "float", "default": None}


# ---------------------------------------------------------------------------
# Tests for _build_signature
# ---------------------------------------------------------------------------


class TestBuildSignature:
    def _parse_first(self, source: str):
        tree = ast.parse(source)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return node
        raise ValueError("No function found")

    def test_basic_signature(self):
        node = self._parse_first(SAMPLE_SOURCE)
        sig = _build_signature(node)
        assert sig == "def normalize_list(data: list[float], scale: float = 1.0) -> list[float]"

    def test_async_signature(self):
        node = self._parse_first(ASYNC_SOURCE)
        sig = _build_signature(node)
        assert sig == "async def fetch(url: str, *, timeout: int = 30) -> bytes"

    def test_no_return_annotation(self):
        node = self._parse_first(BARE_FUNCTION_SOURCE)
        sig = _build_signature(node)
        assert sig == "def greet(name)"
        assert "->" not in sig


# ---------------------------------------------------------------------------
# Tests for extract_all_function_infos
# ---------------------------------------------------------------------------


MULTI_FUNC_SOURCE = '''\
def foo(x: int) -> int:
    """Foo docstring."""
    return x

def bar(y: str) -> str:
    """Bar docstring."""
    return y

async def baz() -> None:
    """Baz docstring."""
    pass
'''


class TestExtractAllFunctionInfos:
    def test_extracts_all_functions(self):
        infos = extract_all_function_infos(MULTI_FUNC_SOURCE)
        assert len(infos) == 3
        assert [i.name for i in infos] == ["foo", "bar", "baz"]

    def test_module_name_propagated(self):
        infos = extract_all_function_infos(MULTI_FUNC_SOURCE, module_name="mymod")
        assert all(i.qualified_name.startswith("mymod.") for i in infos)

    def test_empty_source(self):
        infos = extract_all_function_infos("")
        assert infos == []

    def test_source_with_no_functions(self):
        infos = extract_all_function_infos("x = 42\ny = 'hello'\n")
        assert infos == []
