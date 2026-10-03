import numpy as np
import pandas as pd

from app.pipeline import CRASH_PEAK_G, _detect_crashes


def _make_crash_data():
    """Build synthetic data with a known crash."""
    base_t = 1759986000000
    n_samples = 3000  # 60 seconds at 50 Hz

    times = np.arange(base_t, base_t + n_samples * 20, 20)

    # Normal driving acceleration
    accel_forward = np.random.normal(0, 0.05, len(times))
    accel_lateral = np.random.normal(0, 0.05, len(times))
    accel_vertical = np.random.normal(0, 0.1, len(times))

    # Insert crash at sample 1000 (20 seconds in): 5g spike
    crash_idx = 1000
    accel_forward[crash_idx] = 3.0
    accel_lateral[crash_idx] = 2.5
    accel_vertical[crash_idx] = 3.5

    # After crash: everything goes still
    for i in range(crash_idx + 1, min(crash_idx + 2000, len(times))):
        accel_forward[i] = np.random.normal(0, 0.01)
        accel_lateral[i] = np.random.normal(0, 0.01)
        accel_vertical[i] = np.random.normal(0, 0.02)

    imu_df = pd.DataFrame(
        {
            "t": times,
            "time": pd.to_datetime(times, unit="ms", utc=True),
            "accel_forward": accel_forward,
            "accel_lateral": accel_lateral,
            "accel_vertical": accel_vertical,
        }
    )

    # GPS: moving before crash, stops after
    gps_times = np.arange(base_t, base_t + 60000, 1000)
    gps_speeds = np.concatenate(
        [
            np.random.uniform(10, 20, 20),  # moving for 20s
            np.zeros(40),  # stopped after crash
        ]
    )
    gps_df = pd.DataFrame(
        {
            "t": gps_times,
            "time": pd.to_datetime(gps_times, unit="ms", utc=True),
            "lat": 22.3193 + np.linspace(0, 0.005, len(gps_times)),
            "lon": 114.1694 + np.linspace(0, 0.005, len(gps_times)),
            "speed": gps_speeds,
        }
    )

    return imu_df, gps_df


def test_crash_detected():
    """A synthetic crash should be detected."""
    imu_df, gps_df = _make_crash_data()
    crashes = _detect_crashes(imu_df, gps_df)

    assert len(crashes) >= 1
    crash = crashes[0]
    assert crash["type"] == "crash"
    assert crash["peak_g"] > CRASH_PEAK_G
    assert "lat" not in crash
    assert "lon" not in crash


def test_no_crash_normal_driving():
    """Normal driving should not trigger crash detection."""
    base_t = 1759986000000
    n = 2000
    times = np.arange(base_t, base_t + n * 20, 20)

    imu_df = pd.DataFrame(
        {
            "t": times,
            "time": pd.to_datetime(times, unit="ms", utc=True),
            "accel_forward": np.random.normal(0, 0.1, len(times)),
            "accel_lateral": np.random.normal(0, 0.1, len(times)),
            "accel_vertical": np.random.normal(0, 0.1, len(times)),
        }
    )

    gps_times = np.arange(base_t, base_t + 40000, 1000)
    gps_df = pd.DataFrame(
        {
            "t": gps_times,
            "time": pd.to_datetime(gps_times, unit="ms", utc=True),
            "lat": 22.3193 + np.linspace(0, 0.005, len(gps_times)),
            "lon": 114.1694 + np.linspace(0, 0.005, len(gps_times)),
            "speed": np.random.uniform(10, 20, len(gps_times)),
        }
    )

    crashes = _detect_crashes(imu_df, gps_df)
    assert len(crashes) == 0


def test_hard_brake_not_crash():
    """A hard brake (< 4g) should not be classified as a crash."""
    base_t = 1759986000000
    n = 2000
    times = np.arange(base_t, base_t + n * 20, 20)

    accel_forward = np.random.normal(0, 0.05, len(times))
    accel_forward[500] = -0.6  # hard brake, not crash

    imu_df = pd.DataFrame(
        {
            "t": times,
            "time": pd.to_datetime(times, unit="ms", utc=True),
            "accel_forward": accel_forward,
            "accel_lateral": np.random.normal(0, 0.05, len(times)),
            "accel_vertical": np.random.normal(0, 0.1, len(times)),
        }
    )

    gps_times = np.arange(base_t, base_t + 40000, 1000)
    gps_df = pd.DataFrame(
        {
            "t": gps_times,
            "time": pd.to_datetime(gps_times, unit="ms", utc=True),
            "lat": 22.3193 + np.linspace(0, 0.005, len(gps_times)),
            "lon": 114.1694 + np.linspace(0, 0.005, len(gps_times)),
            "speed": np.random.uniform(5, 15, len(gps_times)),
        }
    )

    crashes = _detect_crashes(imu_df, gps_df)
    assert len(crashes) == 0
