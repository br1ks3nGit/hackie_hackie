import logging
import shutil
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Consent, Driver, Event, Incident, Trip, TripChunk, TripFeature, TripScore

logger = logging.getLogger(__name__)


def _remove_one_trip_dir(root: Path, trip_id: str) -> int:
    """Delete DATA_DIR/<trip_id>/ if it is a real directory directly under root."""
    raw = root / trip_id
    if not raw.exists() and not raw.is_symlink():
        return 0
    if raw.is_symlink() or raw.resolve().parent != root.resolve() or not raw.is_dir():
        logger.warning("Skipped unsafe raw dir during erasure (trip %s)", trip_id)
        return 0
    files = sum(1 for p in raw.rglob("*") if p.is_file())
    shutil.rmtree(raw)
    return files


def _remove_trip_dirs(trip_ids: list[str]) -> int:
    """Best-effort removal of raw files; returns the number of files actually removed."""
    root = Path(get_settings().data_dir)
    if root.is_symlink():
        logger.warning("DATA_DIR is a symlink; raw file removal skipped")
        return 0
    removed = 0
    for trip_id in trip_ids:
        try:
            removed += _remove_one_trip_dir(root, trip_id)
        except OSError:
            logger.exception("Raw file removal failed after erasure (trip %s)", trip_id)
    return removed


def delete_driver_data(db: Session, driver_id: str) -> int:
    """Erase a driver's rows in one transaction, then their raw files; returns files removed.

    Known gap (accepted for the POC): erasure can race an in-flight process_trip or chunk
    upload, which may recreate rows or files for the driver's trips after this runs.
    """
    try:
        trip_ids = list(db.scalars(select(Trip.id).where(Trip.driver_id == driver_id)))
        if trip_ids:
            for model in (Event, TripFeature, TripScore, TripChunk):
                db.execute(delete(model).where(model.trip_id.in_(trip_ids)))
        db.execute(delete(Incident).where(Incident.driver_id == driver_id))
        db.execute(delete(Consent).where(Consent.driver_id == driver_id))
        db.execute(delete(Trip).where(Trip.driver_id == driver_id))
        db.execute(delete(Driver).where(Driver.id == driver_id))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Driver erasure failed and rolled back (driver %s)", driver_id)
        raise
    files = _remove_trip_dirs(trip_ids)
    logger.info("Driver %s erased: %s trips, %s files removed", driver_id, len(trip_ids), files)
    return files
