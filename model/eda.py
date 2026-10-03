"""Fresh-eye EDA on the window feature partitions.

Questions:
1. What does a window look like, and how do the two sources (VED = OBD-derived,
   DAF = phone) differ on NORMAL driving (label 0)?  -> source shift
2. Which features carry the event signal within each source?                -> label signal
3. Which features are BOTH label-discriminative in each source AND stable
   across sources?                                                          -> safe features
4. Feature quality: constants, missing, redundancy.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent / "snapshots" / "bolttech_boosting_snapshot_2026-10-03"
DATA = ROOT / "data" / "processed" / "leakage_safe"
OUT = Path(__file__).resolve().parent / "eda"
OUT.mkdir(exist_ok=True)

FEATS = pd.read_csv(ROOT / "models_leakage_safe" / "feature_names.csv").iloc[:, 0].tolist()

ved = pd.concat([
    pd.read_parquet(DATA / f"{n}.parquet")
    for n in ["train", "stopping", "calibration", "test"]
])
daf = pd.read_parquet(DATA / "external_DAF.parquet")


def cohens_d(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    sd = np.sqrt((a.std() ** 2 + b.std() ** 2) / 2)
    return (a.mean() - b.mean()) / sd if sd > 0 else 0.0


report = []

# --- 0. sanity ------------------------------------------------------------
report.append("== 0. Sanity ==")
report.append(f"VED windows: {len(ved)} (label1 share {ved.label.mean():.3f}), "
              f"cars {ved.car.nunique()}")
report.append(f"DAF windows: {len(daf)} (label1 share {daf.label.mean():.3f}), "
              f"cars {daf.car.nunique()}")

# --- 1. feature quality ----------------------------------------------------
report.append("\n== 1. Feature quality (VED train+stop+cal+test) ==")
n_nan = ved[FEATS].isna().sum()
n_inf = np.isinf(ved[FEATS].to_numpy(float)).sum()
const = [f for f in FEATS if ved[f].std() == 0]
report.append(f"NaNs: {int(n_nan.sum())} total | Infs: {int(n_inf)} | constant features: {const}")
near_const = [f for f in FEATS if 0 < ved[f].std() < 1e-8]
report.append(f"near-constant: {near_const}")

# --- 2. the gravity / vertical-axis artifact -------------------------------
report.append("\n== 2. Vertical axis & gravity (baseline windows only) ==")
v0, d0 = ved[ved.label == 0], daf[daf.label == 0]
for f in ["az_mean", "az_std", "az_absmax" if "az_absmax" in FEATS else "az_max",
          "mag_mean", "mag_std", "ax_std", "ay_std"]:
    if f in FEATS:
        report.append(f"{f:12s}  VED mean {v0[f].mean():+.4f} std {v0[f].std():.4f}   |   "
                      f"DAF mean {d0[f].mean():+.4f} std {d0[f].std():.4f}")

# --- 3. source shift on normal driving ------------------------------------
report.append("\n== 3. Source shift: |Cohen's d| VED vs DAF, baseline windows ==")
shift = pd.Series({f: abs(cohens_d(v0[f], d0[f])) for f in FEATS}).sort_values(ascending=False)
report.append("Top 15 source-shifted features:")
report.append(shift.head(15).to_string(float_format=lambda x: f"{x:.2f}"))
report.append(f"features with |d| > 0.8 (large shift): {(shift > 0.8).sum()} / {len(FEATS)}")

# --- 4. label signal within each source ------------------------------------
report.append("\n== 4. Label signal: |Cohen's d| event vs baseline, within source ==")
sig_ved = pd.Series({f: abs(cohens_d(ved[ved.label == 1][f], v0[f])) for f in FEATS})
sig_daf = pd.Series({f: abs(cohens_d(daf[daf.label == 1][f], d0[f])) for f in FEATS})
cmp = pd.DataFrame({"ved_signal": sig_ved, "daf_signal": sig_daf, "source_shift": shift})
cmp = cmp.sort_values("ved_signal", ascending=False)
report.append("Top 15 by VED signal:")
report.append(cmp.head(15).to_string(float_format=lambda x: f"{x:.2f}"))
report.append(f"\ncorr(ved_signal, daf_signal) across features: "
              f"{cmp.ved_signal.cmp.daf_signal.corr() if False else cmp['ved_signal'].corr(cmp['daf_signal']):.3f}")

# --- 5. safe features: signal in both sources, low shift -------------------
report.append("\n== 5. Candidate 'safe' features ==")
safe = cmp[(cmp.ved_signal > 0.3) & (cmp.daf_signal > 0.3) & (cmp.source_shift < 0.5)]
report.append(f"signal>0.3 in both sources AND shift<0.5: {len(safe)} features")
report.append(safe.sort_values("ved_signal", ascending=False).to_string(
    float_format=lambda x: f"{x:.2f}"))

# --- 6. redundancy -----------------------------------------------------------
report.append("\n== 6. Redundancy (VED, abs Pearson > 0.95) ==")
c = ved[FEATS].corr().abs()
iu = np.triu_indices(len(FEATS), 1)
pairs = [(FEATS[i], FEATS[j]) for i, j in zip(*iu) if c.iloc[i, j] > 0.95]
report.append(f"pairs with |r|>0.95: {len(pairs)} (of {len(FEATS)*(len(FEATS)-1)//2})")
report.append(f"features involved in >=1 such pair: {len(set(sum(pairs, ())))}")

text = "\n".join(report)
print(text)
(OUT / "eda_report.txt").write_text(text)
cmp.to_csv(OUT / "feature_signal_vs_shift.csv")
