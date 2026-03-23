"""Language-specific test framework abstraction for the DTS stage.

Provides the TestFramework abstract base class that each framework adapter
must implement, plus the UnsupportedFrameworkError for unknown languages.

Requirements: 3.1
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class UnsupportedFrameworkError(Exception):
    """Raised when a language has no registered test framework."""

    def __init__(self, language: str) -> None:
        self.language = language
        super().__init__(
            f"Unsupported language: {language!r}. "
            f"No test framework registered for this language."
        )


class TestFramework(ABC):
    """Abstract test framework adapter for DTS test generation."""

    @abstractmethod
    def get_framework_name(self) -> str:
        """Return framework name (e.g. 'pytest', 'jest', 'junit')."""
        ...

    @abstractmethod
    def get_system_prompt_context(self) -> str:
        """Return framework-specific context for the LLM system prompt.

        Includes import conventions, assertion styles, test structure, etc.
        """
        ...

    @abstractmethod
    def validate_test_syntax(self, test_code: str) -> bool:
        """Check if generated test code is syntactically valid."""
        ...

    @abstractmethod
    def get_test_template(self) -> str:
        """Return a minimal test template for the framework."""
        ...
