# Remade model — final report (2026-10-03)

## Final artifact: `model.json`

Logistic regression, robust (median/IQR) scaling, Platt calibration, 80 features
(all 106 minus every `az_*` feature and the two constant ones). Pure-JSON serving:
no pickle, no xgboost, no sklearn at inference.

- **IN:** 250 rows `ax/ay/az` in g @ 50 Hz (ts_ms 20 ms grid). Same contract as frozen.
- **OUT:** `risk_score` in [0,1] per 5 s window. Threshold 0.5.
- Fit on VED train only; scaler on train; Platt on calibration cohort;
  feature set + C selected on stopping partition AUC. VED test scored once after freezing.

## Numbers (VED held-out test, threshold 0.5)

| model | AUC | F1 | acc | FPR |
|---|---|---|---|---|
| frozen XGBoost @106 (reference) | 0.9846 | 0.9312 | 0.9318 | 5.9% |
| **remade logreg @no_az (shipped)** | 0.9559 | 0.8922 | 0.8936 | 9.3% |
| remade logreg @safe_plus_mag (fallback) | 0.8503 | 0.7638 | 0.7684 | 21.2% |

Overfit gap (train vs test AUC): 0.0047 — negligible. Partition barriers re-verified:
all 10 partition pairs disjoint on cars and base windows. Their 10/10 leakage regression
tests pass in my env. Their frozen score reproduces to 2e-4 (library version drift only).

## DAF removed from consideration (2026-10-03)

Proof: (1) 63% of DAF windows (3,712/5,868) come from experiments sampled at 5-14 Hz
(200 ms / 70 ms phones) upsampled to 50 Hz via zero-order hold — spectral features on
them are resampling artifacts. (2) DAF is a driver-fingerprinting collection: 430 min,
2 drivers, one fixed night route; never driving-behavior data. (3) Mechanically clean
(no duplicates/degenerates/overlap) — unrepresentative, not corrupt.

**All DAF-based metrics are retracted for both models** — the frozen model's 50% FPR
indictment and the remade model's DAF AUC/FPR claims were both measured on this set.

## Why not the frozen XGBoost, despite higher VED AUC

VED's vertical axis is synthetic zeros; a real phone has gravity and arbitrary
orientation. The frozen model relies on 36 `az_*` features trained on that synthetic
axis, so it cannot score phone windows correctly no matter its VED numbers. `no_az`
removes that entire failure class by construction. Logreg over trees: servable as
pure JSON, and every tree ensemble tested overfit source-specific thresholds.

## Honest remaining risks

- Labels are synthetic injected pulses vs assumed-normal baselines; not validated
  risky-driving labels. The frozen threshold 0.5 is calibrated at artificial 50%
  prevalence; at real-world 1-5% event prevalence, per-window precision is low —
  trip-level aggregation (mean/share of window scores) is required before pricing.
- No valid phone-sensor validation set exists right now. **Next step: score our own
  recorded trips (Sensor Logger / app) and re-baseline.** Until then, treat
  `risk_score` as a demo signal, not a verified risk measure.
- `safe_plus_mag` (20 features) remains the fallback if real phone data later shows
  the ax/ay percentile ladders transfer poorly.
