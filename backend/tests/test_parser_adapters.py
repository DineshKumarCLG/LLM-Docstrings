"""Unit and property tests for ParserRegistry and all language parser adapters.

**Validates: Requirements 2.1, 2.2, 2.9**

Tests:
- ParserRegistry raises UnsupportedLanguageError for unknown languages
- ParserRegistry.supported_languages() covers all six languages
- Each parser: parse_functions extracts functions with correct fields
- Each parser: validate_syntax returns (True, None) for valid source
- Each parser: validate_syntax returns (False, error_message) for invalid source
- Each parser: extract_comments returns doc comments with required keys
- Property: validate_syntax never raises an exception for any string input
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

# Force all parsers to register themselves
import app.pipeline.parsers.python_parser  # noqa: F401
import app.pipeline.parsers.javascript_parser  # noqa: F401
import app.pipeline.parsers.typescript_parser  # noqa: F401
import app.pipeline.parsers.java_parser  # noqa: F401
import app.pipeline.parsers.go_parser  # noqa: F401
import app.pipeline.parsers.rust_parser  # noqa: F401

from app.pipeline.parsers import UnsupportedLanguageError
from app.pipeline.parsers.registry import ParserRegistry
from app.pipeline.parsers.python_parser import PythonParser
from app.pipeline.parsers.javascript_parser import JavaScriptParser
from app.pipeline.parsers.typescript_parser import TypeScriptParser
from app.pipeline.parsers.java_parser import JavaParser
from app.pipeline.parsers.go_parser import GoParser
from app.pipeline.parsers.rust_parser import RustParser


# ===========================================================================
# ParserRegistry tests  (Requirement 2.1, 2.9)
# ===========================================================================


class TestParserRegistry:
    """Tests for ParserRegistry lookup, registration, and error handling."""

    def test_all_six_languages_registered(self):
        langs = set(ParserRegistry.supported_languages())
        assert {"python", "javascript", "typescript", "java", "go", "rust"}.issubset(langs)

    def test_get_returns_correct_parser_type(self):
        assert isinstance(ParserRegistry.get("python"), PythonParser)
        assert isinstance(ParserRegistry.get("javascript"), JavaScriptParser)
        assert isinstance(ParserRegistry.get("typescript"), TypeScriptParser)
        assert isinstance(ParserRegistry.get("java"), JavaParser)
        assert isinstance(ParserRegistry.get("go"), GoParser)
        assert isinstance(ParserRegistry.get("rust"), RustParser)

    def test_get_returns_new_instance_each_call(self):
        a = ParserRegistry.get("python")
        b = ParserRegistry.get("python")
        assert a is not b

    def test_unknown_language_raises_unsupported_error(self):
        with pytest.raises(UnsupportedLanguageError):
            ParserRegistry.get("cobol")

    def test_unsupported_error_message_contains_language(self):
        with pytest.raises(UnsupportedLanguageError) as exc_info:
            ParserRegistry.get("brainfuck")
        assert "brainfuck" in str(exc_info.value)

    def test_unsupported_error_has_language_attribute(self):
        with pytest.raises(UnsupportedLanguageError) as exc_info:
            ParserRegistry.get("ruby")
        assert exc_info.value.language == "ruby"

    def test_supported_languages_returns_list(self):
        assert isinstance(ParserRegistry.supported_languages(), list)

    def test_register_and_get_custom_parser(self):
        """Registering a new parser class makes it retrievable."""
        class _DummyParser(PythonParser):
            def get_language(self) -> str:
                return "_test_dummy"

        ParserRegistry.register("_test_dummy", _DummyParser)
        try:
            parser = ParserRegistry.get("_test_dummy")
            assert isinstance(parser, _DummyParser)
        finally:
            ParserRegistry._parsers.pop("_test_dummy", None)


# ===========================================================================
# Helper: assert comment dict has required keys
# ===========================================================================

_COMMENT_KEYS = {"text", "start_line", "end_line", "associated_function"}


def _assert_comment_keys(comments: list) -> None:
    for c in comments:
        assert _COMMENT_KEYS.issubset(c.keys()), (
            f"Comment dict missing keys. Got: {set(c.keys())}"
        )
        assert isinstance(c["text"], str)
        assert isinstance(c["start_line"], int)
        assert isinstance(c["end_line"], int)


# ===========================================================================
# PythonParser tests  (Requirement 2.2, 2.3)
# ===========================================================================

_PY_VALID = '''\
def add(a: int, b: int) -> int:
    """Return the sum of a and b."""
    return a + b


def greet(name: str) -> str:
    """Say hello to name."""
    return f"Hello, {name}"
'''

_PY_INVALID = "def broken(\n    pass\n"


class TestPythonParser:
    parser = PythonParser()

    def test_get_language(self):
        assert self.parser.get_language() == "python"

    def test_parse_functions_extracts_all(self):
        funcs = self.parser.parse_functions(_PY_VALID)
        names = [f.name for f in funcs]
        assert "add" in names
        assert "greet" in names

    def test_parse_functions_fields(self):
        funcs = self.parser.parse_functions(_PY_VALID)
        add = next(f for f in funcs if f.name == "add")
        assert add.docstring == "Return the sum of a and b."
        assert add.return_annotation == "int"
        param_names = [p["name"] for p in add.params]
        assert "a" in param_names
        assert "b" in param_names

    def test_parse_functions_empty_source(self):
        assert self.parser.parse_functions("") == []

    def test_validate_syntax_valid(self):
        ok, err = self.parser.validate_syntax(_PY_VALID)
        assert ok is True
        assert err is None

    def test_validate_syntax_invalid(self):
        ok, err = self.parser.validate_syntax(_PY_INVALID)
        assert ok is False
        assert isinstance(err, str)
        assert len(err) > 0

    def test_extract_comments_returns_list(self):
        comments = self.parser.extract_comments(_PY_VALID)
        assert isinstance(comments, list)

    def test_extract_comments_keys(self):
        comments = self.parser.extract_comments(_PY_VALID)
        _assert_comment_keys(comments)

    def test_extract_comments_associated_function(self):
        comments = self.parser.extract_comments(_PY_VALID)
        funcs = {c["associated_function"] for c in comments}
        assert "add" in funcs
        assert "greet" in funcs

    def test_extract_comments_empty_source(self):
        assert self.parser.extract_comments("") == []


# ===========================================================================
# JavaScriptParser tests  (Requirement 2.2, 2.4)
# ===========================================================================

_JS_VALID = '''\
/**
 * Add two numbers.
 * @param {number} a - First operand.
 * @param {number} b - Second operand.
 * @returns {number}
 */
function add(a, b) {
    return a + b;
}

/**
 * Greet a user.
 * @param {string} name
 * @throws {Error} if name is empty
 */
const greet = (name) => {
    if (!name) throw new Error("empty name");
    return `Hello, ${name}`;
};
'''

_JS_INVALID = "function broken( { return 1; }"


class TestJavaScriptParser:
    parser = JavaScriptParser()

    def test_get_language(self):
        assert self.parser.get_language() == "javascript"

    def test_parse_functions_extracts_named_function(self):
        funcs = self.parser.parse_functions(_JS_VALID)
        names = [f.name for f in funcs]
        assert "add" in names

    def test_parse_functions_extracts_arrow_function(self):
        funcs = self.parser.parse_functions(_JS_VALID)
        names = [f.name for f in funcs]
        assert "greet" in names

    def test_parse_functions_docstring(self):
        funcs = self.parser.parse_functions(_JS_VALID)
        add = next(f for f in funcs if f.name == "add")
        assert add.docstring is not None
        assert "Add two numbers" in add.docstring

    def test_parse_functions_params_from_jsdoc(self):
        funcs = self.parser.parse_functions(_JS_VALID)
        add = next(f for f in funcs if f.name == "add")
        param_names = [p["name"] for p in add.params]
        assert "a" in param_names
        assert "b" in param_names

    def test_parse_functions_throw_statements(self):
        funcs = self.parser.parse_functions(_JS_VALID)
        greet = next(f for f in funcs if f.name == "greet")
        exc_classes = [r["exception_class"] for r in greet.raise_statements]
        assert "Error" in exc_classes

    def test_validate_syntax_valid(self):
        ok, err = self.parser.validate_syntax(_JS_VALID)
        assert ok is True
        assert err is None

    def test_validate_syntax_invalid(self):
        ok, err = self.parser.validate_syntax(_JS_INVALID)
        assert ok is False
        assert isinstance(err, str)

    def test_extract_comments_keys(self):
        comments = self.parser.extract_comments(_JS_VALID)
        _assert_comment_keys(comments)

    def test_extract_comments_associated_function(self):
        comments = self.parser.extract_comments(_JS_VALID)
        funcs = {c["associated_function"] for c in comments}
        assert "add" in funcs

    def test_extract_comments_empty_source(self):
        assert self.parser.extract_comments("") == []


# ===========================================================================
# TypeScriptParser tests  (Requirement 2.2, 2.5)
# ===========================================================================

_TS_VALID = '''\
/**
 * Multiply two numbers.
 * @param a - First factor.
 * @param b - Second factor.
 * @returns The product.
 */
function multiply(a: number, b: number): number {
    return a * b;
}

class Calculator {
    /**
     * Divide numerator by denominator.
     * @throws {Error} if denominator is zero
     */
    divide(numerator: number, denominator: number): number {
        if (denominator === 0) throw new Error("division by zero");
        return numerator / denominator;
    }
}
'''

_TS_INVALID = "function broken( { return 1; }"


class TestTypeScriptParser:
    parser = TypeScriptParser()

    def test_get_language(self):
        assert self.parser.get_language() == "typescript"

    def test_parse_functions_extracts_function(self):
        funcs = self.parser.parse_functions(_TS_VALID)
        names = [f.name for f in funcs]
        assert "multiply" in names

    def test_parse_functions_return_annotation(self):
        funcs = self.parser.parse_functions(_TS_VALID)
        mul = next(f for f in funcs if f.name == "multiply")
        assert mul.return_annotation is not None
        assert "number" in mul.return_annotation

    def test_parse_functions_class_method(self):
        funcs = self.parser.parse_functions(_TS_VALID)
        names = [f.name for f in funcs]
        assert "divide" in names

    def test_parse_functions_throw_in_method(self):
        funcs = self.parser.parse_functions(_TS_VALID)
        divide = next(f for f in funcs if f.name == "divide")
        exc_classes = [r["exception_class"] for r in divide.raise_statements]
        assert "Error" in exc_classes

    def test_validate_syntax_valid(self):
        ok, err = self.parser.validate_syntax(_TS_VALID)
        assert ok is True
        assert err is None

    def test_validate_syntax_invalid(self):
        ok, err = self.parser.validate_syntax(_TS_INVALID)
        assert ok is False
        assert isinstance(err, str)

    def test_extract_comments_keys(self):
        comments = self.parser.extract_comments(_TS_VALID)
        _assert_comment_keys(comments)

    def test_extract_comments_associated_function(self):
        comments = self.parser.extract_comments(_TS_VALID)
        funcs = {c["associated_function"] for c in comments}
        assert "multiply" in funcs


# ===========================================================================
# JavaParser tests  (Requirement 2.2, 2.6)
# ===========================================================================

_JAVA_VALID = '''\
public class MathUtils {

    /**
     * Add two integers.
     * @param a first operand
     * @param b second operand
     * @return the sum
     */
    public int add(int a, int b) {
        return a + b;
    }

    /**
     * Divide numerator by denominator.
     * @param numerator the dividend
     * @param denominator the divisor
     * @throws ArithmeticException if denominator is zero
     */
    public double divide(int numerator, int denominator) throws ArithmeticException {
        if (denominator == 0) throw new ArithmeticException("zero");
        return (double) numerator / denominator;
    }
}
'''

_JAVA_INVALID = "public class Broken { public void foo() { }"  # missing closing }


class TestJavaParser:
    parser = JavaParser()

    def test_get_language(self):
        assert self.parser.get_language() == "java"

    def test_parse_functions_extracts_methods(self):
        funcs = self.parser.parse_functions(_JAVA_VALID)
        names = [f.name for f in funcs]
        assert "add" in names
        assert "divide" in names

    def test_parse_functions_qualified_name(self):
        funcs = self.parser.parse_functions(_JAVA_VALID)
        add = next(f for f in funcs if f.name == "add")
        assert "MathUtils" in add.qualified_name

    def test_parse_functions_docstring(self):
        funcs = self.parser.parse_functions(_JAVA_VALID)
        add = next(f for f in funcs if f.name == "add")
        assert add.docstring is not None
        assert "Add two integers" in add.docstring

    def test_parse_functions_params_from_javadoc(self):
        funcs = self.parser.parse_functions(_JAVA_VALID)
        add = next(f for f in funcs if f.name == "add")
        param_names = [p["name"] for p in add.params]
        assert "a" in param_names
        assert "b" in param_names

    def test_parse_functions_throws_from_signature(self):
        funcs = self.parser.parse_functions(_JAVA_VALID)
        divide = next(f for f in funcs if f.name == "divide")
        exc_classes = [r["exception_class"] for r in divide.raise_statements]
        assert "ArithmeticException" in exc_classes

    def test_validate_syntax_valid(self):
        ok, err = self.parser.validate_syntax(_JAVA_VALID)
        assert ok is True
        assert err is None

    def test_validate_syntax_invalid(self):
        ok, err = self.parser.validate_syntax(_JAVA_INVALID)
        assert ok is False
        assert isinstance(err, str)

    def test_extract_comments_keys(self):
        comments = self.parser.extract_comments(_JAVA_VALID)
        _assert_comment_keys(comments)

    def test_extract_comments_text(self):
        comments = self.parser.extract_comments(_JAVA_VALID)
        texts = [c["text"] for c in comments]
        assert any("Add two integers" in t for t in texts)

    def test_extract_comments_empty_source(self):
        assert self.parser.extract_comments("") == []


# ===========================================================================
# GoParser tests  (Requirement 2.2, 2.7)
# ===========================================================================

_GO_VALID = '''\
package math

// Add returns the sum of a and b.
func Add(a int, b int) int {
    return a + b
}

// Divide returns a divided by b.
// It panics if b is zero.
func Divide(a, b float64) float64 {
    if b == 0 {
        panic("division by zero")
    }
    return a / b
}
'''

_GO_INVALID = "func broken( { return 1 }"


class TestGoParser:
    parser = GoParser()

    def test_get_language(self):
        assert self.parser.get_language() == "go"

    def test_parse_functions_extracts_functions(self):
        funcs = self.parser.parse_functions(_GO_VALID)
        names = [f.name for f in funcs]
        assert "Add" in names
        assert "Divide" in names

    def test_parse_functions_docstring(self):
        funcs = self.parser.parse_functions(_GO_VALID)
        add = next(f for f in funcs if f.name == "Add")
        assert add.docstring is not None
        assert "sum" in add.docstring

    def test_parse_functions_params(self):
        funcs = self.parser.parse_functions(_GO_VALID)
        add = next(f for f in funcs if f.name == "Add")
        param_names = [p["name"] for p in add.params]
        assert "a" in param_names
        assert "b" in param_names

    def test_parse_functions_return_annotation(self):
        funcs = self.parser.parse_functions(_GO_VALID)
        add = next(f for f in funcs if f.name == "Add")
        assert add.return_annotation is not None

    def test_parse_functions_panic_as_raise(self):
        funcs = self.parser.parse_functions(_GO_VALID)
        divide = next(f for f in funcs if f.name == "Divide")
        exc_classes = [r["exception_class"] for r in divide.raise_statements]
        assert "panic" in exc_classes

    def test_validate_syntax_valid(self):
        ok, err = self.parser.validate_syntax(_GO_VALID)
        assert ok is True
        assert err is None

    def test_validate_syntax_invalid_missing_package(self):
        ok, err = self.parser.validate_syntax("func foo() {}")
        assert ok is False
        assert isinstance(err, str)

    def test_validate_syntax_invalid_unbalanced_braces(self):
        ok, err = self.parser.validate_syntax(_GO_INVALID)
        assert ok is False
        assert isinstance(err, str)

    def test_extract_comments_keys(self):
        comments = self.parser.extract_comments(_GO_VALID)
        _assert_comment_keys(comments)

    def test_extract_comments_associated_function(self):
        comments = self.parser.extract_comments(_GO_VALID)
        funcs = {c["associated_function"] for c in comments}
        assert "Add" in funcs
        assert "Divide" in funcs

    def test_extract_comments_empty_source(self):
        assert self.parser.extract_comments("") == []


# ===========================================================================
# RustParser tests  (Requirement 2.2, 2.8)
# ===========================================================================

_RUST_VALID = '''\
/// Add two integers and return the result.
pub fn add(a: i32, b: i32) -> i32 {
    a + b
}

/// Divide a by b.
///
/// # Panics
/// Panics if b is zero.
pub fn divide(a: f64, b: f64) -> f64 {
    if b == 0.0 {
        panic!("division by zero");
    }
    a / b
}
'''

_RUST_INVALID = "fn broken() { { 1 }"  # missing closing }


class TestRustParser:
    parser = RustParser()

    def test_get_language(self):
        assert self.parser.get_language() == "rust"

    def test_parse_functions_extracts_functions(self):
        funcs = self.parser.parse_functions(_RUST_VALID)
        names = [f.name for f in funcs]
        assert "add" in names
        assert "divide" in names

    def test_parse_functions_docstring(self):
        funcs = self.parser.parse_functions(_RUST_VALID)
        add = next(f for f in funcs if f.name == "add")
        assert add.docstring is not None
        assert "Add two integers" in add.docstring

    def test_parse_functions_params(self):
        funcs = self.parser.parse_functions(_RUST_VALID)
        add = next(f for f in funcs if f.name == "add")
        param_names = [p["name"] for p in add.params]
        assert "a" in param_names
        assert "b" in param_names

    def test_parse_functions_param_annotations(self):
        funcs = self.parser.parse_functions(_RUST_VALID)
        add = next(f for f in funcs if f.name == "add")
        annotations = {p["name"]: p["annotation"] for p in add.params}
        assert annotations["a"] == "i32"
        assert annotations["b"] == "i32"

    def test_parse_functions_return_annotation(self):
        funcs = self.parser.parse_functions(_RUST_VALID)
        add = next(f for f in funcs if f.name == "add")
        assert add.return_annotation is not None
        assert "i32" in add.return_annotation

    def test_parse_functions_panic_as_raise(self):
        funcs = self.parser.parse_functions(_RUST_VALID)
        divide = next(f for f in funcs if f.name == "divide")
        exc_classes = [r["exception_class"] for r in divide.raise_statements]
        assert "panic" in exc_classes

    def test_validate_syntax_valid(self):
        ok, err = self.parser.validate_syntax(_RUST_VALID)
        assert ok is True
        assert err is None

    def test_validate_syntax_invalid(self):
        ok, err = self.parser.validate_syntax(_RUST_INVALID)
        assert ok is False
        assert isinstance(err, str)

    def test_extract_comments_keys(self):
        comments = self.parser.extract_comments(_RUST_VALID)
        _assert_comment_keys(comments)

    def test_extract_comments_associated_function(self):
        comments = self.parser.extract_comments(_RUST_VALID)
        funcs = {c["associated_function"] for c in comments}
        assert "add" in funcs
        assert "divide" in funcs

    def test_extract_comments_empty_source(self):
        assert self.parser.extract_comments("") == []


# ===========================================================================
# Cross-parser: validate_syntax contract  (Requirement 2.9)
# ===========================================================================


class TestValidateSyntaxContract:
    """FOR ALL LanguageParser implementations, validate_syntax SHALL return
    (True, None) for valid source and (False, error_message) for invalid source.
    (Requirement 2.9)
    """

    @pytest.mark.parametrize("parser,valid_source", [
        (PythonParser(), _PY_VALID),
        (JavaScriptParser(), _JS_VALID),
        (TypeScriptParser(), _TS_VALID),
        (JavaParser(), _JAVA_VALID),
        (GoParser(), _GO_VALID),
        (RustParser(), _RUST_VALID),
    ])
    def test_valid_source_returns_true_none(self, parser, valid_source):
        ok, err = parser.validate_syntax(valid_source)
        assert ok is True
        assert err is None

    @pytest.mark.parametrize("parser,invalid_source", [
        (PythonParser(), _PY_INVALID),
        (JavaScriptParser(), _JS_INVALID),
        (TypeScriptParser(), _TS_INVALID),
        (JavaParser(), _JAVA_INVALID),
        (GoParser(), _GO_INVALID),
        (RustParser(), _RUST_INVALID),
    ])
    def test_invalid_source_returns_false_with_message(self, parser, invalid_source):
        ok, err = parser.validate_syntax(invalid_source)
        assert ok is False
        assert isinstance(err, str)
        assert len(err) > 0


# ===========================================================================
# Property-based tests  (Requirement 2.9)
# ===========================================================================

_arbitrary_source = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    max_size=500,
)


@given(source=_arbitrary_source)
@h_settings(max_examples=100)
def test_python_validate_syntax_never_raises(source: str) -> None:
    """**Validates: Requirements 2.9**

    Property: PythonParser.validate_syntax never raises an exception for any
    string input — it always returns a (bool, str|None) tuple.
    """
    result = PythonParser().validate_syntax(source)
    assert isinstance(result, tuple) and len(result) == 2
    ok, err = result
    assert isinstance(ok, bool)
    if ok:
        assert err is None
    else:
        assert isinstance(err, str)


@given(source=_arbitrary_source)
@h_settings(max_examples=100)
def test_javascript_validate_syntax_never_raises(source: str) -> None:
    """**Validates: Requirements 2.9**

    Property: JavaScriptParser.validate_syntax never raises for any input.
    """
    result = JavaScriptParser().validate_syntax(source)
    assert isinstance(result, tuple) and len(result) == 2
    ok, err = result
    assert isinstance(ok, bool)
    if ok:
        assert err is None
    else:
        assert isinstance(err, str)


@given(source=_arbitrary_source)
@h_settings(max_examples=100)
def test_go_validate_syntax_never_raises(source: str) -> None:
    """**Validates: Requirements 2.9**

    Property: GoParser.validate_syntax never raises for any input.
    """
    result = GoParser().validate_syntax(source)
    assert isinstance(result, tuple) and len(result) == 2
    ok, err = result
    assert isinstance(ok, bool)
    if ok:
        assert err is None
    else:
        assert isinstance(err, str)


@given(source=_arbitrary_source)
@h_settings(max_examples=100)
def test_rust_validate_syntax_never_raises(source: str) -> None:
    """**Validates: Requirements 2.9**

    Property: RustParser.validate_syntax never raises for any input.
    """
    result = RustParser().validate_syntax(source)
    assert isinstance(result, tuple) and len(result) == 2
    ok, err = result
    assert isinstance(ok, bool)
    if ok:
        assert err is None
    else:
        assert isinstance(err, str)


@given(source=_arbitrary_source)
@h_settings(max_examples=100)
def test_java_validate_syntax_never_raises(source: str) -> None:
    """**Validates: Requirements 2.9**

    Property: JavaParser.validate_syntax never raises for any input.
    """
    result = JavaParser().validate_syntax(source)
    assert isinstance(result, tuple) and len(result) == 2
    ok, err = result
    assert isinstance(ok, bool)
    if ok:
        assert err is None
    else:
        assert isinstance(err, str)
