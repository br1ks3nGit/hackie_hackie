import math
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Incident

INCIDENTS_PAGE_SIZE = 20
INCIDENT_FILTERS: tuple[str, ...] = ("help_needed", "no_response", "ok", "unconfirmed")


@dataclass(frozen=True)
class IncidentsPage:
    """One page of incidents, newest first."""

    items: list[Incident]
    total: int
    page: int
    pages: int
    page_size: int


def list_incidents(
    db: Session,
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = INCIDENTS_PAGE_SIZE,
) -> IncidentsPage:
    """Incidents newest first; status_filter is a confirmation value or "unconfirmed"."""
    conditions = []
    if status_filter == "unconfirmed":
        conditions.append(Incident.confirmed.is_(None))
    elif status_filter in INCIDENT_FILTERS:
        conditions.append(Incident.confirmed == status_filter)
    total = db.scalar(select(func.count(Incident.id)).where(*conditions)) or 0
    pages = max(1, math.ceil(total / page_size))
    page = min(max(page, 1), pages)
    items = list(
        db.scalars(
            select(Incident)
            .where(*conditions)
            .order_by(Incident.time.desc(), Incident.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    )
    return IncidentsPage(items, total, page, pages, page_size)
