"""Cargo test adapter — TestFramework implementation for Rust.

Provides LLM prompt context, syntax validation, and test templates for
generating Rust test code using ``#[test]`` attributes and the built-in
test harness.

Requirements: 3.6
"""

from __future__ import annotations

from app.pipeline.frameworks import TestFramework
from app.pipeline.frameworks.registry import TestFrameworkRegistry


class CargoTestAdapter(TestFramework):
    """Cargo test adapter for Rust test generation."""

    def get_framework_name(self) -> str:
        """Return ``'cargo_test'``."""
        return "cargo_test"

    def get_system_prompt_context(self) -> str:
        """Return Rust testing-specific LLM prompt context.

        Includes module conventions, assertion macros, test attributes, and
        structure guidance so the LLM generates idiomatic Rust test code.
        """
        return (
            "Generate Rust test code using the built-in test framework.\n"
            "Module conventions:\n"
            "  - Wrap tests in a `#[cfg(test)]` module: `#[cfg(test)] mod tests { ... }`.\n"
            "  - Use `use super::*;` inside the test module to import items from the parent module.\n"
            "Test attributes:\n"
            "  - Annotate each test function with `#[test]`.\n"
            "  - Use `#[should_panic]` or `#[should_panic(expected = \"message\")]` for panic assertions.\n"
            "  - Use `#[ignore]` to skip tests that are slow or require external resources.\n"
            "Assertion style:\n"
            "  - Use `assert!(expression)` for boolean assertions.\n"
            "  - Use `assert_eq!(left, right)` for equality assertions.\n"
            "  - Use `assert_ne!(left, right)` for inequality assertions.\n"
            "  - Add custom messages: `assert_eq!(got, want, \"expected {}, got {}\", want, got)`.\n"
            "Test structure:\n"
            "  - Name test functions with a `test_` prefix: `fn test_<function>_<scenario>()`.\n"
            "  - Each test function should verify exactly one behavior.\n"
            "  - Use descriptive names: `fn test_add_positive_numbers()`.\n"
            "  - Output ONLY valid Rust code."
        )

    def validate_test_syntax(self, test_code: str) -> bool:
        """Validate that *test_code* looks like syntactically valid Rust test code.

        Uses heuristic checks since we don't have a Rust parser in Python:
        - Balanced braces, brackets, and parentheses
        - Presence of at least one ``#[test]`` attribute
        - Presence of at least one ``fn`` keyword
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
            if ch in ('"',):
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

        # Check for at least one #[test] attribute
        if "#[test]" not in test_code:
            return False

        # Check for at least one fn keyword
        if "fn " not in test_code:
            return False

        return True

    def get_test_template(self) -> str:
        """Return a minimal Rust test template."""
        return (
            "#[cfg(test)]\n"
            "mod tests {\n"
            "    use super::*;\n"
            "\n"
            "    #[test]\n"
            "    fn test_example() {\n"
            "        assert_eq!(true, true);\n"
            "    }\n"
            "}\n"
        )


# Register with the TestFrameworkRegistry on import
TestFrameworkRegistry.register("rust", CargoTestAdapter)
