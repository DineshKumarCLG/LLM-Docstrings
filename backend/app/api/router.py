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
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.models import Analysis, Claim, FunctionRecord, Violation
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

    # Validate Python syntax (Requirements 1.1, 1.2, 1.3)
    _validate_python(code)

    # Sanitize for safe frontend rendering (Requirement 11.3)
    code = sanitize_source(code)

    # Persist Analysis record
    analysis = Analysis(
        filename=filename,
        source_code=code,
        llm_provider=llm_provider.value,
        status=AnalysisStatus.PENDING.value,
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
