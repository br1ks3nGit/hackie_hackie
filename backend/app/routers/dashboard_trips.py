from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.dashboard_auth import get_csrf_token, require_login, templates, verify_csrf
from app.database import get_db
from app.services.trips import get_trip_detail

router = APIRouter(
    prefix="/dashboard",
    include_in_schema=False,
    dependencies=[Depends(verify_csrf)],
)


@router.get("/trips/{trip_id}", response_class=HTMLResponse)
def trip_detail_page(
    trip_id: str,
    request: Request,
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    context = {"csrf_token": get_csrf_token(request), "user": user, "active": "drivers"}
    detail = get_trip_detail(db, trip_id)
    if detail is None:
        return templates.TemplateResponse(
            request, "trip_not_found.html", {**context, "trip_id": trip_id}, status_code=404
        )
    return templates.TemplateResponse(request, "trip_detail.html", {**context, "t": detail})
