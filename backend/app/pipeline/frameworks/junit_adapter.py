"""JUnit 5 adapter — TestFramework implementation for Java.

Provides LLM prompt context, syntax validation, and test templates for
generating JUnit 5 test code from Java source.

Requirements: 3.4
"""

from __future__ import annotations

from app.pipeline.frameworks import TestFramework
from app.pipeline.frameworks.registry import TestFrameworkRegistry


class JUnitAdapter(TestFramework):
    """JUnit 5 test framework adapter for Java test generation."""

    def get_framework_name(self) -> str:
        """Return ``'junit'``."""
        return "junit"

    def get_system_prompt_context(self) -> str:
        """Return JUnit 5-specific LLM prompt context.

        Includes import conventions, assertion styles, and test structure
        guidance so the LLM generates idiomatic JUnit 5 code.
        """
        return (
            "Generate Java test code using JUnit 5 (Jupiter).\n"
            "Import conventions:\n"
            "  - Use `import org.junit.jupiter.api.Test;` for the @Test annotation.\n"
            "  - Use `import static org.junit.jupiter.api.Assertions.*;` for assertion methods.\n"
            "  - Use `import org.junit.jupiter.api.BeforeEach;` and `import org.junit.jupiter.api.AfterEach;` for setup/teardown.\n"
            "  - Use `import org.junit.jupiter.api.DisplayName;` for readable test names.\n"
            "  - Import the class under test at the top of the file.\n"
            "Assertion style:\n"
            "  - Use `assertEquals(expected, actual)` for equality checks.\n"
            "  - Use `assertTrue(condition)` / `assertFalse(condition)` for boolean checks.\n"
            "  - Use `assertThrows(ExceptionType.class, () -> { ... })` for exception assertions.\n"
            "  - Use `assertNull(value)` / `assertNotNull(value)` for null checks.\n"
            "  - Use `assertArrayEquals(expected, actual)` for array comparisons.\n"
            "Test structure:\n"
            "  - Annotate test methods with `@Test`.\n"
            "  - Test methods must be `void` and take no arguments.\n"
            "  - Use descriptive method names: `test<Method>_<scenario>`.\n"
            "  - Wrap tests in a public class named `<ClassUnderTest>Test`.\n"
            "  - Each test method should verify exactly one behavior.\n"
            "  - Output ONLY valid Java code."
        )

    def validate_test_syntax(self, test_code: str) -> bool:
        """Validate that *test_code* looks like syntactically valid JUnit 5 test code.

        Uses heuristic checks since we don't have a Java parser in Python:
        - Balanced braces, brackets, and parentheses
        - Presence of at least one @Test annotation
        - Presence of a class declaration
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
            if ch in ("'", '"'):
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

        # Check for at least one @Test annotation
        if "@Test" not in test_code:
            return False

        # Check for a class declaration
        if "class " not in test_code:
            return False

        return True

    def get_test_template(self) -> str:
        """Return a minimal JUnit 5 test template."""
        return (
            "import org.junit.jupiter.api.Test;\n"
            "import static org.junit.jupiter.api.Assertions.*;\n"
            "\n"
            "class ExampleTest {\n"
            "\n"
            "    @Test\n"
            "    void testExample() {\n"
            "        assertTrue(true);\n"
            "    }\n"
            "}\n"
        )


# Register with the TestFrameworkRegistry on import
TestFrameworkRegistry.register("java", JUnitAdapter)
