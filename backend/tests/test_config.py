from pathlib import Path

from app.config import Settings


def test_settings_accepts_test_database_url_in_dotenv(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql+psycopg://u:p@localhost:5432/db\n"
        "TEST_DATABASE_URL=postgresql+psycopg://u:p@localhost:5432/db_test\n"
        "INSURER_API_KEY=insurer-key\n"
        "DRIVER_API_KEY_SALT=salt\n"
    )
    settings = Settings(_env_file=env_file)
    assert settings.test_database_url == "postgresql+psycopg://u:p@localhost:5432/db_test"
