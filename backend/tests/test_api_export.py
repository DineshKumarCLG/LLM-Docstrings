"""Tests for export endpoints and rate limiting middleware.

Covers:
- GET /api/analyses/{id}/export?format=json  (Requirement 7.1)
- GET /api/analyses/{id}/export?format=csv   (Requirement 7.2)
- GET /api/analyses/{id}/export?format=pdf   (Requirement 7.3)
- Content-Type and Content-Disposition headers (Requirement 7.4)
- Rate limiting on POST /api/analyses        (Requirement 11.4)

Requirements: 7.1, 7.2, 7.3, 7.4, 11.4
"""

from __future__ import annotations

import csv
import io
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, StaticPool
from sqlalchemy.orm import sessionmaker

from app.api.router import router, _analysis_rate_limiter
from app.database import get_db
from app.models import Analysis, Base, Claim, FunctionRecord, Violation


# ---------------------------------------------------------------------------
# In-memory DB setup (mirrors test_api_management.py)
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
    with patch("app.pipeline.tasks.run_pipeline") as mock_task:
        mock_task.delay = MagicMock()
        with TestClient(app) as c:
            yield c


def _seed_analysis(with_violations: bool = True) -> str:
    """Insert an Analysis with optional violations and return its id."""
    session = _TestingSession()
    analysis = Analysis(
        filename="example.py",
        source_code="def foo():\n    return 1\n",
        llm_provider="gpt-4o",
        status="complete",
        total_functions=1,
        total_claims=2,
        total_violations=1 if with_violations else 0,
        bcv_rate=0.5 if with_violations else 0.0,
    )
    session.add(analysis)
    session.flush()
    aid = analysis.id

    if with_violations:
        func = FunctionRecord(
            analysis_id=aid,
            name="foo",
            qualified_name="example.foo",
            source="def foo():\n    return 1\n",
            lineno=1,
            signature="def foo()",
            docstring="Returns 1.",
        )
        session.add(func)
        session.flush()

        claim = Claim(
            function_id=func.id,
            category="RSV",
            subject="return",
            predicate_object="returns 1",
            source_line=2,
            raw_text="Returns 1.",
        )
        session.add(claim)
        session.flush()

        violation = Violation(
            claim_id=claim.id,
            outcome="fail",
            test_code="def test_foo(): assert foo() == 2",
            traceback="AssertionError: assert 1 == 2",
            expected="2",
            actual="1",
            execution_time_ms=12.5,
        )
        session.add(violation)

    session.commit()
    session.close()
    return aid


# ---------------------------------------------------------------------------
# JSON export (Requirement 7.1)
# ---------------------------------------------------------------------------


class TestExportJSON:
    def test_json_export_returns_valid_json(self, client):
        aid = _seed_analysis()
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "json"})
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data["analysis_id"] == aid
        assert "violations" in data
        assert "category_breakdown" in data

    def test_json_content_type(self, client):
        aid = _seed_analysis()
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "json"})
        assert "application/json" in resp.headers["content-type"]

    def test_json_content_disposition(self, client):
        aid = _seed_analysis()
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "json"})
        cd = resp.headers["content-disposition"]
        assert "attachment" in cd
        assert f"analysis_{aid}.json" in cd

    def test_json_round_trip(self, client):
        """Property 16: JSON export round-trip produces equivalent data."""
        aid = _seed_analysis()
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "json"})
        data = json.loads(resp.content)
        # Re-serialize and deserialize
        reserialized = json.loads(json.dumps(data))
        assert reserialized == data

    def test_json_violation_fields(self, client):
        aid = _seed_analysis()
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "json"})
        data = json.loads(resp.content)
        v = data["violations"][0]
        assert v["function_name"] == "foo"
        assert v["category"] == "RSV"
        assert v["outcome"] == "fail"
        assert v["expected"] == "2"
        assert v["actual"] == "1"

    def test_json_empty_violations(self, client):
        aid = _seed_analysis(with_violations=False)
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "json"})
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data["violations"] == []


# ---------------------------------------------------------------------------
# CSV export (Requirement 7.2)
# ---------------------------------------------------------------------------


class TestExportCSV:
    def test_csv_content_type(self, client):
        aid = _seed_analysis()
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "csv"})
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    def test_csv_content_disposition(self, client):
        aid = _seed_analysis()
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "csv"})
        cd = resp.headers["content-disposition"]
        assert "attachment" in cd
        assert f"analysis_{aid}.csv" in cd

    def test_csv_header_row(self, client):
        aid = _seed_analysis()
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "csv"})
        reader = csv.reader(io.StringIO(resp.text))
        header = next(reader)
        assert header == [
            "function_name", "category", "claim_text",
            "outcome", "expected", "actual",
        ]

    def test_csv_row_count(self, client):
        """Property 17: N violations → N data rows + header."""
        aid = _seed_analysis()
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "csv"})
        reader = csv.reader(io.StringIO(resp.text))
        rows = list(reader)
        # 1 header + 1 violation row
        assert len(rows) == 2

    def test_csv_row_fields(self, client):
        aid = _seed_analysis()
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "csv"})
        reader = csv.reader(io.StringIO(resp.text))
        next(reader)  # skip header
        row = next(reader)
        assert row[0] == "foo"          # function_name
        assert row[1] == "RSV"          # category
        assert row[2] == "Returns 1."   # claim_text
        assert row[3] == "fail"         # outcome
        assert row[4] == "2"            # expected
        assert row[5] == "1"            # actual

    def test_csv_empty_violations(self, client):
        aid = _seed_analysis(with_violations=False)
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "csv"})
        assert resp.status_code == 200
        reader = csv.reader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 1  # header only


# ---------------------------------------------------------------------------
# PDF export (Requirement 7.3)
# ---------------------------------------------------------------------------


class TestExportPDF:
    def test_pdf_content_type(self, client):
        aid = _seed_analysis()
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "pdf"})
        assert resp.status_code == 200
        assert "application/pdf" in resp.headers["content-type"]

    def test_pdf_content_disposition(self, client):
        aid = _seed_analysis()
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "pdf"})
        cd = resp.headers["content-disposition"]
        assert "attachment" in cd
        assert f"analysis_{aid}.pdf" in cd

    def test_pdf_starts_with_header(self, client):
        aid = _seed_analysis()
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "pdf"})
        assert resp.content.startswith(b"%PDF-1.4")

    def test_pdf_ends_with_eof(self, client):
        aid = _seed_analysis()
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "pdf"})
        assert resp.content.rstrip().endswith(b"%%EOF")

    def test_pdf_empty_violations(self, client):
        aid = _seed_analysis(with_violations=False)
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "pdf"})
        assert resp.status_code == 200
        assert resp.content.startswith(b"%PDF-1.4")


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestExportErrors:
    def test_invalid_format_returns_400(self, client):
        aid = _seed_analysis()
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "xml"})
        assert resp.status_code == 400

    def test_not_found_returns_404(self, client):
        resp = client.get(
            "/api/analyses/nonexistent-id/export", params={"format": "json"}
        )
        assert resp.status_code == 404

    def test_format_case_insensitive(self, client):
        aid = _seed_analysis()
        resp = client.get(f"/api/analyses/{aid}/export", params={"format": "JSON"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Rate limiting (Requirement 11.4)
# ---------------------------------------------------------------------------


class TestRateLimiting:
    @pytest.fixture(autouse=True)
    def _reset_rate_limiter(self):
        """Reset the rate limiter state before each test."""
        _analysis_rate_limiter._requests.clear()
        yield
        _analysis_rate_limiter._requests.clear()

    def test_allows_requests_under_limit(self, client):
        resp = client.post(
            "/api/analyses",
            data={"source_code": "x = 1", "llm_provider": "gpt-4o"},
        )
        assert resp.status_code == 202

    def test_returns_429_when_limit_exceeded(self, client):
        for _ in range(10):
            resp = client.post(
                "/api/analyses",
                data={"source_code": "x = 1", "llm_provider": "gpt-4o"},
            )
            assert resp.status_code == 202

        # 11th request should be rate-limited
        resp = client.post(
            "/api/analyses",
            data={"source_code": "x = 1", "llm_provider": "gpt-4o"},
        )
        assert resp.status_code == 429
