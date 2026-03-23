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


# ---------------------------------------------------------------------------
# Tests for language registry lookups in pipeline orchestrator (Task 7.1)
# Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
# ---------------------------------------------------------------------------


class TestGetAnalysisLanguage:
    def test_reads_language_from_analysis(self, monkeypatch):
        """_get_analysis_language returns the language field from the Analysis record."""
        session = _make_session()
        aid = str(uuid.uuid4())
        analysis = Analysis(
            id=aid,
            source_code="console.log('hi')",
            llm_provider="gpt-4.1-mini",
            status="pending",
            language="javascript",
        )
        session.add(analysis)
        session.commit()

        import app.pipeline.tasks as tasks_mod

        monkeypatch.setattr(tasks_mod, "SessionLocal", lambda: session)

        result = tasks_mod._get_analysis_language(aid)
        assert result == "javascript"

    def test_defaults_to_python_for_missing_analysis(self, monkeypatch):
        """_get_analysis_language returns 'python' when analysis is not found."""
        session = _make_session()

        import app.pipeline.tasks as tasks_mod

        monkeypatch.setattr(tasks_mod, "SessionLocal", lambda: session)

        result = tasks_mod._get_analysis_language("nonexistent-id")
        assert result == "python"

    def test_reads_default_python_language(self, monkeypatch):
        """_get_analysis_language returns 'python' for records with default language."""
        session = _make_session()
        aid = _create_analysis(session)

        import app.pipeline.tasks as tasks_mod

        monkeypatch.setattr(tasks_mod, "SessionLocal", lambda: session)

        result = tasks_mod._get_analysis_language(aid)
        assert result == "python"


class TestFailAnalysisWithError:
    def test_sets_status_to_failed(self, monkeypatch):
        """_fail_analysis_with_error sets status to FAILED and completed_at."""
        session = _make_session()
        aid = _create_analysis(session)

        import app.pipeline.tasks as tasks_mod

        monkeypatch.setattr(tasks_mod, "SessionLocal", lambda: session)

        tasks_mod._fail_analysis_with_error(aid, "No parser for 'cobol'")

        analysis = session.query(Analysis).filter(Analysis.id == aid).first()
        assert analysis is not None
        assert analysis.status == "failed"
        assert analysis.completed_at is not None


class TestRegistryImports:
    def test_parser_registry_has_all_languages(self):
        """ParserRegistry has parsers for all six supported languages."""
        from app.pipeline.parsers.registry import ParserRegistry

        supported = ParserRegistry.supported_languages()
        for lang in ("python", "javascript", "typescript", "java", "go", "rust"):
            assert lang in supported, f"Missing parser for {lang}"

    def test_framework_registry_has_all_languages(self):
        """TestFrameworkRegistry has frameworks for all six supported languages."""
        from app.pipeline.frameworks.registry import TestFrameworkRegistry

        supported = TestFrameworkRegistry.supported_languages()
        for lang in ("python", "javascript", "typescript", "java", "go", "rust"):
            assert lang in supported, f"Missing framework for {lang}"

    def test_runtime_registry_has_all_languages(self):
        """RuntimeRegistry has runtimes for all six supported languages."""
        from app.pipeline.runtimes.registry import RuntimeRegistry

        supported = RuntimeRegistry.supported_languages()
        for lang in ("python", "javascript", "typescript", "java", "go", "rust"):
            assert lang in supported, f"Missing runtime for {lang}"

    def test_parser_registry_raises_for_unsupported(self):
        """ParserRegistry raises UnsupportedLanguageError for unknown language."""
        from app.pipeline.parsers.registry import ParserRegistry
        from app.pipeline.parsers import UnsupportedLanguageError

        import pytest

        with pytest.raises(UnsupportedLanguageError):
            ParserRegistry.get("cobol")

    def test_framework_registry_raises_for_unsupported(self):
        """TestFrameworkRegistry raises UnsupportedFrameworkError for unknown language."""
        from app.pipeline.frameworks.registry import TestFrameworkRegistry
        from app.pipeline.frameworks import UnsupportedFrameworkError

        import pytest

        with pytest.raises(UnsupportedFrameworkError):
            TestFrameworkRegistry.get("cobol")

    def test_runtime_registry_raises_for_unsupported(self):
        """RuntimeRegistry raises UnsupportedRuntimeError for unknown language."""
        from app.pipeline.runtimes.registry import RuntimeRegistry
        from app.pipeline.runtimes import UnsupportedRuntimeError

        import pytest

        with pytest.raises(UnsupportedRuntimeError):
            RuntimeRegistry.get("cobol")


# ---------------------------------------------------------------------------
# Integration tests for multi-language pipeline routing (Task 7.5)
# Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
# ---------------------------------------------------------------------------


class TestPipelineLanguageRouting:
    """Integration tests verifying run_pipeline routes to correct adapters."""

    def test_python_routes_to_python_adapters(self, monkeypatch):
        """run_pipeline reads language='python' and passes it to each stage.

        Verifies that run_bce, run_dts, and run_rv all receive
        language='python' when the Analysis record has language='python'.

        Requirements: 5.1, 5.2, 5.3, 5.4
        """
        session = _make_session()
        aid = _create_analysis(session, status="pending")

        import app.pipeline.tasks as tasks_mod

        monkeypatch.setattr(tasks_mod, "SessionLocal", lambda: session)

        # Track language arguments passed to each stage
        captured_languages = {}

        def fake_run_bce(analysis_id, source_code, language=None):
            captured_languages["bce"] = language
            return {"claim_schemas": []}

        def fake_run_dts(analysis_id, claim_schemas, llm_provider, language=None):
            captured_languages["dts"] = language
            return {"test_suites": []}

        def fake_run_rv(analysis_id, test_suites, source_code, language=None):
            captured_languages["rv"] = language
            return {"violation_reports": []}

        monkeypatch.setattr(tasks_mod, "run_bce", fake_run_bce)
        monkeypatch.setattr(tasks_mod, "run_dts", fake_run_dts)
        monkeypatch.setattr(tasks_mod, "run_rv", fake_run_rv)

        result = tasks_mod.run_pipeline(
            aid, "def foo(): pass", "gpt-4.1-mini",
        )

        assert result["status"] == "complete"
        assert captured_languages["bce"] == "python"
        assert captured_languages["dts"] == "python"
        assert captured_languages["rv"] == "python"

    def test_javascript_routes_to_javascript_adapters(self, monkeypatch):
        """run_pipeline reads language='javascript' and passes it to each stage.

        Requirements: 5.1, 5.2, 5.3, 5.4
        """
        session = _make_session()
        aid = str(uuid.uuid4())
        analysis = Analysis(
            id=aid,
            source_code="function foo() {}",
            llm_provider="gpt-4.1-mini",
            status="pending",
            language="javascript",
        )
        session.add(analysis)
        session.commit()

        import app.pipeline.tasks as tasks_mod

        monkeypatch.setattr(tasks_mod, "SessionLocal", lambda: session)

        captured_languages = {}

        def fake_run_bce(analysis_id, source_code, language=None):
            captured_languages["bce"] = language
            return {"claim_schemas": []}

        def fake_run_dts(analysis_id, claim_schemas, llm_provider, language=None):
            captured_languages["dts"] = language
            return {"test_suites": []}

        def fake_run_rv(analysis_id, test_suites, source_code, language=None):
            captured_languages["rv"] = language
            return {"violation_reports": []}

        monkeypatch.setattr(tasks_mod, "run_bce", fake_run_bce)
        monkeypatch.setattr(tasks_mod, "run_dts", fake_run_dts)
        monkeypatch.setattr(tasks_mod, "run_rv", fake_run_rv)

        result = tasks_mod.run_pipeline(
            aid, "function foo() {}", "gpt-4.1-mini",
        )

        assert result["status"] == "complete"
        assert captured_languages["bce"] == "javascript"
        assert captured_languages["dts"] == "javascript"
        assert captured_languages["rv"] == "javascript"

    def test_unsupported_language_fails_gracefully(self, monkeypatch):
        """run_pipeline fails with descriptive error for unsupported language.

        When the Analysis record has a language with no registered parser,
        the pipeline should set status to 'failed' and return an error.

        Requirements: 5.5
        """
        session = _make_session()
        aid = str(uuid.uuid4())
        analysis = Analysis(
            id=aid,
            source_code="COBOL code here",
            llm_provider="gpt-4.1-mini",
            status="pending",
            language="cobol",
        )
        session.add(analysis)
        session.commit()

        import app.pipeline.tasks as tasks_mod

        monkeypatch.setattr(tasks_mod, "SessionLocal", lambda: session)

        result = tasks_mod.run_pipeline(
            aid, "COBOL code here", "gpt-4.1-mini",
        )

        assert result["status"] == "failed"
        assert "error" in result
        assert "cobol" in result["error"].lower()

        # Verify the analysis record was updated to failed
        analysis = session.query(Analysis).filter(Analysis.id == aid).first()
        assert analysis.status == "failed"
        assert analysis.completed_at is not None

    def test_pipeline_status_transitions_with_language(self, monkeypatch):
        """run_pipeline goes through correct status transitions for a routed language.

        Requirements: 5.1, 5.2, 5.3, 5.4
        """
        session = _make_session()
        aid = _create_analysis(session, status="pending")

        import app.pipeline.tasks as tasks_mod

        monkeypatch.setattr(tasks_mod, "SessionLocal", lambda: session)

        status_history = []
        original_update = tasks_mod._update_status

        def tracking_update(analysis_id, status):
            status_history.append(status)
            original_update(analysis_id, status)

        monkeypatch.setattr(tasks_mod, "_update_status", tracking_update)

        def fake_run_bce(analysis_id, source_code, language=None):
            return {"claim_schemas": []}

        def fake_run_dts(analysis_id, claim_schemas, llm_provider, language=None):
            return {"test_suites": []}

        def fake_run_rv(analysis_id, test_suites, source_code, language=None):
            return {"violation_reports": []}

        monkeypatch.setattr(tasks_mod, "run_bce", fake_run_bce)
        monkeypatch.setattr(tasks_mod, "run_dts", fake_run_dts)
        monkeypatch.setattr(tasks_mod, "run_rv", fake_run_rv)

        result = tasks_mod.run_pipeline(
            aid, "def foo(): pass", "gpt-4.1-mini",
        )

        assert result["status"] == "complete"
        assert status_history == [
            "bce_running",
            "bce_complete",
            "dts_running",
            "dts_complete",
            "rv_running",
            "complete",
        ]

    def test_pipeline_resolves_parser_framework_runtime(self, monkeypatch):
        """run_pipeline resolves all three registries before calling stages.

        Verifies that ParserRegistry.get, TestFrameworkRegistry.get, and
        RuntimeRegistry.get are called with the correct language.

        Requirements: 5.2, 5.3, 5.4
        """
        session = _make_session()
        aid = str(uuid.uuid4())
        analysis = Analysis(
            id=aid,
            source_code="package main",
            llm_provider="gpt-4.1-mini",
            status="pending",
            language="go",
        )
        session.add(analysis)
        session.commit()

        import app.pipeline.tasks as tasks_mod

        monkeypatch.setattr(tasks_mod, "SessionLocal", lambda: session)

        registry_calls = []

        original_parser_get = tasks_mod.ParserRegistry.get
        original_framework_get = tasks_mod.TestFrameworkRegistry.get
        original_runtime_get = tasks_mod.RuntimeRegistry.get

        def tracking_parser_get(language):
            registry_calls.append(("parser", language))
            return original_parser_get(language)

        def tracking_framework_get(language):
            registry_calls.append(("framework", language))
            return original_framework_get(language)

        def tracking_runtime_get(language):
            registry_calls.append(("runtime", language))
            return original_runtime_get(language)

        monkeypatch.setattr(tasks_mod.ParserRegistry, "get", staticmethod(tracking_parser_get))
        monkeypatch.setattr(tasks_mod.TestFrameworkRegistry, "get", staticmethod(tracking_framework_get))
        monkeypatch.setattr(tasks_mod.RuntimeRegistry, "get", staticmethod(tracking_runtime_get))

        def fake_run_bce(analysis_id, source_code, language=None):
            return {"claim_schemas": []}

        def fake_run_dts(analysis_id, claim_schemas, llm_provider, language=None):
            return {"test_suites": []}

        def fake_run_rv(analysis_id, test_suites, source_code, language=None):
            return {"violation_reports": []}

        monkeypatch.setattr(tasks_mod, "run_bce", fake_run_bce)
        monkeypatch.setattr(tasks_mod, "run_dts", fake_run_dts)
        monkeypatch.setattr(tasks_mod, "run_rv", fake_run_rv)

        result = tasks_mod.run_pipeline(
            aid, "package main", "gpt-4.1-mini",
        )

        assert result["status"] == "complete"
        assert ("parser", "go") in registry_calls
        assert ("framework", "go") in registry_calls
        assert ("runtime", "go") in registry_calls
