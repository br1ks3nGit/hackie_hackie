"""Evaluate the shipped window model on Ferreira 2017 events. EVALUATION ONLY.

Ferreira 2017 has no licence: never train on it, never commit its data (gitignored).
Run: uv run --project backend python model/eval_ferreira.py

Variant A = model as shipped. Variant B = diagnostic copy with mag_min zeroed (coef = 0); it is
NOT a new model. Caveats: 69 events, 2 drivers, earth-frame data (our app is device-frame),
only the 14 non-aggressive events are true negatives; results are indicative only.
"""

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))
from app.window_model import SAMPLE_RATE_HZ, WINDOW_SAMPLES, score_window  # noqa: E402

DATA = ROOT / "data" / "external" / "ferreira_2017" / "data"
MODEL = ROOT / "remade_model" / "model.json"
G = 9.80665
THRESHOLD = 0.5
NEG_MIN_DISTANCE_S = 10.0
NEG_PER_TRIP = 150
SEED = 0
NON_AGGRESSIVE = "evento_nao_agressivo"


def load_sensor(path: Path, first_ns: int, to_g: bool) -> tuple[np.ndarray, np.ndarray]:
    df = pd.read_csv(path)
    t = (df["uptimeNanos"].to_numpy(dtype=np.float64) - first_ns) / 1e9
    xyz = df[["x", "y", "z"]].to_numpy(dtype=np.float64)
    return t, xyz / G if to_g else xyz


def resample(t: np.ndarray, xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    grid = np.arange(t[0], t[-1], 1.0 / SAMPLE_RATE_HZ)
    return grid, np.column_stack([np.interp(grid, t, xyz[:, i]) for i in range(3)])


def load_trip(trip: str) -> dict:
    d = DATA / trip
    first = json.loads((d / "viagem.json").read_text())["firstCollectionUptimeNanos"]
    grid, acc = resample(*load_sensor(d / "acelerometro_terra.csv", first, True))
    # gyro is aligned the same way but the window model does not use it
    gt = pd.read_csv(d / "groundTruth.csv", skipinitialspace=True)
    gt.columns = [c.strip() for c in gt.columns]
    return {"trip": trip, "t0": grid[0], "acc": acc, "events": gt}


def window_at(trip: dict, centre_s: float) -> np.ndarray | None:
    i = round((centre_s - trip["t0"]) * SAMPLE_RATE_HZ) - WINDOW_SAMPLES // 2
    if i < 0 or i + WINDOW_SAMPLES > len(trip["acc"]):
        return None
    return trip["acc"][i : i + WINDOW_SAMPLES]


def patched_model(model: dict) -> dict:
    patched = copy.deepcopy(model)
    patched["coef"][patched["feature_names"].index("mag_min")] = 0.0
    return patched


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    ranks = rankdata(np.concatenate([pos, neg]))
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def collect(trips: list[dict]) -> tuple[pd.DataFrame, list[np.ndarray]]:
    rng = np.random.default_rng(SEED)
    rows, neg_windows = [], []
    for tr in trips:
        ev = tr["events"]
        for e in ev.itertuples(index=False):
            w = window_at(tr, (e.inicio + e.fim) / 2)
            if w is not None:
                rows.append({"type": e.evento, "window": w})
        end = tr["t0"] + len(tr["acc"]) / SAMPLE_RATE_HZ
        centres = rng.uniform(tr["t0"] + 2.5, end - 2.5, NEG_PER_TRIP * 10)
        kept = [
            c
            for c in centres
            if np.all(
                (c + 2.5 < ev["inicio"] - NEG_MIN_DISTANCE_S)
                | (c - 2.5 > ev["fim"] + NEG_MIN_DISTANCE_S)
            )
        ][:NEG_PER_TRIP]
        neg_windows += [w for c in kept if (w := window_at(tr, c)) is not None]
    return pd.DataFrame(rows), neg_windows


def report(name: str, model: dict, events: pd.DataFrame, negs: list[np.ndarray]) -> None:
    ev = events.assign(score=[score_window(w, model)["risk_score"] for w in events["window"]])
    neg_scores = np.array([score_window(w, model)["risk_score"] for w in negs])
    aggressive = ev["type"] != NON_AGGRESSIVE
    print(f"\n=== {name} ===")
    print(f"{'type':32s} {'n':>3s} {'min':>6s} {'median':>6s} {'max':>6s} {'det@0.5':>8s}")
    for typ, g in ev.groupby("type"):
        s = g["score"]
        rate = f"{(s > THRESHOLD).mean():.2f}"
        print(f"{typ:32s} {len(g):3d} {s.min():6.3f} {s.median():6.3f} {s.max():6.3f} {rate:>8s}")
    a = auc(ev.loc[aggressive, "score"].to_numpy(), ev.loc[~aggressive, "score"].to_numpy())
    print(
        f"ROC AUC aggressive ({aggressive.sum()}) vs non-aggressive "
        f"({(~aggressive).sum()}): {a:.3f}"
    )
    print(f"aggressive detection @0.5: {(ev.loc[aggressive, 'score'] > THRESHOLD).mean():.2f}")
    print(f"non-aggressive flagged @0.5: {(ev.loc[~aggressive, 'score'] > THRESHOLD).mean():.2f}")
    print(f"unlabelled windows > 0.5: {(neg_scores > THRESHOLD).mean():.2f} (n={len(neg_scores)})")


def main() -> None:
    model = json.loads(MODEL.read_text())
    model.setdefault("threshold", THRESHOLD)
    trips = [load_trip(t) for t in ("16", "17", "20", "21")]
    events, negs = collect(trips)
    print("Ferreira 2017 evaluation (EVALUATION ONLY, no training, data not committed)")
    print(
        f"{len(events)} event windows (5 s, centred), {len(negs)} unlabelled windows >= 10 s away"
    )
    print("Caveats: n tiny (69 events, 2 drivers); earth-frame data, not device-frame; only the")
    print("14 non-aggressive events are true negatives; indicative only.")
    report("A: model as shipped", model, events, negs)
    report("B: DIAGNOSTIC mag_min zeroed (not a new model)", patched_model(model), events, negs)


if __name__ == "__main__":
    main()
