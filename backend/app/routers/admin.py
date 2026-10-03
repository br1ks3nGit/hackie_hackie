import os
import shutil

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_driver, get_current_insurer
from app.config import get_settings
from app.database import get_db
from app.models import Consent, Driver, Event, Incident, Trip, TripChunk, TripFeature, TripScore
from app.pipeline import process_trip
from app.schemas import DeleteDriverResponse, ReprocessResponse

router = APIRouter()
settings = get_settings()


@router.post("/trips/{trip_id}/reprocess", response_model=ReprocessResponse)
def reprocess_trip(
    trip_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(get_current_insurer),
    db: Session = Depends(get_db),
):
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Delete old results (incidents would duplicate crash detections on reprocess)
    db.query(Event).filter(Event.trip_id == trip_id).delete()
    db.query(TripFeature).filter(TripFeature.trip_id == trip_id).delete()
    db.query(TripScore).filter(TripScore.trip_id == trip_id).delete()
    db.query(Incident).filter(Incident.trip_id == trip_id).delete()

    trip.status = "processing"
    trip.failure_reason = None
    db.commit()

    background_tasks.add_task(process_trip, trip_id)

    return ReprocessResponse(trip_id=trip_id, status="processing")


@router.delete("/me", response_model=DeleteDriverResponse)
def delete_my_data(
    driver: Driver = Depends(get_current_driver),
    db: Session = Depends(get_db),
):
    # Delete raw files
    deleted_files = 0
    driver_dir = os.path.join(settings.data_dir)
    if os.path.exists(driver_dir):
        for trip_dir in os.listdir(driver_dir):
            trip_path = os.path.join(driver_dir, trip_dir)
            trip = db.query(Trip).filter(Trip.id == trip_dir, Trip.driver_id == driver.id).first()
            if trip and os.path.isdir(trip_path):
                shutil.rmtree(trip_path)
                deleted_files += 1

    # Delete DB records
    db.query(Event).filter(
        Event.trip_id.in_(db.query(Trip.id).filter(Trip.driver_id == driver.id))
    ).delete(synchronize_session=False)
    db.query(TripFeature).filter(
        TripFeature.trip_id.in_(db.query(Trip.id).filter(Trip.driver_id == driver.id))
    ).delete(synchronize_session=False)
    db.query(TripScore).filter(
        TripScore.trip_id.in_(db.query(Trip.id).filter(Trip.driver_id == driver.id))
    ).delete(synchronize_session=False)
    db.query(TripChunk).filter(
        TripChunk.trip_id.in_(db.query(Trip.id).filter(Trip.driver_id == driver.id))
    ).delete(synchronize_session=False)
    db.query(Incident).filter(Incident.driver_id == driver.id).delete(synchronize_session=False)
    db.query(Consent).filter(Consent.driver_id == driver.id).delete(synchronize_session=False)
    db.query(Trip).filter(Trip.driver_id == driver.id).delete(synchronize_session=False)
    db.query(Driver).filter(Driver.id == driver.id).delete(synchronize_session=False)

    db.commit()

    return DeleteDriverResponse(status="deleted", deleted_files=deleted_files)
