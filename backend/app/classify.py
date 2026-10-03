import json
import logging
import math
import os
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TRANSIT_GEOJSON_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "transit_lines.geojson")

# Thresholds (all in one place for easy tuning)
CONFIG = {
    # Transit: fraction of GPS points within this distance of a transit line
    "transit_match_distance_m": 30.0,
    "transit_match_ratio": 0.70,
    # Bus-like stops: more than this many stops of 10-60s per 500m
    "bus_stop_min_duration_s": 10.0,
    "bus_stop_max_duration_s": 60.0,
    "bus_stop_speed_threshold_ms": 1.0,
    "bus_stops_per_500m_threshold": 1.0,
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


def _load_transit_lines() -> List[Dict[str, Any]]:
    global _transit_lines_cache
    if _transit_lines_cache is not None:
        return _transit_lines_cache

    if not os.path.exists(TRANSIT_GEOJSON_PATH):
        logger.warning(f"Transit lines file not found: {TRANSIT_GEOJSON_PATH}")
        _transit_lines_cache = []
        return _transit_lines_cache

    with open(TRANSIT_GEOJSON_PATH, "r") as f:
        data = json.load(f)

    lines = []
    for feature in data.get("features", []):
        coords = feature["geometry"]["coordinates"]
        lines.append({
            "name": feature["properties"].get("name", "unknown"),
            "mode": feature["properties"].get("mode", "unknown"),
            "underground": feature["properties"].get("underground", False),
            "coordinates": coords,
        })

    _transit_lines_cache = lines
    return lines


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _point_to_segment_distance_m(
    px: float, py: float,
    ax: float, ay: float,
    bx: float, by: float,
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


def _min_distance_to_line(lat: float, lon: float, line_coords: List[List[float]]) -> float:
    """Minimum distance from a point to a polyline (list of [lon, lat])."""
    min_dist = float("inf")
    for i in range(len(line_coords) - 1):
        ax, ay = line_coords[i]
        bx, by = line_coords[i + 1]
        dist = _point_to_segment_distance_m(lon, lat, ax, ay, bx, by)
        min_dist = min(min_dist, dist)
    return min_dist


def _check_transit_route_match(gps_df: pd.DataFrame) -> Tuple[bool, Optional[str]]:
    """Check if >70% of GPS points are within 30m of a transit line."""
    lines = _load_transit_lines()
    if not lines or len(gps_df) == 0:
        return False, None

    for line in lines:
        match_count = 0
        for _, row in gps_df.iterrows():
            dist = _min_distance_to_line(row["lat"], row["lon"], line["coordinates"])
            if dist <= CONFIG["transit_match_distance_m"]:
                match_count += 1

        ratio = match_count / len(gps_df)
        if ratio >= CONFIG["transit_match_ratio"]:
            return True, line["name"]

    return False, None


def _check_underground_gps_gaps(gps_df: pd.DataFrame) -> bool:
    """Check for GPS gaps on routes that match underground lines."""
    if len(gps_df) < 2:
        return False

    lines = _load_transit_lines()
    underground_lines = [l for l in lines if l["underground"]]
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
            if (dist_before <= CONFIG["transit_match_distance_m"] and
                    dist_after <= CONFIG["transit_match_distance_m"]):
                return True

    return False


def _check_bus_like_stops(gps_df: pd.DataFrame) -> bool:
    """Detect bus-like stop patterns: multiple 10-60s stops per 500m."""
    if len(gps_df) < 10:
        return False

    speeds = gps_df["speed"].fillna(0).values
    times = gps_df["t"].values

    stops = []
    in_stop = False
    stop_start = None

    for i in range(len(speeds)):
        if speeds[i] < CONFIG["bus_stop_speed_threshold_ms"] and not in_stop:
            in_stop = True
            stop_start = times[i]
        elif speeds[i] >= CONFIG["bus_stop_speed_threshold_ms"] and in_stop:
            in_stop = False
            duration_s = (times[i] - stop_start) / 1000.0
            if CONFIG["bus_stop_min_duration_s"] <= duration_s <= CONFIG["bus_stop_max_duration_s"]:
                stops.append({"time": stop_start, "lat": gps_df.iloc[i]["lat"], "lon": gps_df.iloc[i]["lon"]})

    if len(stops) < 2:
        return False

    # Calculate total distance
    total_distance_m = 0
    for i in range(1, len(gps_df)):
        total_distance_m += _haversine_m(
            gps_df.iloc[i - 1]["lat"], gps_df.iloc[i - 1]["lon"],
            gps_df.iloc[i]["lat"], gps_df.iloc[i]["lon"],
        )

    if total_distance_m < 100:
        return False

    stops_per_500m = len(stops) / (total_distance_m / 500.0)
    return stops_per_500m > CONFIG["bus_stops_per_500m_threshold"]


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
    bluetooth_connected_ratio: Optional[float] = None,
) -> Dict[str, Any]:
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

    if _check_bus_like_stops(gps_df):
        return {
            "trip_type": "transit",
            "label_source": "rules",
            "driver_likelihood": None,
            "transit_line": "bus-like stops",
        }

    # Rule 2: Bluetooth driver detection
    if bluetooth_connected_ratio is not None and bluetooth_connected_ratio > CONFIG["bluetooth_driver_ratio"]:
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
