import os
import unittest.mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import Base, get_db
from app.main import app

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def db_override():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def teardown_module():
    if os.path.exists("./test.db"):
        os.remove("./test.db")


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_register_driver():
    response = client.post("/v1/drivers/register", json={})
    assert response.status_code == 200
    data = response.json()
    assert "driver_id" in data
    assert "api_key" in data
    assert data["driver_id"].startswith("drv-")


def test_consent_required_for_trip():
    response = client.post("/v1/drivers/register", json={})
    data = response.json()
    api_key = data["api_key"]

    response = client.post("/v1/trips/start", headers={"X-API-Key": api_key})
    assert response.status_code == 403


def test_full_trip_flow():
    response = client.post("/v1/drivers/register", json={})
    data = response.json()
    api_key = data["api_key"]

    response = client.post(
        "/v1/consent",
        headers={"X-API-Key": api_key},
        json={"version": "1.0"},
    )
    assert response.status_code == 200

    response = client.post("/v1/trips/start", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    trip_id = response.json()["trip_id"]

    chunk = {
        "seq": 0,
        "imu": [
            {
                "t": 1759986000000,
                "ax": 0.1,
                "ay": 0.2,
                "az": 9.8,
                "gx": 0.01,
                "gy": 0.01,
                "gz": 0.02,
            },
            {
                "t": 1759986000020,
                "ax": 0.1,
                "ay": -3.5,
                "az": 9.7,
                "gx": 0.01,
                "gy": 0.01,
                "gz": 0.02,
            },
        ],
        "gps": [
            {"t": 1759986000000, "lat": 22.3193, "lon": 114.1694, "speed": 10.0},
            {"t": 1759986001000, "lat": 22.3200, "lon": 114.1700, "speed": 15.0},
        ],
    }

    response = client.post(
        f"/v1/trips/{trip_id}/chunks",
        headers={"X-API-Key": api_key},
        json=chunk,
    )
    assert response.status_code == 200

    response = client.post(
        f"/v1/trips/{trip_id}/chunks",
        headers={"X-API-Key": api_key},
        json=chunk,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "already_received"

    with unittest.mock.patch("app.routers.ingestion.BackgroundTasks.add_task") as mock_add_task:
        response = client.post(f"/v1/trips/{trip_id}/end", headers={"X-API-Key": api_key})
        assert response.status_code == 200
        assert response.json()["status"] == "processing"
        mock_add_task.assert_called_once()

    response = client.get(f"/v1/trips/{trip_id}/status", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    assert response.json()["trip_id"] == trip_id
    assert response.json()["status"] in ["uploading", "processing", "done", "failed"]


def test_get_driver_summary():
    response = client.post("/v1/drivers/register", json={})
    data = response.json()
    api_key = data["api_key"]

    response = client.get("/v1/me/summary", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    data = response.json()
    assert "score" in data
    assert "tier" in data
    assert "premium_multiplier" in data


def test_invalid_api_key():
    response = client.get("/v1/me/summary", headers={"X-API-Key": "invalid-key"})
    assert response.status_code == 401


def test_insurer_endpoints_require_insurer_key():
    response = client.get("/v1/insurer/overview", headers={"X-API-Key": "invalid-key"})
    assert response.status_code == 401

    settings = get_settings()
    response = client.get("/v1/insurer/overview", headers={"X-API-Key": settings.insurer_api_key})
    assert response.status_code == 200
