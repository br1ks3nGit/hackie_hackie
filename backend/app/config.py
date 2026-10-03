from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SESSION_SECRET_LEN = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", protected_namespaces=()
    )

    database_url: str = "postgresql+psycopg://drivescore:drivescore@localhost:5432/drivescore"
    test_database_url: str | None = None
    insurer_api_key: str  # required, no default — set via env or .env
    driver_api_key_salt: str  # required, no default — set via env or .env
    session_secret: str  # required, no default - signs dashboard session cookies
    dashboard_username: str = "admin"
    dashboard_password_hash: str | None = None  # scrypt:<n>:<r>:<p>:<salt_hex>:<hash_hex>
    session_https_only: bool = False
    cors_origins: str = "http://localhost:3000,http://localhost:19006"
    data_dir: str = "./data/raw"
    model_path: str = "./models/model.pkl"
    trip_min_distance_km: float = 1.0
    trip_max_gps_gap_s: float = 30.0
    trip_min_duration_s: float = 60.0

    @field_validator("session_secret")
    @classmethod
    def _session_secret_long_enough(cls, value: str) -> str:
        value = value.strip()
        if len(value) < MIN_SESSION_SECRET_LEN:
            raise ValueError(
                f"SESSION_SECRET must be at least {MIN_SESSION_SECRET_LEN} characters; generate "
                'one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
