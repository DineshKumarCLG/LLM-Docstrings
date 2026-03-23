"""Central registry mapping language identifiers to TestFramework implementations.

Requirements: 3.1
"""

from __future__ import annotations

from app.pipeline.frameworks import TestFramework, UnsupportedFrameworkError


class TestFrameworkRegistry:
    """Maps language strings to TestFramework classes."""

    _frameworks: dict[str, type[TestFramework]] = {}

    @classmethod
    def register(cls, language: str, framework_cls: type[TestFramework]) -> None:
        """Register a framework class for a given language identifier."""
        cls._frameworks[language] = framework_cls

    @classmethod
    def get(cls, language: str) -> TestFramework:
        """Return a new TestFramework instance for *language*.

        Raises UnsupportedFrameworkError if no framework is registered.
        """
        if language not in cls._frameworks:
            raise UnsupportedFrameworkError(language)
        return cls._frameworks[language]()

    @classmethod
    def supported_languages(cls) -> list[str]:
        """Return the list of currently registered language identifiers."""
        return list(cls._frameworks.keys())
