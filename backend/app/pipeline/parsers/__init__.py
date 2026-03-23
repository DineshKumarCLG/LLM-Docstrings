"""Language-specific parser abstraction for the BCE stage.

Provides the LanguageParser abstract base class that each language adapter
must implement, plus the UnsupportedLanguageError for unknown languages.

Requirements: 2.1, 2.9
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas import FunctionInfo


class UnsupportedLanguageError(Exception):
    """Raised when a language has no registered parser."""

    def __init__(self, language: str) -> None:
        self.language = language
        super().__init__(
            f"Unsupported language: {language!r}. "
            f"No parser registered for this language."
        )


class LanguageParser(ABC):
    """Abstract parser that each language adapter must implement."""

    @abstractmethod
    def parse_functions(self, source_code: str) -> list[FunctionInfo]:
        """Extract all function/method definitions from source code.

        Returns FunctionInfo objects with name, signature, docstring,
        params, return_annotation, raise_statements, and mutation_patterns.
        """
        ...

    @abstractmethod
    def validate_syntax(self, source_code: str) -> tuple[bool, str | None]:
        """Check if source_code is syntactically valid.

        Returns (True, None) on success, (False, error_message) on failure.
        """
        ...

    @abstractmethod
    def get_language(self) -> str:
        """Return the language identifier (e.g. 'python', 'javascript')."""
        ...

    @abstractmethod
    def extract_comments(self, source_code: str) -> list[dict]:
        """Extract doc comments (JSDoc, Javadoc, Go doc, Rust doc) from source.

        Returns list of dicts with keys:
            text, start_line, end_line, associated_function.
        """
        ...
