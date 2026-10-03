import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.main import app
from app.model import score_to_tier
from app.models import Driver, Event, Trip, TripFeature, TripScore
from tests.helpers import create_admin, insurer_headers
from tests.test_dashboard import login

# (driver id, trip score) -> tier A / B / D; "drv-none" has no trips (score 60, tier C, 1.0x)
SEED = [("drv-a", 95), ("drv-b", 80), ("drv-d", 50)]


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


@pytest.fixture(autouse=True)
def configured_login() -> None:
    create_admin()


def _add_trip(db: Session, trip_id: str, driver_id: str, score: int, **fields: Any) -> None:
    """Seed a done trip with a score (tier derived) and 10 km; fields override Trip columns."""
    created = datetime.now(UTC) - timedelta(days=1)
    values: dict[str, Any] = {
        "started_at": created,
        "trip_type": "driver",
        "created_at": created,
        **fields,
    }
    db.add(Trip(id=trip_id, driver_id=driver_id, status="done", **values))
    db.flush()
    db.add(TripFeature(trip_id=trip_id, features={"distance_km": 10.0}))
    db.add(
        TripScore(
            trip_id=trip_id,
            confidence=0.1,
            score=score,
            tier=score_to_tier(score),
            model_version="v-t",
        )
    )


def _seed_basic() -> None:
    db = SessionLocal()
    db.add_all(
        [Driver(id=i, api_key_hash="h") for i, _ in SEED]
        + [Driver(id="drv-none", api_key_hash="h")]
    )
    db.flush()
    for driver_id, score in SEED:
        _add_trip(db, f"t-{driver_id}", driver_id, score)
    db.commit()
    db.close()


def _order(html: str) -> list[str]:
    return re.findall(r'href="/dashboard/drivers/([^"]+)"', html)


@pytest.fixture
def seeded() -> None:
    _seed_basic()


def test_drivers_list_requires_login(client: TestClient) -> None:
    assert client.get("/dashboard/drivers").status_code == 303


def test_drivers_list_renders_seeded_rows(client: TestClient, seeded: None) -> None:
    login(client)
    response = client.get("/dashboard/drivers")
    assert response.status_code == 200
    html = response.text
    assert _order(html) == ["drv-a", "drv-b", "drv-none", "drv-d"]
    assert "4 drivers" in html
    assert "0.80x" in html and "1.15x" in html and "1.00x" in html
    assert 'aria-sort="descending"' in html
    assert 'aria-current="page"' in html
    assert "Showing 1-4 of 4" in html


def test_overview_sets_aria_current(client: TestClient) -> None:
    login(client)
    assert 'aria-current="page"' in client.get("/dashboard").text


def test_tier_filter(client: TestClient, seeded: None) -> None:
    login(client)
    assert _order(client.get("/dashboard/drivers?tier=B").text) == ["drv-b"]
    # unknown tier falls back to all
    assert len(_order(client.get("/dashboard/drivers?tier=Z").text)) == 4


def test_empty_state_with_filter(client: TestClient, seeded: None) -> None:
    login(client)
    html = client.get("/dashboard/drivers?tier=E").text
    assert "No drivers match this filter" in html
    assert "Clear filter" in html
    assert _order(html) == []


def test_empty_state_without_drivers(client: TestClient) -> None:
    login(client)
    assert "No drivers yet" in client.get("/dashboard/drivers").text


@pytest.mark.parametrize(
    ("sort", "expected", "aria"),
    [
        ("score_desc", ["drv-a", "drv-b", "drv-none", "drv-d"], "descending"),
        ("score_asc", ["drv-d", "drv-none", "drv-b", "drv-a"], "ascending"),
        ("multiplier_desc", ["drv-d", "drv-none", "drv-b", "drv-a"], "descending"),
        ("multiplier_asc", ["drv-a", "drv-b", "drv-none", "drv-d"], "ascending"),
        ("bogus", ["drv-a", "drv-b", "drv-none", "drv-d"], "descending"),
    ],
)
def test_sorts(client: TestClient, seeded: None, sort: str, expected: list[str], aria: str) -> None:
    login(client)
    html = client.get(f"/dashboard/drivers?sort={sort}").text
    assert _order(html) == expected
    assert f'aria-sort="{aria}"' in html


def test_pagination_page_two(client: TestClient) -> None:
    db = SessionLocal()
    db.add_all([Driver(id=f"drv-{i:02d}", api_key_hash="h") for i in range(25)])
    db.commit()
    db.close()
    login(client)
    page1 = client.get("/dashboard/drivers").text
    page2 = client.get("/dashboard/drivers?page=2").text
    assert len(_order(page1)) == 20 and len(_order(page2)) == 5
    assert "Showing 21-25 of 25" in page2
    assert "Page 2 of 2" in page2
    assert set(_order(page1)).isdisjoint(_order(page2))
    # out-of-range and garbage pages are clamped
    assert "Page 2 of 2" in client.get("/dashboard/drivers?page=99").text
    assert "Page 1 of 2" in client.get("/dashboard/drivers?page=abc").text


def test_partial_requires_login(client: TestClient) -> None:
    assert client.get("/dashboard/partials/drivers").status_code == 303
    response = client.get("/dashboard/partials/drivers", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == "/dashboard/login"


def test_partial_returns_fragment_and_push_url(client: TestClient, seeded: None) -> None:
    login(client)
    response = client.get("/dashboard/partials/drivers?tier=A&sort=score_asc")
    assert response.status_code == 200
    assert "<html" not in response.text
    assert 'id="drivers-table"' in response.text
    assert _order(response.text) == ["drv-a"]
    assert response.headers["HX-Push-Url"] == "/dashboard/drivers?tier=A&sort=score_asc"


def test_sort_and_page_links_keep_tier(client: TestClient, seeded: None) -> None:
    login(client)
    html = client.get("/dashboard/drivers?tier=A").text
    assert re.search(r'href="/dashboard/drivers\?tier=A&amp;sort=score_asc"', html)
    assert re.search(r'href="/dashboard/drivers\?tier=A&amp;sort=multiplier_desc"', html)
    assert "sort ascending" in html and "sort descending" in html
    assert 'id="drivers-count"' in html and "hx-swap-oob" not in html


def test_partial_updates_count_out_of_band(client: TestClient, seeded: None) -> None:
    login(client)
    html = client.get("/dashboard/partials/drivers?tier=A").text
    assert 'id="drivers-count"' in html and 'hx-swap-oob="true"' in html
    assert "1 driver in tier A" in html


def test_hk_time_handles_none() -> None:
    from app.dashboard_auth import _hk_time

    assert _hk_time(None) == "-"
    assert _hk_time(datetime(2026, 1, 1, 16, 30, tzinfo=UTC)) == "2026-01-02 00:30"


def test_detail_renders_numbers(client: TestClient) -> None:
    db = SessionLocal()
    db.add(Driver(id="drv-x", api_key_hash="h"))
    db.flush()
    start = datetime(2026, 1, 1, 16, 30, tzinfo=UTC)  # 2026-01-02 00:30 Hong Kong
    _add_trip(db, "t-1", "drv-x", 80, started_at=start, label_source="bluetooth")
    _add_trip(db, "t-2", "drv-x", 70, trip_type="passenger", label_source="user")
    db.flush()
    db.add_all(
        [
            Event(trip_id="t-1", type="harsh_brake", time=start, peak_g=0.5),
            Event(trip_id="t-1", type="harsh_brake", time=start, peak_g=0.6),
            Event(trip_id="t-1", type="speeding", time=start),
        ]
    )
    db.commit()
    db.close()
    login(client)
    response = client.get("/dashboard/drivers/drv-x")
    assert response.status_code == 200
    html = response.text
    assert "drv-x" in html
    assert "0.90x" in html
    assert ">50%<" in html
    assert "Review</span>" in html
    assert html.count("Review</span>") == 1
    assert 'id="driver-heading"' in html
    assert "Raw counts in the last 90 days" in html
    assert re.search(r"Harsh brake.*?>2<", html, re.S)
    assert re.search(r"Speeding.*?>1<", html, re.S)
    assert "2026-01-02 00:30" in html
    assert 'href="/dashboard/trips/t-1"' in html
    assert "v-t" in html
    assert "Trend: Stable" in html
    assert re.search(r"Confirmed by driver.*?>1<", html, re.S)


def test_detail_unknown_driver_is_404(client: TestClient) -> None:
    login(client)
    response = client.get("/dashboard/drivers/nope")
    assert response.status_code == 404
    assert "Driver not found" in response.text
    assert "Sign out" in response.text


def test_detail_requires_login(client: TestClient) -> None:
    assert client.get("/dashboard/drivers/x").status_code == 303


def test_json_drivers_unchanged(client: TestClient, seeded: None) -> None:
    response = client.get("/v1/insurer/drivers", headers=insurer_headers())
    assert response.status_code == 200
    assert response.json() == [
        {"driver_id": "drv-a", "score": 95, "confidence": 0.1, "tier": "A",
         "premium_multiplier": 0.8, "total_trips_90d": 1, "total_distance_km_90d": 10.0},
        {"driver_id": "drv-b", "score": 80, "confidence": 0.1, "tier": "B",
         "premium_multiplier": 0.9, "total_trips_90d": 1, "total_distance_km_90d": 10.0},
        {"driver_id": "drv-none", "score": 60, "confidence": 0.5, "tier": "C",
         "premium_multiplier": 1.0, "total_trips_90d": 0, "total_distance_km_90d": 0.0},
        {"driver_id": "drv-d", "score": 50, "confidence": 0.1, "tier": "D",
         "premium_multiplier": 1.15, "total_trips_90d": 1, "total_distance_km_90d": 10.0},
    ]  # fmt: skip
    asc = client.get("/v1/insurer/drivers?sort=score_asc&tier=D", headers=insurer_headers())
    assert [d["driver_id"] for d in asc.json()] == ["drv-d"]
    # JSON route is not paginated
    db = SessionLocal()
    db.add_all([Driver(id=f"more-{i:02d}", api_key_hash="h") for i in range(25)])
    db.commit()
    db.close()
    assert len(client.get("/v1/insurer/drivers", headers=insurer_headers()).json()) == 29


def test_json_driver_detail_unchanged(client: TestClient, seeded: None) -> None:
    response = client.get("/v1/insurer/drivers/drv-b", headers=insurer_headers())
    assert response.status_code == 200
    body = response.json()
    trip = body["trips"][0]
    assert trip.pop("started_at")
    assert body == {
        "driver_id": "drv-b", "score": 80, "confidence": 0.1, "tier": "B",
        "premium_multiplier": 0.9, "event_rates": {},
        "trips": [{
            "trip_id": "t-drv-b", "distance_km": 10.0, "duration_min": None,
            "score": 80, "tier": "B",
            "trip_type": "driver", "needs_confirmation": False, "label_source": None,
            "transit_line": None,
        }],
        "model_version": "v-t", "passenger_share": 0.0,
        "label_sources": {"user": 0, "bluetooth": 0, "rules": 0, "unlabelled": 1},
        "flagged_for_review": False,
    }  # fmt: skip
    missing = client.get("/v1/insurer/drivers/nope", headers=insurer_headers())
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Driver not found"}
