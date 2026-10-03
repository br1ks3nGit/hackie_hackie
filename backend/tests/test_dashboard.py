import json
import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import SessionLocal
from app.main import app
from app.model import tier_to_multiplier
from app.models import Driver, Trip, TripFeature, TripScore, User
from app.services.passwords import hash_password, verify_password
from tests.helpers import ADMIN_PASSWORD, create_admin, insurer_headers

PASSWORD = ADMIN_PASSWORD


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


@pytest.fixture(autouse=True)
def configured_login() -> None:
    create_admin()


def csrf_from(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "no csrf_token input found"
    return match.group(1)


def login(client: TestClient, password: str = PASSWORD, username: str = "admin"):
    token = csrf_from(client.get("/dashboard/login").text)
    return client.post(
        "/dashboard/login",
        data={"username": username, "password": password, "csrf_token": token},
    )


def test_login_page_renders_with_csrf_token(client: TestClient) -> None:
    response = client.get("/dashboard/login")
    assert response.status_code == 200
    assert "DriveScore Insurer" in response.text
    assert len(csrf_from(response.text)) >= 32
    assert "Sign out" not in response.text


def test_login_success_redirects_and_opens_session(client: TestClient) -> None:
    response = login(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "Overview" in page.text
    assert "Sign out" in page.text
    assert "X-CSRF-Token" in page.text


def test_login_rotates_csrf_token(client: TestClient) -> None:
    before = csrf_from(client.get("/dashboard/login").text)
    login(client)
    after = csrf_from(client.get("/dashboard").text)
    assert before != after


@pytest.mark.parametrize(
    ("username", "password"), [("admin", "wrong"), ("someone", PASSWORD), ("", "")]
)
def test_login_bad_credentials_returns_401(
    client: TestClient, username: str, password: str
) -> None:
    response = login(client, password=password, username=username)
    assert response.status_code == 401
    assert "Invalid username or password" in response.text
    assert client.get("/dashboard").status_code == 303


def test_login_without_csrf_token_is_403(client: TestClient) -> None:
    client.get("/dashboard/login")
    response = client.post("/dashboard/login", data={"username": "admin", "password": PASSWORD})
    assert response.status_code == 403


def test_login_with_invalid_csrf_token_is_403(client: TestClient) -> None:
    client.get("/dashboard/login")
    response = client.post(
        "/dashboard/login",
        data={"username": "admin", "password": PASSWORD, "csrf_token": "forged"},
    )
    assert response.status_code == 403


def test_login_with_csrf_in_header_is_accepted(client: TestClient) -> None:
    token = csrf_from(client.get("/dashboard/login").text)
    response = client.post(
        "/dashboard/login",
        data={"username": "admin", "password": PASSWORD},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 303


def test_dashboard_requires_login(client: TestClient) -> None:
    response = client.get("/dashboard")
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard/login"


def test_dashboard_requires_login_htmx_uses_hx_redirect(client: TestClient) -> None:
    response = client.get("/dashboard", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == "/dashboard/login"


def test_logout_requires_csrf(client: TestClient) -> None:
    login(client)
    assert client.post("/dashboard/logout").status_code == 403
    assert client.get("/dashboard").status_code == 200


def test_logout_clears_session(client: TestClient) -> None:
    login(client)
    token = csrf_from(client.get("/dashboard").text)
    response = client.post("/dashboard/logout", data={"csrf_token": token})
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard/login"
    assert client.get("/dashboard").status_code == 303


def test_login_with_no_users_is_rejected(client: TestClient) -> None:
    with SessionLocal() as db:
        db.query(User).delete()
        db.commit()
    response = login(client)
    assert response.status_code == 401
    assert "Invalid username or password" in response.text


def test_dashboard_routes_are_not_in_openapi(client: TestClient) -> None:
    assert not [p for p in app.openapi()["paths"] if p.startswith("/dashboard")]


def test_static_assets_are_served(client: TestClient) -> None:
    assert client.get("/static/css/uno.css").status_code == 200
    assert client.get("/static/vendor/htmx-2.0.11.min.js").status_code == 200


def test_password_hash_round_trip() -> None:
    stored = hash_password("s3cret")
    assert "$" not in stored
    assert stored.startswith("scrypt:32768:8:1:")
    assert verify_password("s3cret", stored)
    assert not verify_password("other", stored)


def test_hash_is_salted() -> None:
    assert hash_password("same") != hash_password("same")


@pytest.mark.parametrize("stored", ["", "garbage", "bcrypt:1:2:3:aa:bb", "scrypt:x:8:1:aa:bb"])
def test_malformed_hash_never_verifies(stored: str) -> None:
    assert not verify_password("anything", stored)


def test_settings_ignore_legacy_credentials_now_stored_in_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INSURER_API_KEY", "k")
    monkeypatch.setenv("DRIVER_API_KEY_SALT", "s")
    monkeypatch.setenv("DASHBOARD_PASSWORD_HASH", "x")
    settings = Settings(session_secret="s" * 32, _env_file=None)
    assert not hasattr(settings, "insurer_api_key")
    assert not hasattr(settings, "dashboard_password_hash")
    assert settings.session_https_only is False


def _trip_rows(
    trip_id: str, driver_id: str, tier: str, trip_type: str = "driver", age_days: int = 1
) -> list[Trip | TripFeature | TripScore]:
    created = datetime.now(UTC) - timedelta(days=age_days)
    return [
        Trip(
            id=trip_id,
            driver_id=driver_id,
            status="done",
            started_at=created,
            trip_type=trip_type,
            created_at=created,
        ),
        TripFeature(trip_id=trip_id, features={"distance_km": 10.0}),
        TripScore(trip_id=trip_id, confidence=0.1, score=90, tier=tier, model_version="test"),
    ]


@pytest.fixture
def seeded_overview() -> None:
    db = SessionLocal()
    db.add_all([Driver(id="drv-a", api_key_hash="h1"), Driver(id="drv-b", api_key_hash="h2")])
    db.flush()
    db.add_all(_trip_rows("t1", "drv-a", "A"))
    db.add_all(_trip_rows("t2", "drv-a", "A"))
    db.add_all(_trip_rows("t3", "drv-b", "C"))
    db.add_all(_trip_rows("t-passenger", "drv-b", "A", "passenger"))
    db.add_all(_trip_rows("t-old", "drv-b", "E", age_days=120))
    db.commit()
    db.close()


def test_overview_renders_seeded_numbers(client: TestClient, seeded_overview: None) -> None:
    login(client)
    html = client.get("/dashboard").text
    assert 'id="overview-stats"' in html
    assert 'hx-trigger="every 30s"' in html
    assert re.search(r"Total drivers</dt>\s*<dd[^>]*>2</dd>", html)
    assert re.search(r"Trips in last 90 days</dt>\s*<dd[^>]*>3</dd>", html)
    expected = (tier_to_multiplier("A") * 2 + tier_to_multiplier("C")) / 3
    assert f">{expected:.2f}x</dd>" in html
    data = re.search(r'id="tier-data">(.*?)</script>', html, re.S)
    assert data
    assert json.loads(data.group(1)) == [
        {"tier": "A", "count": 2},
        {"tier": "B", "count": 0},
        {"tier": "C", "count": 1},
        {"tier": "D", "count": 0},
        {"tier": "E", "count": 0},
    ]
    assert "Scored trips per tier: A 2, B 0, C 1, D 0, E 0" in html


def test_json_overview_seeded(seeded_overview: None) -> None:
    api = TestClient(app)
    response = api.get("/v1/insurer/overview", headers=insurer_headers())
    assert response.status_code == 200
    assert response.json() == {
        "total_drivers": 2,
        "total_trips_90d": 3,
        "tier_distribution": {"A": 2, "C": 1},
        "average_multiplier": 0.87,
    }


def test_overview_empty_state(client: TestClient) -> None:
    login(client)
    html = client.get("/dashboard").text
    assert "No scored trips yet" in html
    assert 'id="tier-data"' not in html
    assert (
        '<dd class="mt-1 text-3xl font-bold text-text">-<span class="sr-only">No data</span></dd>'
        in html
    )


def test_overview_partial_requires_login(client: TestClient) -> None:
    response = client.get("/dashboard/partials/overview")
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard/login"


def test_overview_partial_expired_session_htmx_redirects(client: TestClient) -> None:
    response = client.get("/dashboard/partials/overview", headers={"HX-Request": "true"})
    assert response.headers["HX-Redirect"] == "/dashboard/login"
    assert "<html" not in response.text


def test_overview_partial_returns_fragment(client: TestClient, seeded_overview: None) -> None:
    login(client)
    response = client.get("/dashboard/partials/overview", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert response.text.lstrip().startswith('<div id="overview-stats"')
    assert "<html" not in response.text
    assert "Total drivers" in response.text
