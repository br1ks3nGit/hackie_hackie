import re

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.services.passwords import hash_password, verify_password

PASSWORD = "correct horse battery staple"
PASSWORD_HASH = hash_password(PASSWORD)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


@pytest.fixture(autouse=True)
def configured_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "dashboard_password_hash", PASSWORD_HASH)
    monkeypatch.setattr(get_settings(), "dashboard_username", "admin")


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


def test_unconfigured_hash_shows_clear_message(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "dashboard_password_hash", None)
    response = login(client)
    assert response.status_code == 401
    assert "Dashboard login is not configured" in response.text


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


def test_settings_default_username_and_unset_hash() -> None:
    settings = Settings(
        insurer_api_key="k", driver_api_key_salt="s", session_secret="s" * 32, _env_file=None
    )
    assert settings.dashboard_username == "admin"
    assert settings.dashboard_password_hash is None
    assert settings.session_https_only is False
