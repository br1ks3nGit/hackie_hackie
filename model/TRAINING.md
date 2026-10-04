# Model training notes and retraining plan

Single record of findings on the model's features, assumptions, and training. Evidence tags:
`file:line`, "per REPORT.md" (only the report says it), "not verified". Written 2026-10-04.

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

Inspected 2026-10-04 on this Mac (read-only). Data is gitignored (`model/data/external/`, plus its
own `.gitignore` of `*`). Each folder has `SOURCE.md` and `MANIFEST.sha256`.

### Mendeley 9vr83n7z5j v2 (CC BY 4.0, DOI 10.17632/9vr83n7z5j.2)
- Download: `https://data.mendeley.com/public-api/zip/9vr83n7z5j/download/2`, 24.9 MB zip of 20 rar
  (publisher sha256 of all 20 verified); 418 MB extracted to `mendeley_9vr83n7z5j_v2/rar_x/`
  (bsdtar reads rar). No login or consent needed.
- Layout: `Day-{1..7}{S,R,E}` (2020-05-23..30, one folder per drive; 16 distinct incl. `Day-3E`,
  `Day-4E1..E3`), `Driver-1..7` (2021-02-02..04) and `Daywise data.rar`, which duplicates the
  Day-* folders (md5-identical CSVs, 12 of 16) and adds `Day-3E`, `Day-4E1-3`. Each folder:
  `Accelerometer.csv`, `Gyroscope.csv`, plus `GPS.csv` (0 bytes in every Day folder),
  `Proximity.csv` (Day) or `Pressure.csv` (Driver, all zeros in the head), some `.xlsx` copies.
- Schema Day: `Timestamp,Milliseconds,X,Y,Z`; Driver: `Timestamp,Unix Timestamp,Milliseconds,X,Y,Z`.
  `Timestamp` has minute (Driver) or second resolution; `Milliseconds` is elapsed ms since start.
- Pairs with acc and gyro >1000 rows: 19 = 9 Day + 3 Day-E + 7 Driver. Missing
  gyro: `Day-2R`, `Day-6R`. Truncated: `Day-3R` (463 rows), `Day-4E1` (1 row), `Driver-2` (12 s).
  `Day-1S` gyro has 8,731 rows vs 103,252 acc. `Day-4S`/`Day-4E2` gyro has a stray trailing row
  (NaN) and a row count unlike acc (296,402 / 132,550 vs 99,576 / 158,863).
- BIGGEST ISSUE, frozen sensor: the recording is live only for roughly the first minute, then the
  last value repeats. Day-1R: 88,332 of 94,627 acc rows (93%) equal the previous row, one run of
  883 s; per-minute share of changing rows: minute 0 = 1.00, minute 1 = 0.10, then ~0.00 with a
  brief burst near minute 15. Same in every Day folder (frozen 75-98%) and Driver folders (68-93%;
  Driver-1: minute 0 = 1.00, minute 1 = 0.32, then 0.00). Timestamps keep advancing, so a naive
  load looks like a complete 16-min trip. Live time (non-frozen intervals) is 63-72 s per Day
  folder, 122-178 s per Driver folder (`Driver-2` 12 s), 26 min in total across the 19 pairs
  versus about 302 min nominal. The live segment is the start of the drive, so the labelled
  behaviour may not be in it (not verifiable: no label annotations).
- Sampling (live rows only): Day acc and gyro median dt 10 ms, p95 11 ms, so 100 Hz, not the
  stated 50 Hz; Driver median 10 ms, p95 45 ms (bursty, ~25 Hz effective). Gaps > 100 ms in live
  data: 1 in `Day-1S` (12.2 s), 1 in `Day-4E2` (0.27 s), none elsewhere. Whole-file maximum gap
  (acc) was `Driver-3` 5.7 s (the only 100 ms+ gap in Driver files).
- Duplicate timestamps: 68-99% of rows in Day files (Day-1R 87,415 acc rows with dt = 0), from
  the frozen repeat; none in live data. No NaN in acc; no non-monotonic time anywhere.
- Units: |acc| median over live rows 9.6-10.6 (Day), 9.6-10.0 (Driver), i.e. m/s^2, not g.
  Gyro: no declared sign or unit check possible; live norm median 0.004-0.10 and p99 0.5-1.2
  (Driver; 2.2-3.3 in Day, handling noise at start) is consistent with rad/s and not with
  the stated deg/s (a car turning at 20 deg/s would show 20). Not proven (no labelled turns).
- Orientation: gravity is on Z (mean live acc about (-1..2, -3..1, 9.4-9.8), tilt up to ~19 deg
  from Z), the phone is not vehicle-aligned and the mount differs per drive. Stable within the live
  minute (per-minute mean direction within 8 deg of trip mean in Day, 3-7 deg in Driver);
  stability over the frozen part cannot be assessed. Mount type is not stated.
- Clipping: acc max |axis| = 19.7 in all Day folders (about 2 g sensor range), 4 rows in
  `Day-5S` at >= 19.6; Driver phones reach 28 (no saturation).
- Labels: NONE in the data. No label column, no label file, no per-trip metadata. The dataset page
  says normal / aggressive / risky but not which folder is which. Folder suffixes `S`, `R`, `E`
  (counts: 7 S, 5 R, 4 E incl. `Day-4E1-3`) and the `Driver-N` folders have no documented
  mapping. Guess "S = safe/normal, R = risky, E = extreme/aggressive" is NOT verified.
  Class balance is therefore unknown. Needs the author (or dataset paper) before any use.

### Ferreira 2017 (no licence stated: internal evaluation only)
- Clone depth 1, commit `b65118d794432a559932a4f58b9b6dd612f0bb22`, 97 MB (`ferreira_2017/data/{16,17,20,21}`).
- Per trip 6 files: `acelerometro_terra.csv`, `aceleracaoLinear_terra.csv`, `giroscopio_terra.csv`,
  `campoMagnetico_terra.csv` (`timestamp,uptimeNanos,x,y,z`), `groundTruth.csv`
  (`evento, inicio, fim`, header has spaces), `viagem.json`. "terra" = earth frame, not device.
- Trips: 16 = 1269 s (64,645 rows), 17 = 406 s (20,675), 20 = 589 s (30,014), 21 = 809 s
  (41,178); total 51 min. Acc, linear acc and gyro share the same timestamps.
- Sampling: acc, linear, gyro 50.9 Hz, dt median 19.6 ms, p95 20 ms, max 40 ms, no gaps > 100 ms,
  no duplicates, no NaN, monotonic. Magnetometer is 101.7 Hz with every timestamp duplicated.
- Units: acc z mean 9.65-9.74 m/s^2, |acc| median 9.64-9.78, so m/s^2. Linear acc has gravity
  removed (mean z -0.07..-0.16). Gyro |w| median 0.05-0.15, p99 0.6-0.9, max 2.3 and yaw peaks
  +-1.1..1.5 in turns: rad/s.
- Orientation: z is up (gravity); x, y are horizontal earth-frame axes (means 0), so braking or
  turning does not map to a fixed vehicle axis (per-event peak x/y sign flips with heading).
  Gravity direction constant (per-minute mean direction within 0.83 deg). Only gz (yaw rate) and
  horizontal magnitude are vehicle-independent.
- Labels (`groundTruth.csv`): 69 events, 7 types: `evento_nao_agressivo` 14, `freada_agressiva`
  12, `aceleracao_agressiva` 12, `curva_direita_agressiva` 11, `curva_esquerda_agressiva` 11,
  `troca_faixa_direita_agressiva` 5, `troca_faixa_esquerda_agressiva` 4. (README list omits
  `aceleracao_agressiva`.) Duration 1.6-4.9 s, median ~3 s; events cover ~3.5 min of 51 min.
  Unlabelled time is not "normal": only 14 explicit non-aggressive events. Trip 21 file is not
  sorted by `inicio` (one overlap).
- Time alignment (checked trip 20 end to end): event seconds are elapsed since
  `viagem.json` `firstCollectionUptimeNanos`; `t = (uptimeNanos - first) / 1e9`. All 12 aggressive
  turns have their peak |gz| inside [inicio, fim] (e.g. 9.5-12.5 s right turn peaks at 10.4 s,
  gz -1.2; left turns +0.9..1.5), and 11 of 12 exceed the +-6 s surroundings. The wall-clock
  `timestamp` column has 1 s resolution; use `uptimeNanos`.

## 6. Retraining plan

1. Fix saturation: floor scaler scales (e.g. max(scale, small epsilon relative to feature range)),
   and drop degenerate features (`mag_min` first). Add a test that no feature of a phone-like window
   gives |z| above a bound.
2. Orientation-invariant features: horizontal magnitude, gravity-aligned vertical component;
   optional vehicle-frame rotation from gravity (mean accel) + PCA of horizontal plane, or GPS.
3. Add gyroscope (yaw rate, gravity-aligned) and GPS speed context as inputs (needs a new
   input contract: the backend already has gx/gy/gz and speed, signal.py:18, loading.py:62).
4. Units: convert accel to g per dataset (both m/s^2). Gyro is rad/s in Ferreira and, by the data, in
   Mendeley (not deg/s as the page says). Mendeley is blocked until labels and frozen data are resolved (section 5).
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
- Page claims accel m/s^2, gyro deg/s, 50 Hz, per-trip labels normal / aggressive / risky. Files
  contradict: 100 Hz, gyro looks rad/s, no labels in the data (section 5).

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
