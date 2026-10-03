import os
import unittest.mock
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db
from app.config import get_settings

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_classify.db"
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
    if os.path.exists("./test_classify.db"):
        os.remove("./test_classify.db")


def _register_and_consent():
    response = client.post("/v1/drivers/register", json={})
    data = response.json()
    driver_id = data["driver_id"]
    api_key = data["api_key"]
    client.post(
        "/v1/consent",
        headers={"X-API-Key": api_key},
        json={"driver_id": driver_id, "version": "1.0"},
    )
    return driver_id, api_key


def _upload_trip(api_key, chunks):
    response = client.post("/v1/trips/start", headers={"X-API-Key": api_key})
    trip_id = response.json()["trip_id"]
    for chunk in chunks:
        client.post(
            f"/v1/trips/{trip_id}/chunks",
            headers={"X-API-Key": api_key},
            json=chunk,
        )
    return trip_id


def test_label_trip_as_passenger_removes_from_score():
    """A passenger label should remove the trip from the driver score."""
    driver_id, api_key = _register_and_consent()

    # Upload a trip
    chunks = [{
        "seq": 0,
        "imu": [
            {"t": 1759986000000 + i * 20, "ax": 0.1, "ay": 0.2, "az": 9.8,
             "gx": 0.01, "gy": 0.01, "gz": 0.02}
            for i in range(100)
        ],
        "gps": [
            {"t": 1759986000000 + i * 1000, "lat": 22.50 + i * 0.005,
             "lon": 114.30 + i * 0.005, "speed": 15.0}
            for i in range(60)
        ],
    }]
    trip_id = _upload_trip(api_key, chunks)

    # Label as passenger
    response = client.post(
        f"/v1/me/trips/{trip_id}/label",
        headers={"X-API-Key": api_key},
        json={"trip_type": "passenger"},
    )
    assert response.status_code == 200
    assert response.json()["trip_type"] == "passenger"
    assert response.json()["status"] == "removed_from_score"


def test_label_trip_as_driver_adds_to_score():
    """A driver label should add the trip to the driver score."""
    driver_id, api_key = _register_and_consent()

    chunks = [{
        "seq": 0,
        "imu": [
            {"t": 1759986000000 + i * 20, "ax": 0.1, "ay": 0.2, "az": 9.8,
             "gx": 0.01, "gy": 0.01, "gz": 0.02}
            for i in range(100)
        ],
        "gps": [
            {"t": 1759986000000 + i * 1000, "lat": 22.50 + i * 0.005,
             "lon": 114.30 + i * 0.005, "speed": 15.0}
            for i in range(60)
        ],
    }]
    trip_id = _upload_trip(api_key, chunks)

    response = client.post(
        f"/v1/me/trips/{trip_id}/label",
        headers={"X-API-Key": api_key},
        json={"trip_type": "driver"},
    )
    assert response.status_code == 200
    assert response.json()["trip_type"] == "driver"
    assert response.json()["status"] == "added_to_score"


def test_trip_list_includes_trip_type():
    """Trip list should include trip_type and needs_confirmation."""
    driver_id, api_key = _register_and_consent()

    chunks = [{
        "seq": 0,
        "imu": [
            {"t": 1759986000000 + i * 20, "ax": 0.1, "ay": 0.2, "az": 9.8,
             "gx": 0.01, "gy": 0.01, "gz": 0.02}
            for i in range(100)
        ],
        "gps": [
            {"t": 1759986000000 + i * 1000, "lat": 22.50 + i * 0.005,
             "lon": 114.30 + i * 0.005, "speed": 15.0}
            for i in range(60)
        ],
    }]
    _upload_trip(api_key, chunks)

    response = client.get("/v1/me/trips", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    trips = response.json()
    assert len(trips) >= 1
    assert "trip_type" in trips[0]
    assert "needs_confirmation" in trips[0]


def test_register_with_emergency_contact():
    """Registration should accept emergency contact info."""
    response = client.post("/v1/drivers/register", json={
        "emergency_contact_name": "Mom",
        "emergency_contact_phone": "+852 9123 4567",
    })
    assert response.status_code == 200
    assert "driver_id" in response.json()


def test_create_and_confirm_incident():
    """Should be able to create and confirm an incident."""
    driver_id, api_key = _register_and_consent()

    response = client.post(
        "/v1/me/incidents",
        headers={"X-API-Key": api_key},
        json={
            "type": "crash",
            "time": datetime.utcnow().isoformat(),
            "lat": 22.3193,
            "lon": 114.1694,
            "peak_g": 5.2,
        },
    )
    assert response.status_code == 200
    incident_id = response.json()["id"]

    response = client.post(
        f"/v1/me/incidents/{incident_id}/confirm",
        headers={"X-API-Key": api_key},
        json={"confirmed": "ok"},
    )
    assert response.status_code == 200
    assert response.json()["confirmed"] == "ok"


def test_insurer_detail_includes_passenger_share():
    """Insurer driver detail should include passenger share and label sources."""
    driver_id, api_key = _register_and_consent()

    chunks = [{
        "seq": 0,
        "imu": [
            {"t": 1759986000000 + i * 20, "ax": 0.1, "ay": 0.2, "az": 9.8,
             "gx": 0.01, "gy": 0.01, "gz": 0.02}
            for i in range(100)
        ],
        "gps": [
            {"t": 1759986000000 + i * 1000, "lat": 22.50 + i * 0.005,
             "lon": 114.30 + i * 0.005, "speed": 15.0}
            for i in range(60)
        ],
    }]
    trip_id = _upload_trip(api_key, chunks)

    # Label as passenger
    client.post(
        f"/v1/me/trips/{trip_id}/label",
        headers={"X-API-Key": api_key},
        json={"trip_type": "passenger"},
    )

    settings = get_settings()
    response = client.get(
        f"/v1/insurer/drivers/{driver_id}",
        headers={"X-API-Key": settings.insurer_api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert "passenger_share" in data
    assert "label_sources" in data
    assert "flagged_for_review" in data
