"""Orientation-robust window features (feature set `horizontal-mag-v2`).

Pure numpy/scipy. The same code builds training features (from the VED feature snapshot) and
serves phone windows later.

Why horizontal only: VED's vertical axis is synthetic zeros and its ax/ay are already horizontal
(vehicle frame). A phone has gravity on an arbitrary axis and an arbitrary heading, so only
quantities that do not depend on the horizontal heading are well defined on both:
the magnitude of the horizontal vector, and rotation-invariant summaries of its 2x2 covariance.

Phone path: window (250, 3) in g, gravity included -> horizontal_components (remove the gravity
direction, project on two orthonormal horizontal axes) -> 0.5 Hz causal high-pass per component
(same filter as the v1 pipeline) -> window_features.
VED path: v1 `mag_*` equals the magnitude of high-passed (ax, ay) because az = 0, so the training
columns are reused via `derive_from_v1_columns`; test_features_v2.py checks both paths agree.
"""

from __future__ import annotations

from collections.abc import Mapping
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

# v1 magnitude features that are rotation invariant in the horizontal plane and non-degenerate.
# Dropped from the v1 `mag_*` family: mag_min (scaler scale 5.7e-18 on VED, magnitude of a
# 2-D vector whose minimum is ~0), mag_zcr and mag_dom_freq (constant 0 on VED train).
MAG_FEATURES = (
    [f"mag_{k}" for k in ("mean", "std", "max", "range", "rms", "skew", "kurt", "mad")]
    + [f"mag_p{p}" for p in (10, 25, 50, 75, 90)]
    + [f"mag_jerk_{k}" for k in ("mean", "std", "max", "min", "rms")]
    + [f"mag_{k}" for k in ("spec_entropy", "spec_centroid", "low_energy_ratio")]
    + ["mag_energy", "mag_peak_count"]
)
# Rotation-invariant summaries of the horizontal (x, y) covariance and jerk.
INVARIANT_FEATURES = ["h_std_total", "h_std_major", "h_std_minor", "h_anisotropy", "h_jerk_rms"]
FEATURE_SETS = {
    "mag_only": MAG_FEATURES,
    "mag_plus_invariants": MAG_FEATURES + INVARIANT_FEATURES,
}


def _highpass(sig: np.ndarray) -> np.ndarray:
    if not np.isfinite(sig).all():
        raise ValueError("Non-finite accelerometer samples")
    sos = butter(4, GRAVITY_CUTOFF_HZ, btype="high", fs=SAMPLE_RATE_HZ, output="sos")
    return sosfilt(sos, sig, zi=sosfilt_zi(sos) * sig[0])[0]


def horizontal_components(window: np.ndarray) -> np.ndarray:
    """(T, 3) accel in g, gravity included -> (T, 2) components on two horizontal axes.

    Gravity direction = window mean. If the mean norm is below GRAVITY_MIN_NORM_G there is no
    gravity (VED-like data): the first two columns are returned unchanged.
    """
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


def _mag_features(mag: np.ndarray) -> dict[str, float]:
    x = mag
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
    """From the 2x2 covariance [[sx^2, cov], [cov, sy^2]] and the horizontal jerk power."""
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


def derive_from_v1_columns(cols: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Training path: v2 columns from the extracted v1 VED feature columns (az = 0 there)."""
    out = {name: np.asarray(cols[name], dtype=np.float64) for name in MAG_FEATURES}
    sx, sy = np.asarray(cols["ax_std"], float), np.asarray(cols["ay_std"], float)
    cov_xy = np.asarray(cols["ax_ay_corr"], float) * sx * sy
    jerk_sq = (
        np.asarray(cols["ax_jerk_rms"], float) ** 2 + np.asarray(cols["ay_jerk_rms"], float) ** 2
    )
    rows = [_invariants(a, b, c, d) for a, b, c, d in zip(sx, sy, cov_xy, jerk_sq)]
    for name in INVARIANT_FEATURES:
        out[name] = np.array([r[name] for r in rows])
    return out


def score_window(window: np.ndarray, model: Mapping[str, Any]) -> dict[str, float | int]:
    """Score one phone window with a `window-logreg-v2` model dict (model.json)."""
    feats = phone_window_features(window)
    x = np.array([feats[n] for n in model["feature_names"]], dtype=np.float64)
    if not np.isfinite(x).all():
        raise ValueError("non-finite features")
    z = (x - np.array(model["scaler"]["center"])) / np.array(model["scaler"]["scale"])
    z = np.clip(z, -model["z_clip"], model["z_clip"])
    logit = float(z @ np.array(model["coef"]) + model["intercept"])
    cal = model["calibration"]
    risk = float(expit(cal["coef"] * logit + cal["intercept"]))
    return {
        "risk_score": risk,
        "logit": logit,
        "label": int(risk >= model["threshold"]),
    }
