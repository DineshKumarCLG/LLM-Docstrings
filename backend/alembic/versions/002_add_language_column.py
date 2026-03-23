"""Add language column to analyses table

Revision ID: 002_add_language
Revises: 001_initial
Create Date: 2024-01-15 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002_add_language"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column(
            "language",
            sa.String(20),
            nullable=False,
            server_default="python",
        ),
    )


def downgrade() -> None:
    op.drop_column("analyses", "language")
