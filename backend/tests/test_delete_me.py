import logging
import os
import shutil
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import (
    Consent,
    Driver,
    Event,
    Incident,
    Trip,
    TripChunk,
    TripFeature,
    TripScore,
)

client = TestClient(app)
NOW = datetime(2025, 10, 9, 10, 0, tzinfo=UTC)
TRIP_MODELS = (Event, TripFeature, TripScore, TripChunk)


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path, monkeypatch) -> str:
    """Point the cached settings instance at a per-test dir, never the real data/raw."""
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path))
    return str(tmp_path)


def _register() -> tuple[str, str]:
    data = client.post("/v1/drivers/register", json={}).json()
    return data["driver_id"], data["api_key"]


def _seed_driver(driver_id: str) -> tuple[str, str]:
    """Add consent, a trip with chunk file, event, features, score and an incident."""
    trip_id = f"trip-{uuid.uuid4().hex}"
    trip_dir = os.path.join(get_settings().data_dir, trip_id)
    os.makedirs(trip_dir, exist_ok=True)
    chunk_path = os.path.join(trip_dir, "0.json.gz")
    with open(chunk_path, "wb") as f:
        f.write(b"x")
    with SessionLocal() as db:
        db.add(Consent(driver_id=driver_id, version="1.0"))
        db.add(Trip(id=trip_id, driver_id=driver_id, started_at=NOW, status="done"))
        db.flush()
        db.add(TripChunk(trip_id=trip_id, seq=0, file_path=chunk_path))
        db.add(Event(trip_id=trip_id, type="hard_brake", time=NOW, peak_g=0.5))
        db.add(TripFeature(trip_id=trip_id, features={"distance_km": 1.0}))
        db.add(TripScore(trip_id=trip_id, confidence=0.9, score=80, tier="good", model_version="t"))
        db.add(Incident(driver_id=driver_id, trip_id=trip_id, type="crash", time=NOW))
        db.commit()
    return trip_id, trip_dir


def _row_count(driver_id: str, trip_id: str) -> int:
    with SessionLocal() as db:
        total = sum(
            db.scalar(select(func.count()).select_from(t).where(t.driver_id == driver_id)) or 0
            for t in (Consent, Trip, Incident)
        )
        total += db.scalar(select(func.count()).select_from(Driver).where(Driver.id == driver_id))
        for m in TRIP_MODELS:
            total += db.scalar(select(func.count()).select_from(m).where(m.trip_id == trip_id))
    return total or 0


def test_delete_me_erases_only_own_data():
    a_id, a_key = _register()
    b_id, b_key = _register()
    a_trip, a_dir = _seed_driver(a_id)
    b_trip, b_dir = _seed_driver(b_id)
    assert _row_count(a_id, a_trip) == 8

    resp = client.delete("/v1/me", headers={"X-API-Key": a_key})

    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted", "deleted_files": 1}
    assert _row_count(a_id, a_trip) == 0
    assert not os.path.exists(a_dir)
    assert _row_count(b_id, b_trip) == 8
    assert os.path.isdir(b_dir)
    assert client.get("/v1/me/summary", headers={"X-API-Key": b_key}).status_code == 200

    assert client.delete("/v1/me", headers={"X-API-Key": b_key}).status_code == 200
    assert _row_count(b_id, b_trip) == 0


def test_deleted_key_no_longer_authenticates():
    _, key = _register()
    assert client.delete("/v1/me", headers={"X-API-Key": key}).status_code == 200
    assert client.delete("/v1/me", headers={"X-API-Key": key}).status_code == 401
    assert client.get("/v1/me/summary", headers={"X-API-Key": key}).status_code == 401


def test_delete_me_requires_api_key():
    assert client.delete("/v1/me").status_code == 422
    assert client.delete("/v1/me", headers={"X-API-Key": "bogus"}).status_code == 401


def test_file_removal_failure_still_succeeds_and_logs(monkeypatch, caplog):
    driver_id, key = _register()
    trip_id, trip_dir = _seed_driver(driver_id)

    def boom(*_args, **_kwargs):
        raise OSError("disk error")

    monkeypatch.setattr(shutil, "rmtree", boom)
    with caplog.at_level(logging.ERROR, logger="app.services.erasure"):
        resp = client.delete("/v1/me", headers={"X-API-Key": key})

    assert resp.status_code == 200
    assert resp.json()["deleted_files"] == 0
    assert _row_count(driver_id, trip_id) == 0
    assert "Raw file removal failed after erasure" in caplog.text
    assert os.path.isdir(trip_dir)


def test_symlinked_trip_dir_is_not_followed(tmp_data_dir, tmp_path_factory, caplog):
    driver_id, key = _register()
    outside = tmp_path_factory.mktemp("outside")
    (outside / "keep.txt").write_text("keep")
    trip_id = f"trip-{uuid.uuid4().hex}"
    os.symlink(outside, os.path.join(tmp_data_dir, trip_id))
    with SessionLocal() as db:
        db.add(Trip(id=trip_id, driver_id=driver_id, started_at=NOW, status="done"))
        db.commit()

    with caplog.at_level(logging.WARNING, logger="app.services.erasure"):
        resp = client.delete("/v1/me", headers={"X-API-Key": key})

    assert resp.status_code == 200
    assert (outside / "keep.txt").exists()
    assert "Skipped unsafe raw dir" in caplog.text
