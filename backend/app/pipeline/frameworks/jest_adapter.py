"""Jest/Vitest adapter — TestFramework implementation for JavaScript/TypeScript.

Provides LLM prompt context, syntax validation, and test templates for
generating Jest or Vitest test code from JavaScript and TypeScript source.

Requirements: 3.3
"""

from __future__ import annotations

from app.pipeline.frameworks import TestFramework
from app.pipeline.frameworks.registry import TestFrameworkRegistry


class JestAdapter(TestFramework):
    """Jest/Vitest test framework adapter for JS/TS test generation."""

    def get_framework_name(self) -> str:
        """Return ``'jest'``."""
        return "jest"

    def get_system_prompt_context(self) -> str:
        """Return jest/vitest-specific LLM prompt context.

        Includes import conventions, assertion styles, and test structure
        guidance so the LLM generates idiomatic Jest/Vitest code.
        """
        return (
            "Generate JavaScript/TypeScript test code using Jest or Vitest.\n"
            "Import conventions:\n"
            "  - Use `import { describe, it, expect } from 'vitest';` or rely on Jest globals.\n"
            "  - Import the module under test using ES module syntax: `import { fn } from './module';`\n"
            "  - For CommonJS modules use: `const { fn } = require('./module');`\n"
            "Assertion style:\n"
            "  - Use `expect(value).toBe(expected)` for strict equality.\n"
            "  - Use `expect(value).toEqual(expected)` for deep equality.\n"
            "  - Use `expect(() => fn()).toThrow(ErrorType)` for exception assertions.\n"
            "  - Use `expect(value).toBeCloseTo(expected, numDigits)` for floating-point comparisons.\n"
            "  - Use `expect(value).toBeTruthy()` / `expect(value).toBeFalsy()` for boolean checks.\n"
            "Test structure:\n"
            "  - Wrap related tests in `describe('functionName', () => { ... })`.\n"
            "  - Use `it('should <behavior>', () => { ... })` or `test('description', () => { ... })` for individual tests.\n"
            "  - Each test should verify exactly one behavior.\n"
            "  - Use descriptive names: `it('should return X when given Y')`.\n"
            "  - Output ONLY valid JavaScript or TypeScript code."
        )

    def validate_test_syntax(self, test_code: str) -> bool:
        """Validate that *test_code* looks like syntactically valid JS/TS test code.

        Uses basic heuristic checks since we don't have a JS parser in Python:
        - Balanced braces, brackets, and parentheses
        - Presence of at least one describe/it/test block
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
            if ch in ("'", '"', "`"):
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

        # Check for at least one test block keyword
        test_keywords = ("describe(", "it(", "test(")
        if not any(kw in test_code for kw in test_keywords):
            return False

        return True

    def get_test_template(self) -> str:
        """Return a minimal Jest/Vitest test template."""
        return (
            "import { describe, it, expect } from 'vitest';\n"
            "\n"
            "describe('example', () => {\n"
            "  it('should pass', () => {\n"
            "    expect(true).toBe(true);\n"
            "  });\n"
            "});\n"
        )


# Register with the TestFrameworkRegistry for both JS and TS on import
TestFrameworkRegistry.register("javascript", JestAdapter)
TestFrameworkRegistry.register("typescript", JestAdapter)
