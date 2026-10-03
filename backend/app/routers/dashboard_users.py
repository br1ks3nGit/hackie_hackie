from typing import NamedTuple

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dashboard_auth import (
    flash,
    get_csrf_token,
    pop_flash,
    require_user,
    templates,
    verify_csrf,
)
from app.database import get_db
from app.models import User
from app.services import users as user_service

router = APIRouter(
    prefix="/dashboard/users",
    include_in_schema=False,
    dependencies=[Depends(verify_csrf)],
)

PAGE_URL = "/dashboard/users"


class PasswordForm(NamedTuple):
    password: str
    confirm: str


def password_form(password: str = Form(""), password_confirm: str = Form("")) -> PasswordForm:
    return PasswordForm(password, password_confirm)


def _checked_password(form: PasswordForm) -> str:
    """The new password if the two entries match and meet the dashboard rule."""
    if form.password != form.confirm:
        raise ValueError("Passwords do not match.")
    return user_service.validate_password(form.password)


def _render(
    request: Request,
    db: Session,
    current: User,
    error: str | None = None,
    form_username: str = "",
) -> HTMLResponse:
    context = {
        "csrf_token": get_csrf_token(request),
        "user": current.username,
        "current_id": current.id,
        "active": "users",
        "users": db.scalars(select(User).order_by(User.username)).all(),
        "notice": pop_flash(request),
        "error": error,
        "form_username": form_username,
        "min_password_len": user_service.MIN_PASSWORD_LEN,
    }
    status_code = 422 if error else 200
    return templates.TemplateResponse(request, "users.html", context, status_code=status_code)


def _back(request: Request, kind: str, message: str) -> RedirectResponse:
    flash(request, kind, message)
    return RedirectResponse(PAGE_URL, status_code=303)


@router.get("", response_class=HTMLResponse)
def users_page(
    request: Request, current: User = Depends(require_user), db: Session = Depends(get_db)
) -> HTMLResponse:
    return _render(request, db, current)


@router.post("")
def create_user(
    request: Request,
    username: str = Form(""),
    form: PasswordForm = Depends(password_form),
    current: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    try:
        user = user_service.create_user(db, username, _checked_password(form))
    except ValueError as exc:
        return _render(request, db, current, str(exc), username)
    return _back(request, "success", f"User '{user.username}' created.")


@router.post("/{user_id}/password")
def reset_password(
    request: Request,
    user_id: int,
    form: PasswordForm = Depends(password_form),
    _current: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    target = db.get(User, user_id)
    if target is None:
        return _back(request, "error", "User not found.")
    try:
        user_service.set_password(db, target, _checked_password(form))
    except ValueError as exc:
        return _back(request, "error", str(exc))
    return _back(request, "success", f"Password changed for '{target.username}'.")


@router.post("/{user_id}/active")
def set_active(
    request: Request,
    user_id: int,
    active: str = Form(""),
    current: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    target = db.get(User, user_id)
    if target is None:
        return _back(request, "error", "User not found.")
    enable = active == "true"
    if not enable and target.id == current.id:
        return _back(request, "error", "You cannot deactivate your own account.")
    try:
        user_service.set_active(db, target, enable)
    except ValueError as exc:
        return _back(request, "error", str(exc))
    state = "activated" if enable else "deactivated"
    return _back(request, "success", f"User '{target.username}' {state}.")
