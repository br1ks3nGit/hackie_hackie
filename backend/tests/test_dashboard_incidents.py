import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import Driver, Incident, Trip
from tests.test_dashboard import PASSWORD_HASH, login

BASE = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


@pytest.fixture(autouse=True)
def configured_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "dashboard_password_hash", PASSWORD_HASH)
    monkeypatch.setattr(get_settings(), "dashboard_username", "admin")


def _seed(rows: list[dict[str, Any]]) -> None:
    """Seed driver drv-1, trip t-1 and incidents; minute offset i gives newest = last."""
    db = SessionLocal()
    db.add(Driver(id="drv-1", api_key_hash="h"))
    db.flush()
    db.add(Trip(id="t-1", driver_id="drv-1", status="done", started_at=BASE, trip_type="driver"))
    db.flush()
    for n, row in enumerate(rows):
        values = {"driver_id": "drv-1", "type": "crash", "time": BASE + timedelta(minutes=n)}
        db.add(Incident(**{**values, **row}))
    db.commit()
    db.close()


def _five() -> None:
    _seed(
        [
            {"confirmed": None, "lat": 22.30, "lon": 114.17, "peak_g": 4.0},
            {"confirmed": "ok", "trip_id": "t-1", "lat": 22.31, "lon": 114.18, "peak_g": 3.5},
            {"confirmed": "no_response", "lat": 22.32, "lon": 114.19, "peak_g": 5.25},
            {"confirmed": "help_needed", "trip_id": "t-1", "lat": 22.33, "lon": 114.2},
        ]
    )


def test_requires_login(client: TestClient) -> None:
    assert client.get("/dashboard/incidents").status_code == 303


def test_list_newest_first_with_all_statuses(client: TestClient) -> None:
    _five()
    login(client)
    html = client.get("/dashboard/incidents").text
    times = re.findall(r'<time datetime="([^"]+)"', html)
    assert times == sorted(times, reverse=True) and len(times) == 4
    for text in ("Help needed", "No response", ">OK<", "Unconfirmed", "4 incidents"):
        assert text in html
    assert "20:03" in html  # 12:03 UTC shown as HKT
    assert "22.3300, 114.2000" in html
    assert "5.25 g" in html
    assert 'aria-current="page"' in html and "bg-danger-soft" in html


def test_links(client: TestClient) -> None:
    _five()
    login(client)
    html = client.get("/dashboard/incidents").text
    assert 'href="/dashboard/drivers/drv-1"' in html
    assert 'href="/dashboard/trips/t-1"' in html
    assert html.count("View on map") == 2
    assert html.count("Open in OpenStreetMap") == 2
    assert "https://www.openstreetmap.org/?mlat=22.300000&amp;mlon=114.170000#map=16/22.3" in html
    assert 'rel="noopener noreferrer"' in html


@pytest.mark.parametrize(
    ("status", "count"),
    [("help_needed", 1), ("no_response", 1), ("ok", 1), ("unconfirmed", 1), ("bogus", 4), ("", 4)],
)
def test_filters(client: TestClient, status: str, count: int) -> None:
    _five()
    login(client)
    html = client.get(f"/dashboard/incidents?status={status}").text
    assert len(re.findall(r"<time datetime=", html)) == count


def test_empty_states(client: TestClient) -> None:
    login(client)
    assert "No incidents recorded." in client.get("/dashboard/incidents").text
    html = client.get("/dashboard/incidents?status=ok").text
    assert "No incidents match this filter" in html and "Clear filter" in html


def test_pagination(client: TestClient) -> None:
    _seed([{"confirmed": "ok"} for _ in range(25)])
    login(client)
    page1 = client.get("/dashboard/incidents").text
    page2 = client.get("/dashboard/incidents?page=2").text
    assert page1.count("<time ") == 20 and page2.count("<time ") == 5
    assert "Showing 21-25 of 25" in page2 and "Page 2 of 2" in page2
    assert "Page 2 of 2" in client.get("/dashboard/incidents?page=99").text
    assert "Page 1 of 2" in client.get("/dashboard/incidents?page=abc").text


def test_partial_requires_login(client: TestClient) -> None:
    assert client.get("/dashboard/partials/incidents").status_code == 303
    response = client.get("/dashboard/partials/incidents", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == "/dashboard/login"


def test_partial_fragment_and_push_url(client: TestClient) -> None:
    _five()
    login(client)
    response = client.get("/dashboard/partials/incidents?status=ok")
    assert response.status_code == 200
    assert "<html" not in response.text and 'hx-swap-oob="true"' in response.text
    assert "1 incident (OK)" in response.text
    assert response.headers["HX-Push-Url"] == "/dashboard/incidents?status=ok"
