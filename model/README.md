# Model

Risk model for driving windows: 250 accelerometer samples (5 s @ 50 Hz, g units) in,
calibrated risk score out. Full write-up: `remade_model/REPORT.md`.

## Ship this: `remade_model/`
- `model.json` - the model: logistic regression, 80 features (all except az_* and 2
  constants), robust scaler + Platt calibration. VED test: AUC 0.956, F1 0.892,
  FPR 9.3%, overfit gap 0.005.
- `serve.py` - self-contained serving (numpy/pandas/scipy only, no xgboost/sklearn):
  gravity removal + feature extraction vendored from the original training pipeline,
  scoring math from model.json. `python serve.py window.csv` scores a CSV,
  `python serve.py --selftest` verifies against `expected_score.json`.
- `example_window.csv` / `expected_score.json` - selftest fixture.
- `REPORT.md` - comparison vs the old frozen XGBoost, stress tests, DAF removal verdict.

## Contract
IN: exactly 250 rows of `ax, ay, az` in g @ 50 Hz (optional `ts_ms`).
OUT: `{risk_score, uncalibrated_score, label, score_semantics}`, threshold 0.5.
Backend integration: slice cleaned 50 Hz IMU into 250-sample windows, score each via
serve.py's predict(), aggregate to a trip confidence.

## Analysis scripts (root of this folder)
`eda.py`, `remake.py`, `baseline_experiment.py`, `stress_test.py` + outputs in `eda/`
and `baseline_results.csv`. These document how the model was rebuilt. They read the
teammate snapshot, which is no longer in the repo; restore it from
`~/Documents/drivescore-model-backup/` or git branch `KA1` to re-run them.

## Note
The old frozen XGBoost snapshot was removed from the repo on 2026-10-04 (it scores
real phone data at coin-flip quality; backup kept locally). Two CSVs later found in
its data folder were evaluated and deleted as not trainable: `accelerometer.csv`
(unlabeled parameter sweep, no timestamps) and `mobile_accelerometer_car_12K.csv`
(sorted-by-class 2-block file, 23% duplicate rows, no timestamps - no leakage-safe
split possible).
