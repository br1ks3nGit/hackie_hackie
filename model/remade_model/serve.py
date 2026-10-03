"""Self-contained serving for the remade DriveScore window model (model.json).

No xgboost, no sklearn, no snapshot code needed at inference. Deps: numpy, pandas, scipy.

Usage:
    python serve.py window.csv            # score a 250-row ax/ay/az CSV (g, 50 Hz)
    python serve.py --selftest            # score example_window.csv, compare to expected

The feature extraction and gravity removal below are vendored verbatim from the
teammate snapshot (src/feature_engineering.py, src/preprocessing.py) so scores are
bit-identical to the training pipeline.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import butter, sosfilt, sosfilt_zi
from scipy.stats import kurtosis, skew

HERE = Path(__file__).resolve().parent
EPS = 1e-9
WINDOW_SAMPLES = 250
FS = 50.0

# --- vendored from src/preprocessing.py (gravity removal only) ---


def _highpass_signal(sig: np.ndarray, fs: float, cutoff: float = 0.5) -> np.ndarray:
    sig = np.asarray(sig, dtype=np.float64)
    if not len(sig):
        return sig.copy()
    if not np.isfinite(sig).all():
        raise ValueError("Non-finite accelerometer samples")
    sos = butter(4, cutoff, btype="high", fs=fs, output="sos")
    return sosfilt(sos, sig, zi=sosfilt_zi(sos) * sig[0])[0]


def remove_gravity(df: pd.DataFrame, fs: float = FS) -> pd.DataFrame:
    out = df.copy()
    for col in ["ax", "ay", "az"]:
        out[col] = _highpass_signal(df[col].values.astype(np.float64), fs)
    return out


# --- vendored from src/feature_engineering.py ---


def _percentiles(x: np.ndarray) -> dict:
    return {f"p{p}": np.percentile(x, p) for p in (10, 25, 50, 75, 90)}


def _time_features(x: np.ndarray, prefix: str) -> dict:
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
    feats.update({f"{prefix}_{k}": v for k, v in _percentiles(x).items()})
    return feats


def _jerk_features(a: np.ndarray, prefix: str, dt: float) -> dict:
    jerk = np.diff(a) / dt
    if len(jerk) == 0:
        jerk = np.zeros_like(a)
    return {
        f"{prefix}_jerk_mean": np.mean(jerk),
        f"{prefix}_jerk_std": np.std(jerk),
        f"{prefix}_jerk_max": np.max(jerk),
        f"{prefix}_jerk_min": np.min(jerk),
        f"{prefix}_jerk_rms": np.sqrt(np.mean(jerk**2)),
    }


def _event_counts(ax: np.ndarray, ay: np.ndarray, az: np.ndarray) -> dict:
    hard_brake, rapid_accel, sharp_turn = -0.25, 0.25, 0.20
    return {
        "event_hard_brake": int(np.sum(ax < hard_brake)),
        "event_rapid_accel": int(np.sum(ax > rapid_accel)),
        "event_sharp_left": int(np.sum(ay > sharp_turn)),
        "event_sharp_right": int(np.sum(ay < -sharp_turn)),
        "event_any": int(np.sum((ax < hard_brake) | (ax > rapid_accel) | (np.abs(ay) > sharp_turn))),
    }


def _freq_features(x: np.ndarray, fs: float, prefix: str) -> dict:
    n = len(x)
    if n < 8:
        return {f"{prefix}_{k}": 0.0 for k in
                ("dom_freq", "spec_entropy", "spec_centroid", "low_energy_ratio")}
    psd = np.abs(np.fft.rfft(x)) ** 2
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    psd_sum = np.sum(psd) + EPS
    psd_norm = psd / psd_sum
    dom_idx = np.argmax(psd)
    return {
        f"{prefix}_dom_freq": freqs[dom_idx] if dom_idx < len(freqs) else 0.0,
        f"{prefix}_spec_entropy": -np.sum(psd_norm * np.log2(psd_norm + EPS)),
        f"{prefix}_spec_centroid": np.sum(freqs * psd) / psd_sum,
        f"{prefix}_low_energy_ratio": np.sum(psd[freqs <= 2.0]) / psd_sum,
    }


def extract_features_from_window(df_window: pd.DataFrame, fs: float = FS) -> dict:
    ax = df_window["ax"].values.astype(np.float64)
    ay = df_window["ay"].values.astype(np.float64)
    az = df_window["az"].values.astype(np.float64)
    mag = np.sqrt(ax**2 + ay**2 + az**2)
    dt = 1.0 / fs

    feats: dict = {}
    for arr, prefix in [(ax, "ax"), (ay, "ay"), (az, "az"), (mag, "mag")]:
        feats.update(_time_features(arr, prefix))
        feats.update(_jerk_features(arr, prefix, dt))
        feats.update(_freq_features(arr, fs, prefix))
    feats.update(_event_counts(ax, ay, az))
    feats["ax_ay_corr"] = np.corrcoef(ax, ay)[0, 1] if np.std(ax) > 0 and np.std(ay) > 0 else 0.0
    feats["ax_az_corr"] = np.corrcoef(ax, az)[0, 1] if np.std(ax) > 0 and np.std(az) > 0 else 0.0
    feats["ay_az_corr"] = np.corrcoef(ay, az)[0, 1] if np.std(ay) > 0 and np.std(az) > 0 else 0.0
    feats["mag_energy"] = np.sum(mag**2)
    feats["mag_peak_count"] = int(
        np.sum((mag[1:-1] > mag[:-2]) & (mag[1:-1] > mag[2:]) & (mag[1:-1] > 0.3))
    )
    return feats


# --- model serving ---


def load_model(path: Path = HERE / "model.json") -> dict:
    return json.loads(Path(path).read_text())


def predict(window: pd.DataFrame, model: dict | None = None) -> dict:
    """Score one window: exactly 250 rows of ax/ay/az in g at 50 Hz (ts_ms optional)."""
    model = model or load_model()
    missing = {"ax", "ay", "az"} - set(window.columns)
    if missing:
        raise ValueError(f"window is missing columns: {sorted(missing)}")
    if len(window) != WINDOW_SAMPLES:
        raise ValueError(f"window must have exactly {WINDOW_SAMPLES} rows, got {len(window)}")

    feats = extract_features_from_window(remove_gravity(window))
    names = model["feature_names"]
    x = np.array([feats[n] for n in names], dtype=np.float64)
    if not np.isfinite(x).all():
        bad = [n for n, v in zip(names, x) if not np.isfinite(v)]
        raise ValueError(f"non-finite features: {bad}")

    z = (x - np.array(model["scaler"]["center"])) / np.array(model["scaler"]["scale"])
    logit = float(z @ np.array(model["coef"]) + model["intercept"])
    cal = model["calibration"]
    risk = float(1.0 / (1.0 + np.exp(-(cal["coef"] * logit + cal["intercept"]))))
    return {
        "risk_score": risk,
        "uncalibrated_score": float(1.0 / (1.0 + np.exp(-logit))),
        "label": int(risk >= model["threshold"]),
        "score_semantics": "synthetic manoeuvre probability; not future insured loss",
    }


def _selftest() -> None:
    window = pd.read_csv(HERE / "example_window.csv")
    expected = json.loads((HERE / "expected_score.json").read_text())
    got = predict(window)
    drift = abs(got["risk_score"] - expected["risk_score"])
    print(f"risk_score={got['risk_score']:.10f} expected={expected['risk_score']:.10f} "
          f"drift={drift:.2e}")
    if drift > 1e-9:
        raise SystemExit("SELFTEST FAILED: score drifted from expected output")
    print("SELFTEST OK")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        _selftest()
    elif len(sys.argv) == 2:
        print(json.dumps(predict(pd.read_csv(sys.argv[1])), indent=2))
    else:
        print(__doc__)
        raise SystemExit(2)
