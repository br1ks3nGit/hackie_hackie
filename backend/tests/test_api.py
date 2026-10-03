import unittest.mock
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import TripFeature
from tests.helpers import insurer_headers

client = TestClient(app)


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
        "speed_samples": [
            {"t": 1759986000000, "speed": 10.0},
            {"t": 1759986001000, "speed": 15.0},
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

    response = client.get("/v1/insurer/overview", headers=insurer_headers())
    assert response.status_code == 200


def test_trip_list_datetime_is_timezone_aware():
    api_key = client.post("/v1/drivers/register", json={}).json()["api_key"]
    headers = {"X-API-Key": api_key}
    client.post("/v1/consent", headers=headers, json={"version": "1.0"})
    assert client.post("/v1/trips/start", headers=headers).status_code == 200

    response = client.get("/v1/me/trips", headers=headers)
    assert response.status_code == 200
    started_at = datetime.fromisoformat(response.json()[0]["started_at"])
    assert started_at.tzinfo is not None
    assert started_at.utcoffset() == timedelta(0)


def test_trip_list_has_duration_min():
    api_key = client.post("/v1/drivers/register", json={}).json()["api_key"]
    headers = {"X-API-Key": api_key}
    client.post("/v1/consent", headers=headers, json={"version": "1.0"})
    trip_id = client.post("/v1/trips/start", headers=headers).json()["trip_id"]

    assert client.get("/v1/me/trips", headers=headers).json()[0]["duration_min"] is None
    detail = client.get(f"/v1/me/trips/{trip_id}", headers=headers).json()
    assert detail["duration_min"] is None

    with SessionLocal() as db:
        db.add(TripFeature(trip_id=trip_id, features={"distance_km": 3.0, "duration_min": 21.5}))
        db.commit()
    assert client.get("/v1/me/trips", headers=headers).json()[0]["duration_min"] == 21.5
