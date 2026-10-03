import secrets
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Form, Header, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

LOGIN_URL = "/dashboard/login"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
SESSION_MAX_AGE_S = 8 * 60 * 60

HK_TZ = ZoneInfo("Asia/Hong_Kong")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def _hk_time(value: datetime | None) -> str:
    """Format a datetime in Hong Kong local time (naive values are taken as UTC)."""
    if value is None:
        return "-"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(HK_TZ).strftime("%Y-%m-%d %H:%M")


templates.env.filters["hk_time"] = _hk_time


class LoginRequired(Exception):
    """Raised by `require_login` when the request has no staff session."""


def login_required_handler(request: Request, exc: Exception) -> Response:
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=200, headers={"HX-Redirect": LOGIN_URL})
    return RedirectResponse(LOGIN_URL, status_code=303)


def get_csrf_token(request: Request) -> str:
    """Return the session's CSRF token, creating it on first use."""
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def start_session(request: Request, username: str) -> None:
    """Replace any existing session (rotates the CSRF token) with a logged-in one."""
    request.session.clear()
    request.session["user"] = username
    request.session["csrf_token"] = secrets.token_urlsafe(32)


def require_login(request: Request) -> str:
    user = request.session.get("user")
    if not user:
        raise LoginRequired
    return user


def verify_csrf(
    request: Request,
    csrf_token: str | None = Form(None),
    x_csrf_token: str | None = Header(None),
) -> None:
    """Router-level check for state-changing requests (form field or X-CSRF-Token header)."""
    if request.method in SAFE_METHODS:
        return
    expected = request.session.get("csrf_token")
    supplied = csrf_token or x_csrf_token
    if not expected or not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token")
