"""Core enums, data types, and Pydantic schemas for the VeriDoc BCV Detection Pipeline.

Defines the six-category BCV taxonomy, pipeline status model, claim formal
definition c_i = (τ_i, σ_i, ν_i, κ_i), and all request/response schemas used
across the BCE, DTS, and RV stages.

Requirements: 2.6, 10.1, 10.2, 10.3
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums (str-based for JSON serialization)
# ---------------------------------------------------------------------------


class BCVCategory(str, Enum):
    """Six-category BCV taxonomy from the VeriDoc paper."""

    RSV = "RSV"  # Return Specification Violation
    PCV = "PCV"  # Parameter Contract Violation
    SEV = "SEV"  # Side Effect Violation
    ECV = "ECV"  # Exception Contract Violation
    COV = "COV"  # Completeness Omission Violation
    CCV = "CCV"  # Complexity Contract Violation


class LLMProvider(str, Enum):
    """Supported LLM providers for docstring generation and test synthesis."""

    GPT4_1_MINI = "gpt-4.1-mini"
    CLAUDE_SONNET = "claude-sonnet-4-20250514"
    GEMINI_FLASH = "gemini-3-flash-preview"
    BEDROCK = "bedrock"


class AnalysisStatus(str, Enum):
    """Pipeline execution status, following the stage transition sequence."""

    PENDING = "pending"
    BCE_RUNNING = "bce_running"
    BCE_COMPLETE = "bce_complete"
    DTS_RUNNING = "dts_running"
    DTS_COMPLETE = "dts_complete"
    RV_RUNNING = "rv_running"
    COMPLETE = "complete"
    FAILED = "failed"


class TestOutcome(str, Enum):
    """Outcome classification for a single synthesized test execution."""

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    UNDETERMINED = "undetermined"


# ---------------------------------------------------------------------------
# Pipeline data models
# ---------------------------------------------------------------------------


class Claim(BaseModel):
    """Single behavioral claim: c_i = (τ_i, σ_i, ν_i, κ_i).

    Validation rules (Requirements 10.1, 10.2, 10.3):
    - category must be a valid BCVCategory
    - subject must be non-empty
    - predicate_object must be non-empty
    - source_line must be a positive integer
    """

    category: BCVCategory
    subject: str = Field(..., min_length=1)
    predicate_object: str = Field(..., min_length=1)
    conditionality: Optional[str] = None
    source_line: int = Field(..., gt=0)
    raw_text: str = Field(..., min_length=1)

    @field_validator("subject", "predicate_object", "raw_text")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field must not be blank or whitespace-only")
        return v


class FunctionInfo(BaseModel):
    """Structural information extracted from a Python function via AST."""

    name: str
    qualified_name: str
    source: str
    lineno: int
    signature: str
    docstring: Optional[str] = None
    params: list[dict] = Field(default_factory=list)
    return_annotation: Optional[str] = None
    raise_statements: list[dict] = Field(default_factory=list)
    mutation_patterns: list[dict] = Field(default_factory=list)


class ClaimSchema(BaseModel):
    """C(F) = {c_i = (τ_i, σ_i, ν_i, κ_i)} — all claims for one function."""

    function: FunctionInfo
    claims: list[Claim] = Field(default_factory=list)


class SynthesizedTest(BaseModel):
    """Output of the DTS stage for a single claim."""

    claim: Claim
    test_code: str
    test_function_name: str
    synthesis_model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ViolationRecord(BaseModel):
    """Single test execution result from the RV stage."""

    function_id: str
    claim: Claim
    test_code: str
    outcome: TestOutcome
    stdout: str = ""
    stderr: str = ""
    traceback: Optional[str] = None
    expected: Optional[str] = None
    actual: Optional[str] = None
    execution_time_ms: float = 0.0


class ViolationReport(BaseModel):
    """Aggregated verification results for one function."""

    analysis_id: str
    function_name: str
    total_claims: int
    violations: list[ViolationRecord] = Field(default_factory=list)
    pass_count: int = 0
    fail_count: int = 0
    error_count: int = 0
    bcv_rate: float = Field(default=0.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# API request / response models
# ---------------------------------------------------------------------------


class AnalysisCreate(BaseModel):
    """Request body for creating a new analysis."""

    source_code: Optional[str] = None
    llm_provider: LLMProvider = LLMProvider.GEMINI_FLASH
    generate_docstrings: bool = False


class AnalysisResponse(BaseModel):
    """Response body for an analysis record."""

    id: UUID
    status: AnalysisStatus
    filename: Optional[str] = None
    llm_provider: LLMProvider
    total_functions: int = 0
    total_claims: int = 0
    total_violations: int = 0
    bcv_rate: float = 0.0
    created_at: datetime
    completed_at: Optional[datetime] = None
