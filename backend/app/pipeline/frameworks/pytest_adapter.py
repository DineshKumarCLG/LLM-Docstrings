"""Pytest adapter — TestFramework implementation for Python.

Wraps the existing pytest generation logic from the DTS synthesizer,
preserving backward compatibility while conforming to the TestFramework
abstract interface.

Requirements: 3.2
"""

from __future__ import annotations

import ast

from app.pipeline.frameworks import TestFramework
from app.pipeline.frameworks.registry import TestFrameworkRegistry


class PytestAdapter(TestFramework):
    """Pytest test framework adapter for Python test generation."""

    def get_framework_name(self) -> str:
        """Return ``'pytest'``."""
        return "pytest"

    def get_system_prompt_context(self) -> str:
        """Return pytest-specific LLM prompt context.

        Includes import conventions, assertion styles, and test structure
        guidance so the LLM generates idiomatic pytest code.
        """
        return (
            "Generate Python test code using the pytest framework.\n"
            "Import conventions:\n"
            "  - Use `import pytest` for fixtures and markers.\n"
            "  - Use `from copy import deepcopy` when testing side-effects.\n"
            "  - Import the module under test at the top of the file.\n"
            "Assertion style:\n"
            "  - Use plain `assert` statements (not unittest-style methods).\n"
            "  - Use `pytest.raises(ExceptionType)` for exception assertions.\n"
            "  - Use `pytest.approx()` for floating-point comparisons.\n"
            "Test structure:\n"
            "  - Name test functions with a `test_` prefix.\n"
            "  - Each test function should verify exactly one behavior.\n"
            "  - Use descriptive names: `test_<function>_<scenario>`.\n"
            "  - Output ONLY valid Python code."
        )

    def validate_test_syntax(self, test_code: str) -> bool:
        """Validate that *test_code* is syntactically valid Python.

        Uses ``ast.parse()`` — the same validation the existing DTS
        synthesizer applies to generated pytest output.
        """
        try:
            ast.parse(test_code)
        except SyntaxError:
            return False
        return True

    def get_test_template(self) -> str:
        """Return a minimal pytest test template."""
        return (
            "import pytest\n"
            "\n"
            "\n"
            "def test_example():\n"
            "    assert True\n"
        )


# Register with the TestFrameworkRegistry on import
TestFrameworkRegistry.register("python", PytestAdapter)
