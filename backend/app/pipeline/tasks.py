"""Celery task orchestration for the VeriDoc BCV Detection Pipeline.

Configures a Celery app with Redis broker (db 0) and result backend (db 1),
and implements the three pipeline stage tasks (BCE, DTS, RV) plus the
orchestrating ``run_pipeline`` task that chains them with status tracking.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from celery import Celery

from app.config import settings
from app.database import SessionLocal
from app.models import Analysis, Claim as ClaimModel, FunctionRecord, Violation
from app.schemas import (
    AnalysisStatus,
    BCVCategory,
    ClaimSchema,
    LLMProvider,
    SynthesizedTest,
    TestOutcome,
    Claim,
    FunctionInfo,
)

# Import registries
from app.pipeline.parsers.registry import ParserRegistry
from app.pipeline.frameworks.registry import TestFrameworkRegistry
from app.pipeline.runtimes.registry import RuntimeRegistry

# Import error types
from app.pipeline.parsers import UnsupportedLanguageError
from app.pipeline.frameworks import UnsupportedFrameworkError
from app.pipeline.runtimes import UnsupportedRuntimeError

# Import adapter modules so they register themselves with their registries
import app.pipeline.parsers.python_parser  # noqa: F401
import app.pipeline.parsers.javascript_parser  # noqa: F401
import app.pipeline.parsers.typescript_parser  # noqa: F401
import app.pipeline.parsers.java_parser  # noqa: F401
import app.pipeline.parsers.go_parser  # noqa: F401
import app.pipeline.parsers.rust_parser  # noqa: F401

import app.pipeline.frameworks.pytest_adapter  # noqa: F401
import app.pipeline.frameworks.jest_adapter  # noqa: F401
import app.pipeline.frameworks.junit_adapter  # noqa: F401
import app.pipeline.frameworks.gotest_adapter  # noqa: F401
import app.pipeline.frameworks.cargotest_adapter  # noqa: F401

import app.pipeline.runtimes.python_runtime  # noqa: F401
import app.pipeline.runtimes.nodejs_runtime  # noqa: F401
import app.pipeline.runtimes.java_runtime  # noqa: F401
import app.pipeline.runtimes.go_runtime  # noqa: F401
import app.pipeline.runtimes.rust_runtime  # noqa: F401

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Celery app configuration
# ---------------------------------------------------------------------------

# Broker uses Redis db 0, result backend uses Redis db 1
_broker_url = settings.redis_url  # default: redis://localhost:6379/0
_backend_url = settings.redis_url.rsplit("/", 1)[0] + "/1"

app = Celery("veridoc", broker=_broker_url, backend=_backend_url)
app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _update_status(analysis_id: str, status: str) -> None:
    """Update the Analysis status in the database."""
    db = SessionLocal()
    try:
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if analysis is None:
            logger.error("Analysis %s not found for status update", analysis_id)
            return
        analysis.status = status
        if status in (AnalysisStatus.COMPLETE.value, AnalysisStatus.FAILED.value):
            analysis.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _store_bce_results(
    analysis_id: str,
    claim_schemas: list[dict[str, Any]],
) -> None:
    """Persist BCE results (FunctionRecords + Claims) to the database."""
    db = SessionLocal()
    try:
        total_functions = 0
        total_claims = 0

        for cs in claim_schemas:
            func = cs["function"]
            func_record = FunctionRecord(
                analysis_id=analysis_id,
                name=func["name"],
                qualified_name=func["qualified_name"],
                source=func["source"],
                lineno=func["lineno"],
                signature=func["signature"],
                docstring=func.get("docstring"),
                params=func.get("params", []),
                return_annotation=func.get("return_annotation"),
                raise_statements=func.get("raise_statements", []),
                mutation_patterns=func.get("mutation_patterns", []),
            )
            db.add(func_record)
            db.flush()  # get func_record.id
            total_functions += 1

            for claim in cs.get("claims", []):
                claim_record = ClaimModel(
                    function_id=func_record.id,
                    category=claim["category"],
                    subject=claim["subject"],
                    predicate_object=claim["predicate_object"],
                    conditionality=claim.get("conditionality"),
                    source_line=claim["source_line"],
                    raw_text=claim["raw_text"],
                )
                db.add(claim_record)
                total_claims += 1

        # Update analysis summary counts
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if analysis:
            analysis.total_functions = total_functions
            analysis.total_claims = total_claims

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _store_rv_results(
    analysis_id: str,
    violation_reports: list[dict[str, Any]],
) -> None:
    """Persist RV results (Violations) and update analysis summary."""
    db = SessionLocal()
    try:
        total_violations = 0
        total_pass = 0
        total_fail = 0

        # Build a lookup from (function_name, claim raw_text) → claim DB id
        func_records = (
            db.query(FunctionRecord)
            .filter(FunctionRecord.analysis_id == analysis_id)
            .all()
        )
        claim_lookup: dict[tuple[str, str], str] = {}
        for fr in func_records:
            for c in fr.claims:
                claim_lookup[(fr.name, c.raw_text)] = c.id

        for report in violation_reports:
            func_name = report.get("function_name", "")
            total_pass += report.get("pass_count", 0)
            total_fail += report.get("fail_count", 0)

            for v in report.get("violations", []):
                claim_data = v.get("claim", {})
                claim_id = claim_lookup.get(
                    (func_name, claim_data.get("raw_text", ""))
                )
                if claim_id is None:
                    logger.warning(
                        "Could not find claim record for violation in %s",
                        func_name,
                    )
                    continue

                violation_record = Violation(
                    claim_id=claim_id,
                    outcome=v.get("outcome", "fail"),
                    test_code=v.get("test_code", ""),
                    stdout=v.get("stdout", ""),
                    stderr=v.get("stderr", ""),
                    traceback=v.get("traceback"),
                    expected=v.get("expected"),
                    actual=v.get("actual"),
                    execution_time_ms=v.get("execution_time_ms", 0.0),
                )
                db.add(violation_record)
                total_violations += 1

        # Update analysis summary
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if analysis:
            analysis.total_violations = total_violations
            total = total_pass + total_fail
            analysis.bcv_rate = total_fail / total if total > 0 else 0.0

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Individual stage tasks
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_RETRY_BACKOFF = 60  # base seconds for exponential backoff


@app.task(bind=True, max_retries=_MAX_RETRIES, default_retry_delay=_RETRY_BACKOFF)
def run_bce(self, analysis_id: str, source_code: str, language: str | None = None) -> dict[str, Any]:
    """Stage 1: Extract behavioral claims from source code.

    Returns a dict with ``claim_schemas`` (list of serialised ClaimSchema).

    When *language* is provided, the appropriate ``LanguageParser`` is
    resolved from the ``ParserRegistry`` and passed to the extractor.
    When *language* is ``None``, the extractor falls back to the existing
    Python ``ast``-based extraction for backward compatibility.
    """
    try:
        from app.pipeline.bce.extractor import BehavioralClaimExtractor

        parser = None
        if language is not None:
            try:
                parser = ParserRegistry.get(language)
            except UnsupportedLanguageError:
                logger.warning(
                    "No parser for language %r in BCE, falling back to default",
                    language,
                )

        extractor = BehavioralClaimExtractor(parser=parser)
        schemas: list[ClaimSchema] = extractor.extract(source_code)

        # Serialise to plain dicts for JSON transport between tasks
        result = [cs.model_dump() for cs in schemas]
        return {"claim_schemas": result}

    except Exception as exc:
        logger.exception("BCE failed for analysis %s", analysis_id)
        try:
            self.retry(exc=exc, countdown=_RETRY_BACKOFF * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            _update_status(analysis_id, AnalysisStatus.FAILED.value)
            raise


@app.task(bind=True, max_retries=_MAX_RETRIES, default_retry_delay=_RETRY_BACKOFF)
def run_dts(
    self,
    analysis_id: str,
    claim_schemas: list[dict[str, Any]],
    llm_provider: str,
    language: str | None = None,
) -> dict[str, Any]:
    """Stage 2: Synthesize tests from extracted claims.

    Returns a dict with ``test_suites`` — a list of dicts, each containing
    ``function_name`` and ``tests`` (list of serialised SynthesizedTest).

    When *language* is provided, the appropriate ``TestFramework`` is
    resolved from the ``TestFrameworkRegistry`` and passed to the
    synthesizer.  When *language* is ``None``, the synthesizer falls back
    to the existing hardcoded pytest prompts for backward compatibility.
    """
    try:
        from app.pipeline.dts.synthesizer import DynamicTestSynthesizer

        provider = LLMProvider(llm_provider)

        framework = None
        if language is not None:
            try:
                framework = TestFrameworkRegistry.get(language)
            except UnsupportedFrameworkError:
                logger.warning(
                    "No test framework for language %r in DTS, falling back to default",
                    language,
                )

        synthesizer = DynamicTestSynthesizer(
            llm_provider=provider,
            framework=framework,
        )

        test_suites: list[dict[str, Any]] = []
        for cs_dict in claim_schemas:
            cs = ClaimSchema.model_validate(cs_dict)
            if not cs.claims:
                continue

            # DTS synthesize is async — run in a fresh event loop
            loop = asyncio.new_event_loop()
            try:
                tests = loop.run_until_complete(synthesizer.synthesize(cs))
            finally:
                loop.close()

            test_suites.append({
                "function_name": cs.function.name,
                "function_signature": cs.function.signature,
                "tests": [t.model_dump() for t in tests],
            })

        return {"test_suites": test_suites}

    except Exception as exc:
        logger.exception("DTS failed for analysis %s", analysis_id)
        try:
            self.retry(exc=exc, countdown=_RETRY_BACKOFF * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            _update_status(analysis_id, AnalysisStatus.FAILED.value)
            raise


@app.task(bind=True, max_retries=_MAX_RETRIES, default_retry_delay=_RETRY_BACKOFF)
def run_rv(
    self,
    analysis_id: str,
    test_suites: list[dict[str, Any]],
    source_code: str,
    language: str | None = None,
) -> dict[str, Any]:
    """Stage 3: Execute synthesized tests and produce violation reports.

    Returns a dict with ``violation_reports`` (list of serialised ViolationReport).

    When *language* is provided, the appropriate ``RuntimeAdapter`` is
    resolved from the ``RuntimeRegistry`` and passed to the verifier.
    When *language* is ``None``, the verifier falls back to the existing
    hardcoded pytest execution for backward compatibility.
    """
    try:
        from app.pipeline.rv.verifier import RuntimeVerifier

        runtime = None
        if language is not None:
            try:
                runtime = RuntimeRegistry.get(language)
            except UnsupportedRuntimeError:
                logger.warning(
                    "No runtime for language %r in RV, falling back to default",
                    language,
                )

        verifier = RuntimeVerifier(runtime=runtime)
        reports: list[dict[str, Any]] = []

        for suite in test_suites:
            tests = [
                SynthesizedTest.model_validate(t) for t in suite.get("tests", [])
            ]
            if not tests:
                continue

            report = verifier.verify(
                test_suite=tests,
                source_code=source_code,
                analysis_id=analysis_id,
                function_name=suite.get("function_name", ""),
            )
            reports.append(report.model_dump())

        return {"violation_reports": reports}

    except Exception as exc:
        logger.exception("RV failed for analysis %s", analysis_id)
        try:
            self.retry(exc=exc, countdown=_RETRY_BACKOFF * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            _update_status(analysis_id, AnalysisStatus.FAILED.value)
            raise


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------


def _get_analysis_language(analysis_id: str) -> str:
    """Read the language field from the Analysis record.

    Returns the language string (e.g. 'python', 'javascript').
    Defaults to 'python' if the record is not found.

    Requirements: 5.1
    """
    db = SessionLocal()
    try:
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if analysis is None:
            logger.warning(
                "Analysis %s not found when reading language, defaulting to 'python'",
                analysis_id,
            )
            return "python"
        return analysis.language
    finally:
        db.close()


def _fail_analysis_with_error(analysis_id: str, error_message: str) -> None:
    """Set analysis status to FAILED and log the error.

    Requirements: 5.5
    """
    logger.error("Analysis %s failed: %s", analysis_id, error_message)
    db = SessionLocal()
    try:
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if analysis:
            analysis.status = AnalysisStatus.FAILED.value
            analysis.completed_at = datetime.now(timezone.utc)
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.task(bind=True, max_retries=_MAX_RETRIES, default_retry_delay=_RETRY_BACKOFF)
def run_pipeline(
    self,
    analysis_id: str,
    source_code: str,
    llm_provider: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Orchestrate the BCE → DTS → RV pipeline as a single Celery task.

    Updates the Analysis status at each stage transition:
        PENDING → BCE_RUNNING → BCE_COMPLETE →
        DTS_RUNNING → DTS_COMPLETE →
        RV_RUNNING → COMPLETE

    On failure after max retries, sets status to FAILED.

    Reads the ``language`` field from the Analysis record and uses the
    ParserRegistry, TestFrameworkRegistry, and RuntimeRegistry to obtain
    the correct language-specific adapters for each pipeline stage.

    Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
    """
    try:
        # ---- Read language and resolve adapters ----
        language = _get_analysis_language(analysis_id)

        try:
            parser = ParserRegistry.get(language)
        except UnsupportedLanguageError as exc:
            _fail_analysis_with_error(
                analysis_id,
                f"No parser registered for language '{language}': {exc}",
            )
            return {
                "analysis_id": analysis_id,
                "status": AnalysisStatus.FAILED.value,
                "error": str(exc),
            }

        try:
            framework = TestFrameworkRegistry.get(language)
        except UnsupportedFrameworkError as exc:
            _fail_analysis_with_error(
                analysis_id,
                f"No test framework registered for language '{language}': {exc}",
            )
            return {
                "analysis_id": analysis_id,
                "status": AnalysisStatus.FAILED.value,
                "error": str(exc),
            }

        try:
            runtime = RuntimeRegistry.get(language)
        except UnsupportedRuntimeError as exc:
            _fail_analysis_with_error(
                analysis_id,
                f"No runtime registered for language '{language}': {exc}",
            )
            return {
                "analysis_id": analysis_id,
                "status": AnalysisStatus.FAILED.value,
                "error": str(exc),
            }

        logger.info(
            "Pipeline for analysis %s: language=%s, parser=%s, framework=%s, runtime=%s",
            analysis_id,
            language,
            type(parser).__name__,
            type(framework).__name__,
            type(runtime).__name__,
        )

        # ---- Stage 1: BCE ----
        _update_status(analysis_id, AnalysisStatus.BCE_RUNNING.value)
        bce_result = run_bce(analysis_id, source_code, language)
        claim_schemas = bce_result["claim_schemas"]

        _update_status(analysis_id, AnalysisStatus.BCE_COMPLETE.value)
        _store_bce_results(analysis_id, claim_schemas)

        # ---- Stage 2: DTS ----
        _update_status(analysis_id, AnalysisStatus.DTS_RUNNING.value)
        dts_result = run_dts(analysis_id, claim_schemas, llm_provider, language)
        test_suites = dts_result["test_suites"]

        _update_status(analysis_id, AnalysisStatus.DTS_COMPLETE.value)

        # ---- Stage 3: RV ----
        _update_status(analysis_id, AnalysisStatus.RV_RUNNING.value)
        rv_result = run_rv(analysis_id, test_suites, source_code, language)
        violation_reports = rv_result["violation_reports"]

        _store_rv_results(analysis_id, violation_reports)
        _update_status(analysis_id, AnalysisStatus.COMPLETE.value)

        return {
            "analysis_id": analysis_id,
            "status": AnalysisStatus.COMPLETE.value,
            "claim_schemas": claim_schemas,
            "test_suites": test_suites,
            "violation_reports": violation_reports,
        }

    except Exception as exc:
        logger.exception("Pipeline failed for analysis %s", analysis_id)
        try:
            self.retry(exc=exc, countdown=_RETRY_BACKOFF * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            _update_status(analysis_id, AnalysisStatus.FAILED.value)
            raise
