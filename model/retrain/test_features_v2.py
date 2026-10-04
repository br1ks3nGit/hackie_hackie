"""Tests for features_v2: train/serve parity, orientation invariance, no saturation.

Run: uv run --project backend pytest model/retrain/test_features_v2.py -q
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.signal import butter, sosfilt, sosfilt_zi

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "backend"))
import features_v2 as f2  # noqa: E402
from app.window_model import extract_features  # noqa: E402

MODEL = json.loads((HERE.parent / "retrained_model" / "model.json").read_text())
G_UP = 1.0


def pulse_window(rng: np.random.Generator, noise: float = 0.02) -> np.ndarray:
    w = rng.normal(0.0, noise, (f2.WINDOW_SAMPLES, 3))
    w[100:105, 0] += 0.9
    w[110:116, 1] -= 0.5
    return w


def random_rotation(rng: np.random.Generator) -> np.ndarray:
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    return q * np.sign(np.linalg.det(q))


def correlated_window(rng: np.random.Generator) -> np.ndarray:
    w = pulse_window(rng)
    w[:, 1] = 0.7 * w[:, 0] + 0.3 * w[:, 1]
    return w


def flat_axis_window(rng: np.random.Generator) -> np.ndarray:
    w = pulse_window(rng)
    w[:, 1] = 0.0  # zero variance: v1 ax_ay_corr takes its 0.0 branch
    return w


@pytest.mark.parametrize("make", [pulse_window, correlated_window, flat_axis_window])
def test_training_columns_match_serving_features(make) -> None:
    """v1 extracted columns of an az=0 window (VED path) equal the v2 window features."""
    rng = np.random.default_rng(1)
    raw = make(rng)
    raw[:, 2] = 0.0
    sos = butter(4, f2.GRAVITY_CUTOFF_HZ, btype="high", fs=f2.SAMPLE_RATE_HZ, output="sos")
    hp = np.column_stack(
        [sosfilt(sos, raw[:, i], zi=sosfilt_zi(sos) * raw[0, i])[0] for i in range(3)]
    )
    v1 = {k: np.array([v]) for k, v in extract_features(hp[:, 0], hp[:, 1], hp[:, 2]).items()}
    train_cols = f2.derive_from_v1_columns(v1)
    serve = f2.phone_window_features(raw)
    for name in f2.FEATURE_SETS["mag_plus_invariants"]:
        assert serve[name] == pytest.approx(float(train_cols[name][0]), rel=1e-6, abs=1e-9), name


def test_serving_is_rotation_invariant_for_correlated_axes() -> None:
    """Parity also holds after rotating a correlated horizontal pair in the plane."""
    rng = np.random.default_rng(4)
    base = correlated_window(rng)
    ref = f2.phone_window_features(base + np.array([0.0, 0.0, 1.0]))
    theta = 0.9
    c, s = np.cos(theta), np.sin(theta)
    rot = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    got = f2.phone_window_features((base + np.array([0.0, 0.0, 1.0])) @ rot.T)
    for name in f2.FEATURE_SETS["mag_plus_invariants"]:
        assert got[name] == pytest.approx(ref[name], rel=1e-6, abs=1e-9), name


def test_rotation_and_gravity_do_not_change_risk() -> None:
    rng = np.random.default_rng(2)
    base = pulse_window(rng)
    gravity = np.array([0.0, 0.0, 1.0])
    upright = f2.score_window(base + gravity, MODEL)["logit"]
    # gravity vs none: only the window-mean gravity estimate shifts slightly (measured 1e-3)
    assert abs(f2.score_window(base, MODEL)["logit"] - upright) < 0.05
    for _ in range(20):  # exact rotations of the full 3-D signal: float-level equality
        phone = (base + gravity) @ random_rotation(rng).T
        assert abs(f2.score_window(phone, MODEL)["logit"] - upright) < 1e-6


def test_no_logit_saturation_on_phone_windows() -> None:
    rng = np.random.default_rng(3)
    for _ in range(200):
        w = pulse_window(rng, noise=rng.uniform(0.005, 0.1)) + rng.normal(size=3) * 0.0
        phone = (w + np.array([0.0, 0.0, 1.0])) @ random_rotation(rng).T
        assert abs(f2.score_window(phone, MODEL)["logit"]) < 20.0


def test_no_degenerate_scales() -> None:
    assert min(MODEL["scaler"]["scale"]) >= MODEL["scale_floor"]["abs"]
    assert not {"mag_min", "mag_zcr", "mag_dom_freq"} & set(MODEL["feature_names"])
    assert not any(n.startswith(("az_", "ax_", "ay_", "event_")) for n in MODEL["feature_names"])


def test_rejects_bad_shape() -> None:
    with pytest.raises(ValueError):
        f2.phone_window_features(np.zeros((100, 3)))
