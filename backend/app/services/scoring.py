from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.model import score_to_tier, tier_to_multiplier
from app.models import Event, Trip, TripFeature, TripScore

UNCONFIRMED_EXPIRY_DAYS = 7
PASSENGER_SHARE_FLAG = 0.40


def is_scoreable(trip: Trip) -> bool:
    """Only confirmed driver trips count toward the score."""
    if trip.trip_type == "driver":
        return True
    if trip.trip_type in ("transit", "passenger"):
        return False
    # Unknown trips: only count if labelled by user as driver
    return bool(trip.trip_type == "unknown" and trip.label_source == "user")


def is_expired_unknown(trip: Trip) -> bool:
    """Unknown trips older than 7 days without a label do not count."""
    if trip.trip_type != "unknown":
        return False
    if trip.label_source == "user":
        return False
    age = datetime.now(UTC) - trip.created_at
    return age.days >= UNCONFIRMED_EXPIRY_DAYS


def calculate_driver_score(db: Session, driver_id: str, days: int = 90) -> tuple:
    """Calculate distance-weighted driver score over the last N days."""
    cutoff = datetime.now(UTC) - timedelta(days=days)

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
    scoreable = [(t, s, f) for t, s, f in results if is_scoreable(t) and not is_expired_unknown(t)]

    if not scoreable:
        return 60, 0.5, "C", 1.0, "stable", 0, 0.0

    total_distance = 0.0
    weighted_score_sum = 0.0
    confidences = []

    for _trip, score, features in scoreable:
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

    return (
        int(avg_score),
        round(avg_confidence, 4),
        tier,
        multiplier,
        trend,
        len(scoreable),
        round(total_distance, 2),
    )


def calculate_passenger_stats(db: Session, driver_id: str, days: int = 90) -> dict:
    """Calculate passenger share and label source breakdown."""
    cutoff = datetime.now(UTC) - timedelta(days=days)

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


def generate_explanation(events: list[Event], features: dict) -> str:
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
