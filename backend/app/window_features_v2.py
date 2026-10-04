"""Window model v2 (feature set `horizontal-mag-v2`): orientation-robust phone window scoring.

Faithful port of model/retrain/features_v2.py (phone path only; numpy/scipy, no import from
../model). Window (250, 3) in g, gravity included -> two horizontal components (gravity direction
= window mean) -> 0.5 Hz causal high-pass -> magnitude + rotation-invariant features -> robust
scale -> clip to z_clip -> logit -> Platt calibration.
"""

import math
from typing import Any

import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi
from scipy.special import expit
from scipy.stats import kurtosis, skew

WINDOW_SAMPLES = 250
SAMPLE_RATE_HZ = 50.0
GRAVITY_CUTOFF_HZ = 0.5
GRAVITY_MIN_NORM_G = 0.5  # window-mean norm below this: no gravity present, use (x, y) as given
LOW_ENERGY_HZ = 2.0
PEAK_MIN_G = 0.3
_EPS = 1e-9

FEATURE_SET_ID = "horizontal-mag-v2"
MODEL_VERSION_V2 = "window-logreg-v2"
FEATURE_NAMES = (
    [f"mag_{k}" for k in ("mean", "std", "max", "range", "rms", "skew", "kurt", "mad")]
    + [f"mag_p{p}" for p in (10, 25, 50, 75, 90)]
    + [f"mag_jerk_{k}" for k in ("mean", "std", "max", "min", "rms")]
    + [f"mag_{k}" for k in ("spec_entropy", "spec_centroid", "low_energy_ratio")]
    + ["mag_energy", "mag_peak_count"]
    + ["h_std_total", "h_std_major", "h_std_minor", "h_anisotropy", "h_jerk_rms"]
)
_REQUIRED_KEYS_V2 = (
    "version",
    "feature_set",
    "feature_names",
    "scaler",
    "coef",
    "intercept",
    "calibration",
    "z_clip",
    "threshold",
)


def _highpass(sig: np.ndarray) -> np.ndarray:
    if not np.isfinite(sig).all():
        raise ValueError("Non-finite accelerometer samples")
    sos = butter(4, GRAVITY_CUTOFF_HZ, btype="high", fs=SAMPLE_RATE_HZ, output="sos")
    return sosfilt(sos, sig, zi=sosfilt_zi(sos) * sig[0])[0]


def horizontal_components(window: np.ndarray) -> np.ndarray:
    """(T, 3) accel in g, gravity included -> (T, 2) components on two horizontal axes."""
    window = np.asarray(window, dtype=np.float64)
    mean = window.mean(axis=0)
    norm = float(np.linalg.norm(mean))
    if norm < GRAVITY_MIN_NORM_G:
        return window[:, :2].copy()
    up = mean / norm
    helper = np.eye(3)[int(np.argmin(np.abs(up)))]
    e1 = np.cross(up, helper)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(up, e1)
    return window @ np.column_stack([e1, e2])


def _mag_features(x: np.ndarray) -> dict[str, float]:
    jerk = np.diff(x) * SAMPLE_RATE_HZ
    psd = np.abs(np.fft.rfft(x)) ** 2
    freqs = np.fft.rfftfreq(len(x), d=1.0 / SAMPLE_RATE_HZ)
    psd_sum = np.sum(psd) + _EPS
    psd_norm = psd / psd_sum
    feats = {
        "mag_mean": np.mean(x),
        "mag_std": np.std(x),
        "mag_max": np.max(x),
        "mag_range": np.max(x) - np.min(x),
        "mag_rms": np.sqrt(np.mean(x**2)),
        "mag_skew": skew(x),
        "mag_kurt": kurtosis(x),
        "mag_mad": np.median(np.abs(x - np.median(x))),
        "mag_jerk_mean": np.mean(jerk),
        "mag_jerk_std": np.std(jerk),
        "mag_jerk_max": np.max(jerk),
        "mag_jerk_min": np.min(jerk),
        "mag_jerk_rms": np.sqrt(np.mean(jerk**2)),
        "mag_spec_entropy": -np.sum(psd_norm * np.log2(psd_norm + _EPS)),
        "mag_spec_centroid": np.sum(freqs * psd) / psd_sum,
        "mag_low_energy_ratio": np.sum(psd[freqs <= LOW_ENERGY_HZ]) / psd_sum,
        "mag_energy": np.sum(x**2),
        "mag_peak_count": int(
            np.sum((x[1:-1] > x[:-2]) & (x[1:-1] > x[2:]) & (x[1:-1] > PEAK_MIN_G))
        ),
    }
    feats.update({f"mag_p{p}": np.percentile(x, p) for p in (10, 25, 50, 75, 90)})
    return {k: float(v) for k, v in feats.items()}


def _invariants(sx: float, sy: float, cov_xy: float, jerk_rms_sq: float) -> dict[str, float]:
    trace = sx**2 + sy**2
    disc = np.sqrt(max(((sx**2 - sy**2) / 2) ** 2 + cov_xy**2, 0.0))
    major = max(trace / 2 + disc, 0.0)
    minor = max(trace / 2 - disc, 0.0)
    return {
        "h_std_total": float(np.sqrt(trace)),
        "h_std_major": float(np.sqrt(major)),
        "h_std_minor": float(np.sqrt(minor)),
        "h_anisotropy": float(np.sqrt(minor / major)) if major > 0 else 1.0,
        "h_jerk_rms": float(np.sqrt(jerk_rms_sq)),
    }


def window_features(h: np.ndarray) -> dict[str, float]:
    """Features from high-passed horizontal components h (T, 2), in g."""
    feats = _mag_features(np.hypot(h[:, 0], h[:, 1]))
    cov = np.cov(h.T, ddof=0)
    jerk = np.diff(h, axis=0) * SAMPLE_RATE_HZ
    feats.update(
        _invariants(
            float(np.sqrt(cov[0, 0])),
            float(np.sqrt(cov[1, 1])),
            float(cov[0, 1]),
            float(np.mean(jerk**2, axis=0).sum()),
        )
    )
    return feats


def phone_window_features(window: np.ndarray) -> dict[str, float]:
    """(250, 3) accel in g at 50 Hz, gravity included -> v2 feature dict."""
    if window.shape != (WINDOW_SAMPLES, 3):
        raise ValueError(f"window must have shape ({WINDOW_SAMPLES}, 3), got {window.shape}")
    comps = horizontal_components(window)
    h = np.column_stack([_highpass(comps[:, i]) for i in range(2)])
    return window_features(h)


def score_window_v2(window: np.ndarray, model: dict[str, Any]) -> dict[str, float | int]:
    """Score one phone window with a validated `window-logreg-v2` model dict."""
    feats = phone_window_features(window)
    x = np.array([feats[n] for n in model["feature_names"]], dtype=np.float64)
    if not np.isfinite(x).all():
        raise ValueError("non-finite features")
    z = (x - np.array(model["scaler"]["center"])) / np.array(model["scaler"]["scale"])
    z = np.clip(z, -model["z_clip"], model["z_clip"])
    logit = float(z @ np.array(model["coef"]) + model["intercept"])
    cal = model["calibration"]
    risk = float(expit(cal["coef"] * logit + cal["intercept"]))
    return {"risk_score": risk, "logit": logit, "label": int(risk >= model["threshold"])}


def _all_finite(values: Any) -> bool:
    try:
        return all(math.isfinite(float(v)) for v in values)
    except (TypeError, ValueError):
        return False


def validate_v2(model: dict[str, Any], path: str) -> dict[str, Any]:
    """Check a parsed v2 model.json; raise ValueError with a clear message."""
    prefix = f"WINDOW_MODEL_PATH {path}"
    missing = [k for k in _REQUIRED_KEYS_V2 if k not in model]
    if missing:
        raise ValueError(f"{prefix}: missing keys {missing}")
    if model["feature_set"] != FEATURE_SET_ID or model["version"] != MODEL_VERSION_V2:
        raise ValueError(
            f"{prefix}: expected feature_set {FEATURE_SET_ID!r} and version "
            f"{MODEL_VERSION_V2!r}, got {model['feature_set']!r} / {model['version']!r}"
        )
    names = model["feature_names"]
    unknown = sorted(set(names) - set(FEATURE_NAMES))
    if unknown or not names or len(set(names)) != len(names):
        raise ValueError(f"{prefix}: unknown, duplicate or empty feature_names {unknown}")
    scaler = model["scaler"]
    center, scale = scaler.get("center", []), scaler.get("scale", [])
    n = len(names)
    if len(model["coef"]) != n or len(center) != n or len(scale) != n:
        raise ValueError(f"{prefix}: feature, scaler and coef sizes differ")
    numbers = [*center, *scale, *model["coef"], model["intercept"], model["z_clip"]]
    cal = model["calibration"]
    numbers += [cal.get("coef"), cal.get("intercept"), model["threshold"]]
    if not _all_finite(numbers) or min(scale) <= 0 or model["z_clip"] <= 0:
        raise ValueError(f"{prefix}: non-finite values, scale <= 0 or z_clip <= 0")
    return model
