from typing import NamedTuple
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.dashboard_auth import get_csrf_token, require_login, templates, verify_csrf
from app.database import get_db
from app.services.incidents import INCIDENT_FILTERS, IncidentsPage, list_incidents

router = APIRouter(
    prefix="/dashboard",
    include_in_schema=False,
    dependencies=[Depends(verify_csrf)],
)

STATUS_LABELS = {
    "help_needed": "Help needed",
    "no_response": "No response",
    "ok": "OK",
    "unconfirmed": "Unconfirmed",
}
PAGE_URL = "/dashboard/incidents"
PARTIAL_URL = "/dashboard/partials/incidents"


class Filters(NamedTuple):
    status: str | None
    page: int


def parse_filters(status: str | None = None, page: str | None = None) -> Filters:
    """Validate query input; unknown values fall back to defaults."""
    try:
        clean_page = max(1, int(page or 1))
    except ValueError:
        clean_page = 1
    return Filters(status if status in INCIDENT_FILTERS else None, clean_page)


def _link(status: str | None, page: int) -> dict[str, str]:
    """Plain href (works without JS) and the partial URL HTMX fetches for the same state."""
    params: dict[str, str | int] = {}
    if status:
        params["status"] = status
    if page > 1:
        params["page"] = page
    query = f"?{urlencode(params)}" if params else ""
    return {"href": PAGE_URL + query, "hx": PARTIAL_URL + query}


def _table_context(status: str | None, result: IncidentsPage) -> dict:
    return {
        "incidents": result.items,
        "total": result.total,
        "page": result.page,
        "pages": result.pages,
        "first": (result.page - 1) * result.page_size + 1 if result.total else 0,
        "last": (result.page - 1) * result.page_size + len(result.items),
        "status": status,
        "status_label": STATUS_LABELS.get(status or ""),
        "prev_link": _link(status, result.page - 1) if result.page > 1 else None,
        "next_link": _link(status, result.page + 1) if result.page < result.pages else None,
        "clear_link": _link(None, 1),
    }


@router.get("/incidents", response_class=HTMLResponse)
def incidents_page(
    request: Request,
    f: Filters = Depends(parse_filters),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    context = {
        "csrf_token": get_csrf_token(request),
        "user": user,
        "active": "incidents",
        "status_options": STATUS_LABELS,
        **_table_context(f.status, list_incidents(db, f.status, f.page)),
    }
    return templates.TemplateResponse(request, "incidents.html", context)


@router.get("/partials/incidents", response_class=HTMLResponse)
def incidents_partial(
    request: Request,
    f: Filters = Depends(parse_filters),
    _user: str = Depends(require_login),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    result = list_incidents(db, f.status, f.page)
    response = templates.TemplateResponse(
        request,
        "partials/incidents_table.html",
        {**_table_context(f.status, result), "oob": True},
    )
    response.headers["HX-Push-Url"] = _link(f.status, result.page)["href"]
    return response
