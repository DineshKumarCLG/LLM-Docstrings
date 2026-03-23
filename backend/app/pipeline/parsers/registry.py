"""Central registry mapping language identifiers to LanguageParser implementations.

Requirements: 2.1, 2.9
"""

from __future__ import annotations

from app.pipeline.parsers import LanguageParser, UnsupportedLanguageError


class ParserRegistry:
    """Maps language strings to LanguageParser classes."""

    _parsers: dict[str, type[LanguageParser]] = {}

    @classmethod
    def register(cls, language: str, parser_cls: type[LanguageParser]) -> None:
        """Register a parser class for a given language identifier."""
        cls._parsers[language] = parser_cls

    @classmethod
    def get(cls, language: str) -> LanguageParser:
        """Return a new LanguageParser instance for *language*.

        Raises UnsupportedLanguageError if no parser is registered.
        """
        if language not in cls._parsers:
            raise UnsupportedLanguageError(language)
        return cls._parsers[language]()

    @classmethod
    def supported_languages(cls) -> list[str]:
        """Return the list of currently registered language identifiers."""
        return list(cls._parsers.keys())
