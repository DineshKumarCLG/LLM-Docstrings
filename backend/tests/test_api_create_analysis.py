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
        assert "line" in detail
        assert "message" in detail

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
        assert detail["line"] is not None

    def test_oversized_file_returns_413(self, client):
        big_content = b"x = 1\n" * 200_000  # ~1.2 MB
        resp = client.post(
            "/api/analyses",
            files={"file": ("big.py", io.BytesIO(big_content), "text/x-python")},
        )
        assert resp.status_code == 413
        assert "File too large" in resp.json()["detail"]["error"]
