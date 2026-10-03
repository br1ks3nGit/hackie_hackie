import atexit
import os
import shutil
import tempfile
from pathlib import Path

from sqlalchemy.engine import make_url

# Must be set before any test module imports the app: get_settings() is
# lru_cached, and conftest is imported by pytest before test modules.
os.environ.setdefault("INSURER_API_KEY", "test-insurer-key")
os.environ.setdefault("DRIVER_API_KEY_SALT", "test-salt")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-0123456789-abcdefghij")
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://drivescore:drivescore@localhost:5432/drivescore_test",
)
_test_db_name = make_url(os.environ["DATABASE_URL"]).database or ""
if not _test_db_name.endswith("_test"):
    raise RuntimeError(
        f"Refusing to run tests: TEST_DATABASE_URL database {_test_db_name!r} must end with "
        "'_test' because tests TRUNCATE every table. Point it at a dedicated test database."
    )
# Raw chunk files must never land in the real backend/data/raw/.
_data_dir = tempfile.mkdtemp(prefix="drivescore-test-data-")
os.environ["DATA_DIR"] = _data_dir
atexit.register(shutil.rmtree, _data_dir, ignore_errors=True)

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

import app.models  # noqa: E402, F401
from app.database import Base, engine  # noqa: E402

BACKEND_DIR = Path(__file__).parent


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return config


@pytest.fixture(scope="session", autouse=True)
def migrated_db(alembic_config: Config) -> None:
    """Build the test schema from the migrations (also proves they apply cleanly).

    Starts from an empty public schema; safe because the module guard above only allows a
    database whose name ends with '_test'.
    """
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config, "head")


@pytest.fixture(autouse=True)
def clean_db(migrated_db: None) -> None:
    """Empty every table before each test."""
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
