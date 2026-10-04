"""Stripped-down baselines vs the frozen 106-feature XGBoost model.

Same frozen partitions, same threshold (0.5), scaler fit on train only.
No tuning on test. Answers: how much do the 106 engineered features and
the tuned 794-tree booster actually buy over a trivial baseline?

Raw sensor data is NOT shipped in the snapshot, so "no feature engineering"
is approximated by using only magnitude-domain features that a one-line
on-phone computation could produce (no per-axis stats, no spectral, no
event flags, no cross-axis correlations).
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, f1_score, accuracy_score, confusion_matrix

ROOT = Path(__file__).resolve().parent / "snapshots" / "bolttech_boosting_snapshot_2026-10-03"
DATA = ROOT / "data" / "processed" / "leakage_safe"

# Tier A: one feature. The dumbest possible detector.
SINGLE = ["mag_std"]

# Tier B: minimal magnitude-domain set, computable in a few lines from |a|
# and its first difference. No per-axis breakdown, no FFT, no event logic.
MINIMAL = [
    "mag_mean", "mag_std", "mag_max", "mag_range", "mag_rms",
    "mag_jerk_max", "mag_jerk_rms", "mag_energy", "mag_peak_count",
]

ALL_FEATURES = pd.read_csv(ROOT / "models_leakage_safe" / "feature_names.csv").iloc[:, 0].tolist()

# Tier C: cheap time-domain stats only (mean/std/max/min/range/rms/jerk per
# axis + magnitude + cross-axis corr). Excludes spectral, percentiles,
# shape stats (skew/kurt/mad/zcr), event flags and peak counting.
CHEAP_TD = [
    n for n in ALL_FEATURES
    if not any(k in n for k in ["spec_", "dom_freq", "zcr", "skew", "kurt", "mad",
                                "_p10", "_p25", "_p50", "_p75", "_p90",
                                "event_", "peak_count", "low_energy"])
]


def load_partitions(features):
    parts = {}
    for name in ["train", "stopping", "test", "external_DAF"]:
        df = pd.read_parquet(DATA / f"{name}.parquet")
        X = df[features].to_numpy(dtype=float)
        X = np.nan_to_num(X, nan=0.0, posinf=1e10, neginf=-1e10).clip(-1e10, 1e10)
        parts[name] = (X, df["label"].to_numpy(dtype=int))
    return parts


def evaluate(clf_predict_proba, parts, name):
    out = {}
    for split in ["test", "external_DAF"]:
        X, y = parts[split]
        p = clf_predict_proba(X)
        pred = (p >= 0.5).astype(int)
        tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
        out[split] = {
            "auc": roc_auc_score(y, p),
            "f1": f1_score(y, pred),
            "acc": accuracy_score(y, pred),
            "fpr": fp / (fp + tn),
        }
    return out


def run_experiment(name, features, model_fn):
    parts = load_partitions(features)
    Xtr, ytr = parts["train"]
    scaler = StandardScaler().fit(Xtr)
    Xtr_s = scaler.transform(Xtr)
    Xst_s = scaler.transform(parts["stopping"][0])
    model = model_fn(Xtr_s, ytr, Xst_s, parts["stopping"][1])
    predict = lambda X: model.predict_proba(scaler.transform(X))[:, 1]
    res = evaluate(predict, parts, name)
    return {
        "name": name,
        "ved_auc": res["test"]["auc"], "ved_f1": res["test"]["f1"], "ved_acc": res["test"]["acc"],
        "daf_auc": res["external_DAF"]["auc"], "daf_f1": res["external_DAF"]["f1"],
        "daf_acc": res["external_DAF"]["acc"], "daf_fpr": res["external_DAF"]["fpr"],
    }


def logreg(max_iter=2000):
    def fit(Xtr, ytr, Xst, yst):
        clf = LogisticRegression(max_iter=max_iter)
        clf.fit(Xtr, ytr)
        return clf
    return fit


def gbm_shallow():
    def fit(Xtr, ytr, Xst, yst):
        clf = HistGradientBoostingClassifier(
            max_depth=3, max_iter=2000, learning_rate=0.05,
            early_stopping=True, validation_fraction=0.15, random_state=0,
        )
        clf.fit(Xtr, ytr)
        return clf
    return fit


def main():
    rows = [
        # Frozen reference numbers, copied from LEAKAGE_SAFE_RESULTS.md (not refit here)
        {"name": "FROZEN xgb-794 @106 feats (reference)", "ved_auc": 0.9846, "ved_f1": 0.9312,
         "ved_acc": 0.9318, "daf_auc": 0.9282, "daf_f1": 0.7969, "daf_acc": 0.7463, "daf_fpr": 0.5031},
        run_experiment("logreg @1 feat (mag_std)", SINGLE, logreg()),
        run_experiment("logreg @9 mag feats", MINIMAL, logreg()),
        run_experiment(f"logreg @{len(CHEAP_TD)} cheap time-domain", CHEAP_TD, logreg()),
        run_experiment("gbm-shallow @cheap time-domain", CHEAP_TD, gbm_shallow()),
        run_experiment("logreg @106 feats", ALL_FEATURES, logreg()),
        run_experiment("gbm-shallow @9 mag feats", MINIMAL, gbm_shallow()),
    ]
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(df.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    df.to_csv(Path(__file__).parent / "baseline_results.csv", index=False)


if __name__ == "__main__":
    main()
