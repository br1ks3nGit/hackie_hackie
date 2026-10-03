import json
import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import Driver, Event, Incident, Trip, TripFeature, TripScore
from app.services.trips import _route_points
from tests.test_dashboard import PASSWORD_HASH, login

START = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)  # 10:00 HKT
ROUTE = [
    {"t": i, "lat": round(22.30 + i * 0.001, 3), "lon": 114.17, "speed": 10.0} for i in range(3)
]


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


@pytest.fixture(autouse=True)
def configured_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "dashboard_password_hash", PASSWORD_HASH)
    monkeypatch.setattr(get_settings(), "dashboard_username", "admin")


def _seed(trip_id: str, route: list[dict], with_events: bool) -> None:
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
    db.add(
        TripFeature(
            trip_id=trip_id, features={"distance_km": 12.5, "duration_min": 20.0, "route": route}
        )
    )
    db.add(TripScore(trip_id=trip_id, confidence=0.25, score=75, tier="B", model_version="v-t"))
    if with_events:
        db.add(
            Event(
                trip_id=trip_id,
                type="harsh_brake",
                time=START + timedelta(minutes=5),
                peak_g=0.45,
                lat=22.301,
                lon=114.17,
            )
        )
        db.add(
            Incident(
                driver_id="drv-t",
                trip_id=trip_id,
                type="crash",
                time=START + timedelta(minutes=9),
                lat=22.302,
                lon=114.17,
                peak_g=3.2,
                confirmed="ok",
            )
        )
    db.commit()
    db.close()


def test_requires_login(client: TestClient) -> None:
    assert client.get("/dashboard/trips/x").status_code == 303


def test_unknown_trip_is_404(client: TestClient) -> None:
    login(client)
    response = client.get("/dashboard/trips/nope")
    assert response.status_code == 404
    assert "Trip not found" in response.text


def test_trip_detail_renders(client: TestClient) -> None:
    _seed("trip-1", ROUTE, with_events=True)
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
    assert "leaflet-1.9.4.min.js" in html
    match = re.search(r'id="trip-map-data">(.*?)</script>', html, re.S)
    assert match
    data = json.loads(match.group(1))
    assert data["route"] == [[22.30, 114.17], [22.301, 114.17], [22.302, 114.17]]
    assert data["events"][0]["type"] == "harsh_brake" and data["events"][0]["peak_g"] == 0.45
    assert data["crashes"][0]["peak_g"] == 3.2


def test_trip_without_route_shows_empty_states(client: TestClient) -> None:
    _seed("trip-2", [], with_events=False)
    login(client)
    html = client.get("/dashboard/trips/trip-2").text
    assert "No route recorded" in html
    assert "No harsh events" in html
    assert "trip-map-data" not in html
    assert "leaflet" not in html


def test_leaflet_not_loaded_globally(client: TestClient) -> None:
    login(client)
    assert "leaflet" not in client.get("/dashboard").text


def _map_data(html: str) -> dict:
    match = re.search(r'id="trip-map-data">(.*?)</script>', html, re.S)
    assert match
    return json.loads(match.group(1))


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


def test_map_json_excludes_unlocated_events_and_orders_by_time(client: TestClient) -> None:
    db = SessionLocal()
    db.add(Driver(id="drv-t", api_key_hash="h"))
    db.flush()
    _seed_trip(db, "trip-3", {"route": ROUTE})
    for minutes, kind, lat in [(8, "speeding", 22.31), (2, "harsh_accel", 22.32)]:
        db.add(
            Event(
                trip_id="trip-3",
                type=kind,
                time=START + timedelta(minutes=minutes),
                peak_g=0.3,
                lat=lat,
                lon=114.2,
            )
        )
    db.add(Event(trip_id="trip-3", type="harsh_brake", time=START + timedelta(minutes=5)))
    db.commit()
    db.close()
    login(client)
    html = client.get("/dashboard/trips/trip-3").text
    data = _map_data(html)
    assert [e["type"] for e in data["events"]] == ["harsh_accel", "speeding"]
    assert html.index("10:02") < html.index("10:05") < html.index("10:08")


def test_route_points_with_null_or_nan_are_skipped(client: TestClient) -> None:
    route = [
        {"t": 0, "lat": 22.3, "lon": 114.17},
        {"t": 1, "lat": None, "lon": 114.17},
        {"t": 4, "lat": "22.5", "lon": 114.17},
        "junk",
        {"t": 5, "lat": 22.31, "lon": 114.18},
    ]
    db = SessionLocal()
    db.add(Driver(id="drv-t", api_key_hash="h"))
    db.flush()
    _seed_trip(db, "trip-4", {"route": route})
    db.commit()
    db.close()
    login(client)
    response = client.get("/dashboard/trips/trip-4")
    assert response.status_code == 200
    assert _map_data(response.text)["route"] == [[22.3, 114.17], [22.31, 114.18]]


def test_route_points_drop_non_finite_values() -> None:
    nan, inf = float("nan"), float("inf")
    route = [
        {"lat": nan, "lon": 114.1},
        {"lat": 22.4, "lon": inf},
        {"lat": True, "lon": 114.1},
        {"lat": 22.5, "lon": 114.2},
    ]
    assert _route_points({"route": route}) == [[22.5, 114.2]]


def test_only_crash_incidents_for_this_trip_listed(client: TestClient) -> None:
    db = SessionLocal()
    db.add(Driver(id="drv-t", api_key_hash="h"))
    db.flush()
    _seed_trip(db, "trip-5", {"route": ROUTE})
    _seed_trip(db, "trip-6", {"route": ROUTE})
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
                lat=22.3,
                lon=114.17,
                peak_g=peak,
            )
        )
    db.commit()
    db.close()
    login(client)
    html = client.get("/dashboard/trips/trip-5").text
    assert "3.10 g" in html
    assert "7.77" not in html and "6.66" not in html
    assert len(_map_data(html)["crashes"]) == 1


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
    assert "No route recorded" in response.text
    assert "distance n/a" in response.text
