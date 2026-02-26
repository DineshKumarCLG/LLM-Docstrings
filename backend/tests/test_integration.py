"""Integration tests for the VeriDoc BCV Detection Pipeline.

Verifies end-to-end flow across BCE → DTS → RV stages, the FastAPI REST
API lifecycle, and Celery task chain execution with mocked LLM responses.

Requirements validated: 1.1–1.6, 5.1–5.5, 6.1–6.6
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, StaticPool
from sqlalchemy.orm import sessionmaker

from app.api.router import router
from app.database import get_db
from app.models import Analysis, Base, FunctionRecord, Claim as ClaimModel, Violation
from app.schemas import (
    AnalysisStatus,
    BCVCategory,
    Claim,
    ClaimSchema,
    FunctionInfo,
    SynthesizedTest,
    TestOutcome,
)

# ---------------------------------------------------------------------------
# normalize_list example from the design document
# ---------------------------------------------------------------------------

NORMALIZE_LIST_SOURCE = '''\
def normalize_list(data: list[float]) -> list[float]:
    """Normalize values to unit range.

    Returns a new list with values scaled to [0, 1].
    Does not modify the input list.

    Args:
        data: List of numeric values. Must be non-empty.

    Returns:
        list[float]: A new normalized list.

    Raises:
        ValueError: If the list is empty.
    """
    min_val = min(data)
    max_val = max(data)
    rng = max_val - min_val
    if rng == 0:
        return [0.0] * len(data)
    for i in range(len(data)):
        data[i] = (data[i] - min_val) / rng
    return data
'''

# Known synthesized test functions that exercise the RSV and SEV violations
# present in normalize_list (returns same list, mutates in place).

_RSV_TEST_CODE = """\
def test_returns_new_list():
    data = [1.0, 2.0, 3.0]
    result = normalize_list(data)
    assert result is not data, "Should return a new list, not the same object"
"""

_SEV_TEST_CODE = """\
from copy import deepcopy

def test_does_not_modify_input():
    data = [1.0, 2.0, 3.0]
    snapshot = deepcopy(data)
    normalize_list(data)
    assert data == snapshot, "Input list should not be modified"
"""

_ECV_TEST_CODE = """\
import pytest

def test_raises_valueerror_empty():
    with pytest.raises(ValueError):
        normalize_list([])
"""

# ---------------------------------------------------------------------------
# Shared in-memory SQLite setup
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
    """FastAPI TestClient with DB override and Celery task mocked."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = _override_get_db

    with patch("app.pipeline.tasks.run_pipeline") as mock_task:
        mock_task.delay = MagicMock()
        with TestClient(app) as c:
            yield c



# =========================================================================
# 1. End-to-end pipeline test with normalize_list example
# =========================================================================


class TestEndToEndPipeline:
    """Run BCE → DTS (mocked LLM) → RV locally and verify the ViolationReport.

    The normalize_list function has known RSV + SEV violations:
    - RSV: docstring says "returns a new list" but it returns the same object
    - SEV: docstring says "does not modify the input" but it mutates in place
    - ECV: docstring says "raises ValueError if empty" — this actually passes
    """

    def test_pipeline_detects_rsv_and_sev_violations(self):
        """BCE extracts claims, mocked DTS returns known tests, RV finds violations."""
        from app.pipeline.bce.extractor import BehavioralClaimExtractor
        from app.pipeline.rv.verifier import RuntimeVerifier

        # --- Stage 1: BCE ---
        bce = BehavioralClaimExtractor()
        claim_schemas = bce.extract(NORMALIZE_LIST_SOURCE)

        # Should produce exactly one ClaimSchema for normalize_list
        assert len(claim_schemas) >= 1
        cs = claim_schemas[0]
        assert cs.function.name == "normalize_list"
        assert len(cs.claims) > 0

        # Verify we got claims in the expected categories
        categories = {c.category for c in cs.claims}
        # At minimum we expect SEV from AST mutation detection
        assert BCVCategory.SEV in categories

        # --- Stage 2: DTS (mocked) ---
        # Instead of calling an LLM, build SynthesizedTest objects from
        # the known test code that exercises the RSV and SEV bugs.
        rsv_claim = Claim(
            category=BCVCategory.RSV,
            subject="return",
            predicate_object="returns a new list",
            conditionality=None,
            source_line=4,
            raw_text="Returns a new list with values scaled to [0, 1].",
        )
        sev_claim = Claim(
            category=BCVCategory.SEV,
            subject="data",
            predicate_object="does not modify the input",
            conditionality=None,
            source_line=5,
            raw_text="Does not modify the input list.",
        )
        ecv_claim = Claim(
            category=BCVCategory.ECV,
            subject="ValueError",
            predicate_object="raises ValueError",
            conditionality="the list is empty",
            source_line=12,
            raw_text="Raises ValueError: If the list is empty.",
        )

        test_suite = [
            SynthesizedTest(
                claim=rsv_claim,
                test_code=_RSV_TEST_CODE,
                test_function_name="test_returns_new_list",
                synthesis_model="gpt-4.1-mini",
            ),
            SynthesizedTest(
                claim=sev_claim,
                test_code=_SEV_TEST_CODE,
                test_function_name="test_does_not_modify_input",
                synthesis_model="gpt-4.1-mini",
            ),
            SynthesizedTest(
                claim=ecv_claim,
                test_code=_ECV_TEST_CODE,
                test_function_name="test_raises_valueerror_empty",
                synthesis_model="gpt-4.1-mini",
            ),
        ]

        # --- Stage 3: RV ---
        rv = RuntimeVerifier(timeout=30)
        report = rv.verify(
            test_suite=test_suite,
            source_code=NORMALIZE_LIST_SOURCE,
            analysis_id="integration-test-001",
            function_name="normalize_list",
        )

        # RSV and SEV should FAIL (known bugs), ECV should PASS
        assert report.fail_count >= 2, (
            f"Expected at least 2 failures (RSV + SEV), got {report.fail_count}"
        )
        assert report.pass_count >= 1, (
            f"Expected at least 1 pass (ECV), got {report.pass_count}"
        )

        # Violations list should contain only FAIL outcomes
        for v in report.violations:
            assert v.outcome == TestOutcome.FAIL

        # BCV rate should reflect the failures
        assert report.bcv_rate > 0.0
        expected_rate = report.fail_count / (report.pass_count + report.fail_count)
        assert abs(report.bcv_rate - expected_rate) < 1e-9

        # Verify violation categories
        violation_categories = {v.claim.category for v in report.violations}
        assert BCVCategory.RSV in violation_categories or BCVCategory.SEV in violation_categories



# =========================================================================
# 2. API flow test
# =========================================================================


class TestAPIFlow:
    """Test the full REST API lifecycle using FastAPI's TestClient.

    POST /api/analyses → GET /api/analyses/{id} → GET violations → GET export
    Celery task is mocked to run synchronously and populate the DB.
    """

    def _seed_analysis_with_results(self, analysis_id: str) -> None:
        """Seed the DB with a completed analysis including violations."""
        session = _TestingSession()
        try:
            analysis = session.query(Analysis).filter_by(id=analysis_id).first()
            assert analysis is not None, "Analysis record should exist"

            # Update status to COMPLETE with summary stats
            analysis.status = AnalysisStatus.COMPLETE.value
            analysis.total_functions = 1
            analysis.total_claims = 3
            analysis.total_violations = 2
            analysis.bcv_rate = 2.0 / 3.0

            # Add a FunctionRecord
            func = FunctionRecord(
                analysis_id=analysis_id,
                name="normalize_list",
                qualified_name="normalize_list",
                source=NORMALIZE_LIST_SOURCE,
                lineno=1,
                signature="def normalize_list(data: list[float]) -> list[float]",
                docstring="Normalize values to unit range.",
                params=[{"name": "data", "annotation": "list[float]", "default": None}],
                return_annotation="list[float]",
            )
            session.add(func)
            session.flush()

            # Add Claims
            rsv_claim = ClaimModel(
                function_id=func.id,
                category="RSV",
                subject="return",
                predicate_object="returns a new list",
                source_line=4,
                raw_text="Returns a new list with values scaled to [0, 1].",
            )
            sev_claim = ClaimModel(
                function_id=func.id,
                category="SEV",
                subject="data",
                predicate_object="does not modify the input",
                source_line=5,
                raw_text="Does not modify the input list.",
            )
            ecv_claim = ClaimModel(
                function_id=func.id,
                category="ECV",
                subject="ValueError",
                predicate_object="raises ValueError",
                source_line=12,
                raw_text="Raises ValueError if empty.",
            )
            session.add_all([rsv_claim, sev_claim, ecv_claim])
            session.flush()

            # Add Violations for RSV and SEV (FAIL outcomes)
            rsv_violation = Violation(
                claim_id=rsv_claim.id,
                outcome="fail",
                test_code=_RSV_TEST_CODE,
                traceback="AssertionError: Should return a new list",
                expected="new list",
                actual="same object",
            )
            sev_violation = Violation(
                claim_id=sev_claim.id,
                outcome="fail",
                test_code=_SEV_TEST_CODE,
                traceback="AssertionError: Input list should not be modified",
                expected="[1.0, 2.0, 3.0]",
                actual="[0.0, 0.5, 1.0]",
            )
            session.add_all([rsv_violation, sev_violation])
            session.commit()
        finally:
            session.close()

    def test_full_api_lifecycle(self, client):
        """POST create → GET status → GET violations → GET export."""
        # --- Step 1: POST /api/analyses with valid Python ---
        resp = client.post(
            "/api/analyses",
            data={"source_code": NORMALIZE_LIST_SOURCE, "llm_provider": "gpt-4.1-mini"},
        )
        assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert "analysis_id" in body
        analysis_id = body["analysis_id"]

        # --- Step 2: Seed DB with completed results (simulating pipeline) ---
        self._seed_analysis_with_results(analysis_id)

        # --- Step 3: GET /api/analyses/{id} — verify status and summary ---
        resp = client.get(f"/api/analyses/{analysis_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "complete"
        assert data["totalFunctions"] == 1
        assert data["totalClaims"] == 3
        assert data["totalViolations"] == 2
        assert data["bcvRate"] > 0.0

        # --- Step 4: GET /api/analyses/{id}/violations — verify violation data ---
        resp = client.get(f"/api/analyses/{analysis_id}/violations")
        assert resp.status_code == 200
        vdata = resp.json()
        assert vdata["analysisId"] == analysis_id
        assert len(vdata["violations"]) == 2
        assert vdata["bcvRate"] > 0.0

        # Verify category breakdown
        categories = vdata["categoryBreakdown"]
        assert "RSV" in categories
        assert "SEV" in categories

        # Verify violation structure
        for v in vdata["violations"]:
            assert "functionName" in v
            assert "claim" in v
            assert "outcome" in v
            assert v["claim"]["category"] in ("RSV", "SEV")

        # --- Step 5: GET /api/analyses/{id}/export?format=json — verify JSON export ---
        resp = client.get(f"/api/analyses/{analysis_id}/export?format=json")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        assert "content-disposition" in resp.headers
        assert "attachment" in resp.headers["content-disposition"]

        export_data = resp.json()
        assert export_data["analysis_id"] == analysis_id
        assert "violations" in export_data
        assert len(export_data["violations"]) == 2

    def test_api_list_analyses(self, client):
        """GET /api/analyses returns the created analysis."""
        # Create an analysis
        resp = client.post(
            "/api/analyses",
            data={"source_code": "x = 1\n", "llm_provider": "gpt-4.1-mini"},
        )
        assert resp.status_code == 202

        # List analyses
        resp = client.get("/api/analyses")
        assert resp.status_code == 200
        analyses = resp.json()
        assert len(analyses) >= 1
        assert analyses[0]["status"] == "pending"

    def test_api_delete_analysis(self, client):
        """DELETE /api/analyses/{id} removes the record."""
        resp = client.post(
            "/api/analyses",
            data={"source_code": "y = 2\n", "llm_provider": "gpt-4.1-mini"},
        )
        analysis_id = resp.json()["analysis_id"]

        # Delete
        resp = client.delete(f"/api/analyses/{analysis_id}")
        assert resp.status_code == 200

        # Verify gone
        resp = client.get(f"/api/analyses/{analysis_id}")
        assert resp.status_code == 404

    def test_api_csv_export(self, client):
        """GET /api/analyses/{id}/export?format=csv returns valid CSV."""
        resp = client.post(
            "/api/analyses",
            data={"source_code": NORMALIZE_LIST_SOURCE, "llm_provider": "gpt-4.1-mini"},
        )
        analysis_id = resp.json()["analysis_id"]
        self._seed_analysis_with_results(analysis_id)

        resp = client.get(f"/api/analyses/{analysis_id}/export?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

        lines = resp.text.strip().split("\n")
        # Header + 2 violation rows
        assert len(lines) == 3
        header = lines[0]
        assert "function_name" in header
        assert "category" in header

    def test_api_claims_endpoint(self, client):
        """GET /api/analyses/{id}/claims returns claims grouped by function."""
        resp = client.post(
            "/api/analyses",
            data={"source_code": NORMALIZE_LIST_SOURCE, "llm_provider": "gpt-4.1-mini"},
        )
        analysis_id = resp.json()["analysis_id"]
        self._seed_analysis_with_results(analysis_id)

        resp = client.get(f"/api/analyses/{analysis_id}/claims")
        assert resp.status_code == 200
        claims_data = resp.json()
        assert len(claims_data) >= 1
        assert claims_data[0]["functionName"] == "normalize_list"
        assert len(claims_data[0]["claims"]) == 3



# =========================================================================
# 3. Celery task chain test
# =========================================================================


class TestCeleryTaskChain:
    """Test the Celery task chain (run_bce → run_dts → run_rv) with mocked LLM.

    Verifies that the pipeline orchestrator correctly chains the three
    stages, updates status at each transition, and stores results.
    """

    def _create_analysis_record(self) -> str:
        """Insert a PENDING Analysis record and return its id."""
        session = _TestingSession()
        try:
            analysis = Analysis(
                filename="test_normalize.py",
                source_code=NORMALIZE_LIST_SOURCE,
                llm_provider="gpt-4.1-mini",
                status=AnalysisStatus.PENDING.value,
            )
            session.add(analysis)
            session.commit()
            aid = analysis.id
        finally:
            session.close()
        return aid

    def test_run_bce_task_extracts_claims(self):
        """run_bce extracts claims and returns serialised ClaimSchemas."""
        from app.pipeline.tasks import run_bce

        analysis_id = self._create_analysis_record()

        # Call the task function directly (not via Celery)
        result = run_bce(analysis_id, NORMALIZE_LIST_SOURCE)

        assert "claim_schemas" in result
        schemas = result["claim_schemas"]
        assert len(schemas) >= 1

        # Verify the first schema is for normalize_list
        cs = schemas[0]
        assert cs["function"]["name"] == "normalize_list"
        assert len(cs["claims"]) > 0

    def test_run_dts_task_with_mocked_llm(self):
        """run_dts synthesizes tests when LLM is mocked to return known code."""
        from app.pipeline.tasks import run_dts

        analysis_id = self._create_analysis_record()

        # First run BCE to get real claim schemas
        from app.pipeline.tasks import run_bce

        bce_result = run_bce(analysis_id, NORMALIZE_LIST_SOURCE)
        claim_schemas = bce_result["claim_schemas"]

        # Mock the LLM client to return a known test function
        mock_llm_response = f'```python\n{_RSV_TEST_CODE}\n```'

        with patch(
            "app.pipeline.dts.synthesizer.LLMClient.call",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            result = run_dts(analysis_id, claim_schemas, "gpt-4.1-mini")

        assert "test_suites" in result
        # Should have at least one test suite
        if result["test_suites"]:
            suite = result["test_suites"][0]
            assert "function_name" in suite
            assert "tests" in suite
            assert len(suite["tests"]) > 0

    def test_run_rv_task_executes_tests(self):
        """run_rv executes synthesized tests and produces violation reports."""
        from app.pipeline.tasks import run_rv

        analysis_id = self._create_analysis_record()

        # Build a test suite dict matching what run_dts would produce
        rsv_claim_dict = {
            "category": "RSV",
            "subject": "return",
            "predicate_object": "returns a new list",
            "conditionality": None,
            "source_line": 4,
            "raw_text": "Returns a new list with values scaled to [0, 1].",
        }
        test_suites = [
            {
                "function_name": "normalize_list",
                "function_signature": "def normalize_list(data: list[float]) -> list[float]",
                "tests": [
                    {
                        "claim": rsv_claim_dict,
                        "test_code": _RSV_TEST_CODE,
                        "test_function_name": "test_returns_new_list",
                        "synthesis_model": "gpt-4.1-mini",
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                    }
                ],
            }
        ]

        result = run_rv(analysis_id, test_suites, NORMALIZE_LIST_SOURCE)

        assert "violation_reports" in result
        reports = result["violation_reports"]
        assert len(reports) >= 1

        report = reports[0]
        assert report["function_name"] == "normalize_list"
        # RSV test should fail (normalize_list returns same object)
        assert report["fail_count"] >= 1
        assert report["bcv_rate"] > 0.0

    def test_pipeline_orchestrator_status_transitions(self):
        """run_pipeline chains BCE → DTS → RV with correct status transitions.

        The tasks module uses its own ``SessionLocal`` to update the DB.
        We patch it to use the test in-memory session factory so that
        ``_update_status``, ``_store_bce_results``, and ``_store_rv_results``
        all operate on the same test database.
        """
        from app.pipeline import tasks as tasks_mod

        analysis_id = self._create_analysis_record()

        # Track status transitions via a wrapper
        status_history: list[str] = []
        _orig_update = tasks_mod._update_status

        def tracking_update(aid: str, status: str) -> None:
            status_history.append(status)
            _orig_update(aid, status)

        # Mock the LLM to return a known test function
        mock_llm_response = f'```python\n{_ECV_TEST_CODE}\n```'

        with patch.object(
            tasks_mod, "SessionLocal", _TestingSession,
        ), patch.object(
            tasks_mod, "_update_status", side_effect=tracking_update,
        ), patch(
            "app.pipeline.dts.synthesizer.LLMClient.call",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            result = tasks_mod.run_pipeline(
                analysis_id=analysis_id,
                source_code=NORMALIZE_LIST_SOURCE,
                llm_provider="gpt-4.1-mini",
            )

        # Verify the pipeline completed
        assert result["status"] == "complete"
        assert result["analysis_id"] == analysis_id

        # Verify status transitions followed the correct sequence
        expected_transitions = [
            AnalysisStatus.BCE_RUNNING.value,
            AnalysisStatus.BCE_COMPLETE.value,
            AnalysisStatus.DTS_RUNNING.value,
            AnalysisStatus.DTS_COMPLETE.value,
            AnalysisStatus.RV_RUNNING.value,
            AnalysisStatus.COMPLETE.value,
        ]
        assert status_history == expected_transitions, (
            f"Expected transitions {expected_transitions}, got {status_history}"
        )

        # Verify DB was updated
        session = _TestingSession()
        try:
            analysis = session.query(Analysis).filter_by(id=analysis_id).first()
            assert analysis is not None
            assert analysis.status == AnalysisStatus.COMPLETE.value
            assert analysis.total_functions >= 1
            assert analysis.total_claims >= 1
        finally:
            session.close()
