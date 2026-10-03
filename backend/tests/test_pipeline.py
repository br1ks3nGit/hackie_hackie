from datetime import UTC, datetime

import numpy as np
import pandas as pd

from app.pipeline import (
    _calculate_distance_km,
    _calculate_features,
    _detect_events,
    _resample_imu,
)


def test_calculate_distance_km():
    # Test with known coordinates (Hong Kong to Kowloon)
    gps_df = pd.DataFrame(
        {
            "lat": [22.3193, 22.3200, 22.3210],
            "lon": [114.1694, 114.1700, 114.1710],
        }
    )
    distance = _calculate_distance_km(gps_df)
    assert distance > 0
    assert distance < 10  # should be a few km


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
            "lat": 22.32,
            "lon": 114.17,
        },
        {
            "type": "harsh_accel",
            "time": datetime.now(UTC),
            "peak_g": 0.4,
            "lat": 22.32,
            "lon": 114.17,
        },
    ]

    features = _calculate_features(imu_df, gps_df, events)

    assert "distance_km" in features
    assert "duration_min" in features
    assert "events_per_100km" in features
    assert "harsh_brake" in features["events_per_100km"]
    assert features["events_per_100km"]["harsh_brake"] > 0
