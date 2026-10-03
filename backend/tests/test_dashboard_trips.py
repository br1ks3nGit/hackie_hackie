import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import Driver, Event, Incident, Trip, TripFeature, TripScore
from tests.test_dashboard import PASSWORD_HASH, login

START = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)  # 10:00 HKT


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


@pytest.fixture(autouse=True)
def configured_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "dashboard_password_hash", PASSWORD_HASH)
    monkeypatch.setattr(get_settings(), "dashboard_username", "admin")


def _seed(trip_id: str, with_events: bool) -> None:
    db = SessionLocal()
    db.add(Driver(id="drv-t", api_key_hash="h"))
    db.flush()
    db.add(
        Trip(
            id=trip_id,
            driver_id="drv-t",
            status="done",
            trip_type="driver",
            label_source="rules",
            started_at=START,
            ended_at=START + timedelta(minutes=20),
        )
    )
    db.flush()
    db.add(TripFeature(trip_id=trip_id, features={"distance_km": 12.5, "duration_min": 20.0}))
    db.add(TripScore(trip_id=trip_id, confidence=0.25, score=75, tier="B", model_version="v-t"))
    if with_events:
        db.add(
            Event(
                trip_id=trip_id,
                type="harsh_brake",
                time=START + timedelta(minutes=5),
                peak_g=0.45,
            )
        )
        db.add(
            Incident(
                driver_id="drv-t",
                trip_id=trip_id,
                type="crash",
                time=START + timedelta(minutes=9),
                peak_g=3.2,
                confirmed="ok",
            )
        )
    db.commit()
    db.close()


def assert_no_location(html: str) -> None:
    low = html.lower()
    for text in ("leaflet", "openstreetmap", "trip-map-data", "route", "latitude", "longitude"):
        assert text not in low
    assert "Location" not in html and 'x-ref="map"' not in html
    assert not re.search(r"\d{2}\.\d{4,}, ?\d{2,3}\.\d{4,}", html)


def test_requires_login(client: TestClient) -> None:
    assert client.get("/dashboard/trips/x").status_code == 303


def test_unknown_trip_is_404(client: TestClient) -> None:
    login(client)
    response = client.get("/dashboard/trips/nope")
    assert response.status_code == 404
    assert "Trip not found" in response.text


def test_trip_detail_renders(client: TestClient) -> None:
    _seed("trip-1", with_events=True)
    login(client)
    response = client.get("/dashboard/trips/trip-1")
    assert response.status_code == 200
    html = response.text
    assert 'href="/dashboard/drivers/drv-t"' in html
    assert "2026-01-01 10:00" in html and "2026-01-01 10:20" in html
    assert "12.50 km" in html and "20.0 min" in html
    assert "75" in html and "Tier B" in html and "25%" in html
    assert "This trip included 1 harsh brake(s)." in html
    assert "0.45 g" in html and "Harsh brake" in html and "2026-01-01 10:05" in html
    assert "Crash incidents" in html and "3.20 g" in html and "Driver OK" in html
    assert_no_location(html)


def test_trip_without_events_shows_empty_state(client: TestClient) -> None:
    _seed("trip-2", with_events=False)
    login(client)
    html = client.get("/dashboard/trips/trip-2").text
    assert "No harsh events" in html
    assert_no_location(html)


def test_no_leaflet_on_dashboard(client: TestClient) -> None:
    login(client)
    assert "leaflet" not in client.get("/dashboard").text.lower()


def _seed_trip(db, trip_id: str, features: dict | None) -> None:
    db.add(
        Trip(
            id=trip_id,
            driver_id="drv-t",
            status="done",
            started_at=START,
            ended_at=START + timedelta(minutes=20),
        )
    )
    db.flush()
    if features is not None:
        db.add(TripFeature(trip_id=trip_id, features=features))


def test_events_ordered_by_time(client: TestClient) -> None:
    db = SessionLocal()
    db.add(Driver(id="drv-t", api_key_hash="h"))
    db.flush()
    _seed_trip(db, "trip-3", {})
    for minutes, kind in [(8, "speeding"), (2, "harsh_accel"), (5, "harsh_brake")]:
        db.add(
            Event(
                trip_id="trip-3",
                type=kind,
                time=START + timedelta(minutes=minutes),
                peak_g=0.3,
            )
        )
    db.commit()
    db.close()
    login(client)
    html = client.get("/dashboard/trips/trip-3").text
    assert html.index("10:02") < html.index("10:05") < html.index("10:08")


def test_only_crash_incidents_for_this_trip_listed(client: TestClient) -> None:
    db = SessionLocal()
    db.add(Driver(id="drv-t", api_key_hash="h"))
    db.flush()
    _seed_trip(db, "trip-5", {})
    _seed_trip(db, "trip-6", {})
    for trip_id, kind, peak in [
        ("trip-5", "crash", 3.1),
        ("trip-6", "crash", 7.77),
        ("trip-5", "fall", 6.66),
    ]:
        db.add(
            Incident(
                driver_id="drv-t",
                trip_id=trip_id,
                type=kind,
                time=START + timedelta(minutes=3),
                peak_g=peak,
            )
        )
    db.commit()
    db.close()
    login(client)
    html = client.get("/dashboard/trips/trip-5").text
    assert "3.10 g" in html
    assert "7.77" not in html and "6.66" not in html
    assert_no_location(html)


def test_trip_without_score_or_features_renders(client: TestClient) -> None:
    db = SessionLocal()
    db.add(Driver(id="drv-t", api_key_hash="h"))
    db.flush()
    _seed_trip(db, "trip-7", None)
    db.commit()
    db.close()
    login(client)
    response = client.get("/dashboard/trips/trip-7")
    assert response.status_code == 200
    assert "Not scored" in response.text
    assert "distance n/a" in response.text
