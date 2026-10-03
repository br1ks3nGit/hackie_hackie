from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings

DOTENV_KEYS = (
    "DATABASE_URL",
    "TEST_DATABASE_URL",
    "SESSION_SECRET",
)


def test_settings_accepts_test_database_url_in_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Real env vars (set by conftest and CI) take precedence over the dotenv file; clear them so
    # this test only sees the file.
    for key in DOTENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql+psycopg://u:p@localhost:5432/db\n"
        "TEST_DATABASE_URL=postgresql+psycopg://u:p@localhost:5432/db_test\n"
        "SESSION_SECRET=test-session-secret-0123456789-abcdefghij\n"
    )
    settings = Settings(_env_file=env_file)
    assert settings.test_database_url == "postgresql+psycopg://u:p@localhost:5432/db_test"


def test_short_session_secret_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(session_secret="short", _env_file=None)
