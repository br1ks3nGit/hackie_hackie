from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.auth import get_current_driver, get_current_insurer
from app.database import get_db
from app.models import Driver, Trip, TripScore, TripFeature, Event, Incident
from app.pipeline import process_trip
from app.schemas import (
    DriverSummaryResponse,
    TripListItem,
    TripDetailResponse,
    EventResponse,
    RoutePoint,
    InsurerOverviewResponse,
    InsurerDriverItem,
    InsurerDriverDetailResponse,
    TripLabelRequest,
    TripLabelResponse,
    IncidentCreate,
    IncidentConfirm,
    IncidentResponse,
)
from app.model import tier_to_multiplier

router = APIRouter()

UNCONFIRMED_EXPIRY_DAYS = 7
PASSENGER_SHARE_FLAG = 0.40


def _is_scoreable(trip: Trip) -> bool:
    """Only confirmed driver trips count toward the score."""
    if trip.trip_type == "driver":
        return True
    if trip.trip_type in ("transit", "passenger"):
        return False
    # Unknown trips: only count if labelled by user as driver
    if trip.trip_type == "unknown" and trip.label_source == "user":
        return True
    return False


def _is_expired_unknown(trip: Trip) -> bool:
    """Unknown trips older than 7 days without a label do not count."""
    if trip.trip_type != "unknown":
        return False
    if trip.label_source == "user":
        return False
    age = datetime.utcnow() - trip.created_at
    return age.days >= UNCONFIRMED_EXPIRY_DAYS


def _calculate_driver_score(db: Session, driver_id: str, days: int = 90) -> tuple:
    """Calculate distance-weighted driver score over the last N days."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    results = (
        db.query(Trip, TripScore, TripFeature)
        .join(TripScore, Trip.id == TripScore.trip_id)
        .outerjoin(TripFeature, TripFeature.trip_id == Trip.id)
        .filter(Trip.driver_id == driver_id)
        .filter(Trip.created_at >= cutoff)
        .filter(Trip.status == "done")
        .order_by(Trip.started_at)
        .all()
    )

    # Filter to only scoreable trips
    scoreable = [(t, s, f) for t, s, f in results if _is_scoreable(t) and not _is_expired_unknown(t)]

    if not scoreable:
        return 60, 0.5, "C", 1.0, "stable", 0, 0.0

    total_distance = 0.0
    weighted_score_sum = 0.0
    confidences = []

    for trip, score, features in scoreable:
        distance_km = features.features.get("distance_km", 0) if features else 0
        total_distance += distance_km
        weighted_score_sum += score.score * distance_km
        confidences.append(score.confidence)

    if total_distance == 0:
        return 60, 0.5, "C", 1.0, "stable", len(scoreable), 0.0

    avg_score = weighted_score_sum / total_distance
    avg_confidence = sum(confidences) / len(confidences)
    tier = score_to_tier(int(avg_score))
    multiplier = tier_to_multiplier(tier)

    mid = len(scoreable) // 2
    if mid > 0:
        first_half = [r[1].score for r in scoreable[:mid]]
        second_half = [r[1].score for r in scoreable[mid:]]
        if sum(second_half) / len(second_half) > sum(first_half) / len(first_half) + 2:
            trend = "improving"
        elif sum(second_half) / len(second_half) < sum(first_half) / len(first_half) - 2:
            trend = "worsening"
        else:
            trend = "stable"
    else:
        trend = "stable"

    return int(avg_score), round(avg_confidence, 4), tier, multiplier, trend, len(scoreable), round(total_distance, 2)


def _calculate_passenger_stats(db: Session, driver_id: str, days: int = 90) -> dict:
    """Calculate passenger share and label source breakdown."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    trips = (
        db.query(Trip)
        .filter(Trip.driver_id == driver_id)
        .filter(Trip.created_at >= cutoff)
        .filter(Trip.status == "done")
        .all()
    )

    if not trips:
        return {"passenger_share": 0.0, "label_sources": {}, "total": 0}

    total = len(trips)
    passenger_count = len([t for t in trips if t.trip_type in ("passenger", "transit")])
    passenger_share = passenger_count / total if total > 0 else 0.0

    label_sources = {"user": 0, "bluetooth": 0, "rules": 0, "unlabelled": 0}
    for t in trips:
        if t.label_source == "user":
            label_sources["user"] += 1
        elif t.label_source == "bluetooth":
            label_sources["bluetooth"] += 1
        elif t.label_source == "rules":
            label_sources["rules"] += 1
        else:
            label_sources["unlabelled"] += 1

    return {
        "passenger_share": round(passenger_share, 4),
        "label_sources": label_sources,
        "total": total,
    }


def score_to_tier(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "E"


@router.get("/me/summary", response_model=DriverSummaryResponse)
def get_my_summary(
    driver: Driver = Depends(get_current_driver),
    db: Session = Depends(get_db),
):
    score, confidence, tier, multiplier, trend, total_trips, total_distance = _calculate_driver_score(db, driver.id)
    return DriverSummaryResponse(
        driver_id=driver.id,
        score=score,
        confidence=confidence,
        tier=tier,
        premium_multiplier=multiplier,
        trend=trend,
        total_trips_90d=total_trips,
        total_distance_km_90d=total_distance,
    )


@router.get("/me/trips", response_model=List[TripListItem])
def get_my_trips(
    driver: Driver = Depends(get_current_driver),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    trips = (
        db.query(Trip, TripScore)
        .outerjoin(TripScore, Trip.id == TripScore.trip_id)
        .filter(Trip.driver_id == driver.id)
        .order_by(Trip.started_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = []
    for trip, score in trips:
        needs_confirmation = (
            trip.trip_type == "unknown"
            and trip.label_source != "user"
            and not _is_expired_unknown(trip)
        )
        items.append(TripListItem(
            trip_id=trip.id,
            started_at=trip.started_at,
            distance_km=trip.features.features.get("distance_km", 0) if trip.features else 0,
            score=score.score if score else None,
            tier=score.tier if score else None,
            trip_type=trip.trip_type,
            needs_confirmation=needs_confirmation,
            label_source=trip.label_source,
            transit_line=trip.transit_line,
        ))
    return items


@router.post("/me/trips/{trip_id}/label", response_model=TripLabelResponse)
def label_trip(
    trip_id: str,
    request: TripLabelRequest,
    background_tasks: BackgroundTasks,
    driver: Driver = Depends(get_current_driver),
    db: Session = Depends(get_db),
):
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.driver_id == driver.id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    trip.trip_type = request.trip_type
    trip.label_source = "user"
    db.commit()

    status = "relabelled"
    if request.trip_type == "passenger":
        status = "removed_from_score"
    elif request.trip_type == "driver":
        status = "added_to_score"
        # An unscored, finished trip labelled as driver needs processing to produce a
        # score. Trips still uploading/processing pick up the user label when they run.
        if trip.score is None and trip.status in ("done", "failed"):
            if trip.features is not None:
                db.delete(trip.features)
                db.commit()
            background_tasks.add_task(process_trip, trip_id)

    return TripLabelResponse(
        trip_id=trip.id,
        trip_type=trip.trip_type,
        status=status,
    )


@router.get("/me/trips/{trip_id}", response_model=TripDetailResponse)
def get_my_trip_detail(
    trip_id: str,
    driver: Driver = Depends(get_current_driver),
    db: Session = Depends(get_db),
):
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.driver_id == driver.id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    score = trip.score
    events = trip.events
    features = trip.features.features if trip.features else {}

    route = []
    if trip.features and "route" in features:
        route_points = features["route"]
        step = max(1, len(route_points) // 100)
        route = [RoutePoint(**p) for p in route_points[::step]]

    explanation = _generate_explanation(events, features) if score else None

    return TripDetailResponse(
        trip_id=trip.id,
        started_at=trip.started_at,
        ended_at=trip.ended_at,
        distance_km=features.get("distance_km", 0),
        duration_min=features.get("duration_min", 0),
        score=score.score if score else None,
        confidence=score.confidence if score else None,
        tier=score.tier if score else None,
        events=[EventResponse(
            type=e.type,
            time=e.time,
            peak_g=e.peak_g,
            lat=e.lat,
            lon=e.lon,
        ) for e in events],
        route=route,
        explanation=explanation,
    )


def _generate_explanation(events: List[Event], features: dict) -> str:
    if not events:
        return "Smooth trip with no detected harsh events."

    event_counts = {}
    for e in events:
        event_counts[e.type] = event_counts.get(e.type, 0) + 1

    parts = []
    if event_counts.get("harsh_brake", 0) > 0:
        parts.append(f"{event_counts['harsh_brake']} harsh brake(s)")
    if event_counts.get("harsh_accel", 0) > 0:
        parts.append(f"{event_counts['harsh_accel']} harsh acceleration(s)")
    if event_counts.get("sharp_corner", 0) > 0:
        parts.append(f"{event_counts['sharp_corner']} sharp corner(s)")
    if event_counts.get("speeding", 0) > 0:
        parts.append("speeding detected")

    if parts:
        return "This trip included " + ", ".join(parts) + "."
    return "Trip completed."


@router.get("/insurer/overview", response_model=InsurerOverviewResponse)
def get_insurer_overview(
    _: None = Depends(get_current_insurer),
    db: Session = Depends(get_db),
):
    cutoff = datetime.utcnow() - timedelta(days=90)

    total_drivers = db.query(func.count(Driver.id)).scalar()

    # Only scoreable trips count toward trip totals and the tier distribution
    rows = (
        db.query(Trip, TripScore)
        .join(TripScore, Trip.id == TripScore.trip_id)
        .filter(Trip.created_at >= cutoff)
        .filter(Trip.status == "done")
        .all()
    )
    scoreable = [(t, s) for t, s in rows if _is_scoreable(t)]
    total_trips = len(scoreable)

    tier_distribution = {}
    for _, score in scoreable:
        tier_distribution[score.tier] = tier_distribution.get(score.tier, 0) + 1

    # Average multiplier weighted by the number of trips in each tier
    total_scored = sum(tier_distribution.values())
    average_multiplier = (
        sum(tier_to_multiplier(tier) * count for tier, count in tier_distribution.items()) / total_scored
        if total_scored > 0
        else 1.0
    )

    return InsurerOverviewResponse(
        total_drivers=total_drivers,
        total_trips_90d=total_trips,
        tier_distribution=tier_distribution,
        average_multiplier=round(average_multiplier, 2),
    )


@router.get("/insurer/drivers", response_model=List[InsurerDriverItem])
def get_insurer_drivers(
    _: None = Depends(get_current_insurer),
    db: Session = Depends(get_db),
    tier: Optional[str] = Query(None),
    sort: Optional[str] = Query("score_desc"),
):
    drivers = db.query(Driver).all()
    items = []

    for driver in drivers:
        score, confidence, tier_val, multiplier, trend, total_trips, total_distance = _calculate_driver_score(db, driver.id)
        if tier and tier_val != tier:
            continue
        items.append(InsurerDriverItem(
            driver_id=driver.id,
            score=score,
            confidence=confidence,
            tier=tier_val,
            premium_multiplier=multiplier,
            total_trips_90d=total_trips,
            total_distance_km_90d=total_distance,
        ))

    if sort == "score_desc":
        items.sort(key=lambda x: x.score, reverse=True)
    elif sort == "score_asc":
        items.sort(key=lambda x: x.score)
    elif sort == "multiplier_desc":
        items.sort(key=lambda x: x.premium_multiplier, reverse=True)
    elif sort == "multiplier_asc":
        items.sort(key=lambda x: x.premium_multiplier)

    return items


@router.get("/insurer/drivers/{driver_id}", response_model=InsurerDriverDetailResponse)
def get_insurer_driver_detail(
    driver_id: str,
    _: None = Depends(get_current_insurer),
    db: Session = Depends(get_db),
):
    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    score, confidence, tier, multiplier, trend, total_trips, total_distance = _calculate_driver_score(db, driver.id)
    passenger_stats = _calculate_passenger_stats(db, driver.id)

    cutoff = datetime.utcnow() - timedelta(days=90)
    events = (
        db.query(Event.type, func.count(Event.id))
        .join(Trip, Trip.id == Event.trip_id)
        .filter(Trip.driver_id == driver_id)
        .filter(Trip.created_at >= cutoff)
        .group_by(Event.type)
        .all()
    )
    event_rates = {event_type: count for event_type, count in events}

    trips = (
        db.query(Trip, TripScore)
        .outerjoin(TripScore, Trip.id == TripScore.trip_id)
        .filter(Trip.driver_id == driver_id)
        .order_by(Trip.started_at.desc())
        .limit(20)
        .all()
    )
    trip_items = [TripListItem(
        trip_id=t.id,
        started_at=t.started_at,
        distance_km=t.features.features.get("distance_km", 0) if t.features else 0,
        score=s.score if s else None,
        tier=s.tier if s else None,
        trip_type=t.trip_type,
        needs_confirmation=(
            t.trip_type == "unknown"
            and t.label_source != "user"
            and not _is_expired_unknown(t)
        ),
        label_source=t.label_source,
        transit_line=t.transit_line,
    ) for t, s in trips]

    model_version = "unknown"
    if trips and trips[0][1]:
        model_version = trips[0][1].model_version

    return InsurerDriverDetailResponse(
        driver_id=driver.id,
        score=score,
        confidence=confidence,
        tier=tier,
        premium_multiplier=multiplier,
        event_rates=event_rates,
        trips=trip_items,
        model_version=model_version,
        passenger_share=passenger_stats["passenger_share"],
        label_sources=passenger_stats["label_sources"],
        flagged_for_review=passenger_stats["passenger_share"] > PASSENGER_SHARE_FLAG,
    )


# --- Incidents ---

@router.post("/me/incidents", response_model=IncidentResponse)
def create_incident(
    request: IncidentCreate,
    driver: Driver = Depends(get_current_driver),
    db: Session = Depends(get_db),
):
    incident = Incident(
        driver_id=driver.id,
        trip_id=request.trip_id,
        type=request.type,
        time=request.time,
        lat=request.lat,
        lon=request.lon,
        peak_g=request.peak_g,
        sensor_snapshot=request.sensor_snapshot,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)

    return IncidentResponse(
        id=incident.id,
        type=incident.type,
        time=incident.time,
        lat=incident.lat,
        lon=incident.lon,
        peak_g=incident.peak_g,
        confirmed=incident.confirmed,
        created_at=incident.created_at,
    )


@router.post("/me/incidents/{incident_id}/confirm", response_model=IncidentResponse)
def confirm_incident(
    incident_id: int,
    request: IncidentConfirm,
    driver: Driver = Depends(get_current_driver),
    db: Session = Depends(get_db),
):
    incident = db.query(Incident).filter(
        Incident.id == incident_id,
        Incident.driver_id == driver.id,
    ).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident.confirmed = request.confirmed
    db.commit()
    db.refresh(incident)

    return IncidentResponse(
        id=incident.id,
        type=incident.type,
        time=incident.time,
        lat=incident.lat,
        lon=incident.lon,
        peak_g=incident.peak_g,
        confirmed=incident.confirmed,
        created_at=incident.created_at,
    )


@router.get("/me/incidents", response_model=List[IncidentResponse])
def list_incidents(
    driver: Driver = Depends(get_current_driver),
    db: Session = Depends(get_db),
):
    incidents = (
        db.query(Incident)
        .filter(Incident.driver_id == driver.id)
        .order_by(Incident.time.desc())
        .limit(50)
        .all()
    )
    return [
        IncidentResponse(
            id=i.id,
            type=i.type,
            time=i.time,
            lat=i.lat,
            lon=i.lon,
            peak_g=i.peak_g,
            confirmed=i.confirmed,
            created_at=i.created_at,
        )
        for i in incidents
    ]
