from typing import Any

import pandas as pd
from pydantic import ValidationError

from app.features import TripFeatures
from app.pipeline.errors import PipelineError
from app.pipeline.events import SPEEDING_THRESHOLD_MS
from app.pipeline.loading import _calculate_distance_km


def _validate_features(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate computed features against TripFeatures; return the storable dict."""
    try:
        return TripFeatures.model_validate(raw).model_dump()
    except ValidationError as e:
        fields = ", ".join(".".join(str(p) for p in err["loc"]) for err in e.errors())
        raise PipelineError(f"feature contract violated: {fields}") from e


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
