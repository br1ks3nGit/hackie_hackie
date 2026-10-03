from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.auth import hash_api_key
from app.database import SessionLocal
from app.main import app
from app.models import Driver, Trip, TripFeature, TripScore

client = TestClient(app)


def _seed_driver_with_scored_trips():
    """Insert one driver with two scored trips directly into the test DB."""
    db = SessionLocal()
    api_key = "test-scoring-driver-key"
    driver = Driver(id="drv-test-scoring", api_key_hash=hash_api_key(api_key))
    db.add(driver)

    now = datetime.utcnow()
    trip_a = Trip(
        id="trp-scoring-a",
        driver_id=driver.id,
        status="done",
        started_at=now - timedelta(hours=2),
        ended_at=now - timedelta(hours=1),
        trip_type="driver",
        label_source="rules",
        created_at=now - timedelta(hours=2),
    )
    trip_b = Trip(
        id="trp-scoring-b",
        driver_id=driver.id,
        status="done",
        started_at=now - timedelta(hours=4),
        ended_at=now - timedelta(hours=3),
        trip_type="driver",
        label_source="rules",
        created_at=now - timedelta(hours=4),
    )
    db.add_all([trip_a, trip_b])
    db.add_all(
        [
            # Trip A: score 80 over 10 km; Trip B: score 40 over 30 km
            TripScore(
                trip_id=trip_a.id, confidence=0.2, score=80, tier="B", model_version="placeholder"
            ),
            TripScore(
                trip_id=trip_b.id, confidence=0.6, score=40, tier="D", model_version="placeholder"
            ),
            TripFeature(trip_id=trip_a.id, features={"distance_km": 10.0}),
            TripFeature(trip_id=trip_b.id, features={"distance_km": 30.0}),
        ]
    )
    db.commit()
    db.close()
    return api_key


def test_summary_returns_distance_weighted_score():
    """GET /v1/me/summary must not crash and must weight scores by distance."""
    api_key = _seed_driver_with_scored_trips()

    response = client.get("/v1/me/summary", headers={"X-API-Key": api_key})
    assert response.status_code == 200

    data = response.json()
    # (80 * 10 + 40 * 30) / 40 = 50
    assert data["score"] == 50
    assert data["total_trips_90d"] == 2
    assert data["total_distance_km_90d"] == 40.0
