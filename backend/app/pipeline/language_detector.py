"""Language detection utility for multi-language source file analysis.

Determines the programming language of a source file based on its file extension.
Falls back to Python for unknown extensions to preserve backward compatibility.

Requirements: 1.1, 1.2, 1.3, 1.4
"""

from __future__ import annotations

import os

from app.schemas import SupportedLanguage


class LanguageDetector:
    """Detects programming language from file extension."""

    EXTENSION_MAP: dict[str, SupportedLanguage] = {
        ".py": SupportedLanguage.PYTHON,
        ".js": SupportedLanguage.JAVASCRIPT,
        ".jsx": SupportedLanguage.JAVASCRIPT,
        ".ts": SupportedLanguage.TYPESCRIPT,
        ".tsx": SupportedLanguage.TYPESCRIPT,
        ".java": SupportedLanguage.JAVA,
        ".go": SupportedLanguage.GO,
        ".rs": SupportedLanguage.RUST,
    }

    @classmethod
    def detect(cls, filename: str, source_code: str | None = None) -> SupportedLanguage:
        """Return language identifier from filename extension.

        Falls back to SupportedLanguage.PYTHON for unknown extensions
        (backward compatibility).
        """
        _, ext = os.path.splitext(filename)
        return cls.EXTENSION_MAP.get(ext.lower(), SupportedLanguage.PYTHON)

    @classmethod
    def supported_extensions(cls) -> list[str]:
        """Return all supported file extensions."""
        return list(cls.EXTENSION_MAP.keys())
