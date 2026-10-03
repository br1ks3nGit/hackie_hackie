import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.main import app
from app.models import ApiKey, AppSetting, User
from app.services import api_keys as key_service
from app.services import users as user_service
from tests.helpers import ADMIN_USER, create_admin, insurer_headers
from tests.test_dashboard import csrf_from, login

GOOD_PASSWORD = "another good password"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def admin_client(client: TestClient) -> TestClient:
    create_admin()
    assert login(client).status_code == 303
    return client


def _token(client: TestClient, page: str) -> str:
    return csrf_from(client.get(page).text)


def _post(client: TestClient, page: str, action: str, **data: str):
    return client.post(action, data={"csrf_token": _token(client, page), **data})


# --- salt ---------------------------------------------------------------------------------


def test_salt_is_generated_once_and_reused() -> None:
    with SessionLocal() as db:
        first = key_service.get_salt(db)
        second = key_service.get_salt(db)
        count = db.scalar(select(func.count()).select_from(AppSetting))
    assert first == second
    assert len(first) >= 32
    assert count == 1


# --- api keys -----------------------------------------------------------------------------


def test_api_key_is_stored_hashed_and_authenticates() -> None:
    with SessionLocal() as db:
        record, plaintext = key_service.create_api_key(db, " Reporting ", None)
        assert plaintext.startswith("dsk_")
        assert record.key_prefix == plaintext[:8]
        assert record.name == "Reporting"
        assert plaintext not in record.key_hash
        found = key_service.find_active_key(db, plaintext)
        assert found is not None and found.id == record.id
        assert found.last_used_at is not None
        assert key_service.find_active_key(db, "dsk_wrong") is None


def test_revoked_key_is_denied() -> None:
    with SessionLocal() as db:
        record, plaintext = key_service.create_api_key(db, "temp", None)
        assert key_service.revoke_api_key(db, record.id)
        assert key_service.find_active_key(db, plaintext) is None
        assert not key_service.revoke_api_key(db, 9999)


def test_insurer_endpoint_accepts_generated_key_only(client: TestClient) -> None:
    assert client.get("/v1/insurer/overview", headers={"X-API-Key": "nope"}).status_code == 401
    assert client.get("/v1/insurer/overview", headers=insurer_headers()).status_code == 200


def test_api_key_name_is_validated() -> None:
    with SessionLocal() as db, pytest.raises(ValueError, match="empty"):
        key_service.create_api_key(db, "   ", None)


# --- users --------------------------------------------------------------------------------


def test_user_password_is_hashed_and_authenticates() -> None:
    with SessionLocal() as db:
        user = user_service.create_user(db, "alice", GOOD_PASSWORD)
        assert user.password_hash.startswith("scrypt:")
        assert GOOD_PASSWORD not in user.password_hash
        assert user_service.authenticate(db, "alice", GOOD_PASSWORD) is not None
        assert user.last_login_at is not None
        assert user_service.authenticate(db, "alice", "wrong") is None
        assert user_service.authenticate(db, "nobody", GOOD_PASSWORD) is None


@pytest.mark.parametrize("username", ["", "   ", "has space", "x" * 65, "semi;colon"])
def test_bad_usernames_rejected(username: str) -> None:
    with SessionLocal() as db, pytest.raises(ValueError):
        user_service.create_user(db, username, GOOD_PASSWORD)


def test_duplicate_username_rejected() -> None:
    with SessionLocal() as db:
        user_service.create_user(db, "bob", GOOD_PASSWORD)
        with pytest.raises(ValueError, match="already exists"):
            user_service.create_user(db, "bob", GOOD_PASSWORD)


def test_inactive_user_cannot_log_in_and_last_active_user_is_protected() -> None:
    with SessionLocal() as db:
        first = user_service.create_user(db, "first", GOOD_PASSWORD)
        with pytest.raises(ValueError, match="last active"):
            user_service.set_active(db, first, False)
        second = user_service.create_user(db, "second", GOOD_PASSWORD)
        user_service.set_active(db, second, False)
        assert user_service.authenticate(db, "second", GOOD_PASSWORD) is None


# --- screens ------------------------------------------------------------------------------


@pytest.mark.parametrize("page", ["/dashboard/users", "/dashboard/api-keys"])
def test_screens_require_login(client: TestClient, page: str) -> None:
    response = client.get(page)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard/login"


def test_users_screen_lists_users_and_has_nav(admin_client: TestClient) -> None:
    html = admin_client.get("/dashboard/users").text
    assert ADMIN_USER in html
    assert 'href="/dashboard/users"' in html
    assert 'href="/dashboard/api-keys"' in html


def test_create_user_from_screen(admin_client: TestClient) -> None:
    response = _post(
        admin_client,
        "/dashboard/users",
        "/dashboard/users",
        username="carol",
        password=GOOD_PASSWORD,
        password_confirm=GOOD_PASSWORD,
    )
    assert response.status_code == 303
    assert "User &#39;carol&#39; created" in admin_client.get("/dashboard/users").text
    with SessionLocal() as db:
        assert user_service.authenticate(db, "carol", GOOD_PASSWORD) is not None


@pytest.mark.parametrize(
    ("password", "confirm", "message"),
    [(GOOD_PASSWORD, "different", "do not match"), ("short", "short", "at least 8")],
)
def test_create_user_rejects_bad_password(
    admin_client: TestClient, password: str, confirm: str, message: str
) -> None:
    response = _post(
        admin_client,
        "/dashboard/users",
        "/dashboard/users",
        username="dave",
        password=password,
        password_confirm=confirm,
    )
    assert response.status_code == 422
    assert message in response.text
    with SessionLocal() as db:
        assert user_service.get_by_username(db, "dave") is None


def test_create_user_requires_csrf(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/dashboard/users",
        data={"username": "eve", "password": GOOD_PASSWORD, "password_confirm": GOOD_PASSWORD},
    )
    assert response.status_code == 403


def test_change_password_from_screen(admin_client: TestClient) -> None:
    with SessionLocal() as db:
        target = user_service.create_user(db, "frank", GOOD_PASSWORD)
        target_id = target.id
    response = _post(
        admin_client,
        "/dashboard/users",
        f"/dashboard/users/{target_id}/password",
        password="a brand new password",
        password_confirm="a brand new password",
    )
    assert response.status_code == 303
    with SessionLocal() as db:
        assert user_service.authenticate(db, "frank", GOOD_PASSWORD) is None
        assert user_service.authenticate(db, "frank", "a brand new password") is not None


def test_deactivate_other_user_and_block_self(admin_client: TestClient) -> None:
    with SessionLocal() as db:
        other = user_service.create_user(db, "grace", GOOD_PASSWORD)
        other_id = other.id
        admin = user_service.get_by_username(db, ADMIN_USER)
        assert admin is not None
        admin_id = admin.id
    _post(admin_client, "/dashboard/users", f"/dashboard/users/{other_id}/active", active="false")
    with SessionLocal() as db:
        other_user = db.get(User, other_id)
        assert other_user is not None
        assert not other_user.is_active
    _post(admin_client, "/dashboard/users", f"/dashboard/users/{admin_id}/active", active="false")
    assert "cannot deactivate your own account" in admin_client.get("/dashboard/users").text
    with SessionLocal() as db:
        admin_user = db.get(User, admin_id)
        assert admin_user is not None
        assert admin_user.is_active


def test_deactivated_user_session_ends(client: TestClient) -> None:
    create_admin()
    with SessionLocal() as db:
        user_service.create_user(db, "henry", GOOD_PASSWORD)
    assert login(client, GOOD_PASSWORD, "henry").status_code == 303
    assert client.get("/dashboard").status_code == 200
    with SessionLocal() as db:
        henry = user_service.get_by_username(db, "henry")
        assert henry is not None
        user_service.set_active(db, henry, False)
    assert client.get("/dashboard").status_code == 303


def test_generate_api_key_from_screen_shows_key_once(admin_client: TestClient) -> None:
    response = _post(
        admin_client, "/dashboard/api-keys", "/dashboard/api-keys", name="Reporting export"
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    with SessionLocal() as db:
        record = db.scalar(select(ApiKey))
        assert record is not None and record.name == "Reporting export"
        assert record.created_by_user_id is not None
    shown = response.text.split('id="new-key"')[1].split(">")[1].split("<")[0]
    assert shown.startswith("dsk_")
    assert shown not in admin_client.get("/dashboard/api-keys").text
    headers = {"X-API-Key": shown}
    assert admin_client.get("/v1/insurer/overview", headers=headers).status_code == 200


def test_revoke_api_key_from_screen(admin_client: TestClient) -> None:
    with SessionLocal() as db:
        record, plaintext = key_service.create_api_key(db, "to revoke", None)
        key_id = record.id
    response = _post(admin_client, "/dashboard/api-keys", f"/dashboard/api-keys/{key_id}/revoke")
    assert response.status_code == 303
    assert "Revoked" in admin_client.get("/dashboard/api-keys").text
    denied = admin_client.get("/v1/insurer/overview", headers={"X-API-Key": plaintext})
    assert denied.status_code == 401


def test_api_keys_screen_explains_generated_salt(admin_client: TestClient) -> None:
    html = admin_client.get("/dashboard/api-keys").text
    assert "Generated automatically" in html
    with SessionLocal() as db:
        assert db.get(AppSetting, key_service.SALT_SETTING) is not None
