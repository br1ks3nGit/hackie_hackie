"""Trip processing pipeline: load -> classify -> signal -> events -> features -> score."""

from app.pipeline.errors import PipelineError, QualityCheckError
from app.pipeline.events import (
    CRASH_PEAK_G,
    CRASH_STILL_DURATION_S,
    CRASH_STOP_SPEED_MS,
    CRASH_STOP_WINDOW_S,
    SPEEDING_THRESHOLD_MS,
    _detect_crashes,
    _detect_events,
    _find_nearest_gps,
    _find_peaks,
    _find_speeding_runs,
)
from app.pipeline.feature_calc import _calculate_features, _validate_features
from app.pipeline.loading import (
    _calculate_distance_km,
    _load_all_chunks,
    _load_chunk,
    _quality_check,
)
from app.pipeline.process import process_trip
from app.pipeline.signal import (
    _apply_lowpass_filter,
    _remove_gravity,
    _resample_imu,
    _rotate_to_car_frame,
)

__all__ = [
    "CRASH_PEAK_G",
    "CRASH_STILL_DURATION_S",
    "CRASH_STOP_SPEED_MS",
    "CRASH_STOP_WINDOW_S",
    "SPEEDING_THRESHOLD_MS",
    "PipelineError",
    "QualityCheckError",
    "_apply_lowpass_filter",
    "_calculate_distance_km",
    "_calculate_features",
    "_detect_crashes",
    "_detect_events",
    "_find_nearest_gps",
    "_find_peaks",
    "_find_speeding_runs",
    "_load_all_chunks",
    "_load_chunk",
    "_quality_check",
    "_remove_gravity",
    "_resample_imu",
    "_rotate_to_car_frame",
    "_validate_features",
    "process_trip",
]
