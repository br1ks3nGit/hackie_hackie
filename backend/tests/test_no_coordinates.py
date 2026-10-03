"""Privacy P1: coordinates never reach disk or the processed rows."""

import glob
import gzip
import json
import os

from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import Event, Incident, TripChunk, TripFeature
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
        "speed": speed,
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
        {
            "seq": 0,
            "imu": [_imu(0)],
            "speed_samples": [_gps(0, 10.0), _gps(1, 12.0)],
            "car_connected": True,
        },
    )

    path = os.path.join(get_settings().data_dir, trip_id, "0.json.gz")
    with gzip.open(path, "rt", encoding="utf-8") as f:
        raw = f.read()
    stored = json.loads(raw)

    assert len(stored["speed_samples"]) == 2
    for sample in stored["speed_samples"]:
        assert set(sample) == {"t", "speed", "accuracy"}
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
        {"seq": 0, "imu": [_imu(i, spike_at=3000) for i in range(n_imu)], "speed_samples": gps},
    )

    process_trip(trip_id)

    with SessionLocal() as db:
        events = db.query(Event).filter(Event.trip_id == trip_id).all()
        incidents = db.query(Incident).filter(Incident.trip_id == trip_id).all()
        feature = db.query(TripFeature).filter(TripFeature.trip_id == trip_id).one()
        assert any(e.type == "speeding" for e in events)
        assert incidents, "synthetic crash was not detected"
        assert not any(hasattr(r, c) for r in (*events, *incidents) for c in ("lat", "lon"))
        assert "route" not in feature.features
        assert feature.features["distance_km"] > 0.5

    detail = client.get(f"/v1/me/trips/{trip_id}", headers={"X-API-Key": api_key})
    assert detail.status_code == 200
    body = detail.json()
    assert "route" not in body
    assert _no_location_keys(body)
    assert all(_no_location_keys(e) for e in body["events"])
    assert _no_location_keys(client.get("/v1/me/incidents", headers={"X-API-Key": api_key}).json())


def _no_location_keys(obj: object) -> bool:
    """True when no dict anywhere in obj has a location or route key."""
    banned = {"lat", "lon", "lng", "latitude", "longitude", "route"}
    if isinstance(obj, dict):
        return banned.isdisjoint(obj) and all(_no_location_keys(v) for v in obj.values())
    if isinstance(obj, list):
        return all(_no_location_keys(v) for v in obj)
    return True


def test_chunk_with_coordinates_is_rejected_and_not_written() -> None:
    api_key, trip_id = _register_and_start()
    for key in ("lat", "lon", "lng"):
        gps = {**_gps(0, 10.0), key: 22.3}
        response = client.post(
            f"/v1/trips/{trip_id}/chunks",
            headers={"X-API-Key": api_key},
            json={"seq": 0, "imu": [_imu(0)], "speed_samples": [gps]},
        )
        assert response.status_code == 422, key
    trip_dir = os.path.join(get_settings().data_dir, trip_id)
    assert not os.path.exists(trip_dir) or not os.listdir(trip_dir)
    with SessionLocal() as db:
        assert db.query(TripChunk).filter(TripChunk.trip_id == trip_id).count() == 0


def test_incident_with_coordinates_is_rejected() -> None:
    api_key, _trip_id = _register_and_start()
    body = {"type": "crash", "time": "2026-01-02T03:04:05Z", "peak_g": 5.0}
    ok = client.post("/v1/me/incidents", headers={"X-API-Key": api_key}, json=body)
    assert ok.status_code == 200
    assert _no_location_keys(ok.json())
    for key in ("lat", "lon", "lng"):
        response = client.post(
            "/v1/me/incidents", headers={"X-API-Key": api_key}, json={**body, key: 22.3}
        )
        assert response.status_code == 422, key


def test_chunk_with_legacy_gps_key_or_heading_is_rejected() -> None:
    api_key, trip_id = _register_and_start()
    url = f"/v1/trips/{trip_id}/chunks"
    headers = {"X-API-Key": api_key}
    body = {"seq": 0, "imu": [_imu(0)], "gps": [_gps(0, 1.0)]}
    legacy = client.post(url, headers=headers, json=body)
    assert legacy.status_code == 422
    with_heading = {**_gps(0, 1.0), "heading": 90.0}
    response = client.post(
        url, headers=headers, json={"seq": 0, "imu": [_imu(0)], "speed_samples": [with_heading]}
    )
    assert response.status_code == 422
