from typing import NamedTuple, get_args
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.dashboard_auth import get_csrf_token, require_login, templates, verify_csrf
from app.database import get_db
from app.services.insurer import DriversPage, get_driver_detail, get_drivers_page
from app.values import Tier

router = APIRouter(
    prefix="/dashboard",
    include_in_schema=False,
    dependencies=[Depends(verify_csrf)],
)

TIERS: tuple[str, ...] = get_args(Tier)
DEFAULT_SORT = "score_desc"
SORT_OPTIONS = {
    "score_desc": "Score, high to low",
    "score_asc": "Score, low to high",
    "multiplier_desc": "Multiplier, high to low",
    "multiplier_asc": "Multiplier, low to high",
}
PAGE_URL = "/dashboard/drivers"
PARTIAL_URL = "/dashboard/partials/drivers"


def _query(tier: str | None, sort: str, page: int) -> str:
    params: dict[str, str | int] = {}
    if tier:
        params["tier"] = tier
    if sort != DEFAULT_SORT:
        params["sort"] = sort
    if page > 1:
        params["page"] = page
    return f"?{urlencode(params)}" if params else ""


def _link(tier: str | None, sort: str, page: int) -> dict[str, str]:
    """Plain href (works without JS) and the partial URL HTMX fetches for the same state."""
    query = _query(tier, sort, page)
    return {"href": PAGE_URL + query, "hx": PARTIAL_URL + query}


class Filters(NamedTuple):
    tier: str | None
    sort: str
    page: int


def parse_filters(
    tier: str | None = None, sort: str | None = None, page: str | None = None
) -> Filters:
    """Validate query input; unknown values fall back to defaults."""
    try:
        clean_page = max(1, int(page or 1))
    except ValueError:
        clean_page = 1
    return Filters(
        tier if tier in TIERS else None,
        sort if sort in SORT_OPTIONS else DEFAULT_SORT,
        clean_page,
    )


def _sort_link(tier: str | None, sort: str, field: str) -> dict[str, str]:
    """Header click: sort by field descending first, then toggle."""
    target = f"{field}_asc" if sort == f"{field}_desc" else f"{field}_desc"
    action = "sort ascending" if target.endswith("_asc") else "sort descending"
    return {**_link(tier, target, 1), "action": action}


def _table_context(tier: str | None, sort: str, result: DriversPage) -> dict:
    return {
        "drivers": result.items,
        "total": result.total,
        "page": result.page,
        "pages": result.pages,
        "first": (result.page - 1) * result.page_size + 1 if result.total else 0,
        "last": (result.page - 1) * result.page_size + len(result.items),
        "tier": tier,
        "sort": sort,
        "prev_link": _link(tier, sort, result.page - 1) if result.page > 1 else None,
        "next_link": _link(tier, sort, result.page + 1) if result.page < result.pages else None,
        "score_sort_link": _sort_link(tier, sort, "score"),
        "multiplier_sort_link": _sort_link(tier, sort, "multiplier"),
        "clear_link": _link(None, sort, 1),
    }


@router.get("/drivers", response_class=HTMLResponse)
def drivers_page(
    request: Request,
    f: Filters = Depends(parse_filters),
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    result = get_drivers_page(db, f.tier, f.sort, f.page)
    context = {
        "csrf_token": get_csrf_token(request),
        "user": user,
        "active": "drivers",
        "tiers": TIERS,
        "sort_options": SORT_OPTIONS,
        **_table_context(f.tier, f.sort, result),
    }
    return templates.TemplateResponse(request, "drivers.html", context)


@router.get("/partials/drivers", response_class=HTMLResponse)
def drivers_partial(
    request: Request,
    f: Filters = Depends(parse_filters),
    _user: str = Depends(require_login),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    result = get_drivers_page(db, f.tier, f.sort, f.page)
    response = templates.TemplateResponse(
        request,
        "partials/drivers_table.html",
        {**_table_context(f.tier, f.sort, result), "oob": True},
    )
    # Keep the address bar on the full-page URL for this state (clamped page included).
    response.headers["HX-Push-Url"] = _link(f.tier, f.sort, result.page)["href"]
    return response


@router.get("/drivers/{driver_id}", response_class=HTMLResponse)
def driver_detail_page(
    driver_id: str,
    request: Request,
    user: str = Depends(require_login),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    context = {"csrf_token": get_csrf_token(request), "user": user, "active": "drivers"}
    detail = get_driver_detail(db, driver_id)
    if detail is None:
        return templates.TemplateResponse(
            request, "driver_not_found.html", {**context, "driver_id": driver_id}, status_code=404
        )
    return templates.TemplateResponse(
        request, "driver_detail.html", {**context, "d": detail.response, "trend": detail.trend}
    )
