import gzip
import json
import os
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.auth import get_current_driver, generate_api_key, hash_api_key
from app.config import get_settings
from app.database import get_db
from app.models import Driver, Consent, Trip, TripChunk
from app.schemas import (
    DriverRegisterRequest,
    DriverRegisterResponse,
    ConsentRequest,
    ConsentResponse,
    TripStartResponse,
    TripChunkRequest,
    TripChunkResponse,
    TripEndResponse,
    TripStatusResponse,
)
from app.pipeline import process_trip

router = APIRouter()
settings = get_settings()


@router.post("/drivers/register", response_model=DriverRegisterResponse)
def register_driver(
    request: DriverRegisterRequest = DriverRegisterRequest(),
    db: Session = Depends(get_db),
):
    driver_id = f"drv-{uuid.uuid4().hex[:12]}"
    api_key = generate_api_key()
    driver = Driver(
        id=driver_id,
        api_key_hash=hash_api_key(api_key),
        emergency_contact_name=request.emergency_contact_name,
        emergency_contact_phone=request.emergency_contact_phone,
    )
    db.add(driver)
    db.commit()
    return DriverRegisterResponse(driver_id=driver_id, api_key=api_key)


@router.post("/consent", response_model=ConsentResponse)
def give_consent(
    request: ConsentRequest,
    driver: Driver = Depends(get_current_driver),
    db: Session = Depends(get_db),
):
    consent = Consent(driver_id=driver.id, version=request.version)
    db.add(consent)
    db.commit()
    return ConsentResponse(status="consent_recorded", granted_at=consent.granted_at)


@router.post("/trips/start", response_model=TripStartResponse)
def start_trip(
    driver: Driver = Depends(get_current_driver),
    db: Session = Depends(get_db),
):
    # Check consent
    consent = db.query(Consent).filter(Consent.driver_id == driver.id).first()
    if not consent:
        raise HTTPException(status_code=403, detail="Consent required before starting trips")

    trip_id = f"trp-{uuid.uuid4().hex[:12]}"
    trip = Trip(id=trip_id, driver_id=driver.id, status="uploading", started_at=datetime.utcnow())
    db.add(trip)
    db.commit()
    return TripStartResponse(trip_id=trip_id)


@router.post("/trips/{trip_id}/chunks", response_model=TripChunkResponse)
def upload_chunk(
    trip_id: str,
    chunk: TripChunkRequest,
    driver: Driver = Depends(get_current_driver),
    db: Session = Depends(get_db),
):
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.driver_id == driver.id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Chunks are only accepted while the trip is open; the mobile client sends
    # /end only after the final chunk has been acknowledged
    if trip.status != "uploading":
        raise HTTPException(status_code=400, detail=f"Cannot upload chunks to trip in status {trip.status}")

    # Idempotency: if chunk already exists, return success
    existing = db.query(TripChunk).filter(TripChunk.trip_id == trip_id, TripChunk.seq == chunk.seq).first()
    if existing:
        return TripChunkResponse(status="already_received", received_at=existing.received_at)

    # Save chunk to disk
    chunk_dir = os.path.join(settings.data_dir, trip_id)
    os.makedirs(chunk_dir, exist_ok=True)
    chunk_path = os.path.join(chunk_dir, f"{chunk.seq}.json.gz")

    chunk_data = {
        "seq": chunk.seq,
        "imu": [s.dict() for s in chunk.imu],
        "gps": [s.dict() for s in chunk.gps],
        "car_connected": chunk.car_connected,
    }

    with gzip.open(chunk_path, "wt", encoding="utf-8") as f:
        json.dump(chunk_data, f)

    # Record in DB
    trip_chunk = TripChunk(trip_id=trip_id, seq=chunk.seq, file_path=chunk_path)
    db.add(trip_chunk)
    db.commit()

    return TripChunkResponse(status="received", received_at=trip_chunk.received_at)


def _read_trip_end_time(trip_id: str) -> Optional[datetime]:
    """Read the last GPS sample timestamp from the highest-seq chunk file."""
    trip_dir = os.path.join(settings.data_dir, trip_id)
    if not os.path.exists(trip_dir):
        return None

    files = [f for f in os.listdir(trip_dir) if f.endswith(".json.gz")]
    files.sort(key=lambda f: int(f.replace(".json.gz", "")), reverse=True)

    for filename in files:
        try:
            with gzip.open(os.path.join(trip_dir, filename), "rt", encoding="utf-8") as f:
                chunk = json.load(f)
        except (OSError, ValueError):
            continue
        gps = chunk.get("gps", [])
        if gps:
            return datetime.utcfromtimestamp(gps[-1]["t"] / 1000.0)
    return None


@router.post("/trips/{trip_id}/end", response_model=TripEndResponse)
def end_trip(
    trip_id: str,
    background_tasks: BackgroundTasks,
    driver: Driver = Depends(get_current_driver),
    db: Session = Depends(get_db),
):
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.driver_id == driver.id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    if trip.status != "uploading":
        raise HTTPException(status_code=400, detail=f"Cannot end trip in status {trip.status}")

    # ended_at reflects the last recorded GPS sample, not the processing time
    trip.ended_at = _read_trip_end_time(trip_id) or datetime.utcnow()
    trip.status = "processing"
    db.commit()

    background_tasks.add_task(process_trip, trip_id)

    return TripEndResponse(status="processing")


@router.get("/trips/{trip_id}/status", response_model=TripStatusResponse)
def get_trip_status(
    trip_id: str,
    driver: Driver = Depends(get_current_driver),
    db: Session = Depends(get_db),
):
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.driver_id == driver.id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    return TripStatusResponse(
        trip_id=trip.id,
        status=trip.status,
        failure_reason=trip.failure_reason,
    )
