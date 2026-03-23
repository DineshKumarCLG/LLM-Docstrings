"""Unit tests for TestFrameworkRegistry and all test framework adapters.

**Validates: Requirements 3.1, 3.7, 3.8**

Tests:
- TestFrameworkRegistry.get() returns correct adapter for each language
- TestFrameworkRegistry.get() raises UnsupportedFrameworkError for unknown language
- TestFrameworkRegistry.supported_languages() returns all registered languages
- Each adapter's get_framework_name() returns expected name
- Each adapter's get_system_prompt_context() returns non-empty string
- Each adapter's validate_test_syntax() returns True for valid test code and False for invalid
- Each adapter's get_test_template() returns non-empty string that passes its own validate_test_syntax()
"""

from __future__ import annotations

import pytest

# Force all framework adapters to register themselves
import app.pipeline.frameworks.pytest_adapter  # noqa: F401
import app.pipeline.frameworks.jest_adapter  # noqa: F401
import app.pipeline.frameworks.junit_adapter  # noqa: F401
import app.pipeline.frameworks.gotest_adapter  # noqa: F401
import app.pipeline.frameworks.cargotest_adapter  # noqa: F401

from app.pipeline.frameworks import TestFramework as _TestFrameworkABC, UnsupportedFrameworkError
from app.pipeline.frameworks.registry import TestFrameworkRegistry
from app.pipeline.frameworks.pytest_adapter import PytestAdapter
from app.pipeline.frameworks.jest_adapter import JestAdapter
from app.pipeline.frameworks.junit_adapter import JUnitAdapter
from app.pipeline.frameworks.gotest_adapter import GoTestAdapter
from app.pipeline.frameworks.cargotest_adapter import CargoTestAdapter


# ===========================================================================
# TestFrameworkRegistry tests  (Requirement 3.1)
# ===========================================================================


class TestTestFrameworkRegistry:
    """Tests for TestFrameworkRegistry lookup, registration, and error handling."""

    def test_get_returns_correct_adapter_for_python(self):
        assert isinstance(TestFrameworkRegistry.get("python"), PytestAdapter)

    def test_get_returns_correct_adapter_for_javascript(self):
        assert isinstance(TestFrameworkRegistry.get("javascript"), JestAdapter)

    def test_get_returns_correct_adapter_for_typescript(self):
        assert isinstance(TestFrameworkRegistry.get("typescript"), JestAdapter)

    def test_get_returns_correct_adapter_for_java(self):
        assert isinstance(TestFrameworkRegistry.get("java"), JUnitAdapter)

    def test_get_returns_correct_adapter_for_go(self):
        assert isinstance(TestFrameworkRegistry.get("go"), GoTestAdapter)

    def test_get_returns_correct_adapter_for_rust(self):
        assert isinstance(TestFrameworkRegistry.get("rust"), CargoTestAdapter)

    def test_get_raises_unsupported_framework_error_for_unknown(self):
        with pytest.raises(UnsupportedFrameworkError):
            TestFrameworkRegistry.get("cobol")

    def test_unsupported_error_message_contains_language(self):
        with pytest.raises(UnsupportedFrameworkError) as exc_info:
            TestFrameworkRegistry.get("brainfuck")
        assert "brainfuck" in str(exc_info.value)

    def test_unsupported_error_has_language_attribute(self):
        with pytest.raises(UnsupportedFrameworkError) as exc_info:
            TestFrameworkRegistry.get("ruby")
        assert exc_info.value.language == "ruby"

    def test_supported_languages_returns_all_registered(self):
        langs = set(TestFrameworkRegistry.supported_languages())
        assert {"python", "javascript", "typescript", "java", "go", "rust"}.issubset(langs)

    def test_supported_languages_returns_list(self):
        assert isinstance(TestFrameworkRegistry.supported_languages(), list)

    def test_get_returns_new_instance_each_call(self):
        a = TestFrameworkRegistry.get("python")
        b = TestFrameworkRegistry.get("python")
        assert a is not b

    def test_all_adapters_are_test_framework_subclasses(self):
        for lang in ("python", "javascript", "typescript", "java", "go", "rust"):
            adapter = TestFrameworkRegistry.get(lang)
            assert isinstance(adapter, _TestFrameworkABC)


# ===========================================================================
# PytestAdapter tests  (Requirement 3.2, 3.7, 3.8)
# ===========================================================================

_VALID_PYTEST = (
    "import pytest\n"
    "\n"
    "\n"
    "def test_addition():\n"
    "    assert 1 + 1 == 2\n"
)

_INVALID_PYTEST = "def test_broken(\n    assert True\n"


class TestPytestAdapter:
    adapter = PytestAdapter()

    def test_get_framework_name(self):
        assert self.adapter.get_framework_name() == "pytest"

    def test_get_system_prompt_context_non_empty(self):
        ctx = self.adapter.get_system_prompt_context()
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_get_system_prompt_context_mentions_pytest(self):
        ctx = self.adapter.get_system_prompt_context()
        assert "pytest" in ctx

    def test_validate_test_syntax_valid(self):
        assert self.adapter.validate_test_syntax(_VALID_PYTEST) is True

    def test_validate_test_syntax_invalid(self):
        assert self.adapter.validate_test_syntax(_INVALID_PYTEST) is False

    def test_get_test_template_non_empty(self):
        template = self.adapter.get_test_template()
        assert isinstance(template, str)
        assert len(template) > 0

    def test_get_test_template_passes_own_validation(self):
        template = self.adapter.get_test_template()
        assert self.adapter.validate_test_syntax(template) is True


# ===========================================================================
# JestAdapter tests  (Requirement 3.3, 3.7, 3.8)
# ===========================================================================

_VALID_JEST = (
    "import { describe, it, expect } from 'vitest';\n"
    "\n"
    "describe('math', () => {\n"
    "  it('should add', () => {\n"
    "    expect(1 + 1).toBe(2);\n"
    "  });\n"
    "});\n"
)

_INVALID_JEST_UNBALANCED = (
    "describe('math', () => {\n"
    "  it('should add', () => {\n"
    "    expect(1 + 1).toBe(2);\n"
    "  });\n"
    # missing closing });
)

_INVALID_JEST_NO_TEST_BLOCK = (
    "const x = 1;\n"
    "console.log(x);\n"
)


class TestJestAdapter:
    adapter = JestAdapter()

    def test_get_framework_name(self):
        assert self.adapter.get_framework_name() == "jest"

    def test_get_system_prompt_context_non_empty(self):
        ctx = self.adapter.get_system_prompt_context()
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_get_system_prompt_context_mentions_jest(self):
        ctx = self.adapter.get_system_prompt_context()
        assert "Jest" in ctx or "jest" in ctx.lower()

    def test_validate_test_syntax_valid(self):
        assert self.adapter.validate_test_syntax(_VALID_JEST) is True

    def test_validate_test_syntax_invalid_unbalanced(self):
        assert self.adapter.validate_test_syntax(_INVALID_JEST_UNBALANCED) is False

    def test_validate_test_syntax_invalid_no_test_block(self):
        assert self.adapter.validate_test_syntax(_INVALID_JEST_NO_TEST_BLOCK) is False

    def test_get_test_template_non_empty(self):
        template = self.adapter.get_test_template()
        assert isinstance(template, str)
        assert len(template) > 0

    def test_get_test_template_passes_own_validation(self):
        template = self.adapter.get_test_template()
        assert self.adapter.validate_test_syntax(template) is True


# ===========================================================================
# JUnitAdapter tests  (Requirement 3.4, 3.7, 3.8)
# ===========================================================================

_VALID_JUNIT = (
    "import org.junit.jupiter.api.Test;\n"
    "import static org.junit.jupiter.api.Assertions.*;\n"
    "\n"
    "class MathTest {\n"
    "\n"
    "    @Test\n"
    "    void testAddition() {\n"
    "        assertEquals(2, 1 + 1);\n"
    "    }\n"
    "}\n"
)

_INVALID_JUNIT_NO_TEST = (
    "class MathTest {\n"
    "    void testAddition() {\n"
    "        assertEquals(2, 1 + 1);\n"
    "    }\n"
    "}\n"
)

_INVALID_JUNIT_NO_CLASS = (
    "@Test\n"
    "void testAddition() {\n"
    "    assertEquals(2, 1 + 1);\n"
    "}\n"
)


class TestJUnitAdapter:
    adapter = JUnitAdapter()

    def test_get_framework_name(self):
        assert self.adapter.get_framework_name() == "junit"

    def test_get_system_prompt_context_non_empty(self):
        ctx = self.adapter.get_system_prompt_context()
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_get_system_prompt_context_mentions_junit(self):
        ctx = self.adapter.get_system_prompt_context()
        assert "JUnit" in ctx or "junit" in ctx.lower()

    def test_validate_test_syntax_valid(self):
        assert self.adapter.validate_test_syntax(_VALID_JUNIT) is True

    def test_validate_test_syntax_invalid_no_test_annotation(self):
        assert self.adapter.validate_test_syntax(_INVALID_JUNIT_NO_TEST) is False

    def test_validate_test_syntax_invalid_no_class(self):
        assert self.adapter.validate_test_syntax(_INVALID_JUNIT_NO_CLASS) is False

    def test_get_test_template_non_empty(self):
        template = self.adapter.get_test_template()
        assert isinstance(template, str)
        assert len(template) > 0

    def test_get_test_template_passes_own_validation(self):
        template = self.adapter.get_test_template()
        assert self.adapter.validate_test_syntax(template) is True


# ===========================================================================
# GoTestAdapter tests  (Requirement 3.5, 3.7, 3.8)
# ===========================================================================

_VALID_GO_TEST = (
    "package math\n"
    "\n"
    'import "testing"\n'
    "\n"
    "func TestAdd(t *testing.T) {\n"
    "\tgot := 1 + 1\n"
    "\twant := 2\n"
    "\tif got != want {\n"
    '\t\tt.Errorf("got %d, want %d", got, want)\n'
    "\t}\n"
    "}\n"
)

_INVALID_GO_NO_FUNC_TEST = (
    "package math\n"
    "\n"
    'import "testing"\n'
    "\n"
    "func Add(a, b int) int {\n"
    "\treturn a + b\n"
    "}\n"
)

_INVALID_GO_NO_TESTING_IMPORT = (
    "package math\n"
    "\n"
    "func TestAdd(t *testing.T) {\n"
    "\t// no testing import\n"
    "}\n"
)


class TestGoTestAdapter:
    adapter = GoTestAdapter()

    def test_get_framework_name(self):
        assert self.adapter.get_framework_name() == "go_test"

    def test_get_system_prompt_context_non_empty(self):
        ctx = self.adapter.get_system_prompt_context()
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_get_system_prompt_context_mentions_go(self):
        ctx = self.adapter.get_system_prompt_context()
        assert "Go" in ctx or "go" in ctx.lower()

    def test_validate_test_syntax_valid(self):
        assert self.adapter.validate_test_syntax(_VALID_GO_TEST) is True

    def test_validate_test_syntax_invalid_no_test_func(self):
        assert self.adapter.validate_test_syntax(_INVALID_GO_NO_FUNC_TEST) is False

    def test_validate_test_syntax_invalid_no_testing_import(self):
        assert self.adapter.validate_test_syntax(_INVALID_GO_NO_TESTING_IMPORT) is False

    def test_get_test_template_non_empty(self):
        template = self.adapter.get_test_template()
        assert isinstance(template, str)
        assert len(template) > 0

    def test_get_test_template_passes_own_validation(self):
        template = self.adapter.get_test_template()
        assert self.adapter.validate_test_syntax(template) is True


# ===========================================================================
# CargoTestAdapter tests  (Requirement 3.6, 3.7, 3.8)
# ===========================================================================

_VALID_CARGO_TEST = (
    "#[cfg(test)]\n"
    "mod tests {\n"
    "    use super::*;\n"
    "\n"
    "    #[test]\n"
    "    fn test_add() {\n"
    "        assert_eq!(1 + 1, 2);\n"
    "    }\n"
    "}\n"
)

_INVALID_CARGO_NO_TEST_ATTR = (
    "mod tests {\n"
    "    fn test_add() {\n"
    "        assert_eq!(1 + 1, 2);\n"
    "    }\n"
    "}\n"
)

_INVALID_CARGO_NO_FN = (
    "#[test]\n"
    "let x = 1;\n"
)


class TestCargoTestAdapter:
    adapter = CargoTestAdapter()

    def test_get_framework_name(self):
        assert self.adapter.get_framework_name() == "cargo_test"

    def test_get_system_prompt_context_non_empty(self):
        ctx = self.adapter.get_system_prompt_context()
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_get_system_prompt_context_mentions_rust(self):
        ctx = self.adapter.get_system_prompt_context()
        assert "Rust" in ctx or "rust" in ctx.lower()

    def test_validate_test_syntax_valid(self):
        assert self.adapter.validate_test_syntax(_VALID_CARGO_TEST) is True

    def test_validate_test_syntax_invalid_no_test_attr(self):
        assert self.adapter.validate_test_syntax(_INVALID_CARGO_NO_TEST_ATTR) is False

    def test_validate_test_syntax_invalid_no_fn(self):
        assert self.adapter.validate_test_syntax(_INVALID_CARGO_NO_FN) is False

    def test_get_test_template_non_empty(self):
        template = self.adapter.get_test_template()
        assert isinstance(template, str)
        assert len(template) > 0

    def test_get_test_template_passes_own_validation(self):
        template = self.adapter.get_test_template()
        assert self.adapter.validate_test_syntax(template) is True


# ===========================================================================
# Cross-adapter: validate_test_syntax and template contract  (Req 3.7, 3.8)
# ===========================================================================


class TestCrossAdapterContracts:
    """Cross-cutting tests that verify contracts hold for all adapters."""

    @pytest.mark.parametrize("language", [
        "python", "javascript", "typescript", "java", "go", "rust",
    ])
    def test_get_system_prompt_context_returns_non_empty_string(self, language):
        adapter = TestFrameworkRegistry.get(language)
        ctx = adapter.get_system_prompt_context()
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    @pytest.mark.parametrize("language", [
        "python", "javascript", "typescript", "java", "go", "rust",
    ])
    def test_get_test_template_passes_own_validation(self, language):
        adapter = TestFrameworkRegistry.get(language)
        template = adapter.get_test_template()
        assert isinstance(template, str)
        assert len(template) > 0
        assert adapter.validate_test_syntax(template) is True

    @pytest.mark.parametrize("language", [
        "python", "javascript", "typescript", "java", "go", "rust",
    ])
    def test_get_framework_name_returns_non_empty_string(self, language):
        adapter = TestFrameworkRegistry.get(language)
        name = adapter.get_framework_name()
        assert isinstance(name, str)
        assert len(name) > 0
