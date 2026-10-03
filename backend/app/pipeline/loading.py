import gzip
import json
import os
from typing import Any

import numpy as np
import pandas as pd

from app.config import get_settings
from app.pipeline.errors import PipelineError, QualityCheckError

settings = get_settings()


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

    # Check distance (integrated GPS speed)
    distance_km = _calculate_distance_km(gps_df)
    if distance_km < settings.trip_min_distance_km:
        raise QualityCheckError(
            f"Trip too short: {distance_km:.2f}km < {settings.trip_min_distance_km}km"
        )


def _calculate_distance_km(gps_df: pd.DataFrame) -> float:
    """Distance from GPS speed: trapezoid integral of speed (m/s) over time.

    Negative or missing speeds count as 0; each interval is capped at the max GPS gap so a
    long gap does not add phantom distance. Uses no coordinates.
    """
    if len(gps_df) < 2:
        return 0.0
    t = gps_df["t"].to_numpy(dtype=float)
    speed = pd.to_numeric(gps_df["speed"], errors="coerce").to_numpy(dtype=float)
    speed = np.where(np.isnan(speed) | (speed < 0), 0.0, speed)
    dt_s = np.minimum(np.diff(t) / 1000.0, settings.trip_max_gps_gap_s)
    dt_s = np.maximum(dt_s, 0.0)
    distance_m = np.sum((speed[:-1] + speed[1:]) / 2.0 * dt_s)
    return float(distance_m / 1000.0)
