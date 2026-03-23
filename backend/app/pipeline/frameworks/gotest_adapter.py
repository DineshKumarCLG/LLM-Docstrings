"""Go test adapter — TestFramework implementation for Go.

Provides LLM prompt context, syntax validation, and test templates for
generating Go test code using the standard ``testing`` package.

Requirements: 3.5
"""

from __future__ import annotations

from app.pipeline.frameworks import TestFramework
from app.pipeline.frameworks.registry import TestFrameworkRegistry


class GoTestAdapter(TestFramework):
    """Go testing-package adapter for Go test generation."""

    def get_framework_name(self) -> str:
        """Return ``'go_test'``."""
        return "go_test"

    def get_system_prompt_context(self) -> str:
        """Return Go testing-specific LLM prompt context.

        Includes import conventions, assertion styles, and test structure
        guidance so the LLM generates idiomatic Go test code.
        """
        return (
            "Generate Go test code using the standard testing package.\n"
            "Import conventions:\n"
            '  - Use `import "testing"` for the testing package.\n'
            "  - Import the package under test (usually same package or `_test` suffix).\n"
            '  - Use `import "reflect"` when deep equality checks are needed.\n'
            "Assertion style:\n"
            '  - Use `t.Errorf("got %v, want %v", got, want)` for non-fatal assertion failures.\n'
            '  - Use `t.Fatalf("...")` for fatal assertion failures that should stop the test.\n'
            "  - Use `reflect.DeepEqual(got, want)` for deep equality comparisons.\n"
            "  - There are no built-in assertion helpers; use if-statements with t.Errorf/t.Fatalf.\n"
            "Test structure:\n"
            "  - Name test functions `func TestXxx(t *testing.T)` where Xxx starts with an uppercase letter.\n"
            "  - Use table-driven tests for multiple input/output scenarios:\n"
            "      tests := []struct{ name string; input int; want int }{ ... }\n"
            "      for _, tt := range tests { t.Run(tt.name, func(t *testing.T) { ... }) }\n"
            "  - Each test function should verify exactly one behavior.\n"
            "  - Use descriptive names: `TestFunctionName_Scenario`.\n"
            "  - Output ONLY valid Go code."
        )

    def validate_test_syntax(self, test_code: str) -> bool:
        """Validate that *test_code* looks like syntactically valid Go test code.

        Uses heuristic checks since we don't have a Go parser in Python:
        - Balanced braces, brackets, and parentheses
        - Presence of at least one ``func Test`` declaration
        - Presence of ``import "testing"`` or ``"testing"`` in imports
        """
        # Check balanced delimiters
        stack: list[str] = []
        matching = {")": "(", "]": "[", "}": "{"}
        in_string: str | None = None
        escape = False

        for ch in test_code:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if in_string:
                if ch == in_string:
                    in_string = None
                continue
            if ch in ('"', '`'):
                in_string = ch
                continue
            if ch in ("(", "[", "{"):
                stack.append(ch)
            elif ch in (")", "]", "}"):
                if not stack or stack[-1] != matching[ch]:
                    return False
                stack.pop()

        if stack:
            return False

        # Check for at least one test function declaration
        if "func Test" not in test_code:
            return False

        # Check for testing package import
        if '"testing"' not in test_code:
            return False

        return True

    def get_test_template(self) -> str:
        """Return a minimal Go test template."""
        return (
            "package example\n"
            "\n"
            'import "testing"\n'
            "\n"
            "func TestExample(t *testing.T) {\n"
            "\tgot := true\n"
            "\twant := true\n"
            "\tif got != want {\n"
            '\t\tt.Errorf("got %v, want %v", got, want)\n'
            "\t}\n"
            "}\n"
        )


# Register with the TestFrameworkRegistry on import
TestFrameworkRegistry.register("go", GoTestAdapter)
