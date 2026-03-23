"""Language-specific runtime abstraction for the RV stage.

Provides the RuntimeAdapter abstract base class that each runtime adapter
must implement, plus the UnsupportedRuntimeError for unknown languages.

Requirements: 4.1
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class UnsupportedRuntimeError(Exception):
    """Raised when a language has no registered runtime adapter."""

    def __init__(self, language: str) -> None:
        self.language = language
        super().__init__(
            f"Unsupported language: {language!r}. "
            f"No runtime adapter registered for this language."
        )


class RuntimeAdapter(ABC):
    """Abstract runtime adapter for RV test execution."""

    @abstractmethod
    def write_test_module(
        self, tests: list, source_code: str, tmpdir: str
    ) -> str:
        """Write test files to tmpdir and return the entry point path."""
        ...

    @abstractmethod
    def execute(
        self, test_path: str, timeout: int
    ) -> list[dict[str, Any]]:
        """Run the test suite and return per-test results.

        Each result dict has: nodeid, outcome, stdout, stderr, traceback, duration.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the runtime (e.g. node, javac, go, rustc) is installed."""
        ...
