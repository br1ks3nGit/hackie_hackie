from datetime import UTC, datetime, timedelta

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.database import engine


def test_models_match_migrations(alembic_config: Config) -> None:
    """Fails (CommandError) if models changed without a new Alembic revision."""
    command.check(alembic_config)


def test_timestamptz_migration_round_trip(alembic_config: Config) -> None:
    """0002 downgrade/upgrade keeps instants: naive values are read as UTC both ways."""
    instant = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    try:
        command.downgrade(alembic_config, "0001")
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO drivers (id, api_key_hash, created_at) VALUES ('d1', 'h', :t)"),
                {"t": instant.replace(tzinfo=None)},
            )
        command.upgrade(alembic_config, "0002")
        with engine.connect() as conn:
            value = conn.execute(
                text("SELECT created_at FROM drivers WHERE id = 'd1'")
            ).scalar_one()
        assert value == instant
        assert value.tzinfo is not None
        assert value.utcoffset() == timedelta(0)
    finally:
        command.upgrade(alembic_config, "head")
