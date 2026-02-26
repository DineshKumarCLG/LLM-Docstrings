"""Unit tests for the Celery pipeline task orchestration.

Tests the helper functions (_update_status, _store_bce_results, _store_rv_results)
and verifies the task structure (retry config, status transitions).

Requirements: 5.1, 5.2, 5.4, 5.5
"""

from __future__ import annotations

import uuid

from sqlalchemy import create_engine, event, select, func
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Analysis,
    Base,
    Claim as ClaimModel,
    FunctionRecord,
    Violation,
)
from app.schemas import AnalysisStatus


def _make_session() -> Session:
    """Create a fresh in-memory SQLite session with all tables."""
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _create_analysis(session: Session, status: str = "pending") -> str:
    """Insert a minimal Analysis and return its id."""
    aid = str(uuid.uuid4())
    analysis = Analysis(
        id=aid,
        source_code="def foo(): pass",
        llm_provider="gpt-4.1-mini",
        status=status,
    )
    session.add(analysis)
    session.commit()
    return aid


# ---------------------------------------------------------------------------
# Tests for _update_status
# ---------------------------------------------------------------------------


class TestUpdateStatus:
    def test_updates_status_to_bce_running(self, monkeypatch):
        """Status transitions from pending to bce_running."""
        session = _make_session()
        aid = _create_analysis(session)

        # Monkeypatch SessionLocal to return our in-memory session
        import app.pipeline.tasks as tasks_mod

        monkeypatch.setattr(tasks_mod, "SessionLocal", lambda: session)

        tasks_mod._update_status(aid, AnalysisStatus.BCE_RUNNING.value)

        analysis = session.query(Analysis).filter(Analysis.id == aid).first()
        assert analysis is not None
        assert analysis.status == "bce_running"
        assert analysis.completed_at is None

    def test_sets_completed_at_on_complete(self, monkeypatch):
        """completed_at is set when status becomes COMPLETE."""
        session = _make_session()
        aid = _create_analysis(session)

        import app.pipeline.tasks as tasks_mod

        monkeypatch.setattr(tasks_mod, "SessionLocal", lambda: session)

        tasks_mod._update_status(aid, AnalysisStatus.COMPLETE.value)

        analysis = session.query(Analysis).filter(Analysis.id == aid).first()
        assert analysis is not None
        assert analysis.status == "complete"
        assert analysis.completed_at is not None

    def test_sets_completed_at_on_failed(self, monkeypatch):
        """completed_at is set when status becomes FAILED."""
        session = _make_session()
        aid = _create_analysis(session)

        import app.pipeline.tasks as tasks_mod

        monkeypatch.setattr(tasks_mod, "SessionLocal", lambda: session)

        tasks_mod._update_status(aid, AnalysisStatus.FAILED.value)

        analysis = session.query(Analysis).filter(Analysis.id == aid).first()
        assert analysis is not None
        assert analysis.status == "failed"
        assert analysis.completed_at is not None

    def test_nonexistent_analysis_does_not_raise(self, monkeypatch):
        """Updating a missing analysis logs an error but doesn't crash."""
        session = _make_session()

        import app.pipeline.tasks as tasks_mod

        monkeypatch.setattr(tasks_mod, "SessionLocal", lambda: session)

        # Should not raise
        tasks_mod._update_status("nonexistent-id", "bce_running")


# ---------------------------------------------------------------------------
# Tests for _store_bce_results
# ---------------------------------------------------------------------------


class TestStoreBceResults:
    def test_stores_functions_and_claims(self, monkeypatch):
        """BCE results are persisted as FunctionRecords and Claims."""
        session = _make_session()
        aid = _create_analysis(session)

        import app.pipeline.tasks as tasks_mod

        monkeypatch.setattr(tasks_mod, "SessionLocal", lambda: session)

        claim_schemas = [
            {
                "function": {
                    "name": "foo",
                    "qualified_name": "mod.foo",
                    "source": "def foo(): pass",
                    "lineno": 1,
                    "signature": "def foo()",
                    "docstring": "Does stuff.",
                    "params": [],
                    "return_annotation": None,
                    "raise_statements": [],
                    "mutation_patterns": [],
                },
                "claims": [
                    {
                        "category": "RSV",
                        "subject": "return",
                        "predicate_object": "returns int",
                        "conditionality": None,
                        "source_line": 2,
                        "raw_text": "Returns int.",
                    },
                    {
                        "category": "ECV",
                        "subject": "ValueError",
                        "predicate_object": "raises ValueError",
                        "conditionality": "if empty",
                        "source_line": 3,
                        "raw_text": "Raises ValueError if empty.",
                    },
                ],
            }
        ]

        tasks_mod._store_bce_results(aid, claim_schemas)

        # Verify FunctionRecord
        frs = session.query(FunctionRecord).filter(
            FunctionRecord.analysis_id == aid
        ).all()
        assert len(frs) == 1
        assert frs[0].name == "foo"

        # Verify Claims
        claims = session.query(ClaimModel).filter(
            ClaimModel.function_id == frs[0].id
        ).all()
        assert len(claims) == 2
        categories = {c.category for c in claims}
        assert categories == {"RSV", "ECV"}

        # Verify analysis summary updated
        analysis = session.query(Analysis).filter(Analysis.id == aid).first()
        assert analysis.total_functions == 1
        assert analysis.total_claims == 2


# ---------------------------------------------------------------------------
# Tests for _store_rv_results
# ---------------------------------------------------------------------------


class TestStoreRvResults:
    def test_stores_violations_and_updates_bcv_rate(self, monkeypatch):
        """RV results are persisted and bcv_rate is computed."""
        session = _make_session()
        aid = _create_analysis(session)

        import app.pipeline.tasks as tasks_mod

        monkeypatch.setattr(tasks_mod, "SessionLocal", lambda: session)

        # First store BCE results so we have claims to link violations to
        claim_schemas = [
            {
                "function": {
                    "name": "bar",
                    "qualified_name": "mod.bar",
                    "source": "def bar(): pass",
                    "lineno": 1,
                    "signature": "def bar()",
                    "docstring": "Bar doc.",
                    "params": [],
                    "return_annotation": None,
                    "raise_statements": [],
                    "mutation_patterns": [],
                },
                "claims": [
                    {
                        "category": "RSV",
                        "subject": "return",
                        "predicate_object": "returns list",
                        "conditionality": None,
                        "source_line": 2,
                        "raw_text": "Returns list.",
                    },
                ],
            }
        ]
        tasks_mod._store_bce_results(aid, claim_schemas)

        # Now store RV results
        violation_reports = [
            {
                "function_name": "bar",
                "pass_count": 0,
                "fail_count": 1,
                "violations": [
                    {
                        "claim": {
                            "category": "RSV",
                            "subject": "return",
                            "predicate_object": "returns list",
                            "raw_text": "Returns list.",
                        },
                        "outcome": "fail",
                        "test_code": "def test_bar(): assert False",
                        "stdout": "",
                        "stderr": "",
                        "traceback": "AssertionError",
                        "expected": "list",
                        "actual": "None",
                        "execution_time_ms": 12.5,
                    }
                ],
            }
        ]
        tasks_mod._store_rv_results(aid, violation_reports)

        # Verify Violation record
        violations = session.query(Violation).all()
        assert len(violations) == 1
        assert violations[0].outcome == "fail"
        assert violations[0].test_code == "def test_bar(): assert False"

        # Verify analysis summary
        analysis = session.query(Analysis).filter(Analysis.id == aid).first()
        assert analysis.total_violations == 1
        assert analysis.bcv_rate == 1.0  # 1 fail / (0 pass + 1 fail)


# ---------------------------------------------------------------------------
# Tests for Celery task configuration
# ---------------------------------------------------------------------------


class TestCeleryTaskConfig:
    def test_celery_app_name(self):
        """Celery app is named 'veridoc'."""
        from app.pipeline.tasks import app

        assert app.main == "veridoc"

    def test_task_registered(self):
        """All four tasks are registered with the Celery app."""
        from app.pipeline.tasks import run_bce, run_dts, run_rv, run_pipeline

        assert run_bce.name is not None
        assert run_dts.name is not None
        assert run_rv.name is not None
        assert run_pipeline.name is not None

    def test_tasks_have_max_retries(self):
        """Each task is configured with max_retries=3."""
        from app.pipeline.tasks import run_bce, run_dts, run_rv, run_pipeline

        assert run_bce.max_retries == 3
        assert run_dts.max_retries == 3
        assert run_rv.max_retries == 3
        assert run_pipeline.max_retries == 3

    def test_backend_uses_redis_db_1(self):
        """Result backend URL uses Redis db 1."""
        from app.pipeline.tasks import app

        backend_url = app.conf.result_backend
        assert backend_url.endswith("/1")
