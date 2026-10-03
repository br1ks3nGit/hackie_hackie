from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_insurer
from app.database import get_db
from app.models import Event, Incident, Trip, TripFeature, TripScore
from app.pipeline import process_trip
from app.schemas import ReprocessResponse

router = APIRouter()


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
