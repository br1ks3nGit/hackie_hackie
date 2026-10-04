import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from test_window_model import _imu, _run_trip

from app import window_model
from app.config import get_settings
from app.model import load_model

MODEL_DIR = Path(__file__).resolve().parents[2] / "model" / "retrained_model"
MODEL_FILE = MODEL_DIR / "model.json"
FEATURES_V2 = Path(__file__).resolve().parents[2] / "model" / "retrain" / "features_v2.py"

pytestmark = pytest.mark.skipif(not MODEL_FILE.exists(), reason="model/retrained_model not present")


@pytest.fixture
def window_v2(monkeypatch: pytest.MonkeyPatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "model_kind", "window")
    monkeypatch.setattr(settings, "window_model_path", str(MODEL_FILE))
    monkeypatch.setattr(window_model, "_window_model", None)
    load_model()
    yield
    monkeypatch.setattr(window_model, "_window_model", None)


def _model() -> dict:
    return window_model.read_model_file(str(MODEL_FILE))


def _rotation(rng: np.random.Generator) -> np.ndarray:
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    return q * np.sign(np.linalg.det(q))


def _phone_window(seed: int, noise: float, pulse: float) -> np.ndarray:
    """Gravity on a random axis plus noise and a brake pulse, random orientation."""
    rng = np.random.default_rng(seed)
    w = rng.normal(0.0, noise, (250, 3))
    w[100:105, 0] += pulse
    return (w + np.array([0.0, 0.0, 1.0])) @ _rotation(rng).T


def test_v2_loaded_from_file_records_version() -> None:
    assert _model()["version"] == "window-logreg-v2"


@pytest.mark.skipif(not FEATURES_V2.exists(), reason="model/retrain/features_v2.py not present")
@pytest.mark.parametrize(
    ("seed", "noise", "pulse"), [(1, 0.01, 0.0), (2, 0.05, 0.4), (3, 0.15, 0.8), (4, 0.3, -0.9)]
)
def test_v2_matches_reference_score_window(seed: int, noise: float, pulse: float) -> None:
    spec = importlib.util.spec_from_file_location("features_v2_ref", FEATURES_V2)
    assert spec is not None and spec.loader is not None
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)
    model = _model()
    window = _phone_window(seed, noise, pulse)
    want = ref.score_window(window, json.loads(MODEL_FILE.read_text()))
    got = window_model.score_window(window, model)
    assert got["risk_score"] == pytest.approx(want["risk_score"], abs=1e-9)
    assert got["logit"] == pytest.approx(want["logit"], abs=1e-9)
    assert got["label"] == want["label"]


def test_v2_phone_window_does_not_saturate() -> None:
    got = window_model.score_window(_phone_window(7, 0.05, 0.4), _model())
    assert np.isfinite(got["logit"]) and abs(got["logit"]) < 15


@pytest.mark.parametrize(
    ("key", "value", "match"),
    [
        ("feature_set", "something-else", "expected feature_set"),
        ("version", "window-logreg-v9", "expected feature_set"),
        ("feature_names", ["mag_mean", "nope"], "unknown"),
        ("z_clip", 0, "z_clip"),
        ("coef", [0.1], "sizes differ"),
    ],
)
def test_v2_invalid_file_fails_fast(tmp_path: Path, key: str, value: object, match: str) -> None:
    bad = copy.deepcopy(_model())
    bad[key] = value
    with pytest.raises(window_model.WindowModelError, match=match):
        window_model.validate_model(bad, "x.json")


def test_v2_missing_key_fails_fast() -> None:
    bad = copy.deepcopy(_model())
    del bad["z_clip"]
    with pytest.raises(window_model.WindowModelError, match="missing keys"):
        window_model.validate_model(bad, "x.json")


def test_window_kind_v2_end_to_end(window_v2: None) -> None:
    seconds = 100  # 5000 samples = 20 full windows
    calm_trip, calm = _run_trip(_imu(seconds, None), seconds)
    wild_trip, wild = _run_trip(_imu(seconds, 50.0), seconds)
    assert calm_trip.status == "done" and wild_trip.status == "done"
    assert calm is not None and wild is not None
    assert calm.model_version == "window-logreg-v2"
    assert wild.model_version == "window-logreg-v2"
    assert 0.0 <= calm.confidence <= 1.0
    assert wild.confidence > calm.confidence
