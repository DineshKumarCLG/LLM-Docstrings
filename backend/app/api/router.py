"""FastAPI REST API router for VeriDoc.

Implements analysis creation, management, claims, violations, and export
endpoints with Python source validation, file size enforcement, input
sanitization, rate limiting, and Celery task enqueueing.

Requirements: 1.1–1.6, 5.3, 6.1–6.6, 7.1–7.4, 11.3, 11.4
"""

from __future__ import annotations

import ast
import csv
import io
import json
import re
import time
import uuid
import zipfile
from collections import defaultdict
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.api.documentation import build_documentation_tree
from app.config import settings
from app.database import get_db
from app.models import Analysis, Claim, FunctionRecord, Violation
from app.pipeline.language_detector import LanguageDetector
from app.pipeline.parsers import UnsupportedLanguageError
from app.pipeline.parsers.registry import ParserRegistry
from app.schemas import AnalysisStatus, LLMProvider

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Rate limiting (Requirement 11.4)
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Simple in-memory per-IP rate limiter.

    Tracks request timestamps per client IP and rejects requests that
    exceed *max_requests* within *window_seconds*.
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = {}

    def is_allowed(self, client_ip: str) -> bool:
        now = time.monotonic()
        timestamps = self._requests.get(client_ip, [])
        # Prune expired entries
        cutoff = now - self.window_seconds
        timestamps = [t for t in timestamps if t > cutoff]
        if len(timestamps) >= self.max_requests:
            self._requests[client_ip] = timestamps
            return False
        timestamps.append(now)
        self._requests[client_ip] = timestamps
        return True


_analysis_rate_limiter = _RateLimiter(max_requests=10, window_seconds=60)


# ---------------------------------------------------------------------------
# Input sanitization (Requirement 11.3)
# ---------------------------------------------------------------------------

# Patterns for XSS-dangerous content
_SCRIPT_TAG_RE = re.compile(r"<script[\s>].*?</script>", re.IGNORECASE | re.DOTALL)
_EVENT_HANDLER_RE = re.compile(r"\bon\w+\s*=\s*[\"'][^\"']*[\"']", re.IGNORECASE)
_JAVASCRIPT_URI_RE = re.compile(r"javascript\s*:", re.IGNORECASE)


def sanitize_source(source: str) -> str:
    """Strip XSS-dangerous content from source code strings.

    Removes <script> tags, on* event handler attributes, and javascript: URIs
    so that source code can be safely rendered in the frontend code viewer.
    """
    result = _SCRIPT_TAG_RE.sub("", source)
    result = _EVENT_HANDLER_RE.sub("", result)
    result = _JAVASCRIPT_URI_RE.sub("", result)
    return result


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_python(source: str) -> None:
    """Validate that *source* is syntactically valid Python.

    Raises HTTPException 422 with line number and message on failure.
    """
    try:
        ast.parse(source)
    except SyntaxError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Invalid Python syntax",
                "line": exc.lineno,
                "message": str(exc.msg),
            },
        )


# ---------------------------------------------------------------------------
# POST /api/analyses — Create new analysis
# ---------------------------------------------------------------------------


@router.post("/analyses", status_code=202)
async def create_analysis(
    request: Request,
    file: Optional[UploadFile] = File(None),
    source_code: Optional[str] = Form(None),
    llm_provider: LLMProvider = Form(LLMProvider.GEMINI_FLASH),
    db: Session = Depends(get_db),
) -> dict:
    """Create a new analysis from a file upload or pasted source code.

    Accepts either a Python file upload or a ``source_code`` form field.
    Validates the source with ``ast.parse()``, enforces the 1 MB file-size
    limit, sanitizes the content, creates an Analysis record, enqueues the
    Celery pipeline task, and returns 202 with the ``analysis_id``.

    Rate-limited to 10 requests per minute per client IP (Requirement 11.4).

    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 11.4
    """
    # Rate limiting (Requirement 11.4)
    client_ip = request.client.host if request.client else "unknown"
    if not _analysis_rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail={"error": "Too many requests. Try again later."},
        )
    filename: str | None = None
    code: str

    if file is not None:
        # --- File upload path ---
        raw = await file.read()

        # Enforce 1 MB limit (Requirement 1.4)
        if len(raw) > settings.max_file_size:
            raise HTTPException(
                status_code=413,
                detail={
                    "error": "File too large",
                    "max_bytes": settings.max_file_size,
                },
            )

        code = raw.decode("utf-8", errors="replace")
        filename = file.filename

    elif source_code is not None:
        code = source_code
    else:
        raise HTTPException(
            status_code=400,
            detail={"error": "Provide either a file upload or source_code"},
        )

    # Detect language from filename (Requirements 1.1, 1.2, 10.1)
    if filename:
        language = LanguageDetector.detect(filename, code).value
    else:
        # Code paste without filename — default to Python (Requirement 10.1)
        language = "python"

    # Validate syntax using language-specific parser (Requirements 1.1, 1.2, 10.2, 10.3)
    try:
        parser = ParserRegistry.get(language)
        is_valid, error_message = parser.validate_syntax(code)
        if not is_valid:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": f"Invalid {language} syntax",
                    "message": error_message or "Syntax error",
                },
            )
    except UnsupportedLanguageError:
        # Fallback to Python validation for backward compatibility
        _validate_python(code)

    # Sanitize for safe frontend rendering (Requirement 11.3)
    code = sanitize_source(code)

    # Persist Analysis record
    analysis = Analysis(
        filename=filename,
        source_code=code,
        llm_provider=llm_provider.value,
        status=AnalysisStatus.PENDING.value,
        language=language,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    # Enqueue Celery pipeline task (Requirement 5.1)
    from app.pipeline.tasks import run_pipeline

    try:
        run_pipeline.delay(
            analysis_id=analysis.id,
            source_code=code,
            llm_provider=llm_provider.value,
        )
    except Exception as exc:
        # Redis/Celery unavailable — mark analysis as failed and return 503
        analysis.status = AnalysisStatus.FAILED.value
        db.commit()
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Pipeline queue unavailable. Ensure Redis and Celery are running.",
                "analysis_id": analysis.id,
            },
        ) from exc

    return {"analysis_id": analysis.id}


# ---------------------------------------------------------------------------
# POST /api/analyses/batch — Analyse a whole project ZIP
# ---------------------------------------------------------------------------

_MAX_BATCH_SIZE = 20 * 1024 * 1024   # 20 MB total batch size
_MAX_FILES_PER_BATCH = 50            # guard against huge repos

# Supported source file extensions for batch extraction
_SUPPORTED_EXTENSIONS = set(LanguageDetector.supported_extensions())


def _is_supported_source_file(filename: str) -> bool:
    """Return True if *filename* has a supported source extension."""
    _, ext = os.path.splitext(filename)
    return ext.lower() in _SUPPORTED_EXTENSIONS


@router.post("/analyses/batch", status_code=202)
async def create_batch_analysis(
    request: Request,
    file: Optional[UploadFile] = File(None),
    files: Optional[list[UploadFile]] = File(None),
    llm_provider: LLMProvider = Form(LLMProvider.GEMINI_FLASH),
    db: Session = Depends(get_db),
) -> dict:
    """Accept a ZIP archive or multipart FormData with multiple files.

    Detects language per file, validates syntax using the appropriate
    LanguageParser, creates Analysis records with the correct ``language``
    field, and enqueues pipeline tasks with language routing.

    Files that fail syntax validation are skipped and reported in an
    ``errors`` array.  Enforces max 50 files and 20 MB total size.

    Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8
    """
    client_ip = request.client.host if request.client else "unknown"
    if not _analysis_rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail={"error": "Too many requests."})

    # Collect (filename, code_bytes) pairs from either ZIP or multipart files
    file_entries: list[tuple[str, bytes]] = []

    if file is not None and file.filename and file.filename.lower().endswith(".zip"):
        # ---- ZIP upload path (backward compatible) ----
        raw = await file.read()
        if len(raw) > _MAX_BATCH_SIZE:
            raise HTTPException(
                status_code=413,
                detail={"error": f"ZIP too large (max {_MAX_BATCH_SIZE // 1024 // 1024} MB)"},
            )

        try:
            zf = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile:
            raise HTTPException(
                status_code=400, detail={"error": "Invalid or corrupt ZIP file"}
            )

        # Collect all supported source files (skip __pycache__, hidden dirs)
        members = [
            m for m in zf.infolist()
            if _is_supported_source_file(m.filename)
            and not m.filename.startswith("__")
            and "/__pycache__/" not in m.filename
            and not m.is_dir()
        ]

        if not members:
            raise HTTPException(
                status_code=400,
                detail={"error": "No supported source files found in ZIP"},
            )

        if len(members) > _MAX_FILES_PER_BATCH:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": f"Too many files (max {_MAX_FILES_PER_BATCH} files per batch)"
                },
            )

        for member in members:
            try:
                code_bytes = zf.read(member.filename)
                file_entries.append((member.filename, code_bytes))
            except Exception:
                continue  # skip unreadable files

    elif files is not None and len(files) > 0:
        # ---- Multipart FormData with multiple files ----
        if len(files) > _MAX_FILES_PER_BATCH:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": f"Too many files (max {_MAX_FILES_PER_BATCH} files per batch)"
                },
            )

        total_size = 0
        for upload in files:
            raw = await upload.read()
            total_size += len(raw)
            if total_size > _MAX_BATCH_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "error": f"Total size exceeds limit (max {_MAX_BATCH_SIZE // 1024 // 1024} MB)"
                    },
                )
            fname = upload.filename or "unknown.py"
            file_entries.append((fname, raw))

    elif file is not None:
        # Single non-ZIP file uploaded via the `file` param — reject
        raise HTTPException(
            status_code=400,
            detail={"error": "Only .zip files or multiple files (via 'files') are accepted"},
        )
    else:
        raise HTTPException(
            status_code=400,
            detail={"error": "Provide a ZIP file or multiple files via multipart FormData"},
        )

    if not file_entries:
        raise HTTPException(
            status_code=400,
            detail={"error": "No files could be read from the upload"},
        )

    batch_id = str(uuid.uuid4())
    analysis_ids: list[str] = []
    errors: list[dict[str, str]] = []

    from app.pipeline.tasks import run_pipeline

    for fname, code_bytes in file_entries:
        try:
            code = code_bytes.decode("utf-8", errors="replace")
        except Exception:
            errors.append({"filename": fname, "error": "Unable to decode file"})
            continue

        # Detect language (Requirement 8.2)
        language = LanguageDetector.detect(fname, code).value

        # Validate syntax using language-specific parser (Requirement 8.3)
        try:
            parser = ParserRegistry.get(language)
            is_valid, error_message = parser.validate_syntax(code)
            if not is_valid:
                errors.append({
                    "filename": fname,
                    "error": error_message or f"Invalid {language} syntax",
                })
                continue
        except UnsupportedLanguageError:
            # Fallback to Python validation for backward compatibility
            try:
                ast.parse(code)
            except SyntaxError as exc:
                errors.append({
                    "filename": fname,
                    "error": f"Syntax error: {exc.msg}" if exc.msg else "Syntax error",
                })
                continue

        code = sanitize_source(code)

        # Create Analysis record with language field (Requirement 8.4)
        analysis = Analysis(
            filename=fname,
            source_code=code,
            llm_provider=llm_provider.value,
            status=AnalysisStatus.PENDING.value,
            config={"batch_id": batch_id},
            language=language,
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)

        # Enqueue pipeline task with language routing (Requirement 8.5)
        try:
            run_pipeline.delay(
                analysis_id=analysis.id,
                source_code=code,
                llm_provider=llm_provider.value,
            )
            analysis_ids.append(analysis.id)
        except Exception:
            analysis.status = AnalysisStatus.FAILED.value
            db.commit()

    if not analysis_ids and not errors:
        raise HTTPException(
            status_code=422,
            detail={"error": "No valid source files could be processed"},
        )

    if not analysis_ids:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "No valid source files could be processed",
                "errors": errors,
            },
        )

    return {
        "batch_id": batch_id,
        "analysis_ids": analysis_ids,
        "total": len(analysis_ids),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# GET /api/batches/{batch_id} — Poll all analyses in a batch
# ---------------------------------------------------------------------------


@router.get("/batches/{batch_id}")
def get_batch(batch_id: str, db: Session = Depends(get_db)) -> dict:
    """Return summary for every analysis belonging to a batch."""
    analyses = (
        db.query(Analysis)
        .filter(Analysis.config["batch_id"].as_string() == batch_id)
        .order_by(Analysis.created_at.asc())
        .all()
    )
    if not analyses:
        raise HTTPException(status_code=404, detail="Batch not found")

    items = [_analysis_summary(a) for a in analyses]
    total = len(items)
    complete = sum(1 for a in analyses if a.status == AnalysisStatus.COMPLETE.value)
    failed = sum(1 for a in analyses if a.status == AnalysisStatus.FAILED.value)

    return {
        "batch_id": batch_id,
        "total": total,
        "complete": complete,
        "failed": failed,
        "in_progress": total - complete - failed,
        "analyses": items,
    }


# ---------------------------------------------------------------------------
# Helper: build analysis summary dict
# ---------------------------------------------------------------------------


def _analysis_summary(a: Analysis) -> dict:
    """Build a summary dict for an Analysis record (camelCase keys for frontend)."""
    return {
        "id": a.id,
        "status": a.status,
        "filename": a.filename,
        "llmProvider": a.llm_provider,
        "totalFunctions": a.total_functions,
        "totalClaims": a.total_claims,
        "totalViolations": a.total_violations,
        "bcvRate": a.bcv_rate,
        "createdAt": a.created_at.isoformat() if a.created_at else None,
        "completedAt": a.completed_at.isoformat() if a.completed_at else None,
        "language": a.language,
    }


# ---------------------------------------------------------------------------
# GET /api/analyses — List all analyses (Requirement 6.1)
# ---------------------------------------------------------------------------


@router.get("/analyses")
def list_analyses(db: Session = Depends(get_db)) -> list[dict]:
    """Return all analyses with summary info.

    Requirements: 6.1
    """
    analyses = db.query(Analysis).order_by(Analysis.created_at.desc()).all()
    return [_analysis_summary(a) for a in analyses]


# ---------------------------------------------------------------------------
# GET /api/analyses/{id} — Get single analysis (Requirement 6.2, 5.3)
# ---------------------------------------------------------------------------


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: str, db: Session = Depends(get_db)) -> dict:
    """Return a single analysis with full summary. 404 if not found.

    Requirements: 5.3, 6.2
    """
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    result = _analysis_summary(analysis)
    result["sourceCode"] = analysis.source_code
    return result


# ---------------------------------------------------------------------------
# DELETE /api/analyses/{id} — Cascade delete (Requirement 6.5)
# ---------------------------------------------------------------------------


@router.delete("/analyses/{analysis_id}")
def delete_analysis(analysis_id: str, db: Session = Depends(get_db)) -> dict:
    """Delete an analysis and all associated records. 404 if not found.

    Cascade delete removes FunctionRecords, Claims, and Violations.

    Requirements: 6.5
    """
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    db.delete(analysis)
    db.commit()
    return {"detail": "Analysis deleted", "id": analysis_id}


# ---------------------------------------------------------------------------
# POST /api/analyses/{id}/rerun — Re-run analysis (Requirement 6.6)
# ---------------------------------------------------------------------------


@router.post("/analyses/{analysis_id}/rerun", status_code=202)
def rerun_analysis(
    analysis_id: str,
    llm_provider: Optional[LLMProvider] = None,
    db: Session = Depends(get_db),
) -> dict:
    """Re-run an analysis with the same or different config.

    Resets status to PENDING, clears previous results, and enqueues a new
    Celery pipeline task.

    Requirements: 6.6
    """
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Update provider if specified
    if llm_provider is not None:
        analysis.llm_provider = llm_provider.value

    # Reset analysis state
    analysis.status = AnalysisStatus.PENDING.value
    analysis.total_functions = 0
    analysis.total_claims = 0
    analysis.total_violations = 0
    analysis.bcv_rate = 0.0
    analysis.completed_at = None

    # Delete existing child records so the rerun starts fresh
    for func in analysis.functions:
        db.delete(func)

    db.commit()
    db.refresh(analysis)

    # Enqueue new Celery pipeline task
    from app.pipeline.tasks import run_pipeline

    try:
        run_pipeline.delay(
            analysis_id=analysis.id,
            source_code=analysis.source_code,
            llm_provider=analysis.llm_provider,
        )
    except Exception as exc:
        analysis.status = AnalysisStatus.FAILED.value
        db.commit()
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Pipeline queue unavailable. Ensure Redis and Celery are running.",
                "analysis_id": analysis.id,
            },
        ) from exc

    return {"analysis_id": analysis.id, "status": analysis.status}


# ---------------------------------------------------------------------------
# GET /api/analyses/{id}/claims — Claims grouped by function (Requirement 6.3)
# ---------------------------------------------------------------------------


@router.get("/analyses/{analysis_id}/claims")
def get_analysis_claims(
    analysis_id: str, db: Session = Depends(get_db)
) -> list[dict]:
    """Return claims grouped by function for an analysis.

    Each entry contains function_name, function_signature, and a list of
    claim dicts.

    Requirements: 6.3
    """
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    functions = (
        db.query(FunctionRecord)
        .filter(FunctionRecord.analysis_id == analysis_id)
        .options(joinedload(FunctionRecord.claims))
        .all()
    )

    result = []
    for func in functions:
        claims_list = [
            {
                "id": c.id,
                "category": c.category,
                "subject": c.subject,
                "predicateObject": c.predicate_object,
                "conditionality": c.conditionality,
                "sourceLine": c.source_line,
                "rawText": c.raw_text,
            }
            for c in func.claims
        ]
        result.append(
            {
                "functionName": func.name,
                "functionSignature": func.signature,
                "claims": claims_list,
            }
        )

    return result


# ---------------------------------------------------------------------------
# GET /api/analyses/{id}/violations — Full ViolationReport (Requirement 6.4)
# ---------------------------------------------------------------------------


@router.get("/analyses/{analysis_id}/violations")
def get_analysis_violations(
    analysis_id: str, db: Session = Depends(get_db)
) -> dict:
    """Return the full ViolationReport with category breakdowns.

    Requirements: 6.4
    """
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Fetch all violations through the function → claim → violation chain
    violations_query = (
        db.query(Violation, Claim, FunctionRecord)
        .join(Claim, Violation.claim_id == Claim.id)
        .join(FunctionRecord, Claim.function_id == FunctionRecord.id)
        .filter(FunctionRecord.analysis_id == analysis_id)
        .all()
    )

    violations_list = []
    category_breakdown: dict[str, int] = defaultdict(int)

    for violation, claim, func in violations_query:
        violations_list.append(
            {
                "functionId": func.id,
                "functionName": func.name,
                "claim": {
                    "id": claim.id,
                    "category": claim.category,
                    "subject": claim.subject,
                    "predicateObject": claim.predicate_object,
                    "conditionality": claim.conditionality,
                    "sourceLine": claim.source_line,
                    "rawText": claim.raw_text,
                },
                "testCode": violation.test_code,
                "outcome": violation.outcome,
                "traceback": violation.traceback,
                "expected": violation.expected,
                "actual": violation.actual,
                "executionTimeMs": violation.execution_time_ms,
            }
        )
        category_breakdown[claim.category] += 1

    return {
        "analysisId": analysis_id,
        "violations": violations_list,
        "categoryBreakdown": dict(category_breakdown),
        "bcvRate": analysis.bcv_rate,
        "totalFunctions": analysis.total_functions,
        "totalClaims": analysis.total_claims,
    }


# ---------------------------------------------------------------------------
# GET /api/analyses/{id}/documentation — Documentation tree (Requirements 8.1–8.3)
# ---------------------------------------------------------------------------


@router.get("/analyses/{analysis_id}/documentation")
def get_analysis_documentation(
    analysis_id: str, db: Session = Depends(get_db)
) -> dict:
    """Return the documentation tree for a completed analysis.

    Returns 404 if the analysis does not exist, 409 if the analysis has not
    yet completed (status != "complete").

    Requirements: 8.1, 8.2, 8.3
    """
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    if analysis.status != AnalysisStatus.COMPLETE.value:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "Analysis not complete",
                "status": analysis.status,
            },
        )

    return build_documentation_tree(analysis.source_code, analysis_id)


# ---------------------------------------------------------------------------
# GET /api/analyses/{id}/export — Export report (Requirements 7.1–7.4)
# ---------------------------------------------------------------------------

_VALID_EXPORT_FORMATS = {"json", "csv", "pdf"}


@router.get("/analyses/{analysis_id}/export")
def export_analysis(
    analysis_id: str,
    format: str = Query(..., description="Export format: json, csv, or pdf"),
    db: Session = Depends(get_db),
) -> Response:
    """Export the violation report in JSON, CSV, or PDF format.

    Sets Content-Type and Content-Disposition headers for file download.
    Returns 404 if analysis not found, 400 if invalid format.

    Requirements: 7.1, 7.2, 7.3, 7.4
    """
    fmt = format.lower()
    if fmt not in _VALID_EXPORT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Invalid format '{format}'. Must be one of: json, csv, pdf"
            },
        )

    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Fetch violations through function → claim → violation chain
    rows = (
        db.query(Violation, Claim, FunctionRecord)
        .join(Claim, Violation.claim_id == Claim.id)
        .join(FunctionRecord, Claim.function_id == FunctionRecord.id)
        .filter(FunctionRecord.analysis_id == analysis_id)
        .all()
    )

    if fmt == "json":
        return _export_json(analysis, rows, analysis_id)
    elif fmt == "csv":
        return _export_csv(rows, analysis_id)
    else:  # pdf
        return _export_pdf(analysis, rows, analysis_id)


def _build_violation_dicts(
    rows: list[tuple[Violation, Claim, FunctionRecord]],
) -> list[dict]:
    """Convert DB rows into serializable violation dicts."""
    result = []
    for violation, claim, func in rows:
        result.append(
            {
                "function_name": func.name,
                "category": claim.category,
                "claim_text": claim.raw_text,
                "outcome": violation.outcome,
                "expected": violation.expected or "",
                "actual": violation.actual or "",
            }
        )
    return result


# -- JSON export (Requirement 7.1) ------------------------------------------


def _export_json(
    analysis: Analysis,
    rows: list[tuple[Violation, Claim, FunctionRecord]],
    analysis_id: str,
) -> Response:
    violations = _build_violation_dicts(rows)
    category_breakdown: dict[str, int] = defaultdict(int)
    for v in violations:
        category_breakdown[v["category"]] += 1

    report = {
        "analysis_id": analysis_id,
        "filename": analysis.filename,
        "llm_provider": analysis.llm_provider,
        "status": analysis.status,
        "total_functions": analysis.total_functions,
        "total_claims": analysis.total_claims,
        "total_violations": analysis.total_violations,
        "bcv_rate": analysis.bcv_rate,
        "category_breakdown": dict(category_breakdown),
        "violations": violations,
    }
    content = json.dumps(report, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="analysis_{analysis_id}.json"'
        },
    )


# -- CSV export (Requirement 7.2) -------------------------------------------


def _export_csv(
    rows: list[tuple[Violation, Claim, FunctionRecord]],
    analysis_id: str,
) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["function_name", "category", "claim_text", "outcome", "expected", "actual"]
    )
    for violation, claim, func in rows:
        writer.writerow(
            [
                func.name,
                claim.category,
                claim.raw_text,
                violation.outcome,
                violation.expected or "",
                violation.actual or "",
            ]
        )
    content = buf.getvalue()
    return Response(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="analysis_{analysis_id}.csv"'
        },
    )


# -- PDF export (Requirement 7.3) -------------------------------------------


def _export_pdf(
    analysis: Analysis,
    rows: list[tuple[Violation, Claim, FunctionRecord]],
    analysis_id: str,
) -> Response:
    """Generate a minimal text-based PDF report.

    Uses a simple, dependency-free PDF structure with summary stats and
    violation details.  No external libraries required.
    """
    lines: list[str] = []
    lines.append(f"VeriDoc Analysis Report — {analysis_id}")
    lines.append("")
    lines.append(f"Filename:         {analysis.filename or 'N/A'}")
    lines.append(f"LLM Provider:     {analysis.llm_provider}")
    lines.append(f"Status:           {analysis.status}")
    lines.append(f"Total Functions:  {analysis.total_functions}")
    lines.append(f"Total Claims:     {analysis.total_claims}")
    lines.append(f"Total Violations: {analysis.total_violations}")
    lines.append(f"BCV Rate:         {analysis.bcv_rate:.2%}")
    lines.append("")

    # Category breakdown
    category_counts: dict[str, int] = defaultdict(int)
    for _v, claim, _f in rows:
        category_counts[claim.category] += 1

    if category_counts:
        lines.append("Category Breakdown:")
        for cat, count in sorted(category_counts.items()):
            lines.append(f"  {cat}: {count}")
        lines.append("")

    # Violation details
    if rows:
        lines.append("Violation Details:")
        lines.append("-" * 60)
        for i, (violation, claim, func) in enumerate(rows, 1):
            lines.append(f"  #{i}  {func.name} [{claim.category}]")
            lines.append(f"      Claim:    {claim.raw_text}")
            lines.append(f"      Outcome:  {violation.outcome}")
            lines.append(f"      Expected: {violation.expected or 'N/A'}")
            lines.append(f"      Actual:   {violation.actual or 'N/A'}")
            lines.append("")
    else:
        lines.append("No violations found.")

    text_body = "\n".join(lines)
    pdf_bytes = _text_to_pdf(text_body)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="analysis_{analysis_id}.pdf"'
        },
    )


def _text_to_pdf(text: str) -> bytes:
    """Convert plain text to a minimal valid PDF document.

    Produces a bare-bones PDF 1.4 file with a single page containing the
    text rendered in Courier 10pt.  No external dependencies.
    """
    # Escape special PDF characters in text content
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    # Build text operators — one Tj per line
    text_lines = safe.split("\n")
    text_ops: list[str] = []
    text_ops.append("BT")
    text_ops.append("/F1 10 Tf")
    text_ops.append("36 756 Td")  # start near top-left with margin
    text_ops.append("12 TL")  # leading (line spacing)
    for line in text_lines:
        text_ops.append(f"({line}) Tj T*")
    text_ops.append("ET")
    stream_body = "\n".join(text_ops)

    # Object 1: Catalog
    obj1 = "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj"
    # Object 2: Pages
    obj2 = "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj"
    # Object 3: Page
    obj3 = (
        "3 0 obj\n"
        "<< /Type /Page /Parent 2 0 R "
        "/MediaBox [0 0 612 792] "
        "/Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>\n"
        "endobj"
    )
    # Object 4: Stream (content)
    stream_bytes = stream_body.encode("latin-1", errors="replace")
    obj4 = (
        f"4 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n"
        + stream_body
        + "\nendstream\nendobj"
    )
    # Object 5: Font
    obj5 = (
        "5 0 obj\n"
        "<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\n"
        "endobj"
    )

    objects = [obj1, obj2, obj3, obj4, obj5]
    body = "\n".join(objects)
    header = "%PDF-1.4\n"

    # Build xref table
    offset = len(header)
    offsets: list[int] = []
    for obj in objects:
        offsets.append(offset)
        offset += len(obj) + 1  # +1 for newline separator

    xref_start = offset
    xref_lines = [f"xref\n0 {len(objects) + 1}"]
    xref_lines.append("0000000000 65535 f ")
    for off in offsets:
        xref_lines.append(f"{off:010d} 00000 n ")
    xref_section = "\n".join(xref_lines)

    trailer = (
        f"\ntrailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF"
    )

    return (header + body + "\n" + xref_section + trailer).encode("latin-1", errors="replace")


# ---------------------------------------------------------------------------
# GET /api/stats — Aggregate statistics for Research tab
# ---------------------------------------------------------------------------


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)) -> dict:
    """Return aggregate statistics across all analyses.

    Provides data for the Research tab including:
    - Total analyses, functions, claims, violations
    - Category breakdown of violations
    - Language distribution
    - LLM provider usage
    - Detection rates per provider
    """
    from sqlalchemy import func

    # Basic counts
    total_analyses = db.query(func.count(Analysis.id)).scalar() or 0
    completed_analyses = (
        db.query(func.count(Analysis.id))
        .filter(Analysis.status == AnalysisStatus.COMPLETE.value)
        .scalar() or 0
    )
    total_functions = db.query(func.sum(Analysis.total_functions)).scalar() or 0
    total_claims = db.query(func.sum(Analysis.total_claims)).scalar() or 0
    total_violations = db.query(func.sum(Analysis.total_violations)).scalar() or 0

    # Average BCV rate across completed analyses
    avg_bcv_rate = (
        db.query(func.avg(Analysis.bcv_rate))
        .filter(Analysis.status == AnalysisStatus.COMPLETE.value)
        .scalar() or 0.0
    )

    # Category breakdown from violations
    category_counts = (
        db.query(Claim.category, func.count(Violation.id))
        .join(Violation, Violation.claim_id == Claim.id)
        .group_by(Claim.category)
        .all()
    )
    category_breakdown = {cat: count for cat, count in category_counts}

    # Language distribution
    language_counts = (
        db.query(Analysis.language, func.count(Analysis.id))
        .group_by(Analysis.language)
        .all()
    )
    language_distribution = {lang: count for lang, count in language_counts}

    # LLM provider usage and detection rates
    provider_stats = (
        db.query(
            Analysis.llm_provider,
            func.count(Analysis.id),
            func.sum(Analysis.total_violations),
            func.sum(Analysis.total_claims),
            func.avg(Analysis.bcv_rate),
        )
        .filter(Analysis.status == AnalysisStatus.COMPLETE.value)
        .group_by(Analysis.llm_provider)
        .all()
    )

    provider_usage = {}
    detection_rates = {}
    for provider, count, violations, claims, avg_rate in provider_stats:
        provider_usage[provider] = count
        # Detection rate = violations found / total claims
        if claims and claims > 0:
            detection_rates[provider] = (violations or 0) / claims
        else:
            detection_rates[provider] = 0.0

    # Recent analyses (last 10)
    recent = (
        db.query(Analysis)
        .order_by(Analysis.created_at.desc())
        .limit(10)
        .all()
    )
    recent_analyses = [
        {
            "id": a.id,
            "filename": a.filename,
            "language": a.language,
            "status": a.status,
            "llmProvider": a.llm_provider,
            "totalClaims": a.total_claims,
            "totalViolations": a.total_violations,
            "bcvRate": a.bcv_rate,
            "createdAt": a.created_at.isoformat() if a.created_at else None,
        }
        for a in recent
    ]

    return {
        "totalAnalyses": total_analyses,
        "completedAnalyses": completed_analyses,
        "totalFunctions": int(total_functions),
        "totalClaims": int(total_claims),
        "totalViolations": int(total_violations),
        "avgBcvRate": float(avg_bcv_rate),
        "categoryBreakdown": category_breakdown,
        "languageDistribution": language_distribution,
        "providerUsage": provider_usage,
        "detectionRates": detection_rates,
        "recentAnalyses": recent_analyses,
    }


# ---------------------------------------------------------------------------
# GET /api/analyses/{id}/graph — Knowledge graph for code visualization
# ---------------------------------------------------------------------------


def _extract_code_graph(source_code: str, language: str) -> dict:
    """Extract a knowledge graph from source code.
    
    Returns nodes (modules, classes, functions, claims, violations) and
    edges (contains, calls, has_claim, imports, inherits).
    """
    import ast as ast_module
    
    nodes = []
    edges = []
    node_id_counter = [0]
    
    def make_id():
        node_id_counter[0] += 1
        return f"n{node_id_counter[0]}"
    
    if language != "python":
        # For non-Python, return a simple module node
        mod_id = make_id()
        nodes.append({
            "id": mod_id,
            "type": "module",
            "name": "source",
            "lineno": 1,
            "docstring": None,
        })
        return {"nodes": nodes, "edges": edges}
    
    try:
        tree = ast_module.parse(source_code)
    except SyntaxError:
        return {"nodes": [], "edges": []}
    
    source_lines = source_code.splitlines()
    
    # Track function/class names to IDs for edge creation
    name_to_id: dict[str, str] = {}
    class_methods: dict[str, list[str]] = {}  # class_name -> [method_ids]
    
    # Module node
    mod_id = make_id()
    nodes.append({
        "id": mod_id,
        "type": "module",
        "name": "module",
        "lineno": 1,
        "docstring": ast_module.get_docstring(tree),
    })
    
    # Extract imports
    imports = []
    for node in ast_module.iter_child_nodes(tree):
        if isinstance(node, ast_module.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast_module.ImportFrom):
            if node.module:
                imports.append(node.module)
    
    # Add import nodes
    for imp in set(imports):
        imp_id = make_id()
        nodes.append({
            "id": imp_id,
            "type": "import",
            "name": imp,
            "lineno": 0,
            "docstring": None,
        })
        edges.append({
            "source": mod_id,
            "target": imp_id,
            "type": "imports",
        })
    
    # Extract classes and functions
    for node in ast_module.iter_child_nodes(tree):
        if isinstance(node, ast_module.ClassDef):
            class_id = make_id()
            name_to_id[node.name] = class_id
            class_methods[node.name] = []
            
            nodes.append({
                "id": class_id,
                "type": "class",
                "name": node.name,
                "lineno": node.lineno,
                "docstring": ast_module.get_docstring(node),
            })
            edges.append({
                "source": mod_id,
                "target": class_id,
                "type": "contains",
            })
            
            # Extract base classes (inheritance)
            for base in node.bases:
                if isinstance(base, ast_module.Name):
                    base_name = base.id
                    if base_name in name_to_id:
                        edges.append({
                            "source": class_id,
                            "target": name_to_id[base_name],
                            "type": "inherits",
                        })
            
            # Extract methods
            for item in node.body:
                if isinstance(item, (ast_module.FunctionDef, ast_module.AsyncFunctionDef)):
                    method_id = make_id()
                    full_name = f"{node.name}.{item.name}"
                    name_to_id[full_name] = method_id
                    name_to_id[item.name] = method_id  # Also map short name
                    class_methods[node.name].append(method_id)
                    
                    nodes.append({
                        "id": method_id,
                        "type": "method",
                        "name": item.name,
                        "fullName": full_name,
                        "lineno": item.lineno,
                        "docstring": ast_module.get_docstring(item),
                        "signature": _build_signature_simple(item),
                    })
                    edges.append({
                        "source": class_id,
                        "target": method_id,
                        "type": "has_method",
                    })
        
        elif isinstance(node, (ast_module.FunctionDef, ast_module.AsyncFunctionDef)):
            func_id = make_id()
            name_to_id[node.name] = func_id
            
            nodes.append({
                "id": func_id,
                "type": "function",
                "name": node.name,
                "lineno": node.lineno,
                "docstring": ast_module.get_docstring(node),
                "signature": _build_signature_simple(node),
            })
            edges.append({
                "source": mod_id,
                "target": func_id,
                "type": "contains",
            })
    
    # Second pass: extract function calls
    for node in ast_module.walk(tree):
        if isinstance(node, (ast_module.FunctionDef, ast_module.AsyncFunctionDef)):
            caller_name = node.name
            # Find the caller's ID (could be method or function)
            caller_id = None
            for n in nodes:
                if n["name"] == caller_name and n["type"] in ("function", "method"):
                    caller_id = n["id"]
                    break
            
            if caller_id:
                # Find all calls within this function
                for child in ast_module.walk(node):
                    if isinstance(child, ast_module.Call):
                        callee_name = None
                        if isinstance(child.func, ast_module.Name):
                            callee_name = child.func.id
                        elif isinstance(child.func, ast_module.Attribute):
                            callee_name = child.func.attr
                        
                        if callee_name and callee_name in name_to_id:
                            callee_id = name_to_id[callee_name]
                            # Avoid self-loops and duplicates
                            if callee_id != caller_id:
                                edge_exists = any(
                                    e["source"] == caller_id and 
                                    e["target"] == callee_id and 
                                    e["type"] == "calls"
                                    for e in edges
                                )
                                if not edge_exists:
                                    edges.append({
                                        "source": caller_id,
                                        "target": callee_id,
                                        "type": "calls",
                                    })
    
    return {"nodes": nodes, "edges": edges}


def _build_signature_simple(node) -> str:
    """Build a simple signature string for a function node."""
    import ast as ast_module
    prefix = "async def" if isinstance(node, ast_module.AsyncFunctionDef) else "def"
    params = []
    for arg in node.args.args:
        params.append(arg.arg)
    return f"{prefix} {node.name}({', '.join(params)})"


@router.get("/analyses/{analysis_id}/graph")
def get_analysis_graph(
    analysis_id: str, db: Session = Depends(get_db)
) -> dict:
    """Return a knowledge graph representation of the analyzed code.
    
    The graph includes:
    - Nodes: modules, classes, functions, methods, imports
    - Edges: contains, has_method, calls, imports, inherits
    
    Also includes claims and violations linked to their functions.
    """
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    # Extract code structure graph
    graph = _extract_code_graph(analysis.source_code, analysis.language)
    
    # Add claims and violations from the database
    functions = (
        db.query(FunctionRecord)
        .filter(FunctionRecord.analysis_id == analysis_id)
        .options(joinedload(FunctionRecord.claims).joinedload(Claim.violation))
        .all()
    )
    
    # Map function names to graph node IDs
    func_name_to_node = {}
    for node in graph["nodes"]:
        if node["type"] in ("function", "method"):
            func_name_to_node[node["name"]] = node["id"]
    
    # Add claim and violation nodes
    node_counter = len(graph["nodes"])
    for func in functions:
        func_node_id = func_name_to_node.get(func.name)
        
        for claim in func.claims:
            node_counter += 1
            claim_id = f"c{node_counter}"
            
            graph["nodes"].append({
                "id": claim_id,
                "type": "claim",
                "name": claim.raw_text[:50] + "..." if len(claim.raw_text) > 50 else claim.raw_text,
                "category": claim.category,
                "fullText": claim.raw_text,
                "lineno": claim.source_line,
            })
            
            if func_node_id:
                graph["edges"].append({
                    "source": func_node_id,
                    "target": claim_id,
                    "type": "has_claim",
                })
            
            # Add violation if exists
            if claim.violation:
                node_counter += 1
                violation_id = f"v{node_counter}"
                
                graph["nodes"].append({
                    "id": violation_id,
                    "type": "violation",
                    "name": f"{claim.category} Violation",
                    "outcome": claim.violation.outcome,
                    "category": claim.category,
                })
                
                graph["edges"].append({
                    "source": claim_id,
                    "target": violation_id,
                    "type": "violated_by",
                })
    
    return {
        "analysisId": analysis_id,
        "language": analysis.language,
        "graph": graph,
    }


# ---------------------------------------------------------------------------
# GET /api/analyses/{id}/doc-health — Documentation health metrics
# ---------------------------------------------------------------------------


@router.get("/analyses/{analysis_id}/doc-health")
def get_doc_health(
    analysis_id: str, db: Session = Depends(get_db)
) -> dict:
    """Return documentation health metrics for an analysis.
    
    Metrics include:
    - Documentation coverage (% of functions with docstrings)
    - Claim density (avg claims per documented function)
    - Violation rate (% of claims that failed)
    - Per-function breakdown
    """
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    # Parse source to count all functions (including undocumented)
    all_functions = _count_all_functions(analysis.source_code, analysis.language)
    
    # Get documented functions from DB
    functions = (
        db.query(FunctionRecord)
        .filter(FunctionRecord.analysis_id == analysis_id)
        .options(joinedload(FunctionRecord.claims).joinedload(Claim.violation))
        .all()
    )
    
    documented_count = len(functions)
    total_functions = max(all_functions, documented_count)
    
    # Calculate metrics
    coverage = documented_count / total_functions if total_functions > 0 else 0
    
    total_claims = sum(len(f.claims) for f in functions)
    total_violations = sum(
        1 for f in functions 
        for c in f.claims 
        if c.violation and c.violation.outcome == "fail"
    )
    
    claim_density = total_claims / documented_count if documented_count > 0 else 0
    violation_rate = total_violations / total_claims if total_claims > 0 else 0
    
    # Per-function breakdown
    function_health = []
    for func in functions:
        func_claims = len(func.claims)
        func_violations = sum(
            1 for c in func.claims 
            if c.violation and c.violation.outcome == "fail"
        )
        
        # Calculate health score (0-100)
        if func_claims == 0:
            health_score = 50  # No claims = neutral
        else:
            health_score = int(100 * (1 - func_violations / func_claims))
        
        function_health.append({
            "id": func.id,
            "name": func.name,
            "signature": func.signature,
            "hasDocstring": bool(func.docstring),
            "docstringLength": len(func.docstring) if func.docstring else 0,
            "claimCount": func_claims,
            "violationCount": func_violations,
            "healthScore": health_score,
            "categories": list(set(c.category for c in func.claims)),
        })
    
    # Sort by health score (worst first)
    function_health.sort(key=lambda x: x["healthScore"])
    
    # Undocumented functions count
    undocumented_count = total_functions - documented_count
    
    # Overall health score
    if total_functions == 0:
        overall_health = 0
    else:
        # Weighted: 40% coverage, 30% claim density (capped), 30% violation rate
        coverage_score = coverage * 100
        density_score = min(claim_density / 3, 1) * 100  # 3+ claims = max
        violation_score = (1 - violation_rate) * 100
        overall_health = int(0.4 * coverage_score + 0.3 * density_score + 0.3 * violation_score)
    
    return {
        "analysisId": analysis_id,
        "overallHealth": overall_health,
        "metrics": {
            "totalFunctions": total_functions,
            "documentedFunctions": documented_count,
            "undocumentedFunctions": undocumented_count,
            "coverage": round(coverage * 100, 1),
            "totalClaims": total_claims,
            "totalViolations": total_violations,
            "claimDensity": round(claim_density, 2),
            "violationRate": round(violation_rate * 100, 1),
        },
        "functions": function_health,
    }


def _count_all_functions(source_code: str, language: str) -> int:
    """Count all functions in source code, including undocumented ones."""
    import ast as ast_module
    
    if language != "python":
        # For non-Python, use a simple heuristic
        # Count lines that look like function definitions
        count = 0
        for line in source_code.splitlines():
            stripped = line.strip()
            if stripped.startswith("def ") or stripped.startswith("async def "):
                count += 1
            elif language in ("javascript", "typescript"):
                if "function " in stripped or "=>" in stripped:
                    count += 1
        return max(count, 1)
    
    try:
        tree = ast_module.parse(source_code)
    except SyntaxError:
        return 1
    
    count = 0
    for node in ast_module.walk(tree):
        if isinstance(node, (ast_module.FunctionDef, ast_module.AsyncFunctionDef)):
            count += 1
    
    return count
