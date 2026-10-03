"""timestamptz: convert all timestamp columns to TIMESTAMP WITH TIME ZONE

Existing naive values were written as UTC, so they are interpreted as UTC.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column, nullable)
COLUMNS: list[tuple[str, str, bool]] = [
    ("drivers", "created_at", False),
    ("consents", "granted_at", False),
    ("trips", "started_at", False),
    ("trips", "ended_at", True),
    ("trips", "created_at", False),
    ("events", "time", False),
    ("incidents", "time", False),
    ("incidents", "created_at", False),
    ("trip_chunks", "received_at", False),
    ("trip_features", "created_at", False),
    ("trip_scores", "created_at", False),
]


def upgrade() -> None:
    for table, column, nullable in COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=nullable,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    for table, column, nullable in COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=nullable,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
