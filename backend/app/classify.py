import json
import logging
import math
import os
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TRANSIT_GEOJSON_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "transit_lines.geojson"
)

# Thresholds (all in one place for easy tuning)
CONFIG = {
    # Transit: fraction of GPS points within this distance of a transit line
    "transit_match_distance_m": 30.0,
    "transit_match_ratio": 0.70,
    # GPS gap that suggests underground transit
    "underground_gps_gap_s": 30.0,
    # Bluetooth: fraction of trip with car_connected to classify as driver
    "bluetooth_driver_ratio": 0.80,
    # Phone stability: gyroscope variance below this suggests mounted phone
    "gyro_stability_variance_threshold": 0.01,
    # driver_likelihood weights
    "likelihood_mounted_weight": 0.5,
    "likelihood_base": 0.3,
}

_transit_lines_cache = None


def _load_transit_lines() -> list[dict[str, Any]]:
    global _transit_lines_cache
    if _transit_lines_cache is not None:
        return _transit_lines_cache

    if not os.path.exists(TRANSIT_GEOJSON_PATH):
        logger.warning(f"Transit lines file not found: {TRANSIT_GEOJSON_PATH}")
        _transit_lines_cache = []
        return _transit_lines_cache

    with open(TRANSIT_GEOJSON_PATH) as f:
        data = json.load(f)

    lines = []
    for feature in data.get("features", []):
        coords = feature["geometry"]["coordinates"]
        lines.append(
            {
                "name": feature["properties"].get("name", "unknown"),
                "mode": feature["properties"].get("mode", "unknown"),
                "underground": feature["properties"].get("underground", False),
                "coordinates": coords,
            }
        )

    _transit_lines_cache = lines
    return lines


def _point_to_segment_distance_m(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> float:
    """Distance from point (px,py) to segment (ax,ay)-(bx,by) in meters."""
    # Convert to approximate local coordinates (good enough for 30m checks in HK)
    lat_center = (ay + by) / 2
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat_center))

    px_m = px * m_per_deg_lon
    py_m = py * m_per_deg_lat
    ax_m = ax * m_per_deg_lon
    ay_m = ay * m_per_deg_lat
    bx_m = bx * m_per_deg_lon
    by_m = by * m_per_deg_lat

    dx = bx_m - ax_m
    dy = by_m - ay_m
    seg_len_sq = dx * dx + dy * dy

    if seg_len_sq == 0:
        return math.sqrt((px_m - ax_m) ** 2 + (py_m - ay_m) ** 2)

    t = max(0, min(1, ((px_m - ax_m) * dx + (py_m - ay_m) * dy) / seg_len_sq))
    closest_x = ax_m + t * dx
    closest_y = ay_m + t * dy

    return math.sqrt((px_m - closest_x) ** 2 + (py_m - closest_y) ** 2)


def _min_distance_to_line(lat: float, lon: float, line_coords: list[list[float]]) -> float:
    """Minimum distance from a point to a polyline (list of [lon, lat])."""
    min_dist = float("inf")
    for i in range(len(line_coords) - 1):
        ax, ay = line_coords[i]
        bx, by = line_coords[i + 1]
        dist = _point_to_segment_distance_m(lon, lat, ax, ay, bx, by)
        min_dist = min(min_dist, dist)
    return min_dist


def _min_distances_to_line(
    lats: np.ndarray, lons: np.ndarray, line_coords: list[list[float]]
) -> np.ndarray:
    """
    Vectorized minimum distance (meters) from each GPS point to a polyline.
    Broadcasts point-to-segment distance over all points x all segments at once.
    """
    coords = np.asarray(line_coords, dtype=float)  # [[lon, lat], ...]
    ax = coords[:-1, 0]
    ay = coords[:-1, 1]
    bx = coords[1:, 0]
    by = coords[1:, 1]

    # Approximate local coordinates (good enough for 30m checks in HK)
    lat_center = (ay + by) / 2  # per segment
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * np.cos(np.radians(lat_center))  # per segment

    # Broadcast: points (P,1) x segments (1,S) -> (P,S)
    px_m = lons[:, None] * m_per_deg_lon[None, :]
    py_m = lats[:, None] * m_per_deg_lat
    ax_m = ax[None, :] * m_per_deg_lon[None, :]
    ay_m = ay[None, :] * m_per_deg_lat
    bx_m = bx[None, :] * m_per_deg_lon[None, :]
    by_m = by[None, :] * m_per_deg_lat

    dx = bx_m - ax_m
    dy = by_m - ay_m
    seg_len_sq = dx * dx + dy * dy

    with np.errstate(divide="ignore", invalid="ignore"):
        t = ((px_m - ax_m) * dx + (py_m - ay_m) * dy) / seg_len_sq
    # Degenerate segments collapse to their start point
    t = np.where(seg_len_sq == 0, 0.0, t)
    t = np.clip(t, 0.0, 1.0)

    closest_x = ax_m + t * dx
    closest_y = ay_m + t * dy
    dist = np.sqrt((px_m - closest_x) ** 2 + (py_m - closest_y) ** 2)

    return dist.min(axis=1)


def _check_transit_route_match(gps_df: pd.DataFrame) -> tuple[bool, str | None]:
    """Check if >70% of GPS points are within 30m of a transit line."""
    lines = _load_transit_lines()
    if not lines or len(gps_df) == 0:
        return False, None

    lats = gps_df["lat"].values.astype(float)
    lons = gps_df["lon"].values.astype(float)

    for line in lines:
        dists = _min_distances_to_line(lats, lons, line["coordinates"])
        match_count = int(np.sum(dists <= CONFIG["transit_match_distance_m"]))

        ratio = match_count / len(gps_df)
        if ratio >= CONFIG["transit_match_ratio"]:
            return True, line["name"]

    return False, None


def _check_underground_gps_gaps(gps_df: pd.DataFrame) -> bool:
    """Check for GPS gaps on routes that match underground lines."""
    if len(gps_df) < 2:
        return False

    lines = _load_transit_lines()
    underground_lines = [ln for ln in lines if ln["underground"]]
    if not underground_lines:
        return False

    gaps = gps_df["t"].diff().dropna() / 1000.0
    if gaps.max() <= CONFIG["underground_gps_gap_s"]:
        return False

    # Check if points before and after the gap are near an underground line
    gap_indices = gaps[gaps > CONFIG["underground_gps_gap_s"]].index
    for idx in gap_indices:
        pos = gps_df.index.get_loc(idx)
        if pos == 0:
            continue

        before = gps_df.iloc[pos - 1]
        after = gps_df.iloc[pos]

        for line in underground_lines:
            dist_before = _min_distance_to_line(before["lat"], before["lon"], line["coordinates"])
            dist_after = _min_distance_to_line(after["lat"], after["lon"], line["coordinates"])
            if (
                dist_before <= CONFIG["transit_match_distance_m"]
                and dist_after <= CONFIG["transit_match_distance_m"]
            ):
                return True

    return False


def _calculate_driver_likelihood(imu_df: pd.DataFrame) -> float:
    """
    Estimate driver likelihood from phone stability.
    Low gyroscope variance suggests a mounted phone (probably driver).
    """
    likelihood = CONFIG["likelihood_base"]

    if len(imu_df) > 10:
        gyro_vars = []
        for col in ["gx", "gy", "gz"]:
            if col in imu_df.columns:
                gyro_vars.append(float(imu_df[col].var()))

        if gyro_vars:
            mean_variance = sum(gyro_vars) / len(gyro_vars)
            if mean_variance < CONFIG["gyro_stability_variance_threshold"]:
                likelihood += CONFIG["likelihood_mounted_weight"]

    return round(min(likelihood, 1.0), 4)


def classify_trip(
    gps_df: pd.DataFrame,
    imu_df: pd.DataFrame,
    bluetooth_connected_ratio: float | None = None,
) -> dict[str, Any]:
    """
    Classify a trip as transit, driver, or unknown.

    Returns:
        {
            "trip_type": "transit" | "driver" | "unknown",
            "label_source": "rules" | "bluetooth" | None,
            "driver_likelihood": float (only for unknown),
            "transit_line": str or None (if transit),
        }
    """
    # Rule 1: Transit detection
    is_transit, line_name = _check_transit_route_match(gps_df)
    if is_transit:
        return {
            "trip_type": "transit",
            "label_source": "rules",
            "driver_likelihood": None,
            "transit_line": line_name,
        }

    if _check_underground_gps_gaps(gps_df):
        return {
            "trip_type": "transit",
            "label_source": "rules",
            "driver_likelihood": None,
            "transit_line": "underground (GPS gap)",
        }

    # Rule 2: Bluetooth driver detection
    if (
        bluetooth_connected_ratio is not None
        and bluetooth_connected_ratio > CONFIG["bluetooth_driver_ratio"]
    ):
        return {
            "trip_type": "driver",
            "label_source": "bluetooth",
            "driver_likelihood": None,
            "transit_line": None,
        }

    # Rule 3: Unknown
    driver_likelihood = _calculate_driver_likelihood(imu_df)
    return {
        "trip_type": "unknown",
        "label_source": None,
        "driver_likelihood": driver_likelihood,
        "transit_line": None,
    }
