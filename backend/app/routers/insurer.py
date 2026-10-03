from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_insurer
from app.database import get_db
from app.schemas import (
    InsurerDriverDetailResponse,
    InsurerDriverItem,
    InsurerOverviewResponse,
)
from app.services.insurer import get_driver_detail, get_overview, list_drivers

router = APIRouter()


@router.get("/insurer/overview", response_model=InsurerOverviewResponse)
def get_insurer_overview(
    _: None = Depends(get_current_insurer),
    db: Session = Depends(get_db),
):
    return get_overview(db)


@router.get("/insurer/drivers", response_model=list[InsurerDriverItem])
def get_insurer_drivers(
    _: None = Depends(get_current_insurer),
    db: Session = Depends(get_db),
    tier: str | None = Query(None),
    sort: str | None = Query("score_desc"),
):
    return list_drivers(db, tier, sort)


@router.get("/insurer/drivers/{driver_id}", response_model=InsurerDriverDetailResponse)
def get_insurer_driver_detail(
    driver_id: str,
    _: None = Depends(get_current_insurer),
    db: Session = Depends(get_db),
):
    detail = get_driver_detail(db, driver_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Driver not found")
    return detail.response
