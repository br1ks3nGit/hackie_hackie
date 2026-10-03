import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.config import get_settings
from app.dashboard_auth import (
    get_csrf_token,
    require_login,
    start_session,
    templates,
    verify_csrf,
)
from app.services.passwords import verify_password

router = APIRouter(
    prefix="/dashboard",
    include_in_schema=False,
    dependencies=[Depends(verify_csrf)],
)

NOT_CONFIGURED_MSG = "Dashboard login is not configured. Set DASHBOARD_PASSWORD_HASH."
INVALID_CREDENTIALS_MSG = "Invalid username or password"
# Verified against when the username is wrong so timing does not reveal valid usernames.
_DUMMY_HASH = "scrypt:32768:8:1:" + "00" * 16 + ":" + "00" * 32


def _render_login(
    request: Request, error: str | None = None, username: str = "", status_code: int = 200
) -> HTMLResponse:
    context = {"csrf_token": get_csrf_token(request), "error": error, "username": username}
    return templates.TemplateResponse(request, "login.html", context, status_code=status_code)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> Response:
    if request.session.get("user"):
        return RedirectResponse("/dashboard", status_code=303)
    return _render_login(request)


@router.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(""), password: str = Form("")) -> Response:
    settings = get_settings()
    if not settings.dashboard_password_hash:
        return _render_login(request, NOT_CONFIGURED_MSG, username, status_code=401)
    user_ok = secrets.compare_digest(username.encode(), settings.dashboard_username.encode())
    stored = settings.dashboard_password_hash if user_ok else _DUMMY_HASH
    password_ok = verify_password(password, stored)
    if not (user_ok and password_ok):
        return _render_login(request, INVALID_CREDENTIALS_MSG, username, status_code=401)
    start_session(request, settings.dashboard_username)
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/dashboard/login", status_code=303)


@router.get("", response_class=HTMLResponse)
def overview(request: Request, user: str = Depends(require_login)) -> HTMLResponse:
    context = {"csrf_token": get_csrf_token(request), "user": user, "active": "overview"}
    return templates.TemplateResponse(request, "overview.html", context)
