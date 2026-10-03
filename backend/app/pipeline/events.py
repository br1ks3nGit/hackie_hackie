from typing import Any

import numpy as np
import pandas as pd

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
    brake_events = _find_peaks(imu_df, brake_mask, "harsh_brake")
    events.extend(brake_events)

    # Detect harsh acceleration
    accel_mask = imu_df["accel_forward"] > harsh_accel_threshold
    accel_events = _find_peaks(imu_df, accel_mask, "harsh_accel")
    events.extend(accel_events)

    # Detect sharp cornering
    corner_mask = np.abs(imu_df["accel_lateral"]) > sharp_corner_threshold
    corner_events = _find_peaks(imu_df, corner_mask, "sharp_corner")
    events.extend(corner_events)

    # Detect speeding: merge consecutive speeding samples into runs and emit
    # ONE event per run longer than 10s (time of the run start)
    speeding_mask = nearest_speeds > SPEEDING_THRESHOLD_MS
    events.extend(_find_speeding_runs(imu_df, speeding_mask))

    return events


def _find_speeding_runs(
    imu_df: pd.DataFrame,
    mask,
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
            events.append(
                {
                    "type": "speeding",
                    "time": row["time"],
                    "peak_g": None,
                }
            )
        i += 1

    return events


def _find_peaks(imu_df: pd.DataFrame, mask: pd.Series, event_type: str) -> list[dict[str, Any]]:
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
            events.append(
                {
                    "type": event_type,
                    "time": row["time"],
                    "peak_g": float(abs(peak_val)),
                }
            )

    # Flush an event still open at the end of the array
    if in_event and peak_idx is not None:
        row = imu_df.iloc[peak_idx]
        events.append(
            {
                "type": event_type,
                "time": row["time"],
                "peak_g": float(abs(peak_val)),
            }
        )

    return events


CRASH_PEAK_G = 4.0
CRASH_STOP_SPEED_MS = 1.0
CRASH_STOP_WINDOW_S = 5.0
CRASH_STILL_DURATION_S = 30.0


def _group_peaks(imu_df: pd.DataFrame, peak_indices: np.ndarray) -> list[list[int]]:
    """Group consecutive peak samples (within 1 second)."""
    peak_groups = []
    current_group = [peak_indices[0]]
    for i in range(1, len(peak_indices)):
        if imu_df["t"].iloc[peak_indices[i]] - imu_df["t"].iloc[current_group[-1]] < 1000:
            current_group.append(peak_indices[i])
        else:
            peak_groups.append(current_group)
            current_group = [peak_indices[i]]
    peak_groups.append(current_group)
    return peak_groups


def _is_crash_candidate(
    imu_df: pd.DataFrame, gps_df: pd.DataFrame, peak_time_ms: float, mag_cols: tuple[str, ...]
) -> bool:
    """True if GPS speed drops to near 0 within 5s and the phone then stays still for 30s."""
    # Check GPS speed drops to near 0 within 5 seconds
    gps_after = gps_df[gps_df["t"] >= peak_time_ms]
    gps_window = gps_after[gps_after["t"] <= peak_time_ms + CRASH_STOP_WINDOW_S * 1000]

    if len(gps_window) == 0:
        return False

    min_speed = gps_window["speed"].fillna(999).min()
    if min_speed > CRASH_STOP_SPEED_MS:
        return False

    # Check phone stays still for 30s after the stop
    still_end_ms = peak_time_ms + (CRASH_STOP_WINDOW_S + CRASH_STILL_DURATION_S) * 1000
    imu_after = imu_df[(imu_df["t"] > peak_time_ms) & (imu_df["t"] <= still_end_ms)]

    if len(imu_after) < 10:
        return False

    post_accel_mag = np.sqrt(
        imu_after[mag_cols[0]] ** 2 + imu_after[mag_cols[1]] ** 2 + imu_after[mag_cols[2]] ** 2
    )
    # Still = very low variance in acceleration
    return not post_accel_mag.std() > 0.5


def _build_crash(imu_df: pd.DataFrame, peak_idx: int, peak_g: float) -> dict[str, Any]:
    peak_time_ms = imu_df["t"].iloc[peak_idx]

    # Capture sensor snapshot around the crash
    snapshot_start = peak_time_ms - 5000
    snapshot_end = peak_time_ms + 10000
    snapshot_imu = imu_df[(imu_df["t"] >= snapshot_start) & (imu_df["t"] <= snapshot_end)]
    sensor_snapshot = {
        "peak_g": peak_g,
        "imu_samples": len(snapshot_imu),
        "duration_ms": int(snapshot_end - snapshot_start),
    }

    return {
        "type": "crash",
        "time": imu_df["time"].iloc[peak_idx],
        "peak_g": peak_g,
        "sensor_snapshot": sensor_snapshot,
    }


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

    for group in _group_peaks(imu_df, peak_indices):
        peak_idx = group[np.argmax(accel_mag.iloc[group].values)]
        peak_time_ms = imu_df["t"].iloc[peak_idx]
        if not _is_crash_candidate(imu_df, gps_df, peak_time_ms, mag_cols):
            continue
        crashes.append(_build_crash(imu_df, peak_idx, float(accel_mag.iloc[peak_idx])))

    return crashes
