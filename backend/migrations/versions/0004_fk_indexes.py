"""fk indexes

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-03 20:17:14.747083

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain CREATE INDEX is fine at POC size; use postgresql_concurrently=True
    # (inside an autocommit_block) for large tables.
    op.create_index(op.f("ix_consents_driver_id"), "consents", ["driver_id"], unique=False)
    op.create_index(op.f("ix_events_trip_id"), "events", ["trip_id"], unique=False)
    op.create_index(op.f("ix_incidents_driver_id"), "incidents", ["driver_id"], unique=False)
    op.create_index(op.f("ix_incidents_trip_id"), "incidents", ["trip_id"], unique=False)
    op.create_index(op.f("ix_trips_driver_id"), "trips", ["driver_id"], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    op.drop_index(op.f("ix_trips_driver_id"), table_name="trips")
    op.drop_index(op.f("ix_incidents_trip_id"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_driver_id"), table_name="incidents")
    op.drop_index(op.f("ix_events_trip_id"), table_name="events")
    op.drop_index(op.f("ix_consents_driver_id"), table_name="consents")
    # ### end Alembic commands ###
