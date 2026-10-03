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
from app.models import ApiKey, AppSetting, User
from app.services import api_keys as key_service

router = APIRouter(
    prefix="/dashboard/api-keys",
    include_in_schema=False,
    dependencies=[Depends(verify_csrf)],
)

PAGE_URL = "/dashboard/api-keys"


def _render(
    request: Request,
    db: Session,
    current: User,
    error: str | None = None,
    created: tuple[str, str] | None = None,
) -> HTMLResponse:
    """`created` is (name, plaintext key) for a key just made; shown once, never stored."""
    rows = db.execute(
        select(ApiKey, User.username)
        .outerjoin(User, ApiKey.created_by_user_id == User.id)
        .order_by(ApiKey.id.desc())
    ).all()
    key_service.get_salt(db)  # generate the salt now so the page can show it exists
    salt = db.get(AppSetting, key_service.SALT_SETTING)
    context = {
        "csrf_token": get_csrf_token(request),
        "user": current.username,
        "active": "api_keys",
        "keys": [{"key": key, "created_by": username} for key, username in rows],
        "salt_created_at": salt.created_at if salt else None,
        "notice": pop_flash(request),
        "error": error,
        "new_name": created[0] if created else None,
        "new_key": created[1] if created else None,
    }
    response = templates.TemplateResponse(
        request, "api_keys.html", context, status_code=422 if error else 200
    )
    if created:
        response.headers["Cache-Control"] = "no-store"
    return response


@router.get("", response_class=HTMLResponse)
def api_keys_page(
    request: Request, current: User = Depends(require_user), db: Session = Depends(get_db)
) -> HTMLResponse:
    return _render(request, db, current)


@router.post("")
def create_api_key(
    request: Request,
    name: str = Form(""),
    current: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    try:
        record, plaintext = key_service.create_api_key(db, name, current.id)
    except ValueError as exc:
        return _render(request, db, current, error=str(exc))
    return _render(request, db, current, created=(record.name, plaintext))


@router.post("/{key_id}/revoke")
def revoke_api_key(
    request: Request,
    key_id: int,
    _current: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if key_service.revoke_api_key(db, key_id):
        flash(request, "success", "API key revoked. It can no longer be used.")
    else:
        flash(request, "error", "API key not found.")
    return RedirectResponse(PAGE_URL, status_code=303)
