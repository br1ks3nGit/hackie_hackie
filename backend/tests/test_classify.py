import numpy as np
import pandas as pd
from app.classify import (
    classify_trip,
    _check_transit_route_match,
    _calculate_driver_likelihood,
    CONFIG,
)


def _make_gps_df(points, speeds=None):
    """Helper to build a GPS DataFrame."""
    base_t = 1759986000000
    times = [base_t + i * 1000 for i in range(len(points))]
    if speeds is None:
        speeds = [10.0] * len(points)
    return pd.DataFrame({
        "t": times,
        "time": pd.to_datetime(times, unit="ms"),
        "lat": [p[0] for p in points],
        "lon": [p[1] for p in points],
        "speed": speeds,
    })


def _make_imu_df(n=500, gyro_variance=0.001):
    """Helper to build an IMU DataFrame."""
    base_t = 1759986000000
    times = np.arange(base_t, base_t + n * 20, 20)
    return pd.DataFrame({
        "t": times,
        "time": pd.to_datetime(times, unit="ms"),
        "ax": np.random.normal(0, 0.05, len(times)),
        "ay": np.random.normal(0, 0.05, len(times)),
        "az": np.random.normal(9.8, 0.1, len(times)),
        "gx": np.random.normal(0, gyro_variance, len(times)),
        "gy": np.random.normal(0, gyro_variance, len(times)),
        "gz": np.random.normal(0, gyro_variance, len(times)),
    })


def test_transit_mtr_line():
    """Trip along the Island Line should be classified as transit."""
    # Island Line coordinates from the GeoJSON
    mtr_points = [
        (22.2870, 114.1315),
        (22.2846, 114.1400),
        (22.2840, 22.2840),
        (22.2840, 114.1487),
        (22.2829, 114.1581),
        (22.2819, 114.1694),
        (22.2788, 114.1710),
        (22.2780, 114.1750),
    ]
    # Use points very close to the MTR line
    gps_df = _make_gps_df([(p[0], p[1]) for p in mtr_points])
    imu_df = _make_imu_df()

    result = classify_trip(gps_df, imu_df)
    assert result["trip_type"] == "transit"
    assert result["label_source"] == "rules"
    assert result["transit_line"] is not None


def test_transit_route_match_directly():
    """Direct test of transit route matching."""
    # Points along the Tsuen Wan Line
    points = [
        (22.2819, 114.1694),
        (22.2950, 114.1694),
        (22.3048, 114.1694),
        (22.3165, 114.1694),
    ]
    gps_df = _make_gps_df(points)
    is_transit, line_name = _check_transit_route_match(gps_df)
    assert is_transit
    assert line_name is not None


def test_bluetooth_driver():
    """Trip with car_connected > 80% should be classified as driver."""
    # Random driving route (not near transit)
    points = [(22.35 + i * 0.001, 114.20 + i * 0.001) for i in range(20)]
    gps_df = _make_gps_df(points)
    imu_df = _make_imu_df()

    result = classify_trip(gps_df, imu_df, bluetooth_connected_ratio=0.90)
    assert result["trip_type"] == "driver"
    assert result["label_source"] == "bluetooth"


def test_unknown_trip():
    """Trip not near transit and no Bluetooth should be unknown."""
    # Random route far from any transit line
    points = [(22.50 + i * 0.005, 114.30 + i * 0.005) for i in range(10)]
    gps_df = _make_gps_df(points)
    imu_df = _make_imu_df()

    result = classify_trip(gps_df, imu_df, bluetooth_connected_ratio=0.0)
    assert result["trip_type"] == "unknown"
    assert result["driver_likelihood"] is not None


def test_driver_likelihood_mounted_phone():
    """Low gyroscope variance (mounted phone) should raise driver_likelihood."""
    imu_stable = _make_imu_df(gyro_variance=0.001)
    imu_unstable = _make_imu_df(gyro_variance=0.5)

    likelihood_stable = _calculate_driver_likelihood(imu_stable)
    likelihood_unstable = _calculate_driver_likelihood(imu_unstable)

    assert likelihood_stable > likelihood_unstable
    assert likelihood_stable > CONFIG["likelihood_base"]
