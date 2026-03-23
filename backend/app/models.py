"""SQLAlchemy ORM models for the VeriDoc BCV Detection Pipeline.

Defines the four core tables — Analysis, FunctionRecord, Claim, Violation —
with UUID primary keys, cascade-delete foreign keys, JSON columns, and
datetime defaults matching the ER diagram in the design document.

Requirements: 6.5, 10.5, 15 (cascade deletion)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Declarative base for all VeriDoc models."""

    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Analysis(Base):
    """Top-level analysis record representing a single pipeline execution."""

    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_code: Mapped[str] = mapped_column(Text, nullable=False)
    llm_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    total_functions: Mapped[int] = mapped_column(Integer, default=0)
    total_claims: Mapped[int] = mapped_column(Integer, default=0)
    total_violations: Mapped[int] = mapped_column(Integer, default=0)
    bcv_rate: Mapped[float] = mapped_column(Float, default=0.0)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    language: Mapped[str] = mapped_column(
        String(20), nullable=False, default="python"
    )

    # Relationships
    functions: Mapped[list[FunctionRecord]] = relationship(
        "FunctionRecord",
        back_populates="analysis",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Analysis id={self.id!r} status={self.status!r}>"


class FunctionRecord(Base):
    """A single Python function extracted from the analysed source."""

    __tablename__ = "function_records"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    analysis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    qualified_name: Mapped[str] = mapped_column(String(512), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    lineno: Mapped[int] = mapped_column(Integer, nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    docstring: Mapped[str | None] = mapped_column(Text, nullable=True)
    params: Mapped[list | None] = mapped_column(JSON, nullable=True)
    return_annotation: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    raise_statements: Mapped[list | None] = mapped_column(JSON, nullable=True)
    mutation_patterns: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Relationships
    analysis: Mapped[Analysis] = relationship(
        "Analysis", back_populates="functions"
    )
    claims: Mapped[list[Claim]] = relationship(
        "Claim",
        back_populates="function_record",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<FunctionRecord id={self.id!r} name={self.name!r}>"


class Claim(Base):
    """A single behavioral claim extracted from a function's docstring."""

    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    function_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("function_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(10), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    predicate_object: Mapped[str] = mapped_column(Text, nullable=False)
    conditionality: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_line: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    function_record: Mapped[FunctionRecord] = relationship(
        "FunctionRecord", back_populates="claims"
    )
    violation: Mapped[Violation | None] = relationship(
        "Violation",
        back_populates="claim",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<Claim id={self.id!r} category={self.category!r}>"


class Violation(Base):
    """Test execution result indicating a behavioral contract violation."""

    __tablename__ = "violations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    claim_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    test_code: Mapped[str] = mapped_column(Text, nullable=False)
    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected: Mapped[str | None] = mapped_column(String(512), nullable=True)
    actual: Mapped[str | None] = mapped_column(String(512), nullable=True)
    execution_time_ms: Mapped[float] = mapped_column(Float, default=0.0)

    # Relationships
    claim: Mapped[Claim] = relationship(
        "Claim", back_populates="violation"
    )

    def __repr__(self) -> str:
        return f"<Violation id={self.id!r} outcome={self.outcome!r}>"
