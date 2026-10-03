"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-03 23:19:48.819112

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "drivers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("api_key_hash", sa.String(), nullable=False),
        sa.Column("emergency_contact_name", sa.String(), nullable=True),
        sa.Column("emergency_contact_phone", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "consents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("driver_id", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["driver_id"],
            ["drivers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_consents_driver_id"), "consents", ["driver_id"], unique=False)
    op.create_table(
        "trips",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("driver_id", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            comment="uploading, processing, done, failed (see docs/data-model.md)",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "trip_type",
            sa.String(),
            nullable=True,
            comment="driver, passenger, transit, unknown; null until classified",
        ),
        sa.Column(
            "label_source",
            sa.String(),
            nullable=True,
            comment="Who decided trip_type: bluetooth, rules, user; null if unlabelled",
        ),
        sa.Column(
            "driver_likelihood",
            sa.Float(),
            nullable=True,
            comment="Classifier probability 0 to 1 that the user was driving",
        ),
        sa.Column(
            "transit_line",
            sa.String(),
            nullable=True,
            comment="Matched transit line name for transit trips",
        ),
        sa.Column(
            "bluetooth_connected_ratio",
            sa.Float(),
            nullable=True,
            comment="Share 0 to 1 of the trip the phone was on car Bluetooth",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["driver_id"],
            ["drivers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trips_driver_id"), "trips", ["driver_id"], unique=False)
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trip_id", sa.String(), nullable=False),
        sa.Column(
            "type",
            sa.String(),
            nullable=False,
            comment="harsh_brake, harsh_accel, sharp_corner, speeding",
        ),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "peak_g", sa.Float(), nullable=True, comment="Peak acceleration in g; null for speeding"
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_events_trip_id"), "events", ["trip_id"], unique=False)
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("driver_id", sa.String(), nullable=False),
        sa.Column("trip_id", sa.String(), nullable=True),
        sa.Column("type", sa.String(), nullable=False, comment="Incident kind; crash"),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("peak_g", sa.Float(), nullable=True, comment="Peak acceleration in g"),
        sa.Column(
            "confirmed",
            sa.String(),
            nullable=True,
            comment="Driver answer: ok, help_needed, no_response; null if none",
        ),
        sa.Column(
            "sensor_snapshot",
            sa.JSON(),
            nullable=True,
            comment="JSON with peak_g, imu_samples, duration_ms around the crash",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["driver_id"],
            ["drivers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_incidents_driver_id"), "incidents", ["driver_id"], unique=False)
    op.create_index(op.f("ix_incidents_trip_id"), "incidents", ["trip_id"], unique=False)
    op.create_table(
        "trip_chunks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trip_id", sa.String(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column(
            "file_path",
            sa.String(),
            nullable=False,
            comment="Gzipped JSON chunk file under DATA_DIR",
        ),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id", "seq", name="uq_trip_chunk"),
    )
    op.create_table(
        "trip_features",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trip_id", sa.String(), nullable=False),
        sa.Column(
            "features", sa.JSON(), nullable=False, comment="TripFeatures JSON (app/features.py)"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id"),
    )
    op.create_table(
        "trip_scores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trip_id", sa.String(), nullable=False),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            comment="Model output 0 to 1, higher = riskier; score = 100 * (1 - confidence)",
        ),
        sa.Column(
            "score", sa.Integer(), nullable=False, comment="Trip score 0 to 100, higher is safer"
        ),
        sa.Column(
            "tier",
            sa.String(),
            nullable=False,
            comment="Risk tier A to E from score (A >= 90, B >= 75, C >= 60, D >= 40)",
        ),
        sa.Column(
            "model_version",
            sa.String(),
            nullable=False,
            comment="Version of the model that produced the score",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column(
            "password_hash",
            sa.String(),
            nullable=False,
            comment="scrypt:<n>:<r>:<p>:<salt_hex>:<hash_hex> (app/services/passwords.py)",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            comment="False blocks login and ends sessions",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_login_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Null until the first login",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False, comment="Label, e.g. the consumer"),
        sa.Column(
            "key_prefix",
            sa.String(),
            nullable=False,
            comment="First characters of the key, shown to recognise it",
        ),
        sa.Column(
            "key_hash",
            sa.String(),
            nullable=False,
            comment="Salted SHA-256 of the key; the key itself is shown once and never stored",
        ),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Null until first used",
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Set when revoked; revoked keys are denied",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index(
        op.f("ix_api_keys_created_by_user_id"), "api_keys", ["created_by_user_id"], unique=False
    )
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_index(op.f("ix_api_keys_created_by_user_id"), table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_table("users")
    op.drop_table("trip_scores")
    op.drop_table("trip_features")
    op.drop_table("trip_chunks")
    op.drop_index(op.f("ix_incidents_trip_id"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_driver_id"), table_name="incidents")
    op.drop_table("incidents")
    op.drop_index(op.f("ix_events_trip_id"), table_name="events")
    op.drop_table("events")
    op.drop_index(op.f("ix_trips_driver_id"), table_name="trips")
    op.drop_table("trips")
    op.drop_index(op.f("ix_consents_driver_id"), table_name="consents")
    op.drop_table("consents")
    op.drop_table("drivers")
