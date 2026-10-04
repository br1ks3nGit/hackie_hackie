# Model training notes and retraining plan

Single record of findings on the model's features, assumptions, and training. Evidence tags:
`file:line`, "per REPORT.md" (only the report says it), "not verified".
Written 2026-10-04 on branch feat/model-retrain.

## 1. Current model

| Item | Value | Evidence |
|---|---|---|
| Type | Logistic regression, robust (median/IQR) scaler, Platt calibration | model.json `model_type`, `scaler.type`, `calibration.type` |
| Input | 250 x (ax, ay, az) in g, 50 Hz (5 s window) | model/remade_model/serve.py:23-24, backend/app/window_model.py:23-24 |
| Preprocessing | 4th-order 0.5 Hz high-pass per axis (removes gravity) inside the model | window_model.py:40-45, 140 |
| Features | 80 (106 minus 24 az_* minus 2 constants) | model.json `feature_names` (len 80); recomputed: 106 extracted, 24 az_*, extras `mag_zcr`, `mag_dom_freq` |
| Output | risk_score in [0,1] per window, threshold 0.5 | window_model.py:25, 149-155 |
| VED test | AUC 0.956, F1 0.892, FPR 9.3% | model.json `frozen_evaluation`, per REPORT.md |

Backend use:
- `MODEL_KIND=window` switches scoring to the window model (backend/app/pipeline/process.py:80-86).
- The IMU is resampled to 50 Hz, then the raw (gravity-included) grid goes to the model
  (process.py:117-118); non-overlapping 250-sample windows, short tail dropped (window_model.py:200-204).
- Trip confidence = share of windows with risk > 0.5 (window_model.py:207-209, 229).
- score = round(100 * (1 - confidence)) (backend/app/model.py:121-123); tier from score (model.py:126+).
- No full window: falls back to the placeholder model (process.py:85-87).

## 2. Features (80, from model.json)

| Group | Names | Count |
|---|---|---|
| Time stats, per axis ax, ay, mag | mean, std, max, min, range, rms, skew, kurt, mad, zcr (mag has no zcr) | 10+10+9 |
| Percentiles, per axis ax, ay, mag | p10, p25, p50, p75, p90 | 15 |
| Jerk, per axis ax, ay, mag | jerk mean, std, max, min, rms | 15 |
| Frequency, ax, ay | dom_freq, spec_entropy, spec_centroid, low_energy_ratio | 8 |
| Frequency, mag | spec_entropy, spec_centroid, low_energy_ratio (no dom_freq) | 3 |
| Event counts | event_hard_brake, rapid_accel, sharp_left, sharp_right, any (fixed g thresholds -0.25 / 0.25 / 0.20) | 5 |
| Cross-axis | ax_ay_corr, ax_az_corr, ay_az_corr | 3 |
| Magnitude summary | mag_energy, mag_peak_count | 2 |

Total 80 (counted from the list; the group counts above sum to 80).

Removed from the original 106:
- All 24 `az_*` features (time, percentile, jerk, frequency; the report says "36 az_* features"
  for the frozen model, which counts az-derived items including cross terms; not verified
  against the frozen snapshot, which is not in the repo). Reason: VED's vertical axis is
  synthetic zeros, so any az_* feature learns a synthetic axis (per REPORT.md).
- Two constants: `mag_zcr` and `mag_dom_freq` (recomputed: extracted but absent from model.json).
  Why they were constant: not verified.
- Still in the model although az-dependent: `mag_*` (uses az), `ax_az_corr`, `ay_az_corr`.

## 3. Findings

### Saturation (verified by running serve.py)
- Scaler scale for `mag_min` = 5.683683233499104e-18 (model.json `scaler.scale`). It is the only
  feature with scale < 1e-3 (checked all 80; so also the only one < 1e-6).
- Cause: VED has az = 0, so with high-passed data the magnitude minimum is ~0 in training with
  almost no spread (inference from the scale; not verified in VED data).
- On a phone, az carries gravity and noise; `mag_min` differs from the training median by a tiny
  absolute amount, which divided by 5.7e-18 gives a z-score of 1e15+, times its coef: logit ~ -400,
  risk ~0, every trip scores 100 / tier A. Logit ~ -400 per the wiring analysis on its test window; not
  re-measured here.
- Hand demo (my run, serve.predict, seed 0, noise std 0.02 g, 0.9 g pulse on ax for 5 samples):
  az = 0 gives risk 0.00062; az = 1 gives risk 1.1e-192. (The brief quoted 0.98 vs ~1e-186 for
  the pulse window; my synthetic window gave different numbers, same direction: az = 1 collapses
  the score by ~190 orders of magnitude.)

### Labels
- Synthetic injected pulses vs assumed-normal baselines; not validated risky-driving labels (per REPORT.md).
- 50% prevalence is artificial (per REPORT.md).
- Per-window precision at realistic prevalence (TPR 0.948 / FPR 0.214 measured on DAF, which was
  later retracted): 1% -> 0.043, 5% -> 0.189 (model/remade_model/stress_test.txt). Report says
  4-19% for 1-5%. Caveat: the DAF-based inputs are retracted, so treat as indicative only.

### Training data
- VED: vertical axis is synthetic zeros; not phone data (per REPORT.md).
- DAF excluded: 63% of windows from 5-14 Hz sources upsampled to 50 Hz; 2 drivers, one night
  route (per REPORT.md). All DAF-based metrics retracted.
- No valid phone-sensor validation set exists yet (per REPORT.md).
- Snapshot (old frozen XGBoost + data) lives on k-pro at
  `~/Sites/drivescore-model-backup/model/snapshots/bolttech_boosting_snapshot_2026-10-03/`.
  model/README.md says `~/Documents/drivescore-model-backup/`; that path is wrong (location given
  by the team; not checkable from this machine).
- `model/data/` is gitignored (.gitignore:37), and does not exist in this checkout.

## 4. Assumptions

| Assumption | Status | Evidence |
|---|---|---|
| Accelerometer is in g on Android | verified | expo-sensors AccelerometerModule.kt:19-21 divides by GRAVITY_EARTH |
| Accelerometer is in g on iOS | verified | AccelerometerModule.swift:30-36 passes CoreMotion `acceleration` (g) unchanged |
| App samples at 50 Hz | requested only | SensorManager.ts:25 `setUpdateInterval(20)`; delivered rate not measured |
| Timestamps jittery, backend resamples to 50 Hz | verified | app stamps `Date.now()` at JS callback (SensorManager.ts:28-30); linear `np.interp` resample, signal.py:6-22 |
| Phone orientation is arbitrary | assumed true | no mount constraint in app (not verified in UX) |
| Backend rotates raw accel to vehicle frame | wrong (it does not) | `_remove_gravity` is per device axis (signal.py:25-36); "car frame" only from GPS dv/dt and gz*speed (signal.py:39-71). Window model gets grid_imu before that (process.py:118) |
| Model input contains gravity and high-passes internally | verified | process.py:118; window_model.py:140 |
| Model trained with az = 0 | wrong for phones | per REPORT.md (VED synthetic zeros); demo in section 3 |
| Higher confidence = riskier | verified | model.py:121-123 |
| GPS used for speed only | verified | loading.py:62-63 ("Speed is the only GPS signal kept") |
| Gyro used by the window model | no, not used | window_model.py uses ax/ay/az only (split_windows :202) |

## 5. New data

Status: downloading on k-pro; inspection pending (k-pro unreachable at time of writing).
Data is gitignored (`model/data/`).

### Mendeley 9vr83n7z5j v2
- CC BY 4.0, DOI 10.17632/9vr83n7z5j.2. Accel m/s^2, gyro deg/s, 50 Hz, per-trip labels
  normal / aggressive / risky, mounting not stated (all from the dataset page; not verified here).
- Location on k-pro: `~/Sites/hackathon-type-shi/model/data/external/mendeley_9vr83n7z5j_v2/`.
- INSPECTION PLACEHOLDER: file list, drivers/trips count, label counts, real sample rate,
  gravity present?, axis conventions, mounting, gaps/duplicates. TODO.

### Ferreira 2017
- No licence stated: internal evaluation only; never commit or ship. Per-event labels with
  start/end seconds, 69 events, windshield mount, accel m/s^2, gyro rad/s (not verified here).
- Location on k-pro: `~/Sites/hackathon-type-shi/model/data/external/ferreira_2017/`.
- INSPECTION PLACEHOLDER: files, sensors, sample rate, event types and counts, axis
  conventions, trip/driver split. TODO.

## 6. Retraining plan

1. Fix saturation: floor scaler scales (e.g. max(scale, small epsilon relative to feature range)),
   and drop degenerate features (`mag_min` first). Add a test that no feature of a phone-like window
   gives |z| above a bound.
2. Orientation-invariant features: horizontal magnitude, gravity-aligned vertical component;
   optional vehicle-frame rotation from gravity (mean accel) + PCA of horizontal plane, or GPS.
3. Add gyroscope (yaw rate, gravity-aligned) and GPS speed context as inputs (needs a new
   input contract: the backend already has gx/gy/gz and speed, signal.py:18, loading.py:62).
4. Units: convert accel to g and gyro to rad/s per dataset (Mendeley m/s^2 and deg/s, Ferreira m/s^2 and rad/s).
5. Train on VED + Mendeley; evaluate per-trip on held-out Mendeley drivers and per-event on
   Ferreira (internal only).
6. Recalibrate threshold and Platt for realistic prevalence (1-5%); keep trip-level aggregation.
7. Keep logreg + JSON serving (no pickle); keep window_model.py validation compatible.
8. Leakage rules: split by driver, then trip; windows never cross a split; scaler, feature
   selection, C, and Platt fit on train / calibration partitions only; test scored once.
9. Acceptance:
   - No saturation: phone-like windows (gravity present, any orientation) produce finite,
     non-degenerate logits (no |logit| > ~20 from scaler blow-up).
   - Beats the placeholder model on held-out Mendeley trips (per-trip AUC, same split).
   - Orientation test: rotating a window arbitrarily changes risk by less than a set tolerance.

## 7. Licences and citations

All details below: per official dataset page, checked 2026-10-04.

### Mendeley
- "Driver Behavior Detection Using Smartphone - Dataset", author Pawan Wawage. Version 2 published
  2022-01-28 (v1 2021-05-18). DOI 10.17632/9vr83n7z5j.2. Page: https://data.mendeley.com/datasets/9vr83n7z5j/2
- Licence CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Attribution text:
  "Wawage, Pawan (2022), Driver Behavior Detection Using Smartphone - Dataset, Mendeley Data, V2,
  doi: 10.17632/9vr83n7z5j.2", licensed under CC BY 4.0. Indicate any changes made.
- Accel m/s^2, gyro deg/s, 50 Hz; per-trip labels normal / aggressive / risky; mounting and label
  method not stated.

### Ferreira 2017
- Ferreira J Junior, Carvalho E, Ferreira BV, de Souza C, Suhara Y, Pentland A, et al. (2017)
  Driver behavior profiling: An investigation with different smartphone sensors and machine
  learning. PLoS ONE 12(4): e0174959. https://doi.org/10.1371/journal.pone.0174959
- Data repo https://github.com/jair-jr/driverBehaviorDataset has no LICENSE file (404) and no
  licence statement. PLOS Data Availability points to the repo. The article is CC BY, but that does
  not license the data.
- Phone fixed on the windshield; 4 trips, 69 events (braking 12, acceleration 12, left/right turn
  11/11, left/right lane change 4/5, non-aggressive 14) with start/end seconds in groundTruth.csv;
  accel m/s^2, gyro rad/s.
- Use for internal evaluation only: do not commit, redistribute, or ship models derived solely from it.
