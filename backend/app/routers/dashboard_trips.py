from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.dashboard_auth import get_csrf_token, require_login, templates, verify_csrf
from app.database import get_db
from app.services.trips import get_trip_detail, is_coord

router = APIRouter(
    prefix="/dashboard",
    include_in_schema=False,
    dependencies=[Depends(verify_csrf)],
)


def _located(items: list) -> list[dict]:
    """Items with coordinates as plain dicts for the map JSON block."""
    return [
        {
            "type": getattr(i, "type", "crash"),
            "time": i.time.isoformat(),
            "peak_g": i.peak_g,
            "lat": i.lat,
            "lon": i.lon,
        }
        for i in items
        if is_coord(i.lat) and is_coord(i.lon)
    ]


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
    map_data = {
        "route": detail.route,
        "events": _located(detail.events),
        "crashes": _located(detail.crashes),
    }
    return templates.TemplateResponse(
        request, "trip_detail.html", {**context, "t": detail, "map_data": map_data}
    )
