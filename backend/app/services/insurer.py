import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.model import tier_to_multiplier
from app.models import Driver, Event, Trip, TripScore
from app.schemas import (
    InsurerDriverDetailResponse,
    InsurerDriverItem,
    InsurerOverviewResponse,
    TripListItem,
)
from app.services.scoring import (
    PASSENGER_SHARE_FLAG,
    calculate_driver_score,
    calculate_passenger_stats,
    is_expired_unknown,
    is_scoreable,
)
from app.values import EventType

OVERVIEW_WINDOW_DAYS = 90
EVENT_WINDOW_DAYS = 90
RECENT_TRIPS_LIMIT = 20
DRIVERS_PAGE_SIZE = 20

_DRIVER_SORT_KEYS: dict[str, tuple[Callable[[InsurerDriverItem], float], bool]] = {
    "score_desc": (lambda x: x.score, True),
    "score_asc": (lambda x: x.score, False),
    "multiplier_desc": (lambda x: x.premium_multiplier, True),
    "multiplier_asc": (lambda x: x.premium_multiplier, False),
}


@dataclass(frozen=True)
class DriversPage:
    """One page of the filtered, sorted driver list."""

    items: list[InsurerDriverItem]
    total: int
    page: int
    pages: int
    page_size: int


@dataclass(frozen=True)
class DriverDetail:
    """Driver detail response plus the score trend (not part of the JSON schema)."""

    response: InsurerDriverDetailResponse
    trend: str


def get_overview(db: Session) -> InsurerOverviewResponse:
    """Portfolio totals shared by GET /v1/insurer/overview and the dashboard overview."""
    cutoff = datetime.now(UTC) - timedelta(days=OVERVIEW_WINDOW_DAYS)

    total_drivers = db.query(func.count(Driver.id)).scalar()

    # Only scoreable trips count toward trip totals and the tier distribution
    rows = (
        db.query(Trip, TripScore)
        .join(TripScore, Trip.id == TripScore.trip_id)
        .filter(Trip.created_at >= cutoff)
        .filter(Trip.status == "done")
        .all()
    )
    scoreable = [(t, s) for t, s in rows if is_scoreable(t)]
    total_trips = len(scoreable)

    tier_distribution = {}
    for _, score in scoreable:
        tier_distribution[score.tier] = tier_distribution.get(score.tier, 0) + 1

    # Average multiplier weighted by the number of trips in each tier
    total_scored = sum(tier_distribution.values())
    average_multiplier = (
        sum(tier_to_multiplier(tier) * count for tier, count in tier_distribution.items())
        / total_scored
        if total_scored > 0
        else 1.0
    )

    return InsurerOverviewResponse(
        total_drivers=total_drivers,
        total_trips_90d=total_trips,
        tier_distribution=tier_distribution,
        average_multiplier=round(average_multiplier, 2),
    )


def list_drivers(
    db: Session, tier: str | None = None, sort: str | None = "score_desc"
) -> list[InsurerDriverItem]:
    """All drivers with 90-day scores, filtered by tier and sorted; shared by API and dashboard."""
    items = []
    for driver in db.query(Driver).all():
        score, confidence, tier_val, multiplier, _trend, total_trips, total_distance = (
            calculate_driver_score(db, driver.id)
        )
        if tier and tier_val != tier:
            continue
        items.append(
            InsurerDriverItem(
                driver_id=driver.id,
                score=score,
                confidence=confidence,
                tier=tier_val,
                premium_multiplier=multiplier,
                total_trips_90d=total_trips,
                total_distance_km_90d=total_distance,
            )
        )
    if sort in _DRIVER_SORT_KEYS:
        key, reverse = _DRIVER_SORT_KEYS[sort]
        items.sort(key=key, reverse=reverse)
    return items


def get_drivers_page(
    db: Session,
    tier: str | None = None,
    sort: str | None = "score_desc",
    page: int = 1,
    page_size: int = DRIVERS_PAGE_SIZE,
) -> DriversPage:
    """Dashboard pagination: limit/offset applied after filter and sort; page is clamped."""
    items = list_drivers(db, tier, sort)
    pages = max(1, math.ceil(len(items) / page_size))
    page = min(max(page, 1), pages)
    offset = (page - 1) * page_size
    return DriversPage(items[offset : offset + page_size], len(items), page, pages, page_size)


def _event_counts(db: Session, driver_id: str) -> dict[EventType, int]:
    cutoff = datetime.now(UTC) - timedelta(days=EVENT_WINDOW_DAYS)
    rows = (
        db.query(Event.type, func.count(Event.id))
        .join(Trip, Trip.id == Event.trip_id)
        .filter(Trip.driver_id == driver_id)
        .filter(Trip.created_at >= cutoff)
        .group_by(Event.type)
        .all()
    )
    return {event_type: count for event_type, count in rows}


def _trip_item(trip: Trip, score: TripScore | None) -> TripListItem:
    return TripListItem(
        trip_id=trip.id,
        started_at=trip.started_at,
        distance_km=trip.features.features.get("distance_km", 0) if trip.features else 0,
        score=score.score if score else None,
        tier=score.tier if score else None,
        trip_type=trip.trip_type,
        needs_confirmation=(
            trip.trip_type == "unknown"
            and trip.label_source != "user"
            and not is_expired_unknown(trip)
        ),
        label_source=trip.label_source,
        transit_line=trip.transit_line,
    )


def get_driver_detail(db: Session, driver_id: str) -> DriverDetail | None:
    """Driver detail shared by the API and dashboard; None when the driver does not exist."""
    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        return None

    score, confidence, tier, multiplier, trend, _total_trips, _total_distance = (
        calculate_driver_score(db, driver.id)
    )
    passenger_stats = calculate_passenger_stats(db, driver.id)
    trips = (
        db.query(Trip, TripScore)
        .outerjoin(TripScore, Trip.id == TripScore.trip_id)
        .filter(Trip.driver_id == driver_id)
        .order_by(Trip.started_at.desc())
        .limit(RECENT_TRIPS_LIMIT)
        .all()
    )
    model_version = "unknown"
    if trips and trips[0][1]:
        model_version = trips[0][1].model_version

    response = InsurerDriverDetailResponse(
        driver_id=driver.id,
        score=score,
        confidence=confidence,
        tier=tier,
        premium_multiplier=multiplier,
        event_rates=_event_counts(db, driver_id),
        trips=[_trip_item(t, s) for t, s in trips],
        model_version=model_version,
        passenger_share=passenger_stats["passenger_share"],
        label_sources=passenger_stats["label_sources"],
        flagged_for_review=passenger_stats["passenger_share"] > PASSENGER_SHARE_FLAG,
    )
    return DriverDetail(response, trend)
