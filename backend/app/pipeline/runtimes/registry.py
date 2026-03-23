"""Central registry mapping language identifiers to RuntimeAdapter implementations.

Requirements: 4.1
"""

from __future__ import annotations

from app.pipeline.runtimes import RuntimeAdapter, UnsupportedRuntimeError


class RuntimeRegistry:
    """Maps language strings to RuntimeAdapter classes."""

    _runtimes: dict[str, type[RuntimeAdapter]] = {}

    @classmethod
    def register(cls, language: str, runtime_cls: type[RuntimeAdapter]) -> None:
        """Register a runtime class for a given language identifier."""
        cls._runtimes[language] = runtime_cls

    @classmethod
    def get(cls, language: str) -> RuntimeAdapter:
        """Return a new RuntimeAdapter instance for *language*.

        Raises UnsupportedRuntimeError if no runtime is registered.
        """
        if language not in cls._runtimes:
            raise UnsupportedRuntimeError(language)
        return cls._runtimes[language]()

    @classmethod
    def supported_languages(cls) -> list[str]:
        """Return the list of currently registered language identifiers."""
        return list(cls._runtimes.keys())
