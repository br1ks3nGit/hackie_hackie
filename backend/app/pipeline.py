import gzip
import json
import logging
import os
from typing import Any

import numpy as np
import pandas as pd
from pydantic import ValidationError
from scipy import signal

from app.classify import classify_trip
from app.config import get_settings
from app.database import SessionLocal
from app.features import TripFeatures
from app.model import confidence_to_score, predict, score_to_tier
from app.models import Event, Incident, Trip, TripFeature, TripScore

settings = get_settings()
logger = logging.getLogger(__name__)


class PipelineError(Exception):
    pass


class QualityCheckError(PipelineError):
    pass


def _validate_features(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate computed features against TripFeatures; return the storable dict."""
    try:
        return TripFeatures.model_validate(raw).model_dump()
    except ValidationError as e:
        fields = ", ".join(".".join(str(p) for p in err["loc"]) for err in e.errors())
        raise PipelineError(f"feature contract violated: {fields}") from e


def _load_chunk(trip_id: str, seq: int) -> dict[str, Any]:
    path = os.path.join(settings.data_dir, trip_id, f"{seq}.json.gz")
    if not os.path.exists(path):
        raise PipelineError(f"Chunk file not found: {path}")
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _load_all_chunks(trip_id: str) -> tuple[pd.DataFrame, pd.DataFrame, float | None]:
    imu_rows = []
    gps_rows = []
    bt_connected = 0
    bt_total = 0

    trip_dir = os.path.join(settings.data_dir, trip_id)
    if not os.path.exists(trip_dir):
        raise PipelineError(f"No data directory for trip {trip_id}")

    files = sorted([f for f in os.listdir(trip_dir) if f.endswith(".json.gz")])
    if not files:
        raise PipelineError(f"No chunk files found for trip {trip_id}")

    for filename in files:
        seq = int(filename.replace(".json.gz", ""))
        chunk = _load_chunk(trip_id, seq)
        imu_rows.extend(chunk.get("imu", []))
        gps_rows.extend(chunk.get("gps", []))
        if chunk.get("car_connected") is not None:
            bt_total += 1
            if chunk.get("car_connected"):
                bt_connected += 1

    if not imu_rows:
        raise PipelineError("No IMU data found")
    if not gps_rows:
        raise PipelineError("No GPS data found")

    imu_df = pd.DataFrame(imu_rows)
    gps_df = pd.DataFrame(gps_rows)

    # Convert epoch ms to datetime
    imu_df["time"] = pd.to_datetime(imu_df["t"], unit="ms", utc=True)
    gps_df["time"] = pd.to_datetime(gps_df["t"], unit="ms", utc=True)

    # Remove duplicates and sort
    imu_df = imu_df.drop_duplicates(subset=["t"]).sort_values("t").reset_index(drop=True)
    gps_df = gps_df.drop_duplicates(subset=["t"]).sort_values("t").reset_index(drop=True)

    # Fraction of chunks reporting car Bluetooth connection
    bluetooth_connected_ratio = (bt_connected / bt_total) if bt_total > 0 else None

    return imu_df, gps_df, bluetooth_connected_ratio


def _quality_check(imu_df: pd.DataFrame, gps_df: pd.DataFrame) -> None:
    if len(imu_df) < 100:
        raise QualityCheckError("Too little IMU data (need at least 100 samples)")

    if len(gps_df) < 10:
        raise QualityCheckError("Too little GPS data (need at least 10 points)")

    # Check GPS gaps
    gps_gaps = gps_df["t"].diff().dropna() / 1000.0  # seconds
    max_gap = gps_gaps.max()
    if max_gap > settings.trip_max_gps_gap_s:
        raise QualityCheckError(
            f"GPS gap too large: {max_gap:.1f}s > {settings.trip_max_gps_gap_s}s"
        )

    # Check duration
    duration_s = (imu_df["t"].max() - imu_df["t"].min()) / 1000.0
    if duration_s < settings.trip_min_duration_s:
        raise QualityCheckError(
            f"Trip too short: {duration_s:.1f}s < {settings.trip_min_duration_s}s"
        )

    # Check distance (haversine)
    distance_km = _calculate_distance_km(gps_df)
    if distance_km < settings.trip_min_distance_km:
        raise QualityCheckError(
            f"Trip too short: {distance_km:.2f}km < {settings.trip_min_distance_km}km"
        )


def _calculate_distance_km(gps_df: pd.DataFrame) -> float:
    lat1 = np.radians(gps_df["lat"].iloc[:-1].values)
    lon1 = np.radians(gps_df["lon"].iloc[:-1].values)
    lat2 = np.radians(gps_df["lat"].iloc[1:].values)
    lon2 = np.radians(gps_df["lon"].iloc[1:].values)

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    distance_m = 6371000 * c
    return float(np.sum(distance_m) / 1000.0)


def _resample_imu(imu_df: pd.DataFrame, target_hz: float = 50.0) -> pd.DataFrame:
    """Resample IMU data to target frequency using linear interpolation."""
    if len(imu_df) < 2:
        return imu_df

    start_t = imu_df["t"].iloc[0]
    end_t = imu_df["t"].iloc[-1]
    interval_ms = 1000.0 / target_hz

    new_t = np.arange(start_t, end_t, interval_ms)
    new_df = pd.DataFrame({"t": new_t})

    for col in ["ax", "ay", "az", "gx", "gy", "gz"]:
        new_df[col] = np.interp(new_t, imu_df["t"], imu_df[col])

    new_df["time"] = pd.to_datetime(new_df["t"], unit="ms", utc=True)
    return new_df


def _remove_gravity(imu_df: pd.DataFrame, window_s: float = 10.0, fs: float = 50.0) -> pd.DataFrame:
    """
    Remove gravity/DC offset by subtracting a rolling median from each raw axis.
    Orientation-independent: works however the phone is mounted.
    """
    imu_df = imu_df.copy()
    window = int(fs * window_s)
    for col in ["ax", "ay", "az", "gx", "gy", "gz"]:
        if col in imu_df.columns:
            rolling_median = imu_df[col].rolling(window=window, center=True, min_periods=1).median()
            imu_df[col] = imu_df[col] - rolling_median
    return imu_df


def _rotate_to_car_frame(imu_df: pd.DataFrame, gps_df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive car-frame acceleration channels (all in g, matching the event thresholds):
    - accel_forward: dv/dt from GPS speed over ~2s windows, interpolated onto the IMU timeline
    - accel_lateral: yaw rate (gravity-free gz, rad/s) x GPS speed (m/s)
    - accel_vertical: gravity-free az
    """
    imu_df = imu_df.copy()

    gps = gps_df.copy()
    gps["speed"] = gps["speed"].fillna(0)
    gps = gps.sort_values("t")
    imu_t = imu_df["t"].values.astype(float)

    if len(gps) >= 2:
        gps_t = gps["t"].values.astype(float)
        speeds = gps["speed"].values.astype(float)

        # dv/dt over a ~2s window centered on each GPS point (m/s^2)
        window_s = 2.0
        half_ms = window_s / 2.0 * 1000.0
        dv = np.interp(gps_t + half_ms, gps_t, speeds) - np.interp(gps_t - half_ms, gps_t, speeds)
        accel_forward_gps = dv / window_s

        accel_forward_ms2 = np.interp(imu_t, gps_t, accel_forward_gps)
        speed_on_imu = np.interp(imu_t, gps_t, speeds)
    else:
        accel_forward_ms2 = np.zeros(len(imu_df))
        speed_on_imu = np.zeros(len(imu_df))

    # Convert m/s^2 to g so the g-unit thresholds apply
    imu_df["accel_forward"] = accel_forward_ms2 / 9.81
    imu_df["accel_lateral"] = imu_df["gz"].values * speed_on_imu / 9.81
    imu_df["accel_vertical"] = imu_df["az"].values
    return imu_df


def _apply_lowpass_filter(
    imu_df: pd.DataFrame, cutoff_hz: float = 5.0, fs: float = 50.0
) -> pd.DataFrame:
    """Apply Butterworth low-pass filter to remove road vibration."""
    nyquist = fs / 2.0
    normal_cutoff = cutoff_hz / nyquist
    b, a = signal.butter(4, normal_cutoff, btype="low", analog=False)

    imu_df = imu_df.copy()
    for col in ["accel_forward", "accel_lateral", "accel_vertical"]:
        imu_df[col] = signal.filtfilt(b, a, imu_df[col])

    return imu_df


# 50 km/h urban HK default in m/s.
# TODO: use the OSM speed limit for the road + 10 km/h instead of a fixed value.
SPEEDING_THRESHOLD_MS = 13.9


def _detect_events(imu_df: pd.DataFrame, gps_df: pd.DataFrame) -> list[dict[str, Any]]:
    events = []

    # Thresholds in g
    harsh_brake_threshold = -0.4
    harsh_accel_threshold = 0.3
    sharp_corner_threshold = 0.35

    # Merge GPS speed into IMU timeline for event detection
    # Use nearest GPS point for each IMU sample
    imu_times = imu_df["t"].values
    gps_times = gps_df["t"].values
    gps_speeds = gps_df["speed"].fillna(0).values

    # Find nearest GPS point for each IMU sample: searchsorted gives the next
    # point, so step back when the previous point is closer (>= 10 points after QC)
    gps_idx = np.clip(np.searchsorted(gps_times, imu_times), 1, len(gps_times) - 1)
    prev_closer = (imu_times - gps_times[gps_idx - 1]) < (gps_times[gps_idx] - imu_times)
    nearest_speeds = gps_speeds[gps_idx - prev_closer.astype(int)]

    # Detect harsh braking
    brake_mask = imu_df["accel_forward"] < harsh_brake_threshold
    brake_events = _find_peaks(imu_df, brake_mask, "harsh_brake", gps_df)
    events.extend(brake_events)

    # Detect harsh acceleration
    accel_mask = imu_df["accel_forward"] > harsh_accel_threshold
    accel_events = _find_peaks(imu_df, accel_mask, "harsh_accel", gps_df)
    events.extend(accel_events)

    # Detect sharp cornering
    corner_mask = np.abs(imu_df["accel_lateral"]) > sharp_corner_threshold
    corner_events = _find_peaks(imu_df, corner_mask, "sharp_corner", gps_df)
    events.extend(corner_events)

    # Detect speeding: merge consecutive speeding samples into runs and emit
    # ONE event per run longer than 10s (time/lat/lon of the run start)
    speeding_mask = nearest_speeds > SPEEDING_THRESHOLD_MS
    events.extend(_find_speeding_runs(imu_df, speeding_mask, gps_df))

    return events


def _find_speeding_runs(
    imu_df: pd.DataFrame,
    mask,
    gps_df: pd.DataFrame,
    min_duration_s: float = 10.0,
) -> list[dict[str, Any]]:
    """Merge consecutive speeding samples into runs; one event per run > min_duration_s."""
    events = []
    times = imu_df["t"].values
    mask = np.asarray(mask)
    n = len(mask)

    i = 0
    while i < n:
        if not mask[i]:
            i += 1
            continue
        start = i
        while i + 1 < n and mask[i + 1]:
            i += 1
        end = i

        duration_s = (times[end] - times[start]) / 1000.0
        if duration_s > min_duration_s:
            row = imu_df.iloc[start]
            nearest_gps = _find_nearest_gps(row["t"], gps_df)
            events.append(
                {
                    "type": "speeding",
                    "time": row["time"],
                    "peak_g": None,
                    "lat": nearest_gps["lat"],
                    "lon": nearest_gps["lon"],
                }
            )
        i += 1

    return events


def _find_peaks(
    imu_df: pd.DataFrame, mask: pd.Series, event_type: str, gps_df: pd.DataFrame
) -> list[dict[str, Any]]:
    """Find peak events in a boolean mask."""
    events = []
    in_event = False
    peak_idx = None
    peak_val = 0

    values = (
        imu_df["accel_forward"].values
        if "brake" in event_type or "accel" in event_type
        else imu_df["accel_lateral"].values
    )

    for i, (active, val) in enumerate(zip(mask, values, strict=False)):
        if active and not in_event:
            in_event = True
            peak_idx = i
            peak_val = val
        elif active and in_event:
            if abs(val) > abs(peak_val):
                peak_val = val
                peak_idx = i
        elif not active and in_event:
            in_event = False
            row = imu_df.iloc[peak_idx]
            nearest_gps = _find_nearest_gps(row["t"], gps_df)
            events.append(
                {
                    "type": event_type,
                    "time": row["time"],
                    "peak_g": float(abs(peak_val)),
                    "lat": nearest_gps["lat"],
                    "lon": nearest_gps["lon"],
                }
            )

    # Flush an event still open at the end of the array
    if in_event and peak_idx is not None:
        row = imu_df.iloc[peak_idx]
        nearest_gps = _find_nearest_gps(row["t"], gps_df)
        events.append(
            {
                "type": event_type,
                "time": row["time"],
                "peak_g": float(abs(peak_val)),
                "lat": nearest_gps["lat"],
                "lon": nearest_gps["lon"],
            }
        )

    return events


def _find_nearest_gps(t: int, gps_df: pd.DataFrame) -> dict[str, float]:
    """Find nearest GPS point to a timestamp."""
    idx = (gps_df["t"] - t).abs().idxmin()
    row = gps_df.loc[idx]
    return {"lat": row["lat"], "lon": row["lon"]}


def _calculate_features(
    imu_df: pd.DataFrame, gps_df: pd.DataFrame, events: list[dict[str, Any]]
) -> dict[str, Any]:
    distance_km = _calculate_distance_km(gps_df)
    duration_s = (imu_df["t"].max() - imu_df["t"].min()) / 1000.0
    duration_min = duration_s / 60.0

    # Night driving share (23:00-05:00 Asia/Hong_Kong); imu time is tz-aware UTC
    night_hours = set(range(23, 24)) | set(range(0, 6))
    hk_time = imu_df["time"].dt.tz_convert("Asia/Hong_Kong")
    night_samples = imu_df[hk_time.dt.hour.isin(night_hours)]
    night_share = len(night_samples) / len(imu_df) if len(imu_df) > 0 else 0

    # Events per 100 km
    events_per_100km = {}
    for event_type in ["harsh_brake", "harsh_accel", "sharp_corner", "speeding"]:
        count = len([e for e in events if e["type"] == event_type])
        events_per_100km[event_type] = count / max(distance_km, 0.1) * 100

    # Speed stats
    speeds = gps_df["speed"].fillna(0)
    mean_speed = float(speeds.mean())
    max_speed = float(speeds.max())
    speeding_share = float((speeds > SPEEDING_THRESHOLD_MS).mean())

    # Downsampled route for the trip detail endpoint (up to ~100 points)
    route = []
    if len(gps_df) > 0:
        step = max(1, (len(gps_df) + 99) // 100)
        for _, row in gps_df.iloc[::step].iterrows():
            route.append(
                {
                    "t": int(row["t"]),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "speed": float(row["speed"]) if pd.notna(row["speed"]) else None,
                }
            )

    return {
        "distance_km": round(distance_km, 2),
        "duration_min": round(duration_min, 2),
        "night_driving_share": round(night_share, 4),
        "events_per_100km": events_per_100km,
        "mean_speed_ms": round(mean_speed, 2),
        "max_speed_ms": round(max_speed, 2),
        "speeding_time_share": round(speeding_share, 4),
        "route": route,
    }


CRASH_PEAK_G = 4.0
CRASH_STOP_SPEED_MS = 1.0
CRASH_STOP_WINDOW_S = 5.0
CRASH_STILL_DURATION_S = 30.0


def _detect_crashes(imu_df: pd.DataFrame, gps_df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Detect crashes: peak > 4g, then GPS speed drops to near 0 within 5s,
    then phone stays still for 30s.
    """
    crashes = []

    # Compute total acceleration magnitude from the gravity-free raw axes so a
    # real impact spike shows up at full rate (gravity-free magnitude ~ 0 normally).
    # Fall back to the derived channels for callers that pass those directly.
    if {"ax", "ay", "az"}.issubset(imu_df.columns):
        mag_cols = ("ax", "ay", "az")
    else:
        mag_cols = ("accel_forward", "accel_lateral", "accel_vertical")

    accel_mag = np.sqrt(
        imu_df[mag_cols[0]] ** 2 + imu_df[mag_cols[1]] ** 2 + imu_df[mag_cols[2]] ** 2
    )

    # Find peaks above threshold
    peak_indices = np.where(accel_mag > CRASH_PEAK_G)[0]
    if len(peak_indices) == 0:
        return crashes

    # Group consecutive peaks (within 1 second)
    peak_groups = []
    current_group = [peak_indices[0]]
    for i in range(1, len(peak_indices)):
        if imu_df["t"].iloc[peak_indices[i]] - imu_df["t"].iloc[current_group[-1]] < 1000:
            current_group.append(peak_indices[i])
        else:
            peak_groups.append(current_group)
            current_group = [peak_indices[i]]
    peak_groups.append(current_group)

    for group in peak_groups:
        peak_idx = group[np.argmax(accel_mag.iloc[group].values)]
        peak_time_ms = imu_df["t"].iloc[peak_idx]
        peak_g = float(accel_mag.iloc[peak_idx])

        # Check GPS speed drops to near 0 within 5 seconds
        gps_after = gps_df[gps_df["t"] >= peak_time_ms]
        gps_window = gps_after[gps_after["t"] <= peak_time_ms + CRASH_STOP_WINDOW_S * 1000]

        if len(gps_window) == 0:
            continue

        min_speed = gps_window["speed"].fillna(999).min()
        if min_speed > CRASH_STOP_SPEED_MS:
            continue

        # Check phone stays still for 30s after the stop
        still_end_ms = peak_time_ms + (CRASH_STOP_WINDOW_S + CRASH_STILL_DURATION_S) * 1000
        imu_after = imu_df[(imu_df["t"] > peak_time_ms) & (imu_df["t"] <= still_end_ms)]

        if len(imu_after) < 10:
            continue

        post_accel_mag = np.sqrt(
            imu_after[mag_cols[0]] ** 2 + imu_after[mag_cols[1]] ** 2 + imu_after[mag_cols[2]] ** 2
        )
        # Still = very low variance in acceleration
        if post_accel_mag.std() > 0.5:
            continue

        nearest_gps = _find_nearest_gps(peak_time_ms, gps_df)

        # Capture sensor snapshot around the crash
        snapshot_start = peak_time_ms - 5000
        snapshot_end = peak_time_ms + 10000
        snapshot_imu = imu_df[(imu_df["t"] >= snapshot_start) & (imu_df["t"] <= snapshot_end)]
        sensor_snapshot = {
            "peak_g": peak_g,
            "imu_samples": len(snapshot_imu),
            "duration_ms": int(snapshot_end - snapshot_start),
        }

        crashes.append(
            {
                "type": "crash",
                "time": imu_df["time"].iloc[peak_idx],
                "peak_g": peak_g,
                "lat": nearest_gps["lat"],
                "lon": nearest_gps["lon"],
                "sensor_snapshot": sensor_snapshot,
            }
        )

    return crashes


def process_trip(trip_id: str) -> None:
    """Process a trip end-to-end. Called as a background task."""
    db = SessionLocal()
    try:
        logger.info(f"Processing trip {trip_id}")

        trip = db.query(Trip).filter(Trip.id == trip_id).first()
        if not trip:
            raise PipelineError(f"Trip {trip_id} not found")

        trip.status = "processing"
        db.commit()

        # Load data (also derives the bluetooth ratio from chunk metadata)
        imu_df, gps_df, bluetooth_connected_ratio = _load_all_chunks(trip_id)
        trip.bluetooth_connected_ratio = bluetooth_connected_ratio

        # User labels are never overwritten by auto-classification
        if trip.label_source == "user":
            classification = {
                "trip_type": trip.trip_type,
                "label_source": trip.label_source,
                "driver_likelihood": trip.driver_likelihood,
                "transit_line": trip.transit_line,
            }
        else:
            # Classify BEFORE the quality check so underground-MTR GPS gaps
            # are recognised as transit instead of failing the trip
            classification = classify_trip(
                gps_df=gps_df,
                imu_df=imu_df,
                bluetooth_connected_ratio=bluetooth_connected_ratio,
            )
            trip.trip_type = classification["trip_type"]
            trip.label_source = classification["label_source"]
            trip.driver_likelihood = classification["driver_likelihood"]
            trip.transit_line = classification["transit_line"]

        # Transit and user-labelled passenger trips are saved but not scored
        if classification["trip_type"] in ("transit", "passenger"):
            trip.status = "done"
            db.commit()
            logger.info(f"Trip {trip_id} classified as {classification['trip_type']}, not scored")
            return

        _quality_check(imu_df, gps_df)

        # Process signals: resample -> gravity removal -> car-frame -> low-pass
        imu_df = _resample_imu(imu_df)
        imu_df = _remove_gravity(imu_df)
        imu_df = _rotate_to_car_frame(imu_df, gps_df)
        imu_df = _apply_lowpass_filter(imu_df)

        # Detect events
        events = _detect_events(imu_df, gps_df)

        # Detect crashes
        crashes = _detect_crashes(imu_df, gps_df)
        for crash_data in crashes:
            incident = Incident(
                driver_id=trip.driver_id,
                trip_id=trip_id,
                type="crash",
                time=crash_data["time"],
                lat=crash_data["lat"],
                lon=crash_data["lon"],
                peak_g=crash_data["peak_g"],
                sensor_snapshot=crash_data["sensor_snapshot"],
            )
            db.add(incident)
            logger.warning(f"Crash detected in trip {trip_id}: {crash_data['peak_g']:.2f}g")

        # Calculate features
        features = _validate_features(_calculate_features(imu_df, gps_df, events))

        # Save events
        for event_data in events:
            event = Event(
                trip_id=trip_id,
                type=event_data["type"],
                time=event_data["time"],
                peak_g=event_data["peak_g"],
                lat=event_data["lat"],
                lon=event_data["lon"],
            )
            db.add(event)

        # Save features
        trip_feature = TripFeature(trip_id=trip_id, features=features)
        db.add(trip_feature)

        # Score with model
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

        # Mark trip as done (ended_at was set by the /end endpoint)
        trip.status = "done"
        db.commit()

        logger.info(
            f"Trip {trip_id} processed successfully: score={score}, tier={tier}, "
            f"type={classification['trip_type']}"
        )

    except QualityCheckError as e:
        logger.warning(f"Trip {trip_id} failed quality check: {e}")
        trip = db.query(Trip).filter(Trip.id == trip_id).first()
        if trip:
            trip.status = "failed"
            trip.failure_reason = str(e)
            db.commit()
    except Exception as e:
        logger.error(f"Trip {trip_id} processing failed: {e}", exc_info=True)
        # A failed flush leaves the session unusable until rolled back
        db.rollback()
        trip = db.query(Trip).filter(Trip.id == trip_id).first()
        if trip:
            trip.status = "failed"
            trip.failure_reason = str(e)
            db.commit()
        raise
    finally:
        db.close()
