"""Stress tests for the remade model (remade_model/model.json).

1. Overfit gap: train vs VED-test vs DAF AUC.
2. Identity probe: can the 20 features predict WHICH CAR? (> chance = identity channel)
3. Partition barriers: zero shared cars / base windows across partitions.
4. Pulse-shortcut probe: does the model fire on REAL harsh baseline windows,
   or only on the synthetic injection?
5. Prevalence stress: precision at realistic 1-5% event prevalence.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import cross_val_predict

ROOT = Path(__file__).resolve().parent / "snapshots" / "bolttech_boosting_snapshot_2026-10-03"
DATA = ROOT / "data" / "processed" / "leakage_safe"
ART = json.loads((Path(__file__).resolve().parent / "remade_model" / "model.json").read_text())
FEATS = ART["feature_names"]
C, S = np.array(ART["scaler"]["center"]), np.array(ART["scaler"]["scale"])
W, B = np.array(ART["coef"]), ART["intercept"]
CAL_W, CAL_B = ART["calibration"]["coef"], ART["calibration"]["intercept"]


def load(name):
    df = pd.read_parquet(DATA / f"{name}.parquet")
    X = df[FEATS].to_numpy(dtype=float)
    X = np.nan_to_num(X, nan=0.0, posinf=1e10, neginf=-1e10).clip(-1e10, 1e10)
    return df, X


def score(X):
    z = ((X - C) / S) @ W + B
    return 1 / (1 + np.exp(-(CAL_W * z + CAL_B)))


out = []

# 1. overfit gap
tr, Xtr = load("train")
te, Xte = load("test")
daf, Xdaf = load("external_DAF")
auc_tr = roc_auc_score(tr.label, score(Xtr))
auc_te = roc_auc_score(te.label, score(Xte))
auc_daf = roc_auc_score(daf.label, score(Xdaf))
out.append(f"== 1. Overfit gap ==\ntrain AUC {auc_tr:.4f} | VED test {auc_te:.4f} | DAF {auc_daf:.4f}"
           f"\ntrain-test gap: {auc_tr - auc_te:.4f}")

# 2. identity probe: predict car from features (18 train cars, chance ~5.6%)
cars = tr.car.astype(str)
keep = cars.isin(cars.value_counts().head(18).index)
Xc, yc = Xtr[keep.to_numpy()], cars[keep].to_numpy()
pred = cross_val_predict(HistGradientBoostingClassifier(max_depth=6, max_iter=300, random_state=0),
                         Xc, yc, cv=3)
acc = (pred == yc).mean()
out.append(f"\n== 2. Identity probe ==\ncar-from-features accuracy: {acc:.3f} "
           f"(chance ~{1/18:.3f}, {len(set(yc))} cars)")

# 3. partition barriers
names = ["train", "stopping", "calibration", "test", "external_DAF"]
parts = {n: pd.read_parquet(DATA / f"{n}.parquet") for n in names}
bad = 0
for i, a in enumerate(names):
    for b in names[i + 1:]:
        cars_ab = set(parts[a].car) & set(parts[b].car)
        win_ab = set(parts[a].base_window_id) & set(parts[b].base_window_id)
        if cars_ab or win_ab:
            bad += 1
            out.append(f"LEAK: {a} x {b}: shared cars {cars_ab}, shared windows {len(win_ab)}")
out.append(f"\n== 3. Partition barriers ==\n{'all 10 pairs disjoint (cars + base windows)' if not bad else 'BARRIERS BROKEN'}")

# 4. pulse-shortcut probe: real harsh windows inside BASELINE (label 0)
b0 = daf[daf.label == 0].copy()
b0s = score(Xdaf[daf.label == 0])
harsh_idx = b0.mag_energy >= b0.mag_energy.quantile(0.9)
calm_idx = b0.mag_energy <= b0.mag_energy.quantile(0.5)
out.append(f"\n== 4. Pulse-shortcut probe (DAF baselines) =="
           f"\nreal-harsh decile (mag_energy top 10%): mean score {b0s[harsh_idx].mean():.3f}, "
           f"share >0.5: {(b0s[harsh_idx] > 0.5).mean():.3f}"
           f"\ncalm half (bottom 50%): mean score {b0s[calm_idx].mean():.3f}, "
           f"share >0.5: {(b0s[calm_idx] > 0.5).mean():.3f}")

# 5. prevalence stress (DAF rates: FPR 0.101, TPR from confusion)
p = score(Xdaf)
tpr = ((p > 0.5) & (daf.label == 1)).sum() / (daf.label == 1).sum()
fpr = ((p > 0.5) & (daf.label == 0)).sum() / (daf.label == 0).sum()
rows = [f"prevalence {pi:>4.0%}: precision {(pi * tpr) / (pi * tpr + (1 - pi) * fpr):.3f}"
        for pi in [0.01, 0.05, 0.10, 0.50]]
out.append(f"\n== 5. Prevalence stress (DAF TPR {tpr:.3f} FPR {fpr:.3f}) ==\n" + "\n".join(rows))

text = "\n".join(out)
print(text)
(Path(__file__).resolve().parent / "remade_model" / "stress_test.txt").write_text(text)
