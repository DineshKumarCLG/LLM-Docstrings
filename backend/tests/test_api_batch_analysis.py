"""Tests for the updated batch analysis endpoint.

Covers:
- POST /api/analyses/batch with multipart FormData (multiple files)
- POST /api/analyses/batch with ZIP archive (backward compatibility)
- Language detection per file
- Syntax validation per file with errors array
- Max file count and total size enforcement
- Analysis records created with correct language field

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8
"""

from __future__ import annotations

import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, StaticPool
from sqlalchemy.orm import sessionmaker

from app.api.router import router
from app.database import get_db
from app.models import Analysis, Base


# ---------------------------------------------------------------------------
# In-memory DB setup
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


def _make_zip(file_map: dict[str, str]) -> bytes:
    """Create a ZIP archive in memory from a {filename: content} dict."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in file_map.items():
            zf.writestr(name, content)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Multipart FormData tests (multiple files)
# ---------------------------------------------------------------------------


class TestMultipartBatchUpload:
    """Test batch endpoint with multipart FormData containing multiple files."""

    def test_mixed_language_files(self, client):
        """Multiple files of different languages are accepted and processed."""
        resp = client.post(
            "/api/analyses/batch",
            files=[
                ("files", ("hello.py", b"x = 1\n", "text/plain")),
                ("files", ("app.js", b"const x = 1;\n", "text/plain")),
                ("files", ("main.go", b"package main\n", "text/plain")),
            ],
            data={"llm_provider": "gemma-4-31b-it"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["total"] == 3
        assert len(body["analysis_ids"]) == 3
        assert "batch_id" in body
        assert body["errors"] == []

    def test_language_detection_per_file(self, client):
        """Each file gets the correct language assigned."""
        resp = client.post(
            "/api/analyses/batch",
            files=[
                ("files", ("hello.py", b"x = 1\n", "text/plain")),
                ("files", ("app.ts", b"const x: number = 1;\n", "text/plain")),
            ],
            data={"llm_provider": "gemma-4-31b-it"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["total"] == 2

        # Verify language on Analysis records
        session = _TestingSession()
        analyses = session.query(Analysis).order_by(Analysis.filename).all()
        langs = {a.filename: a.language for a in analyses}
        assert langs["app.ts"] == "typescript"
        assert langs["hello.py"] == "python"
        session.close()

    def test_syntax_validation_errors_reported(self, client):
        """Files with syntax errors are skipped and reported in errors array."""
        resp = client.post(
            "/api/analyses/batch",
            files=[
                ("files", ("good.py", b"x = 1\n", "text/plain")),
                ("files", ("bad.py", b"def foo(\n", "text/plain")),
            ],
            data={"llm_provider": "gemma-4-31b-it"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["total"] == 1
        assert len(body["errors"]) == 1
        assert body["errors"][0]["filename"] == "bad.py"
        assert "error" in body["errors"][0]

    def test_max_files_enforced(self, client):
        """More than 50 files triggers a 400 error."""
        too_many = [
            ("files", (f"file_{i}.py", b"x = 1\n", "text/plain"))
            for i in range(51)
        ]
        resp = client.post(
            "/api/analyses/batch",
            files=too_many,
            data={"llm_provider": "gemma-4-31b-it"},
        )
        assert resp.status_code == 400
        assert "50" in resp.json()["detail"]["error"]

    def test_max_total_size_enforced(self, client):
        """Total size exceeding 20 MB triggers a 413 error."""
        # Create two files that together exceed 20 MB
        big_content = b"x" * (11 * 1024 * 1024)  # 11 MB each
        resp = client.post(
            "/api/analyses/batch",
            files=[
                ("files", ("big1.py", big_content, "text/plain")),
                ("files", ("big2.py", big_content, "text/plain")),
            ],
            data={"llm_provider": "gemma-4-31b-it"},
        )
        assert resp.status_code == 413

    def test_all_files_invalid_returns_422(self, client):
        """When all files fail validation, returns 422 with errors."""
        resp = client.post(
            "/api/analyses/batch",
            files=[
                ("files", ("bad1.py", b"def foo(\n", "text/plain")),
                ("files", ("bad2.py", b"class :\n", "text/plain")),
            ],
            data={"llm_provider": "gemma-4-31b-it"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "errors" in body["detail"]
        assert len(body["detail"]["errors"]) == 2

    def test_pipeline_enqueued_per_file(self, client):
        """Each valid file gets a pipeline task enqueued."""
        with patch("app.pipeline.tasks.run_pipeline") as mock_task:
            mock_task.delay = MagicMock()
            resp = client.post(
                "/api/analyses/batch",
                files=[
                    ("files", ("a.py", b"x = 1\n", "text/plain")),
                    ("files", ("b.py", b"y = 2\n", "text/plain")),
                ],
                data={"llm_provider": "gemma-4-31b-it"},
            )
            assert resp.status_code == 202
            assert mock_task.delay.call_count == 2


# ---------------------------------------------------------------------------
# ZIP upload tests (backward compatibility)
# ---------------------------------------------------------------------------


class TestZipBatchUpload:
    """Test batch endpoint with ZIP archive upload (backward compatible)."""

    def test_zip_with_python_files(self, client):
        """ZIP with .py files still works (backward compatibility)."""
        zip_bytes = _make_zip({
            "src/main.py": "x = 1\n",
            "src/utils.py": "y = 2\n",
        })
        resp = client.post(
            "/api/analyses/batch",
            files=[("file", ("project.zip", zip_bytes, "application/zip"))],
            data={"llm_provider": "gemma-4-31b-it"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["total"] == 2
        assert "errors" in body

    def test_zip_with_mixed_languages(self, client):
        """ZIP with multi-language files detects language per file."""
        zip_bytes = _make_zip({
            "main.py": "x = 1\n",
            "app.js": "const x = 1;\n",
            "lib.rs": "fn main() {}\n",
        })
        resp = client.post(
            "/api/analyses/batch",
            files=[("file", ("project.zip", zip_bytes, "application/zip"))],
            data={"llm_provider": "gemma-4-31b-it"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["total"] == 3

        session = _TestingSession()
        analyses = session.query(Analysis).order_by(Analysis.filename).all()
        langs = {a.filename: a.language for a in analyses}
        assert langs["main.py"] == "python"
        assert langs["app.js"] == "javascript"
        assert langs["lib.rs"] == "rust"
        session.close()

    def test_zip_skips_pycache_and_hidden(self, client):
        """ZIP extraction skips __pycache__ and hidden directories."""
        zip_bytes = _make_zip({
            "src/main.py": "x = 1\n",
            "__pycache__/cached.py": "y = 2\n",
            "src/__pycache__/other.py": "z = 3\n",
        })
        resp = client.post(
            "/api/analyses/batch",
            files=[("file", ("project.zip", zip_bytes, "application/zip"))],
            data={"llm_provider": "gemma-4-31b-it"},
        )
        assert resp.status_code == 202
        assert resp.json()["total"] == 1

    def test_zip_no_supported_files(self, client):
        """ZIP with no supported source files returns 400."""
        zip_bytes = _make_zip({
            "readme.md": "# Hello\n",
            "data.csv": "a,b,c\n",
        })
        resp = client.post(
            "/api/analyses/batch",
            files=[("file", ("project.zip", zip_bytes, "application/zip"))],
            data={"llm_provider": "gemma-4-31b-it"},
        )
        assert resp.status_code == 400

    def test_zip_too_large(self, client):
        """ZIP exceeding 20 MB returns 413."""
        big_content = "x" * (21 * 1024 * 1024)
        zip_bytes = _make_zip({"big.py": big_content})
        resp = client.post(
            "/api/analyses/batch",
            files=[("file", ("project.zip", zip_bytes, "application/zip"))],
            data={"llm_provider": "gemma-4-31b-it"},
        )
        assert resp.status_code == 413

    def test_invalid_zip(self, client):
        """Corrupt ZIP returns 400."""
        resp = client.post(
            "/api/analyses/batch",
            files=[("file", ("project.zip", b"not a zip", "application/zip"))],
            data={"llm_provider": "gemma-4-31b-it"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestBatchEdgeCases:
    """Edge cases for the batch endpoint."""

    def test_no_files_provided(self, client):
        """No file or files provided returns 400."""
        resp = client.post(
            "/api/analyses/batch",
            data={"llm_provider": "gemma-4-31b-it"},
        )
        assert resp.status_code == 400 or resp.status_code == 422

    def test_errors_array_in_response(self, client):
        """Response always includes an errors array."""
        resp = client.post(
            "/api/analyses/batch",
            files=[
                ("files", ("good.py", b"x = 1\n", "text/plain")),
            ],
            data={"llm_provider": "gemma-4-31b-it"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "errors" in body
        assert isinstance(body["errors"], list)

    def test_analysis_records_have_batch_id(self, client):
        """Analysis records store the batch_id in config."""
        resp = client.post(
            "/api/analyses/batch",
            files=[
                ("files", ("hello.py", b"x = 1\n", "text/plain")),
            ],
            data={"llm_provider": "gemma-4-31b-it"},
        )
        assert resp.status_code == 202
        batch_id = resp.json()["batch_id"]

        session = _TestingSession()
        analysis = session.query(Analysis).first()
        assert analysis.config["batch_id"] == batch_id
        session.close()
