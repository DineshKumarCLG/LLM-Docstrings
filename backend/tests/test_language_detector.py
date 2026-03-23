"""Unit and property tests for LanguageDetector.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4**

Tests:
- All supported extension mappings return the correct SupportedLanguage
- Unknown extensions fall back to "python"
- Detection is independent per file in a batch
- Property: detect always returns a valid SupportedLanguage member
- Property: supported_extensions covers every key in EXTENSION_MAP
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from app.pipeline.language_detector import LanguageDetector
from app.schemas import SupportedLanguage


# ---------------------------------------------------------------------------
# Unit tests — extension mapping correctness (Requirement 1.3)
# ---------------------------------------------------------------------------


class TestExtensionMappings:
    """WHEN a user uploads a file with a supported extension,
    THE LanguageDetector SHALL return the correct SupportedLanguage identifier.
    (Requirement 1.1)
    """

    @pytest.mark.parametrize(
        "filename, expected",
        [
            ("main.py", SupportedLanguage.PYTHON),
            ("app.js", SupportedLanguage.JAVASCRIPT),
            ("component.jsx", SupportedLanguage.JAVASCRIPT),
            ("index.ts", SupportedLanguage.TYPESCRIPT),
            ("component.tsx", SupportedLanguage.TYPESCRIPT),
            ("Main.java", SupportedLanguage.JAVA),
            ("server.go", SupportedLanguage.GO),
            ("lib.rs", SupportedLanguage.RUST),
        ],
    )
    def test_supported_extension_returns_correct_language(self, filename, expected):
        assert LanguageDetector.detect(filename) == expected

    @pytest.mark.parametrize(
        "filename, expected",
        [
            ("MAIN.PY", SupportedLanguage.PYTHON),
            ("App.JS", SupportedLanguage.JAVASCRIPT),
            ("Index.TS", SupportedLanguage.TYPESCRIPT),
            ("Server.GO", SupportedLanguage.GO),
        ],
    )
    def test_case_insensitive_extension(self, filename, expected):
        assert LanguageDetector.detect(filename) == expected

    def test_path_with_directories(self):
        assert LanguageDetector.detect("src/utils/helper.ts") == SupportedLanguage.TYPESCRIPT

    def test_dotfile_with_extension(self):
        assert LanguageDetector.detect(".hidden.py") == SupportedLanguage.PYTHON


# ---------------------------------------------------------------------------
# Unit tests — unknown extension fallback (Requirement 1.2)
# ---------------------------------------------------------------------------


class TestUnknownExtensionFallback:
    """WHEN a user uploads a file with an unrecognized extension,
    THE LanguageDetector SHALL fall back to "python" for backward compatibility.
    (Requirement 1.2)
    """

    @pytest.mark.parametrize(
        "filename",
        [
            "readme.md",
            "config.yaml",
            "data.csv",
            "Makefile",
            "script.sh",
            "notes.txt",
            "noextension",
        ],
    )
    def test_unknown_extension_falls_back_to_python(self, filename):
        assert LanguageDetector.detect(filename) == SupportedLanguage.PYTHON

    def test_source_code_param_does_not_affect_detection(self):
        result = LanguageDetector.detect("unknown.xyz", source_code="console.log('hi');")
        assert result == SupportedLanguage.PYTHON


# ---------------------------------------------------------------------------
# Unit tests — batch independence (Requirement 1.4)
# ---------------------------------------------------------------------------


class TestBatchIndependence:
    """WHEN detecting language for a batch upload,
    THE LanguageDetector SHALL detect the language independently for each file.
    (Requirement 1.4)
    """

    def test_batch_detection_independent_per_file(self):
        filenames = [
            "app.py",
            "index.js",
            "main.ts",
            "Server.java",
            "handler.go",
            "lib.rs",
            "readme.md",
        ]
        expected = [
            SupportedLanguage.PYTHON,
            SupportedLanguage.JAVASCRIPT,
            SupportedLanguage.TYPESCRIPT,
            SupportedLanguage.JAVA,
            SupportedLanguage.GO,
            SupportedLanguage.RUST,
            SupportedLanguage.PYTHON,  # fallback
        ]
        results = [LanguageDetector.detect(f) for f in filenames]
        assert results == expected

    def test_repeated_detection_is_stable(self):
        """Calling detect multiple times on the same file yields the same result."""
        for _ in range(5):
            assert LanguageDetector.detect("app.ts") == SupportedLanguage.TYPESCRIPT


# ---------------------------------------------------------------------------
# Unit tests — supported_extensions (Requirement 1.3)
# ---------------------------------------------------------------------------


class TestSupportedExtensions:
    def test_returns_all_mapped_extensions(self):
        extensions = LanguageDetector.supported_extensions()
        assert set(extensions) == {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs"}

    def test_returns_list(self):
        assert isinstance(LanguageDetector.supported_extensions(), list)


# ---------------------------------------------------------------------------
# Property-based tests (hypothesis)
# ---------------------------------------------------------------------------


# Strategy: generate filenames with known supported extensions
_supported_ext = st.sampled_from(list(LanguageDetector.EXTENSION_MAP.keys()))
_basename = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
    min_size=1,
    max_size=20,
)


@given(basename=_basename, ext=_supported_ext)
@h_settings(max_examples=200)
def test_detect_always_returns_valid_supported_language(basename, ext):
    """**Validates: Requirements 1.1**

    Property: For any filename with a supported extension,
    detect returns a valid SupportedLanguage member.
    """
    result = LanguageDetector.detect(basename + ext)
    assert isinstance(result, SupportedLanguage)
    assert result == LanguageDetector.EXTENSION_MAP[ext]


# Strategy: generate filenames with arbitrary (likely unsupported) extensions
_arbitrary_ext = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=8,
).map(lambda s: "." + s)


@given(basename=_basename, ext=_arbitrary_ext)
@h_settings(max_examples=200)
def test_detect_always_returns_valid_enum_member(basename, ext):
    """**Validates: Requirements 1.2**

    Property: For any filename (even with unknown extensions),
    detect always returns a valid SupportedLanguage member (never raises).
    """
    result = LanguageDetector.detect(basename + ext)
    assert isinstance(result, SupportedLanguage)
