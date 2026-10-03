"""Dashboard staff users stored in Postgres."""

import re
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User
from app.services.passwords import hash_password, verify_password

MIN_PASSWORD_LEN = 8
MAX_USERNAME_LEN = 64
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
# Verified against when the username is unknown so timing does not reveal valid usernames.
_DUMMY_HASH = "scrypt:32768:8:1:" + "00" * 16 + ":" + "00" * 32


def validate_username(username: str) -> str:
    username = username.strip()
    if not username:
        raise ValueError("Username must not be empty.")
    if len(username) > MAX_USERNAME_LEN:
        raise ValueError(f"Username must be at most {MAX_USERNAME_LEN} characters.")
    if not USERNAME_PATTERN.match(username):
        raise ValueError("Username may only contain letters, digits, '.', '_' and '-'.")
    return username


def validate_password(password: str) -> str:
    """Rule for passwords typed in the dashboard (the CLI only warns, for local dev)."""
    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LEN} characters.")
    return password


def get_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def create_user(db: Session, username: str, password: str) -> User:
    """Create an active user. Raises ValueError for a bad or taken username or empty password."""
    username = validate_username(username)
    if not password:
        raise ValueError("Password must not be empty.")
    if get_by_username(db, username) is not None:
        raise ValueError(f"User '{username}' already exists.")
    user = User(username=username, password_hash=hash_password(password), is_active=True)
    db.add(user)
    db.commit()
    return user


def set_password(db: Session, user: User, password: str) -> None:
    if not password:
        raise ValueError("Password must not be empty.")
    user.password_hash = hash_password(password)
    db.commit()


def set_active(db: Session, user: User, active: bool) -> None:
    """Enable or disable a user; the last active user cannot be disabled."""
    if not active and user.is_active:
        active_count = db.scalar(select(func.count()).select_from(User).where(User.is_active))
        if active_count <= 1:
            raise ValueError("The last active user cannot be deactivated.")
    user.is_active = active
    db.commit()


def authenticate(db: Session, username: str, password: str) -> User | None:
    """Return the active user for valid credentials and record the login, else None."""
    user = get_by_username(db, username.strip())
    stored = user.password_hash if user else _DUMMY_HASH
    password_ok = verify_password(password, stored)
    if user is None or not user.is_active or not password_ok:
        return None
    user.last_login_at = datetime.now(UTC)
    db.commit()
    return user
