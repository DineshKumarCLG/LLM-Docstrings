"""Tests for analysis management endpoints.

Covers:
- GET /api/analyses (list all)
- GET /api/analyses/{id} (single analysis)
- DELETE /api/analyses/{id} (cascade delete)
- POST /api/analyses/{id}/rerun
- GET /api/analyses/{id}/claims (grouped by function)
- GET /api/analyses/{id}/violations (full report with category breakdowns)

Requirements: 5.3, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, StaticPool
from sqlalchemy.orm import sessionmaker

from app.api.router import router
from app.database import get_db
from app.models import Analysis, Base, Claim, FunctionRecord, Violation


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
    with patch("app.pipeline.tasks.run_pipeline") as mock_task:
        mock_task.delay = MagicMock()
        with TestClient(app) as c:
            yield c


def _seed_analysis(
    status: str = "complete",
    filename: str = "test.py",
    llm_provider: str = "gpt-4o",
    with_functions: bool = False,
) -> str:
    """Insert an Analysis (and optionally children) and return its id."""
    session = _TestingSession()
    analysis = Analysis(
        filename=filename,
        source_code="def foo():\n    return 1\n",
        llm_provider=llm_provider,
        status=status,
        total_functions=1 if with_functions else 0,
        total_claims=2 if with_functions else 0,
        total_violations=1 if with_functions else 0,
        bcv_rate=0.5 if with_functions else 0.0,
    )
    session.add(analysis)
    session.flush()
    aid = analysis.id

    if with_functions:
        func = FunctionRecord(
            analysis_id=aid,
            name="foo",
            qualified_name="test.foo",
            source="def foo():\n    return 1\n",
            lineno=1,
            signature="def foo()",
            docstring="Returns 1.",
        )
        session.add(func)
        session.flush()

        claim1 = Claim(
            function_id=func.id,
            category="RSV",
            subject="return",
            predicate_object="returns 1",
            source_line=2,
            raw_text="Returns 1.",
        )
        claim2 = Claim(
            function_id=func.id,
            category="SEV",
            subject="data",
            predicate_object="does not modify input",
            source_line=3,
            raw_text="Does not modify input.",
        )
        session.add_all([claim1, claim2])
        session.flush()

        violation = Violation(
            claim_id=claim1.id,
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
# GET /api/analyses — list all (Requirement 6.1)
# ---------------------------------------------------------------------------


class TestListAnalyses:
    def test_empty_list(self, client):
        resp = client.get("/api/analyses")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_all_analyses(self, client):
        _seed_analysis(filename="a.py")
        _seed_analysis(filename="b.py")
        resp = client.get("/api/analyses")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_summary_fields_present(self, client):
        _seed_analysis(with_functions=True)
        resp = client.get("/api/analyses")
        item = resp.json()[0]
        for key in (
            "id", "status", "filename", "llmProvider",
            "totalFunctions", "totalClaims", "totalViolations",
            "bcvRate", "createdAt", "completedAt",
        ):
            assert key in item


# ---------------------------------------------------------------------------
# GET /api/analyses/{id} — single analysis (Requirements 5.3, 6.2)
# ---------------------------------------------------------------------------


class TestGetAnalysis:
    def test_returns_analysis(self, client):
        aid = _seed_analysis(with_functions=True)
        resp = client.get(f"/api/analyses/{aid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == aid
        assert data["status"] == "complete"
        assert data["totalClaims"] == 2

    def test_not_found(self, client):
        resp = client.get("/api/analyses/nonexistent-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/analyses/{id} — cascade delete (Requirement 6.5)
# ---------------------------------------------------------------------------


class TestDeleteAnalysis:
    def test_deletes_analysis(self, client):
        aid = _seed_analysis(with_functions=True)
        resp = client.delete(f"/api/analyses/{aid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == aid

        # Verify gone
        resp2 = client.get(f"/api/analyses/{aid}")
        assert resp2.status_code == 404

    def test_cascade_deletes_children(self, client):
        aid = _seed_analysis(with_functions=True)
        client.delete(f"/api/analyses/{aid}")

        session = _TestingSession()
        assert session.query(FunctionRecord).count() == 0
        assert session.query(Claim).count() == 0
        assert session.query(Violation).count() == 0
        session.close()

    def test_not_found(self, client):
        resp = client.delete("/api/analyses/nonexistent-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/analyses/{id}/rerun (Requirement 6.6)
# ---------------------------------------------------------------------------


class TestRerunAnalysis:
    def test_rerun_resets_status(self, client):
        aid = _seed_analysis(status="complete", with_functions=True)
        resp = client.post(f"/api/analyses/{aid}/rerun")
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "pending"
        assert data["analysis_id"] == aid

    def test_rerun_clears_children(self, client):
        aid = _seed_analysis(with_functions=True)
        client.post(f"/api/analyses/{aid}/rerun")

        session = _TestingSession()
        assert session.query(FunctionRecord).filter_by(analysis_id=aid).count() == 0
        session.close()

    def test_rerun_with_different_provider(self, client):
        aid = _seed_analysis(llm_provider="gpt-4o")
        resp = client.post(
            f"/api/analyses/{aid}/rerun",
            params={"llm_provider": "claude-3-5-sonnet"},
        )
        assert resp.status_code == 202

        session = _TestingSession()
        analysis = session.query(Analysis).filter_by(id=aid).first()
        assert analysis.llm_provider == "claude-3-5-sonnet"
        session.close()

    def test_rerun_not_found(self, client):
        resp = client.post("/api/analyses/nonexistent-id/rerun")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/analyses/{id}/claims — grouped by function (Requirement 6.3)
# ---------------------------------------------------------------------------


class TestGetClaims:
    def test_returns_claims_grouped(self, client):
        aid = _seed_analysis(with_functions=True)
        resp = client.get(f"/api/analyses/{aid}/claims")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        group = data[0]
        assert group["functionName"] == "foo"
        assert group["functionSignature"] == "def foo()"
        assert len(group["claims"]) == 2

    def test_claim_fields(self, client):
        aid = _seed_analysis(with_functions=True)
        resp = client.get(f"/api/analyses/{aid}/claims")
        claim = resp.json()[0]["claims"][0]
        for key in ("id", "category", "subject", "predicateObject", "sourceLine", "rawText"):
            assert key in claim

    def test_empty_when_no_functions(self, client):
        aid = _seed_analysis(with_functions=False)
        resp = client.get(f"/api/analyses/{aid}/claims")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_not_found(self, client):
        resp = client.get("/api/analyses/nonexistent-id/claims")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/analyses/{id}/violations — full report (Requirement 6.4)
# ---------------------------------------------------------------------------


class TestGetViolations:
    def test_returns_violation_report(self, client):
        aid = _seed_analysis(with_functions=True)
        resp = client.get(f"/api/analyses/{aid}/violations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["analysisId"] == aid
        assert "violations" in data
        assert "categoryBreakdown" in data
        assert "bcvRate" in data
        assert "totalFunctions" in data
        assert "totalClaims" in data

    def test_violation_details(self, client):
        aid = _seed_analysis(with_functions=True)
        resp = client.get(f"/api/analyses/{aid}/violations")
        violations = resp.json()["violations"]
        assert len(violations) == 1
        v = violations[0]
        assert v["outcome"] == "fail"
        assert v["claim"]["category"] == "RSV"
        assert v["expected"] == "2"
        assert v["actual"] == "1"

    def test_category_breakdown(self, client):
        aid = _seed_analysis(with_functions=True)
        resp = client.get(f"/api/analyses/{aid}/violations")
        breakdown = resp.json()["categoryBreakdown"]
        assert breakdown["RSV"] == 1

    def test_empty_violations(self, client):
        aid = _seed_analysis(with_functions=False)
        resp = client.get(f"/api/analyses/{aid}/violations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["violations"] == []
        assert data["categoryBreakdown"] == {}

    def test_not_found(self, client):
        resp = client.get("/api/analyses/nonexistent-id/violations")
        assert resp.status_code == 404
