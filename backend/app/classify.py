from typing import Any

import pandas as pd

# Thresholds (all in one place for easy tuning)
CONFIG = {
    # Bluetooth: fraction of trip with car_connected to classify as driver
    "bluetooth_driver_ratio": 0.80,
    # Phone stability: gyroscope variance below this suggests mounted phone
    "gyro_stability_variance_threshold": 0.01,
    # driver_likelihood weights
    "likelihood_mounted_weight": 0.5,
    "likelihood_base": 0.3,
}


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
    Classify a trip as driver or unknown. Transit is never assigned automatically
    (it would need coordinates); it remains valid for legacy rows and user labels.

    Returns:
        {
            "trip_type": "driver" | "unknown",
            "label_source": "bluetooth" | None,
            "driver_likelihood": float (only for unknown),
            "transit_line": None (legacy column),
        }
    """
    # Rule 1: Bluetooth driver detection
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

    # Rule 2: Unknown
    driver_likelihood = _calculate_driver_likelihood(imu_df)
    return {
        "trip_type": "unknown",
        "label_source": None,
        "driver_likelihood": driver_likelihood,
        "transit_line": None,
    }
