"""Remake the window model per EDA findings.

- Feature sets derived from eda/feature_signal_vs_shift.csv
  (disclosed: the source_shift column uses DAF *baseline* distributions -
  distributional info only, no DAF labels, no DAF event windows).
- Model class: logistic regression with robust (median/IQR) scaling.
  Baselines showed boosted trees overfit source-specific thresholds
  (DAF FPR ~50%) while linear models transfer (FPR 2-20%).
- Selection: C and feature set chosen on the STOPPING partition (VED AUC),
  calibration (Platt sigmoid) fit on the CALIBRATION partition,
  threshold frozen at 0.5, then ONE evaluation on VED test + external DAF.
- Export: JSON artifacts, no pickle, so any runtime can serve the model.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, f1_score, accuracy_score, confusion_matrix, log_loss

ROOT = Path(__file__).resolve().parent / "snapshots" / "bolttech_boosting_snapshot_2026-10-03"
DATA = ROOT / "data" / "processed" / "leakage_safe"
OUT = Path(__file__).resolve().parent / "remade_model"
OUT.mkdir(exist_ok=True)

ALL_FEATURES = pd.read_csv(ROOT / "models_leakage_safe" / "feature_names.csv").iloc[:, 0].tolist()
EDA = pd.read_csv(Path(__file__).resolve().parent / "eda" / "feature_signal_vs_shift.csv", index_col=0)

SAFE16 = EDA[(EDA.ved_signal > 0.3) & (EDA.daf_signal > 0.3) & (EDA.source_shift < 0.5)].index.tolist()
SAFE_PLUS_MAG = SAFE16 + ["mag_mean", "mag_rms", "mag_energy", "mag_peak_count"]
NO_AZ = [f for f in ALL_FEATURES if not f.startswith("az_") and f not in ("mag_zcr", "mag_dom_freq")]

FEATURE_SETS = {"safe16": SAFE16, "safe_plus_mag": SAFE_PLUS_MAG, "no_az": NO_AZ, "all106": ALL_FEATURES}
C_GRID = [0.01, 0.1, 1.0]


def load(name, feats):
    df = pd.read_parquet(DATA / f"{name}.parquet")
    X = df[feats].to_numpy(dtype=float)
    X = np.nan_to_num(X, nan=0.0, posinf=1e10, neginf=-1e10).clip(-1e10, 1e10)
    return X, df["label"].to_numpy(dtype=int)


class RobustScaler:
    def fit(self, X):
        self.center_ = np.median(X, axis=0)
        q75, q25 = np.percentile(X, 75, axis=0), np.percentile(X, 25, axis=0)
        self.scale_ = np.where(q75 - q25 > 0, q75 - q25, 1.0)
        return self

    def transform(self, X):
        return (X - self.center_) / self.scale_


def evaluate(proba_fn, feats, split):
    X, y = load(split, feats)
    p = proba_fn(X)
    pred = (p >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {"auc": roc_auc_score(y, p), "f1": f1_score(y, pred), "acc": accuracy_score(y, pred),
            "fpr": fp / (fp + tn), "logloss": log_loss(y, np.clip(p, 1e-7, 1 - 1e-7))}


def main():
    # --- select on stopping partition only ---
    rows, best = [], None
    for set_name, feats in FEATURE_SETS.items():
        Xtr, ytr = load("train", feats)
        Xst, yst = load("stopping", feats)
        sc = RobustScaler().fit(Xtr)
        for C in C_GRID:
            clf = LogisticRegression(C=C, max_iter=5000).fit(sc.transform(Xtr), ytr)
            p = clf.predict_proba(sc.transform(Xst))[:, 1]
            auc = roc_auc_score(yst, p)
            rows.append({"set": set_name, "C": C, "n_feats": len(feats), "stopping_auc": auc})
            if best is None or auc > best[0]:
                best = (auc, set_name, C, feats)
    sel = pd.DataFrame(rows).sort_values("stopping_auc", ascending=False)
    print("== selection on stopping partition ==")
    print(sel.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    _, set_name, C, feats = best
    print(f"\nselected: {set_name} (C={C}, {len(feats)} features)")

    # --- refit on train, calibrate on calibration partition ---
    Xtr, ytr = load("train", feats)
    Xca, yca = load("calibration", feats)
    scaler = RobustScaler().fit(Xtr)
    clf = LogisticRegression(C=C, max_iter=5000).fit(scaler.transform(Xtr), ytr)
    logits_ca = scaler.transform(Xca) @ clf.coef_[0] + clf.intercept_[0]
    # Platt sigmoid: 1-D logreg on the base model's logits
    platt = LogisticRegression(C=1e10, max_iter=5000).fit(logits_ca.reshape(-1, 1), yca)

    def calibrated_proba(X):
        logits = scaler.transform(X) @ clf.coef_[0] + clf.intercept_[0]
        return platt.predict_proba(logits.reshape(-1, 1))[:, 1]

    # --- one frozen evaluation ---
    res = {"ved_test": evaluate(calibrated_proba, feats, "test"),
           "external_DAF": evaluate(calibrated_proba, feats, "external_DAF")}
    print("\n== frozen evaluation (threshold 0.5) ==")
    print(json.dumps({"selected_set": set_name, "C": C, "n_features": len(feats), **res}, indent=2))

    # --- export JSON artifacts (no pickle) ---
    artifacts = {
        "contract": ROOT.joinpath("models_leakage_safe/manifest.json").read_text() and
                    json.loads((ROOT / "models_leakage_safe/manifest.json").read_text()),
        "model_type": "logistic_regression_robust_scaled_platt_calibrated",
        "feature_names": feats,
        "scaler_center": scaler.center_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "coef": clf.coef_[0].tolist(),
        "intercept": float(clf.intercept_[0]),
        "calibration": {"coef": float(platt.coef_[0][0]), "intercept": float(platt.intercept_[0])},
        "threshold": 0.5,
        "selected_on": "stopping partition AUC (VED); DAF never used for fitting or selection",
        "frozen_evaluation": res,
    }
    (OUT / "model.json").write_text(json.dumps(artifacts, indent=2))
    print(f"\nartifacts -> {OUT / 'model.json'}")


if __name__ == "__main__":
    main()
