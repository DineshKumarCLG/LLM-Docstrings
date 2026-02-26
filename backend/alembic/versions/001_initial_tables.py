"""Initial tables: analyses, function_records, claims, violations

Revision ID: 001_initial
Revises: None
Create Date: 2024-01-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column("source_code", sa.Text(), nullable=False),
        sa.Column("llm_provider", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("total_functions", sa.Integer(), server_default="0"),
        sa.Column("total_claims", sa.Integer(), server_default="0"),
        sa.Column("total_violations", sa.Integer(), server_default="0"),
        sa.Column("bcv_rate", sa.Float(), server_default="0.0"),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "function_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.String(36),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("qualified_name", sa.String(512), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("lineno", sa.Integer(), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("docstring", sa.Text(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("return_annotation", sa.String(255), nullable=True),
        sa.Column("raise_statements", sa.JSON(), nullable=True),
        sa.Column("mutation_patterns", sa.JSON(), nullable=True),
    )

    op.create_table(
        "claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "function_id",
            sa.String(36),
            sa.ForeignKey("function_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(10), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("predicate_object", sa.Text(), nullable=False),
        sa.Column("conditionality", sa.Text(), nullable=True),
        sa.Column("source_line", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
    )

    op.create_table(
        "violations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "claim_id",
            sa.String(36),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("test_code", sa.Text(), nullable=False),
        sa.Column("stdout", sa.Text(), nullable=True),
        sa.Column("stderr", sa.Text(), nullable=True),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("expected", sa.String(512), nullable=True),
        sa.Column("actual", sa.String(512), nullable=True),
        sa.Column("execution_time_ms", sa.Float(), server_default="0.0"),
    )


def downgrade() -> None:
    op.drop_table("violations")
    op.drop_table("claims")
    op.drop_table("function_records")
    op.drop_table("analyses")
