import math
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Event, Incident, Trip, TripScore
from app.services.scoring import generate_explanation


@dataclass(frozen=True)
class TripEventView:
    type: str
    time: datetime
    peak_g: float | None
    lat: float | None
    lon: float | None


@dataclass(frozen=True)
class TripCrashView:
    time: datetime
    peak_g: float | None
    lat: float | None
    lon: float | None
    confirmed: str | None


@dataclass(frozen=True)
class TripDetail:
    """Everything the dashboard trip page shows (insurer view; not part of the JSON schema)."""

    trip_id: str
    driver_id: str
    status: str
    trip_type: str | None
    label_source: str | None
    started_at: datetime
    ended_at: datetime | None
    distance_km: float | None
    duration_min: float | None
    score: int | None
    tier: str | None
    confidence: float | None
    model_version: str | None
    explanation: str | None
    failure_reason: str | None
    events: list[TripEventView]
    route: list[list[float]]
    crashes: list[TripCrashView]


def is_coord(value: object) -> bool:
    """True for a finite int/float (bool excluded)."""
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _route_points(features: dict) -> list[list[float]]:
    points = features.get("route") or []
    return [
        [p["lat"], p["lon"]]
        for p in points
        if isinstance(p, dict) and is_coord(p.get("lat")) and is_coord(p.get("lon"))
    ]


def get_trip_detail(db: Session, trip_id: str) -> TripDetail | None:
    """Trip detail for the insurer dashboard; None when the trip does not exist."""
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if trip is None:
        return None
    score: TripScore | None = trip.score
    features = trip.features.features if trip.features else {}
    events = db.query(Event).filter(Event.trip_id == trip_id).order_by(Event.time, Event.id).all()
    crashes = (
        db.query(Incident)
        .filter(Incident.trip_id == trip_id, Incident.type == "crash")
        .order_by(Incident.time, Incident.id)
        .all()
    )
    return TripDetail(
        trip_id=trip.id,
        driver_id=trip.driver_id,
        status=trip.status,
        trip_type=trip.trip_type,
        label_source=trip.label_source,
        started_at=trip.started_at,
        ended_at=trip.ended_at,
        distance_km=features.get("distance_km"),
        duration_min=features.get("duration_min"),
        score=score.score if score else None,
        tier=score.tier if score else None,
        confidence=score.confidence if score else None,
        model_version=score.model_version if score else None,
        explanation=generate_explanation(events, features) if score else None,
        failure_reason=trip.failure_reason,
        events=[TripEventView(e.type, e.time, e.peak_g, e.lat, e.lon) for e in events],
        route=_route_points(features),
        crashes=[TripCrashView(c.time, c.peak_g, c.lat, c.lon, c.confirmed) for c in crashes],
    )
