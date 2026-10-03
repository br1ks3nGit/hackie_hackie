"""Privacy P1: coordinates never reach disk or the processed rows."""

import glob
import gzip
import json
import os

from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import Event, Incident, TripFeature
from app.pipeline import process_trip

client = TestClient(app)
T0 = 1759986000000


def _register_and_start() -> tuple[str, str]:
    api_key = client.post("/v1/drivers/register", json={}).json()["api_key"]
    client.post("/v1/consent", headers={"X-API-Key": api_key}, json={"version": "1.0"})
    trip_id = client.post("/v1/trips/start", headers={"X-API-Key": api_key}).json()["trip_id"]
    return api_key, trip_id


def _imu(i: int, spike_at: int | None = None) -> dict:
    spike = 80.0 if i == spike_at else 0.0
    return {"t": T0 + i * 20, "ax": spike, "ay": 0.0, "az": 9.8, "gx": 0.0, "gy": 0.0, "gz": 0.0}


def _gps(i: int, speed: float) -> dict:
    return {
        "t": T0 + i * 1000,
        "lat": 22.3 + i * 0.0001,
        "lon": 114.1 + i * 0.0001,
        "speed": speed,
        "heading": 90.0,
        "accuracy": 5.0,
    }


def _upload(api_key: str, trip_id: str, chunk: dict) -> None:
    response = client.post(
        f"/v1/trips/{trip_id}/chunks", headers={"X-API-Key": api_key}, json=chunk
    )
    assert response.status_code == 200


def test_raw_chunk_on_disk_has_no_coordinates() -> None:
    api_key, trip_id = _register_and_start()
    _upload(
        api_key,
        trip_id,
        {"seq": 0, "imu": [_imu(0)], "gps": [_gps(0, 10.0), _gps(1, 12.0)], "car_connected": True},
    )

    path = os.path.join(get_settings().data_dir, trip_id, "0.json.gz")
    with gzip.open(path, "rt", encoding="utf-8") as f:
        raw = f.read()
    stored = json.loads(raw)

    assert len(stored["gps"]) == 2
    for sample in stored["gps"]:
        assert set(sample) == {"t", "speed", "heading", "accuracy"}
    for key in ("lat", "lon", "lng", "latitude", "longitude"):
        assert f'"{key}"' not in raw
    assert not glob.glob(os.path.join(get_settings().data_dir, trip_id, "*.json"))


def test_processed_events_and_incidents_have_no_location() -> None:
    api_key, trip_id = _register_and_start()
    # 120 s at 20 m/s (speeding), then stopped; an impact spike at 60 s, still afterwards
    n_imu = 6000
    gps = [_gps(i, 20.0 if i < 60 else 0.0) for i in range(120)]
    _upload(
        api_key,
        trip_id,
        {"seq": 0, "imu": [_imu(i, spike_at=3000) for i in range(n_imu)], "gps": gps},
    )

    process_trip(trip_id)

    with SessionLocal() as db:
        events = db.query(Event).filter(Event.trip_id == trip_id).all()
        incidents = db.query(Incident).filter(Incident.trip_id == trip_id).all()
        feature = db.query(TripFeature).filter(TripFeature.trip_id == trip_id).one()
        assert any(e.type == "speeding" for e in events)
        assert incidents, "synthetic crash was not detected"
        assert all(e.lat is None and e.lon is None for e in events)
        assert all(i.lat is None and i.lon is None for i in incidents)
        assert "route" not in feature.features
        assert feature.features["distance_km"] > 0.5

    detail = client.get(f"/v1/me/trips/{trip_id}", headers={"X-API-Key": api_key})
    assert detail.status_code == 200
    assert detail.json()["route"] == []
