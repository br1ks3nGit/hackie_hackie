from alembic import command
from alembic.config import Config


def test_models_match_migrations(alembic_config: Config) -> None:
    """Fails (CommandError) if models changed without a new Alembic revision."""
    command.check(alembic_config)
