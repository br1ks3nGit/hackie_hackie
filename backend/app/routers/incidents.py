from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_driver
from app.database import get_db
from app.models import Driver, Incident
from app.schemas import IncidentConfirm, IncidentCreate, IncidentResponse

router = APIRouter()


@router.post("/me/incidents", response_model=IncidentResponse)
def create_incident(
    request: IncidentCreate,
    driver: Driver = Depends(get_current_driver),
    db: Session = Depends(get_db),
):
    incident = Incident(
        driver_id=driver.id,
        trip_id=request.trip_id,
        type=request.type,
        time=request.time,
        lat=request.lat,
        lon=request.lon,
        peak_g=request.peak_g,
        sensor_snapshot=(
            request.sensor_snapshot.model_dump(exclude_unset=True)
            if request.sensor_snapshot
            else None
        ),
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)

    return IncidentResponse(
        id=incident.id,
        type=incident.type,
        time=incident.time,
        lat=incident.lat,
        lon=incident.lon,
        peak_g=incident.peak_g,
        confirmed=incident.confirmed,
        created_at=incident.created_at,
    )


@router.post("/me/incidents/{incident_id}/confirm", response_model=IncidentResponse)
def confirm_incident(
    incident_id: int,
    request: IncidentConfirm,
    driver: Driver = Depends(get_current_driver),
    db: Session = Depends(get_db),
):
    incident = (
        db.query(Incident)
        .filter(
            Incident.id == incident_id,
            Incident.driver_id == driver.id,
        )
        .first()
    )
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident.confirmed = request.confirmed
    db.commit()
    db.refresh(incident)

    return IncidentResponse(
        id=incident.id,
        type=incident.type,
        time=incident.time,
        lat=incident.lat,
        lon=incident.lon,
        peak_g=incident.peak_g,
        confirmed=incident.confirmed,
        created_at=incident.created_at,
    )


@router.get("/me/incidents", response_model=list[IncidentResponse])
def list_incidents(
    driver: Driver = Depends(get_current_driver),
    db: Session = Depends(get_db),
):
    incidents = (
        db.query(Incident)
        .filter(Incident.driver_id == driver.id)
        .order_by(Incident.time.desc())
        .limit(50)
        .all()
    )
    return [
        IncidentResponse(
            id=i.id,
            type=i.type,
            time=i.time,
            lat=i.lat,
            lon=i.lon,
            peak_g=i.peak_g,
            confirmed=i.confirmed,
            created_at=i.created_at,
        )
        for i in incidents
    ]
