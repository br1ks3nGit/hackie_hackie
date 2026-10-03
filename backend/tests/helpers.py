"""Shared test setup: a dashboard user and an insurer API key, both stored in Postgres."""

from app.database import SessionLocal
from app.services.api_keys import create_api_key
from app.services.users import create_user

ADMIN_USER = "admin"
ADMIN_PASSWORD = "correct horse battery staple"


def create_admin() -> None:
    with SessionLocal() as db:
        create_user(db, ADMIN_USER, ADMIN_PASSWORD)


def insurer_headers() -> dict[str, str]:
    """Headers with a freshly generated insurer API key."""
    with SessionLocal() as db:
        _, plaintext = create_api_key(db, "test", None)
    return {"X-API-Key": plaintext}
