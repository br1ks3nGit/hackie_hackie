from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.model import tier_to_multiplier
from app.models import Driver, Trip, TripScore
from app.schemas import InsurerOverviewResponse
from app.services.scoring import is_scoreable

OVERVIEW_WINDOW_DAYS = 90


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
