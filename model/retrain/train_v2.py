"""Retrain the window model (window-logreg-v2) on the VED leakage-safe snapshot.

Usage: python train_v2.py SNAPSHOT_PARTITION_DIR OUT_DIR

Reads train / stopping / calibration / test parquet only. external_DAF is never loaded
(retracted); Ferreira is never seen. Protocol:
- feature set and C chosen on the stopping partition (AUC) only; the selection code never reads
  the test partition (history: a first run with a plain best-AUC C=100 printed test AUC 0.916
  before the C rule was changed, so the test partition was looked at twice in this project);
- partitions are asserted car-disjoint at run time;
- robust (median/IQR) scaler fit on train, scale floored, z clipped;
- Platt sigmoid fit on the calibration partition;
- test scored once per run, after everything is frozen.
Needs numpy, pandas, pyarrow, scikit-learn (training only; serving is numpy/scipy + JSON).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from features_v2 import FEATURE_SET_ID, FEATURE_SETS, derive_from_v1_columns
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, log_loss, roc_auc_score

MODEL_VERSION = "window-logreg-v2"
THRESHOLD = 0.5
C_GRID = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0]
SCALE_FLOOR_ABS = 1e-3  # a scale below this is degenerate; never divide by less
SCALE_FLOOR_REL = 0.1  # ... and never less than this share of the feature's std
AUC_TOLERANCE = 0.01  # prefer the smallest C within this stopping-AUC margin of the best
Z_CLIP = 10.0  # robust z-scores are clipped to +-Z_CLIP at train and serve time
PARTITIONS = ("train", "stopping", "calibration", "test")

Part = tuple[np.ndarray, np.ndarray]  # X, y


def load_partition(path: Path, name: str, feats: list[str]) -> Part:
    df = pd.read_parquet(path / f"{name}.parquet")
    cols = derive_from_v1_columns({c: df[c].to_numpy() for c in df.columns if c != "file"})
    X = np.column_stack([cols[f] for f in feats])
    if not np.isfinite(X).all():
        raise ValueError(f"{name}: non-finite values in {feats}")
    return X, df["label"].to_numpy(dtype=int)


def assert_car_disjoint(path: Path) -> None:
    cars = {
        p: set(pd.read_parquet(path / f"{p}.parquet", columns=["car"])["car"]) for p in PARTITIONS
    }
    for i, a in enumerate(PARTITIONS):
        for b in PARTITIONS[i + 1 :]:
            shared = cars[a] & cars[b]
            if shared:
                raise ValueError(f"partitions {a} and {b} share cars {sorted(shared)}: leakage")


def fit_scaler(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    center = np.median(X, axis=0)
    iqr = np.percentile(X, 75, axis=0) - np.percentile(X, 25, axis=0)
    scale = np.maximum(iqr, np.maximum(SCALE_FLOOR_ABS, SCALE_FLOOR_REL * X.std(axis=0)))
    return center, scale


def transform(X: np.ndarray, center: np.ndarray, scale: np.ndarray) -> np.ndarray:
    return np.clip((X - center) / scale, -Z_CLIP, Z_CLIP)


def fit_logreg(Z: np.ndarray, y: np.ndarray, c: float) -> LogisticRegression:
    return LogisticRegression(C=c, max_iter=5000).fit(Z, y)


def select(data: dict[str, dict[str, Part]]) -> tuple[str, float, list[dict[str, Any]]]:
    """Pick feature set (best stopping AUC) and the smallest C within AUC_TOLERANCE of the best.

    Large C gave huge opposite-sign coefficients on near-collinear features for ~0.01 AUC; those
    cancel on in-distribution data and are fragile on phone data. Stopping partition only.
    """
    rows = []
    for set_name, parts in data.items():
        (Xtr, ytr), (Xst, yst) = parts["train"], parts["stopping"]
        center, scale = fit_scaler(Xtr)
        for c in C_GRID:
            clf = fit_logreg(transform(Xtr, center, scale), ytr, c)
            p = clf.predict_proba(transform(Xst, center, scale))[:, 1]
            rows.append(
                {
                    "set": set_name,
                    "C": c,
                    "n": Xtr.shape[1],
                    "stopping_auc": float(roc_auc_score(yst, p)),
                }
            )
    top = max(r["stopping_auc"] for r in rows)
    best_set = max(rows, key=lambda r: r["stopping_auc"])["set"]
    near = [r for r in rows if r["set"] == best_set and r["stopping_auc"] >= top - AUC_TOLERANCE]
    return best_set, min(r["C"] for r in near), rows


def metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    pred = (p >= THRESHOLD).astype(int)
    return {
        "auc": float(roc_auc_score(y, p)),
        "f1": float(f1_score(y, pred)),
        "acc": float(accuracy_score(y, pred)),
        "fpr": float(pred[y == 0].mean()),
        "logloss": float(log_loss(y, np.clip(p, 1e-7, 1 - 1e-7))),
    }


def build_model(feats: list[str], fit: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_type": "logistic_regression_robust_scaled_platt_calibrated",
        "version": MODEL_VERSION,
        "feature_set": FEATURE_SET_ID,
        "feature_names": feats,
        "scaler": {
            "type": "robust_median_iqr_floored",
            "center": fit["center"].tolist(),
            "scale": fit["scale"].tolist(),
        },
        "scale_floor": {"abs": SCALE_FLOOR_ABS, "rel_std": SCALE_FLOOR_REL},
        "z_clip": Z_CLIP,
        "coef": fit["coef"].tolist(),
        "intercept": fit["intercept"],
        "calibration": {"type": "platt_sigmoid", "coef": fit["a"], "intercept": fit["b"]},
        "threshold": THRESHOLD,
        "input_contract": "250 rows ax/ay/az in g at 50 Hz, gravity included, any orientation; "
        "features_v2.phone_window_features, robust scale, clip to z_clip, logit, Platt.",
        "fit_on": "VED train only (external_DAF and Ferreira never used); C and feature set "
        "on stopping AUC; Platt on calibration; test scored once",
    }


def fit_final(data: dict[str, Part], c: float) -> dict[str, Any]:
    center, scale = fit_scaler(data["train"][0])
    clf = fit_logreg(transform(data["train"][0], center, scale), data["train"][1], c)
    coef, intercept = clf.coef_[0], float(clf.intercept_[0])
    Xca, yca = data["calibration"]
    logit_ca = transform(Xca, center, scale) @ coef + intercept
    platt = LogisticRegression(C=1e10, max_iter=5000).fit(logit_ca.reshape(-1, 1), yca)
    return {
        "center": center,
        "scale": scale,
        "coef": coef,
        "intercept": intercept,
        "a": float(platt.coef_[0][0]),
        "b": float(platt.intercept_[0]),
    }


def logits_of(fit: dict[str, Any], X: np.ndarray) -> np.ndarray:
    return transform(X, fit["center"], fit["scale"]) @ fit["coef"] + fit["intercept"]


def main(path: Path, out: Path) -> None:
    assert_car_disjoint(path)
    data = {s: {p: load_partition(path, p, f) for p in PARTITIONS} for s, f in FEATURE_SETS.items()}
    set_name, c, grid = select(data)
    feats, parts = FEATURE_SETS[set_name], data[set_name]
    fit = fit_final(parts, c)

    def proba(X: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-(fit["a"] * logits_of(fit, X) + fit["b"])))

    # one frozen test evaluation, after selection and calibration
    test, train = (
        metrics(parts["test"][1], proba(parts["test"][0])),
        metrics(parts["train"][1], proba(parts["train"][0])),
    )
    summary = {
        "selected_set": set_name,
        "C": c,
        "n_features": len(feats),
        "ved_test": test,
        "train": train,
        "overfit_gap_auc": train["auc"] - test["auc"],
        "max_abs_logit_test": float(np.abs(logits_of(fit, parts["test"][0])).max()),
        "min_scale": float(fit["scale"].min()),
        "platt": {"a": fit["a"], "b": fit["b"]},
        "selection_grid": grid,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "model.json").write_text(json.dumps(build_model(feats, fit), indent=2))
    (out / "metrics.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "selection_grid"}, indent=2))
    for r in grid:
        print(r)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
