"""Tests for POST /api/analyses endpoint and input sanitization.

Covers:
- File upload and source_code paste acceptance
- Python syntax validation (ast.parse) with 422 on invalid code
- 1MB file size enforcement (413)
- Input sanitization (XSS: script tags, event handlers, javascript URIs)
- Analysis record creation with PENDING status
- 202 response with analysis_id

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 11.3
"""

from __future__ import annotations

import io
from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, StaticPool
from sqlalchemy.orm import Session, sessionmaker

from app.api.router import router, sanitize_source
from app.database import get_db
from app.models import Analysis, Base


# ---------------------------------------------------------------------------
# Shared in-memory engine (StaticPool keeps one connection across threads)
# ---------------------------------------------------------------------------

_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(_engine, "connect")
def _set_pragma(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


_TestingSession = sessionmaker(bind=_engine)


@pytest.fixture(autouse=True)
def _setup_tables():
    """Create tables before each test, drop after."""
    Base.metadata.create_all(_engine)
    yield
    Base.metadata.drop_all(_engine)


def _override_get_db():
    session = _TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    """FastAPI TestClient with DB dependency overridden and Celery mocked."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = _override_get_db
    # Reset the shared rate limiter so tests don't interfere
    from app.api.router import _analysis_rate_limiter
    _analysis_rate_limiter._requests.clear()

    with patch("app.pipeline.tasks.run_pipeline") as mock_task:
        mock_task.delay = MagicMock()
        with TestClient(app) as c:
            yield c


VALID_PYTHON = "def hello():\n    return 42\n"
INVALID_PYTHON = "def broken(\n"


# ---------------------------------------------------------------------------
# Sanitization unit tests (Requirement 11.3)
# ---------------------------------------------------------------------------


class TestSanitizeSource:
    def test_strips_script_tags(self):
        src = 'x = 1\n<script>alert("xss")</script>\ny = 2'
        result = sanitize_source(src)
        assert "<script" not in result
        assert "alert" not in result
        assert "x = 1" in result
        assert "y = 2" in result

    def test_strips_event_handlers(self):
        src = 'x = 1\nonclick="alert(1)"\ny = 2'
        result = sanitize_source(src)
        assert "onclick" not in result

    def test_strips_javascript_uri(self):
        src = "url = 'javascript: void(0)'"
        result = sanitize_source(src)
        assert "javascript:" not in result.lower()

    def test_preserves_normal_python(self):
        result = sanitize_source(VALID_PYTHON)
        assert result == VALID_PYTHON


# ---------------------------------------------------------------------------
# POST /api/analyses — source_code paste (Requirements 1.2, 1.3, 1.5, 1.6)
# ---------------------------------------------------------------------------


class TestCreateAnalysisSourceCode:
    def test_valid_python_returns_202(self, client):
        resp = client.post(
            "/api/analyses",
            data={"source_code": VALID_PYTHON, "llm_provider": "gpt-4o"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "analysis_id" in body

        # Verify DB record
        session = _TestingSession()
        analysis = session.query(Analysis).filter_by(id=body["analysis_id"]).first()
        assert analysis is not None
        assert analysis.status == "pending"
        assert analysis.llm_provider == "gpt-4o"
        session.close()

    def test_invalid_python_returns_422(self, client):
        resp = client.post(
            "/api/analyses",
            data={"source_code": INVALID_PYTHON},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "message" in detail
        assert "error" in detail

    def test_llm_provider_selection(self, client):
        resp = client.post(
            "/api/analyses",
            data={"source_code": VALID_PYTHON, "llm_provider": "claude-3-5-sonnet"},
        )
        assert resp.status_code == 202
        aid = resp.json()["analysis_id"]
        session = _TestingSession()
        analysis = session.query(Analysis).filter_by(id=aid).first()
        assert analysis.llm_provider == "claude-3-5-sonnet"
        session.close()

    def test_no_input_returns_400(self, client):
        resp = client.post("/api/analyses", data={})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/analyses — file upload (Requirements 1.1, 1.3, 1.4)
# ---------------------------------------------------------------------------


class TestCreateAnalysisFileUpload:
    def test_valid_file_returns_202(self, client):
        file_content = VALID_PYTHON.encode()
        resp = client.post(
            "/api/analyses",
            files={"file": ("test.py", io.BytesIO(file_content), "text/x-python")},
            data={"llm_provider": "gpt-4o"},
        )
        assert resp.status_code == 202
        aid = resp.json()["analysis_id"]
        session = _TestingSession()
        analysis = session.query(Analysis).filter_by(id=aid).first()
        assert analysis is not None
        assert analysis.filename == "test.py"
        session.close()

    def test_invalid_file_returns_422(self, client):
        resp = client.post(
            "/api/analyses",
            files={"file": ("bad.py", io.BytesIO(INVALID_PYTHON.encode()), "text/x-python")},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "message" in detail
        assert "error" in detail

    def test_oversized_file_returns_413(self, client):
        big_content = b"x = 1\n" * 200_000  # ~1.2 MB
        resp = client.post(
            "/api/analyses",
            files={"file": ("big.py", io.BytesIO(big_content), "text/x-python")},
        )
        assert resp.status_code == 413
        assert "File too large" in resp.json()["detail"]["error"]


# ---------------------------------------------------------------------------
# POST /api/analyses — Language detection (Requirements 1.1, 1.2, 10.1, 10.2)
# ---------------------------------------------------------------------------

VALID_JS = "function greet(name) {\n  return 'Hello ' + name;\n}\n"
VALID_TS = "function greet(name: string): string {\n  return 'Hello ' + name;\n}\n"
VALID_GO = "package main\n\nfunc main() {\n}\n"
VALID_JAVA = "public class Hello {\n  public static void main(String[] args) {}\n}\n"
VALID_RUST = "fn main() {\n    println!(\"hello\");\n}\n"
INVALID_JS = "function broken({\n"

_LLM = "gemini-3-flash-preview"


class TestLanguageDetectionSingleFile:
    """Test that single-file uploads detect language from file extension.

    Requirements: 1.1, 1.2, 8.1, 10.1
    """

    def test_js_file_detected_as_javascript(self, client):
        """Uploading a .js file sets language='javascript' on the Analysis record."""
        resp = client.post(
            "/api/analyses",
            files={"file": ("app.js", io.BytesIO(VALID_JS.encode()), "text/plain")},
            data={"llm_provider": _LLM},
        )
        assert resp.status_code == 202
        aid = resp.json()["analysis_id"]

        session = _TestingSession()
        analysis = session.query(Analysis).filter_by(id=aid).first()
        assert analysis is not None
        assert analysis.language == "javascript"
        session.close()

    def test_ts_file_detected_as_typescript(self, client):
        """Uploading a .ts file sets language='typescript' on the Analysis record."""
        resp = client.post(
            "/api/analyses",
            files={"file": ("utils.ts", io.BytesIO(VALID_TS.encode()), "text/plain")},
            data={"llm_provider": _LLM},
        )
        assert resp.status_code == 202
        aid = resp.json()["analysis_id"]

        session = _TestingSession()
        analysis = session.query(Analysis).filter_by(id=aid).first()
        assert analysis is not None
        assert analysis.language == "typescript"
        session.close()

    def test_go_file_detected_as_go(self, client):
        """Uploading a .go file sets language='go' on the Analysis record."""
        resp = client.post(
            "/api/analyses",
            files={"file": ("main.go", io.BytesIO(VALID_GO.encode()), "text/plain")},
            data={"llm_provider": _LLM},
        )
        assert resp.status_code == 202
        aid = resp.json()["analysis_id"]

        session = _TestingSession()
        analysis = session.query(Analysis).filter_by(id=aid).first()
        assert analysis is not None
        assert analysis.language == "go"
        session.close()

    def test_py_file_detected_as_python(self, client):
        """Uploading a .py file sets language='python' on the Analysis record."""
        resp = client.post(
            "/api/analyses",
            files={"file": ("test.py", io.BytesIO(VALID_PYTHON.encode()), "text/plain")},
            data={"llm_provider": _LLM},
        )
        assert resp.status_code == 202
        aid = resp.json()["analysis_id"]

        session = _TestingSession()
        analysis = session.query(Analysis).filter_by(id=aid).first()
        assert analysis is not None
        assert analysis.language == "python"
        session.close()


class TestBackwardCompatibility:
    """Test that existing Python workflows remain unchanged.

    Requirements: 10.1, 10.2
    """

    def test_code_paste_defaults_to_python(self, client):
        """source_code paste without a file defaults to language='python'."""
        resp = client.post(
            "/api/analyses",
            data={"source_code": VALID_PYTHON, "llm_provider": _LLM},
        )
        assert resp.status_code == 202
        aid = resp.json()["analysis_id"]

        session = _TestingSession()
        analysis = session.query(Analysis).filter_by(id=aid).first()
        assert analysis is not None
        assert analysis.language == "python"
        session.close()

    def test_python_file_upload_still_works(self, client):
        """Existing .py file upload flow is unchanged."""
        resp = client.post(
            "/api/analyses",
            files={"file": ("hello.py", io.BytesIO(VALID_PYTHON.encode()), "text/x-python")},
            data={"llm_provider": _LLM},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "analysis_id" in body

    def test_invalid_python_paste_still_returns_422(self, client):
        """Invalid Python code paste still returns 422 with error details."""
        resp = client.post(
            "/api/analyses",
            data={"source_code": INVALID_PYTHON},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "error" in detail

    def test_analysis_model_defaults_language_to_python(self):
        """Analysis records created without explicit language get 'python'.

        Simulates existing records after migration: the column default
        ensures all pre-existing rows have language='python'.

        Requirements: 10.4
        """
        session = _TestingSession()
        analysis = Analysis(
            source_code="x = 1\n",
            llm_provider="gemini-3-flash-preview",
        )
        session.add(analysis)
        session.commit()
        session.refresh(analysis)
        assert analysis.language == "python"
        session.close()

    def test_api_response_includes_language_field(self, client):
        """API response for code paste includes language='python'.

        Requirements: 10.5
        """
        resp = client.post(
            "/api/analyses",
            data={"source_code": VALID_PYTHON, "llm_provider": _LLM},
        )
        assert resp.status_code == 202
        aid = resp.json()["analysis_id"]

        # Fetch the analysis detail and verify language is in the response
        detail_resp = client.get(f"/api/analyses/{aid}")
        assert detail_resp.status_code == 200
        body = detail_resp.json()
        assert body["language"] == "python"


class TestSyntaxValidationPerLanguage:
    """Test that syntax validation uses the language-specific parser.

    Requirements: 8.1, 8.8, 10.2
    """

    def test_invalid_js_file_returns_422(self, client):
        """Uploading a .js file with invalid syntax returns 422."""
        resp = client.post(
            "/api/analyses",
            files={"file": ("bad.js", io.BytesIO(INVALID_JS.encode()), "text/plain")},
            data={"llm_provider": _LLM},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "error" in detail

    def test_valid_js_file_passes_validation(self, client):
        """Uploading a valid .js file passes syntax validation and returns 202."""
        resp = client.post(
            "/api/analyses",
            files={"file": ("app.js", io.BytesIO(VALID_JS.encode()), "text/plain")},
            data={"llm_provider": _LLM},
        )
        assert resp.status_code == 202

    def test_valid_rust_file_passes_validation(self, client):
        """Uploading a valid .rs file passes syntax validation and returns 202."""
        resp = client.post(
            "/api/analyses",
            files={"file": ("lib.rs", io.BytesIO(VALID_RUST.encode()), "text/plain")},
            data={"llm_provider": _LLM},
        )
        assert resp.status_code == 202
        aid = resp.json()["analysis_id"]

        session = _TestingSession()
        analysis = session.query(Analysis).filter_by(id=aid).first()
        assert analysis is not None
        assert analysis.language == "rust"
        session.close()
