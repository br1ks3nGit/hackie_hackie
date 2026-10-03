from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from app.pipeline import (
    PipelineError,
    _calculate_distance_km,
    _calculate_features,
    _detect_events,
    _resample_imu,
    _validate_features,
)
from app.pipeline.errors import QualityCheckError
from app.pipeline.loading import _quality_check


def _speed_df(speeds, step_ms=1000, start_t=1000000000000):
    t = [start_t + i * step_ms for i in range(len(speeds))]
    return pd.DataFrame({"t": t, "speed": speeds})


def test_calculate_distance_km_constant_speed():
    # 10 m/s for 100 s -> 1000 m
    gps_df = _speed_df([10.0] * 101)
    assert _calculate_distance_km(gps_df) == pytest.approx(1.0)


def test_calculate_distance_km_trapezoid():
    # speed ramps 0 -> 20 m/s over 10 s: mean 10 m/s -> 100 m
    gps_df = _speed_df([0.0, 20.0], step_ms=10000)
    assert _calculate_distance_km(gps_df) == pytest.approx(0.1)


def test_calculate_distance_km_forward_fills_bad_speeds():
    gps_df = _speed_df([10.0, None, -5.0, 10.0])
    # missing/negative speeds repeat the previous valid sample: 10 m/s over 3 s = 30 m
    assert _calculate_distance_km(gps_df) == pytest.approx(0.03)


def test_calculate_distance_km_leading_missing_speed_is_zero():
    gps_df = _speed_df([None, 10.0, 10.0])
    # first interval (0+10)/2 = 5 m, second 10 m
    assert _calculate_distance_km(gps_df) == pytest.approx(0.015)


def test_calculate_distance_km_without_speed_column():
    gps_df = _speed_df([10.0] * 5).drop(columns=["speed"])
    assert _calculate_distance_km(gps_df) == 0.0


def test_quality_check_reports_missing_speed_data():
    n = 1000
    imu_df = pd.DataFrame({"t": [1000000000000 + i * 100 for i in range(n)]})
    for gps_df in (
        _speed_df([None] * 20),
        _speed_df([10.0] * 20).drop(columns=["speed"]),
    ):
        with pytest.raises(QualityCheckError, match="No GPS speed data"):
            _quality_check(imu_df, gps_df)


def test_calculate_distance_km_caps_gaps():
    from app.config import get_settings

    cap = get_settings().trip_max_gps_gap_s
    # one 1000 s gap at constant 10 m/s adds at most cap seconds of distance
    gps_df = _speed_df([10.0, 10.0], step_ms=1_000_000)
    assert _calculate_distance_km(gps_df) == pytest.approx(10.0 * cap / 1000.0)


def test_calculate_distance_km_needs_no_coordinates():
    assert _calculate_distance_km(_speed_df([10.0])) == 0.0


def test_resample_imu():
    imu_df = pd.DataFrame(
        {
            "t": [1000, 1050, 1100, 1150, 1200],  # 20 Hz
            "ax": [0.1, 0.2, 0.3, 0.4, 0.5],
            "ay": [0.1, 0.2, 0.3, 0.4, 0.5],
            "az": [9.8, 9.8, 9.8, 9.8, 9.8],
            "gx": [0.01, 0.02, 0.03, 0.04, 0.05],
            "gy": [0.01, 0.02, 0.03, 0.04, 0.05],
            "gz": [0.01, 0.02, 0.03, 0.04, 0.05],
        }
    )
    resampled = _resample_imu(imu_df, target_hz=50.0)
    assert len(resampled) > len(imu_df)
    assert resampled["t"].iloc[0] == 1000
    assert resampled["t"].iloc[-1] < 1200


def test_detect_harsh_brake():
    # Create synthetic data with a known harsh brake
    start_t = 1000000000000
    times = np.arange(start_t, start_t + 10000, 20)  # 10 seconds at 50 Hz
    accel_forward = np.random.normal(0, 0.05, len(times))

    # Insert harsh brake at 5 seconds
    brake_idx = 250
    accel_forward[brake_idx] = -0.5

    imu_df = pd.DataFrame(
        {
            "t": times,
            "time": pd.to_datetime(times, unit="ms", utc=True),
            "accel_forward": accel_forward,
            "accel_lateral": np.random.normal(0, 0.05, len(times)),
            "accel_vertical": np.random.normal(9.8, 0.1, len(times)),
        }
    )

    gps_df = pd.DataFrame(
        {
            "t": [start_t, start_t + 5000, start_t + 10000],
            "time": pd.to_datetime([start_t, start_t + 5000, start_t + 10000], unit="ms", utc=True),
            "lat": [22.3193, 22.3200, 22.3210],
            "lon": [114.1694, 114.1700, 114.1710],
            "speed": [10.0, 15.0, 12.0],
        }
    )

    events = _detect_events(imu_df, gps_df)
    harsh_brakes = [e for e in events if e["type"] == "harsh_brake"]

    assert len(harsh_brakes) >= 1
    assert harsh_brakes[0]["peak_g"] > 0.4


def test_detect_sharp_corner():
    start_t = 1000000000000
    times = np.arange(start_t, start_t + 10000, 20)
    accel_lateral = np.random.normal(0, 0.05, len(times))

    # Insert sharp corner at 5 seconds
    corner_idx = 250
    accel_lateral[corner_idx] = 0.4

    imu_df = pd.DataFrame(
        {
            "t": times,
            "time": pd.to_datetime(times, unit="ms", utc=True),
            "accel_forward": np.random.normal(0, 0.05, len(times)),
            "accel_lateral": accel_lateral,
            "accel_vertical": np.random.normal(9.8, 0.1, len(times)),
        }
    )

    gps_df = pd.DataFrame(
        {
            "t": [start_t, start_t + 5000, start_t + 10000],
            "time": pd.to_datetime([start_t, start_t + 5000, start_t + 10000], unit="ms", utc=True),
            "lat": [22.3193, 22.3200, 22.3210],
            "lon": [114.1694, 114.1700, 114.1710],
            "speed": [10.0, 15.0, 12.0],
        }
    )

    events = _detect_events(imu_df, gps_df)
    sharp_corners = [e for e in events if e["type"] == "sharp_corner"]

    assert len(sharp_corners) >= 1
    assert sharp_corners[0]["peak_g"] > 0.35


def test_calculate_features():
    start_t = 1000000000000
    times = np.arange(start_t, start_t + 60000, 20)  # 1 minute at 50 Hz

    imu_df = pd.DataFrame(
        {
            "t": times,
            "time": pd.to_datetime(times, unit="ms", utc=True),
            "accel_forward": np.random.normal(0, 0.05, len(times)),
            "accel_lateral": np.random.normal(0, 0.05, len(times)),
            "accel_vertical": np.random.normal(9.8, 0.1, len(times)),
        }
    )

    gps_df = pd.DataFrame(
        {
            "t": np.arange(start_t, start_t + 60000, 1000),
            "time": pd.to_datetime(np.arange(start_t, start_t + 60000, 1000), unit="ms", utc=True),
            "lat": 22.3193 + np.linspace(0, 0.01, 60),
            "lon": 114.1694 + np.linspace(0, 0.01, 60),
            "speed": np.random.uniform(10, 20, 60),
        }
    )

    events = [
        {
            "type": "harsh_brake",
            "time": datetime.now(UTC),
            "peak_g": 0.5,
        },
        {
            "type": "harsh_accel",
            "time": datetime.now(UTC),
            "peak_g": 0.4,
        },
    ]

    features = _calculate_features(imu_df, gps_df, events)

    assert "distance_km" in features
    assert "duration_min" in features
    assert "events_per_100km" in features
    assert "harsh_brake" in features["events_per_100km"]
    assert features["events_per_100km"]["harsh_brake"] > 0


def _minimal_frames():
    start_t = 1000000000000
    times = np.arange(start_t, start_t + 60000, 20)
    imu_df = pd.DataFrame({"t": times, "time": pd.to_datetime(times, unit="ms", utc=True)})
    gps_t = np.arange(start_t, start_t + 60000, 1000)
    gps_df = pd.DataFrame(
        {
            "t": gps_t,
            "time": pd.to_datetime(gps_t, unit="ms", utc=True),
            "lat": 22.3193 + np.linspace(0, 0.01, 60),
            "lon": 114.1694 + np.linspace(0, 0.01, 60),
            "speed": np.random.uniform(10, 20, 60),
        }
    )
    return imu_df, gps_df


def test_features_validate_and_keep_stored_shape():
    from app.features import TripFeatures

    start_t = 1000000000000
    times = np.arange(start_t, start_t + 60000, 20)
    imu_df = pd.DataFrame({"t": times, "time": pd.to_datetime(times, unit="ms", utc=True)})
    gps_t = np.arange(start_t, start_t + 60000, 1000)
    gps_df = pd.DataFrame(
        {
            "t": gps_t,
            "time": pd.to_datetime(gps_t, unit="ms", utc=True),
            "lat": 22.3193 + np.linspace(0, 0.01, 60),
            "lon": 114.1694 + np.linspace(0, 0.01, 60),
            "speed": np.random.uniform(10, 20, 60),
        }
    )
    raw = _calculate_features(imu_df, gps_df, [])

    stored = TripFeatures.model_validate(raw).model_dump()

    assert list(stored) == list(raw)
    assert list(stored["events_per_100km"]) == list(raw["events_per_100km"])
    assert "route" not in stored
    assert "route" not in raw


def test_validate_features_invalid_raises_short_pipeline_error():
    imu_df, gps_df = _minimal_frames()
    raw = _calculate_features(imu_df, gps_df, [])
    raw["night_driving_share"] = 1.5

    with pytest.raises(PipelineError) as exc:
        _validate_features(raw)

    assert str(exc.value) == "feature contract violated: night_driving_share"
    assert "\n" not in str(exc.value)


def test_load_all_chunks_reads_legacy_gps_key(tmp_path, monkeypatch):
    import gzip
    import json

    from app.pipeline import loading

    monkeypatch.setattr(loading.settings, "data_dir", str(tmp_path))
    trip_dir = tmp_path / "trip-old"
    trip_dir.mkdir()
    chunk = {"imu": [{"t": 1000000000000}], "gps": [{"t": 1000000000000, "speed": 4.0}]}
    with gzip.open(trip_dir / "0.json.gz", "wt", encoding="utf-8") as f:
        json.dump(chunk, f)
    _imu, gps_df, _bt = loading._load_all_chunks("trip-old")
    assert gps_df["speed"].tolist() == [4.0]


def test_load_all_chunks_without_speed_gives_missing_speeds(tmp_path, monkeypatch):
    import gzip
    import json

    from app.pipeline import loading

    monkeypatch.setattr(loading.settings, "data_dir", str(tmp_path))
    trip_dir = tmp_path / "trip-x"
    trip_dir.mkdir()
    samples = [{"t": 1000000000000}, {"t": 1000000001000}]
    chunk = {"imu": [{"t": 1000000000000}], "speed_samples": samples}
    with gzip.open(trip_dir / "0.json.gz", "wt", encoding="utf-8") as f:
        json.dump(chunk, f)
    _imu, gps_df, _bt = loading._load_all_chunks("trip-x")
    assert gps_df["speed"].isna().all()
