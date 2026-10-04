import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import window_model
from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.model import load_model, predict
from app.models import Trip, TripScore
from app.pipeline import process_trip
from app.pipeline.process import _predict

MODEL_DIR = Path(__file__).resolve().parents[2] / "model" / "remade_model"
MODEL_FILE = MODEL_DIR / "model.json"
T0 = 1759986000000
client = TestClient(app)

pytestmark = pytest.mark.skipif(not MODEL_FILE.exists(), reason="model/remade_model not present")


@pytest.fixture
def window_kind(monkeypatch: pytest.MonkeyPatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "model_kind", "window")
    monkeypatch.setattr(settings, "window_model_path", str(MODEL_FILE))
    monkeypatch.setattr(window_model, "_window_model", None)
    load_model()
    yield
    monkeypatch.setattr(window_model, "_window_model", None)


def _df(values: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({"ax": values[:, 0], "ay": values[:, 1], "az": values[:, 2]})


def _fixture_model() -> dict:
    return window_model.read_model_file(str(MODEL_FILE))


def test_scorer_reproduces_expected_score() -> None:
    window = pd.read_csv(MODEL_DIR / "example_window.csv")
    expected = json.loads((MODEL_DIR / "expected_score.json").read_text())
    got = window_model.score_window(window[["ax", "ay", "az"]].to_numpy(), _fixture_model())
    assert abs(got["risk_score"] - expected["risk_score"]) < 1e-9
    assert got["label"] == expected["label"]


@pytest.mark.skipif(
    not (MODEL_DIR / "serve.py").exists(), reason="model/remade_model/serve.py not present"
)
def test_scorer_matches_serve_py_on_noisy_window() -> None:
    spec = importlib.util.spec_from_file_location("serve", MODEL_DIR / "serve.py")
    assert spec is not None and spec.loader is not None
    serve = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(serve)
    rng = np.random.default_rng(3)
    arr = rng.normal(0.0, 0.15, (250, 3)) + np.array([0.0, 0.0, 1.0])
    arr[100:110, 0] -= 0.8
    ref = serve.predict(_df(arr))
    got = window_model.score_window(arr, _fixture_model())
    assert got["risk_score"] == pytest.approx(ref["risk_score"], abs=1e-9)
    assert got["uncalibrated_score"] == pytest.approx(ref["uncalibrated_score"], abs=1e-9)


def test_risky_share_counts_windows_above_threshold() -> None:
    assert window_model.risky_share([0.1, 0.5, 0.51, 0.9]) == 0.5
    assert window_model.risky_share([0.2, 0.3]) == 0.0


def test_split_windows_drops_short_tail() -> None:
    df = _df(np.zeros((620, 3)))
    assert len(window_model.split_windows(df)) == 2
    assert window_model.split_windows(df.iloc[:249]) == []


def test_missing_model_file_fails_fast(
    window_kind: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(get_settings(), "window_model_path", str(tmp_path / "nope.json"))
    with pytest.raises(window_model.WindowModelError, match="does not exist"):
        load_model()


def test_invalid_model_file_fails_fast(
    window_kind: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bad = tmp_path / "model.json"
    bad.write_text(json.dumps({"feature_names": ["ax_mean"]}))
    monkeypatch.setattr(get_settings(), "window_model_path", str(bad))
    with pytest.raises(window_model.WindowModelError, match="missing keys"):
        load_model()


def _imu(seconds: int, aggressive_from: float | None) -> list[dict]:
    rng = np.random.default_rng(5)
    rows = []
    for i in range(seconds * 50):
        loud = aggressive_from is not None and i / 50 >= aggressive_from
        scale = 1.2 if loud else 0.01
        ax, ay = rng.normal(0.0, scale, 2)
        rows.append(
            {"t": T0 + i * 20, "ax": ax, "ay": ay, "az": 1.0, "gx": 0.01, "gy": 0.01, "gz": 0.02}
        )
    return rows


def _run_trip(imu: list[dict], seconds: int) -> tuple[Trip, TripScore | None]:
    data = client.post("/v1/drivers/register", json={}).json()
    headers = {"X-API-Key": data["api_key"]}
    client.post("/v1/consent", headers=headers, json={"version": "1.0"})
    trip_id = client.post("/v1/trips/start", headers=headers).json()["trip_id"]
    speeds = [{"t": T0 + s * 1000, "speed": 20.0} for s in range(seconds + 1)]
    body = {"seq": 0, "imu": imu, "speed_samples": speeds}
    client.post(f"/v1/trips/{trip_id}/chunks", headers=headers, json=body)
    process_trip(trip_id)
    with SessionLocal() as db:
        trip = db.get(Trip, trip_id)
        score = db.query(TripScore).filter(TripScore.trip_id == trip_id).first()
        assert trip is not None
        db.expunge_all()
    return trip, score


def test_window_kind_end_to_end(window_kind: None, monkeypatch: pytest.MonkeyPatch) -> None:
    seconds = 100  # 5000 samples = 20 full windows
    calm_trip, calm = _run_trip(_imu(seconds, None), seconds)
    assert calm_trip.status == "done"
    assert calm is not None and calm.model_version == "window-logreg-v1"
    assert calm.confidence == 0.0 and calm.score == 100

    # score_window is monkeypatched because the shipped model never flags gravity-containing
    # windows (mag_min scaler ~5.7e-18 saturates the logit), so no real input can reach a risky
    # window. Force the loud half risky to
    # prove the share -> confidence -> score path. The resampled grid has 19 full windows (the
    # last sample is dropped), the loud half starts at window 10: 9 risky of 19.
    real = window_model.score_window

    def fake(window: np.ndarray, model: dict) -> dict:
        loud = float(np.std(window[:, 0])) > 0.5
        return {**real(window, model), "risk_score": 0.9 if loud else 0.1}

    monkeypatch.setattr(window_model, "score_window", fake)
    wild_trip, wild = _run_trip(_imu(seconds, 50.0), seconds)
    assert wild_trip.status == "done"
    assert wild is not None and wild.model_version == "window-logreg-v1"
    assert wild.confidence == pytest.approx(9 / 19, abs=1e-4)
    assert wild.score == 53 and wild.tier == "D"


def test_window_kind_without_scorable_window_falls_back(window_kind: None) -> None:
    features = {"events_per_100km": {"harsh_brake": 10.0}}
    tiny = _df(np.zeros((100, 3)))
    result = _predict(features, tiny)
    assert result["model_version"] == "placeholder-window-fallback"
    assert result["confidence"] == predict(features)["confidence"]


def test_placeholder_kind_unchanged() -> None:
    assert get_settings().model_kind == "placeholder"
    trip, score = _run_trip(_imu(100, 0.0), 100)
    assert trip.status == "done"
    assert score is not None and score.model_version == "placeholder"
