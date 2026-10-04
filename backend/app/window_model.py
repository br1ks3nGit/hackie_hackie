"""Window risk model (model/remade_model): logistic regression over 250-sample windows.

Ported from model/remade_model/serve.py (numpy/scipy only, no pandas frames, no pickle).
Feature extraction and gravity removal are the same maths as the training pipeline; the
scoring math reads the coefficients from model.json. Input is accelerometer in g at 50 Hz.
"""

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import butter, sosfilt, sosfilt_zi
from scipy.special import expit
from scipy.stats import kurtosis, skew

from app.config import get_settings

logger = logging.getLogger(__name__)

WINDOW_SAMPLES = 250
SAMPLE_RATE_HZ = 50.0
WINDOW_RISK_THRESHOLD = 0.5
WINDOW_MODEL_VERSION = "window-logreg-v1"
WINDOW_FALLBACK_VERSION = "placeholder-window-fallback"
GRAVITY_CUTOFF_HZ = 0.5
_EPS = 1e-9
_REQUIRED_KEYS = ("feature_names", "scaler", "coef", "intercept", "calibration")


class WindowModelError(Exception):
    pass


_window_model: dict[str, Any] | None = None


def _highpass(sig: np.ndarray) -> np.ndarray:
    sig = np.asarray(sig, dtype=np.float64)
    if not np.isfinite(sig).all():
        raise ValueError("Non-finite accelerometer samples")
    sos = butter(4, GRAVITY_CUTOFF_HZ, btype="high", fs=SAMPLE_RATE_HZ, output="sos")
    return sosfilt(sos, sig, zi=sosfilt_zi(sos) * sig[0])[0]


def _time_features(x: np.ndarray, prefix: str) -> dict[str, float]:
    feats = {
        f"{prefix}_mean": np.mean(x),
        f"{prefix}_std": np.std(x),
        f"{prefix}_max": np.max(x),
        f"{prefix}_min": np.min(x),
        f"{prefix}_range": np.max(x) - np.min(x),
        f"{prefix}_rms": np.sqrt(np.mean(x**2)),
        f"{prefix}_skew": skew(x),
        f"{prefix}_kurt": kurtosis(x),
        f"{prefix}_mad": np.median(np.abs(x - np.median(x))),
        f"{prefix}_zcr": np.mean(np.diff(np.signbit(x).astype(int)) != 0),
    }
    feats.update({f"{prefix}_p{p}": np.percentile(x, p) for p in (10, 25, 50, 75, 90)})
    return feats


def _jerk_features(a: np.ndarray, prefix: str) -> dict[str, float]:
    jerk = np.diff(a) / (1.0 / SAMPLE_RATE_HZ)
    if len(jerk) == 0:
        jerk = np.zeros_like(a)
    return {
        f"{prefix}_jerk_mean": np.mean(jerk),
        f"{prefix}_jerk_std": np.std(jerk),
        f"{prefix}_jerk_max": np.max(jerk),
        f"{prefix}_jerk_min": np.min(jerk),
        f"{prefix}_jerk_rms": np.sqrt(np.mean(jerk**2)),
    }


def _event_counts(ax: np.ndarray, ay: np.ndarray) -> dict[str, int]:
    hard_brake, rapid_accel, sharp_turn = -0.25, 0.25, 0.20
    return {
        "event_hard_brake": int(np.sum(ax < hard_brake)),
        "event_rapid_accel": int(np.sum(ax > rapid_accel)),
        "event_sharp_left": int(np.sum(ay > sharp_turn)),
        "event_sharp_right": int(np.sum(ay < -sharp_turn)),
        "event_any": int(
            np.sum((ax < hard_brake) | (ax > rapid_accel) | (np.abs(ay) > sharp_turn))
        ),
    }


def _freq_features(x: np.ndarray, prefix: str) -> dict[str, float]:
    n = len(x)
    if n < 8:
        return {
            f"{prefix}_{k}": 0.0
            for k in ("dom_freq", "spec_entropy", "spec_centroid", "low_energy_ratio")
        }
    psd = np.abs(np.fft.rfft(x)) ** 2
    freqs = np.fft.rfftfreq(n, d=1.0 / SAMPLE_RATE_HZ)
    psd_sum = np.sum(psd) + _EPS
    psd_norm = psd / psd_sum
    dom_idx = np.argmax(psd)
    return {
        f"{prefix}_dom_freq": freqs[dom_idx] if dom_idx < len(freqs) else 0.0,
        f"{prefix}_spec_entropy": -np.sum(psd_norm * np.log2(psd_norm + _EPS)),
        f"{prefix}_spec_centroid": np.sum(freqs * psd) / psd_sum,
        f"{prefix}_low_energy_ratio": np.sum(psd[freqs <= 2.0]) / psd_sum,
    }


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    if np.std(a) > 0 and np.std(b) > 0:
        return float(np.corrcoef(a, b)[0, 1])
    return 0.0


def extract_features(ax: np.ndarray, ay: np.ndarray, az: np.ndarray) -> dict[str, float]:
    """All 106 window features from gravity-free ax/ay/az (g)."""
    mag = np.sqrt(ax**2 + ay**2 + az**2)
    feats: dict[str, float] = {}
    for arr, prefix in [(ax, "ax"), (ay, "ay"), (az, "az"), (mag, "mag")]:
        feats.update(_time_features(arr, prefix))
        feats.update(_jerk_features(arr, prefix))
        feats.update(_freq_features(arr, prefix))
    feats.update(_event_counts(ax, ay))
    feats["ax_ay_corr"] = _corr(ax, ay)
    feats["ax_az_corr"] = _corr(ax, az)
    feats["ay_az_corr"] = _corr(ay, az)
    feats["mag_energy"] = np.sum(mag**2)
    feats["mag_peak_count"] = int(
        np.sum((mag[1:-1] > mag[:-2]) & (mag[1:-1] > mag[2:]) & (mag[1:-1] > 0.3))
    )
    return feats


def score_window(window: np.ndarray, model: dict[str, Any]) -> dict[str, float | int]:
    """Score one (250, 3) window of ax, ay, az in g at 50 Hz (gravity included)."""
    if window.shape != (WINDOW_SAMPLES, 3):
        raise ValueError(f"window must have shape ({WINDOW_SAMPLES}, 3), got {window.shape}")
    ax, ay, az = (_highpass(window[:, i]) for i in range(3))
    feats = extract_features(ax, ay, az)
    names = model["feature_names"]
    x = np.array([feats[n] for n in names], dtype=np.float64)
    if not np.isfinite(x).all():
        bad = [n for n, v in zip(names, x, strict=True) if not np.isfinite(v)]
        raise ValueError(f"non-finite features: {bad}")
    z = (x - np.array(model["scaler"]["center"])) / np.array(model["scaler"]["scale"])
    logit = float(z @ np.array(model["coef"]) + model["intercept"])
    cal = model["calibration"]
    risk = float(expit(cal["coef"] * logit + cal["intercept"]))
    return {
        "risk_score": risk,
        "uncalibrated_score": float(expit(logit)),
        "label": int(risk >= model["threshold"]),
    }


def validate_model(model: Any, path: str) -> dict[str, Any]:
    """Check the structure of a parsed model.json; raise WindowModelError with a clear message."""
    if not isinstance(model, dict):
        raise WindowModelError(f"WINDOW_MODEL_PATH {path}: top level must be a JSON object")
    missing = [k for k in _REQUIRED_KEYS if k not in model]
    if missing:
        raise WindowModelError(f"WINDOW_MODEL_PATH {path}: missing keys {missing}")
    n = len(model["feature_names"])
    sizes = (len(model["scaler"].get("center", [])), len(model["scaler"].get("scale", [])))
    if n == 0 or len(model["coef"]) != n or sizes != (n, n):
        raise WindowModelError(f"WINDOW_MODEL_PATH {path}: feature, scaler and coef sizes differ")
    probe = np.random.default_rng(0).normal(0.0, 0.1, (WINDOW_SAMPLES, 3))
    unknown = set(model["feature_names"]) - set(extract_features(*probe.T))
    if unknown:
        raise WindowModelError(f"WINDOW_MODEL_PATH {path}: unknown features {sorted(unknown)}")
    model.setdefault("threshold", WINDOW_RISK_THRESHOLD)
    return model


def read_model_file(path: str) -> dict[str, Any]:
    """Read and validate model.json; fail fast with an actionable message."""
    file = Path(path)
    if not file.is_file():
        raise WindowModelError(
            f"MODEL_KIND=window but WINDOW_MODEL_PATH {path!r} does not exist; mount "
            "model/remade_model or set WINDOW_MODEL_PATH to its model.json"
        )
    try:
        parsed = json.loads(file.read_text())
    except (OSError, ValueError) as e:
        raise WindowModelError(f"WINDOW_MODEL_PATH {path}: cannot read JSON: {e}") from e
    return validate_model(parsed, path)


def load_window_model() -> None:
    """Load model.json once (startup). Raises WindowModelError if missing or invalid."""
    global _window_model
    path = get_settings().window_model_path
    _window_model = read_model_file(path)
    logger.info("Window model %s loaded from %s", WINDOW_MODEL_VERSION, path)


def split_windows(imu_df: pd.DataFrame) -> list[np.ndarray]:
    """Non-overlapping 250-sample windows of ax, ay, az; the short tail is dropped."""
    values = imu_df[["ax", "ay", "az"]].to_numpy(dtype=np.float64)
    n = len(values) // WINDOW_SAMPLES
    return [values[i * WINDOW_SAMPLES : (i + 1) * WINDOW_SAMPLES] for i in range(n)]


def risky_share(risk_scores: list[float]) -> float:
    """Share of windows whose risk_score is above the window threshold."""
    return sum(1 for r in risk_scores if r > WINDOW_RISK_THRESHOLD) / len(risk_scores)


def predict_trip(imu_df: pd.DataFrame) -> dict[str, Any] | None:
    """Trip confidence from a 50 Hz grid (g, gravity included); None if no window can be scored.

    confidence = share of risky windows; the existing confidence_to_score treats a higher
    confidence as riskier (score = 100 * (1 - confidence)), so no inversion is needed.
    """
    if _window_model is None:
        raise WindowModelError("MODEL_KIND=window but the window model was not loaded at startup")
    scores: list[float] = []
    for window in split_windows(imu_df):
        try:
            scores.append(float(score_window(window, _window_model)["risk_score"]))
        except ValueError as e:
            logger.warning("Skipping unscorable window: %s", e)
    if not scores:
        return None
    return {
        "confidence": round(risky_share(scores), 4),
        "model_version": WINDOW_MODEL_VERSION,
        "windows": len(scores),
    }
