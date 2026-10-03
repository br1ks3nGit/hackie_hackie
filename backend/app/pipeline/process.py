import logging
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.classify import classify_trip
from app.database import SessionLocal
from app.model import confidence_to_score, predict, score_to_tier
from app.models import Event, Incident, Trip, TripFeature, TripScore
from app.pipeline.errors import PipelineError, QualityCheckError
from app.pipeline.events import _detect_crashes, _detect_events
from app.pipeline.feature_calc import _calculate_features, _validate_features
from app.pipeline.loading import _load_all_chunks, _quality_check
from app.pipeline.signal import (
    _apply_lowpass_filter,
    _remove_gravity,
    _resample_imu,
    _rotate_to_car_frame,
)

logger = logging.getLogger(__name__)


def _classify(
    trip: Trip,
    imu_df: pd.DataFrame,
    gps_df: pd.DataFrame,
    bluetooth_connected_ratio: float | None,
) -> dict[str, Any]:
    """Return the trip classification, applying auto-classification to the trip row."""
    # User labels are never overwritten by auto-classification
    if trip.label_source == "user":
        return {
            "trip_type": trip.trip_type,
            "label_source": trip.label_source,
            "driver_likelihood": trip.driver_likelihood,
            "transit_line": trip.transit_line,
        }

    classification = classify_trip(
        gps_df=gps_df,
        imu_df=imu_df,
        bluetooth_connected_ratio=bluetooth_connected_ratio,
    )
    trip.trip_type = classification["trip_type"]
    trip.label_source = classification["label_source"]
    trip.driver_likelihood = classification["driver_likelihood"]
    trip.transit_line = classification["transit_line"]
    return classification


def _add_incidents(db: Session, trip: Trip, trip_id: str, crashes: list[dict[str, Any]]) -> None:
    for crash_data in crashes:
        incident = Incident(
            driver_id=trip.driver_id,
            trip_id=trip_id,
            type="crash",
            time=crash_data["time"],
            peak_g=crash_data["peak_g"],
            sensor_snapshot=crash_data["sensor_snapshot"],
        )
        db.add(incident)
        logger.warning(f"Crash detected in trip {trip_id}: {crash_data['peak_g']:.2f}g")


def _add_events(db: Session, trip_id: str, events: list[dict[str, Any]]) -> None:
    for event_data in events:
        event = Event(
            trip_id=trip_id,
            type=event_data["type"],
            time=event_data["time"],
            peak_g=event_data["peak_g"],
        )
        db.add(event)


def _add_score(db: Session, trip_id: str, features: dict[str, Any]) -> tuple[int, str]:
    """Score the features with the model and add the TripScore; return (score, tier)."""
    prediction = predict(features)
    confidence = prediction["confidence"]
    score = confidence_to_score(confidence)
    tier = score_to_tier(score)

    trip_score = TripScore(
        trip_id=trip_id,
        confidence=confidence,
        score=score,
        tier=tier,
        model_version=prediction["model_version"],
    )
    db.add(trip_score)
    return score, tier


def _analyse_and_save(
    db: Session, trip: Trip, trip_id: str, imu_df: pd.DataFrame, gps_df: pd.DataFrame
) -> tuple[int, str]:
    """Signal processing, event/crash detection, features and score; adds rows to the session."""
    # Process signals: resample -> gravity removal -> car-frame -> low-pass
    imu_df = _resample_imu(imu_df)
    imu_df = _remove_gravity(imu_df)
    imu_df = _rotate_to_car_frame(imu_df, gps_df)
    imu_df = _apply_lowpass_filter(imu_df)

    events = _detect_events(imu_df, gps_df)

    crashes = _detect_crashes(imu_df, gps_df)
    _add_incidents(db, trip, trip_id, crashes)

    features = _validate_features(_calculate_features(imu_df, gps_df, events))

    _add_events(db, trip_id, events)
    db.add(TripFeature(trip_id=trip_id, features=features))

    return _add_score(db, trip_id, features)


def _run_trip(db: Session, trip_id: str) -> None:
    logger.info(f"Processing trip {trip_id}")

    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise PipelineError(f"Trip {trip_id} not found")

    trip.status = "processing"
    db.commit()

    # Load data (also derives the bluetooth ratio from chunk metadata)
    imu_df, gps_df, bluetooth_connected_ratio = _load_all_chunks(trip_id)
    trip.bluetooth_connected_ratio = bluetooth_connected_ratio

    classification = _classify(trip, imu_df, gps_df, bluetooth_connected_ratio)

    # Transit and user-labelled passenger trips are saved but not scored
    if classification["trip_type"] in ("transit", "passenger"):
        trip.status = "done"
        db.commit()
        logger.info(f"Trip {trip_id} classified as {classification['trip_type']}, not scored")
        return

    _quality_check(imu_df, gps_df)

    score, tier = _analyse_and_save(db, trip, trip_id, imu_df, gps_df)

    # Mark trip as done (ended_at was set by the /end endpoint)
    trip.status = "done"
    db.commit()

    logger.info(
        f"Trip {trip_id} processed successfully: score={score}, tier={tier}, "
        f"type={classification['trip_type']}"
    )


def _mark_failed(db: Session, trip_id: str, reason: str) -> None:
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if trip:
        trip.status = "failed"
        trip.failure_reason = reason
        db.commit()


def process_trip(trip_id: str) -> None:
    """Process a trip end-to-end. Called as a background task."""
    db = SessionLocal()
    try:
        _run_trip(db, trip_id)
    except QualityCheckError as e:
        logger.warning(f"Trip {trip_id} failed quality check: {e}")
        _mark_failed(db, trip_id, str(e))
    except Exception as e:
        logger.error(f"Trip {trip_id} processing failed: {e}", exc_info=True)
        # A failed flush leaves the session unusable until rolled back
        db.rollback()
        _mark_failed(db, trip_id, str(e))
        raise
    finally:
        db.close()
