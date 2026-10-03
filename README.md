# DriveScore

Usage-based car insurance proof of concept for the bolttech hackathon (Hong Kong).

DriveScore turns phone sensor data into a driving-risk score, and the score into a premium
multiplier. This repository holds the FastAPI + PostgreSQL backend (ingestion, signal
processing, model hook, reports) and the Expo / React Native app that records trips.

Contents: [What it is](#1-what-it-is) | [How it works](#2-how-it-works) |
[Repository layout](#3-repository-layout) | [Tech stack](#4-tech-stack) |
[Quick start](#5-quick-start) | [API overview](#6-api-overview) |
[Processing pipeline](#7-processing-pipeline) | [Scoring](#8-scoring) |
[Data model](#9-data-model) | [Privacy](#10-privacy-pdpo) | [Development](#11-development) |
[Limitations](#12-assumptions-and-known-limitations) | [Roadmap](#13-roadmap) | [Team](#14-team)

## 1. What it is

Built for the bolttech hackathon track in Hong Kong: a usage-based insurance (UBI) POC where
premiums follow how a person actually drives rather than who they are.

**Pitch.** A driver installs the app and consents once. From then on the phone records
accelerometer, gyroscope and GPS during trips and uploads them in small chunks. The backend
removes noise, works out whether the person was driving (and not riding the MTR or a bus),
detects harsh braking, harsh acceleration, sharp cornering, speeding and possible crashes,
and turns each trip into features for a risk model. Trip scores roll up into a
distance-weighted 90-day driver score, which maps to a tier (A to E) and a premium
multiplier between 0.80 and 1.30. The driver sees their score and trip explanations in the
app; the insurer sees drivers by anonymous id with tier, multiplier and event rates. No
protected attributes (age, gender, etc.) are used, and a driver can delete all their data.

Status: the backend API, pipeline, classification, scoring and a minimal mobile app work end
to end against synthetic and real sensor data. The whole stack (API + PostgreSQL) runs with
`docker compose up`. The insurer web dashboard is planned but not built yet (see
[Roadmap](#13-roadmap)); today the insurer views are API endpoints only.

## 2. How it works

```
 Phone (Expo app)
 accelerometer 50 Hz, gyroscope 50 Hz, GPS 1 Hz, (car Bluetooth flag)
        |
        |  POST /v1/trips/start            (needs prior consent)
        |  POST /v1/trips/{id}/chunks      (~60 s chunks, idempotent by seq)
        |  POST /v1/trips/{id}/end         (only after last chunk acknowledged)
        v
 +----------------------+      raw chunks, gzip JSON, one file per chunk
 | FastAPI (sync)       |----> data/raw/<trip_id>/<seq>.json.gz
 | ingestion router     |      + trip, trip_chunks rows in PostgreSQL
 +----------+-----------+
            |  BackgroundTasks (thread pool): process_trip(trip_id)
            v
 +-------------------------------------------------------------------+
 | Pipeline (app/pipeline/, app/classify.py)                         |
 |  1. load chunks -> IMU / GPS tables, bluetooth ratio              |
 |  2. classify trip: transit | driver | unknown (+ driver_likelihood)|
 |       transit or passenger -> saved as done, NOT scored           |
 |  3. quality checks (samples, GPS gap, duration, distance)         |
 |  4. resample 50 Hz -> remove gravity -> car frame -> low-pass     |
 |  5. detect events: harsh_brake / harsh_accel / sharp_corner /     |
 |     speeding                                                      |
 |  6. detect crash -> Incident row (needs driver confirmation)      |
 |  7. build features (FEATURE_ORDER vector + route)                 |
 +-------------------------------+-----------------------------------+
                                 v
                  app/model.py predict(features)
                  placeholder rules  OR  models/model.pkl
                                 v
              confidence (0..1) -> score (0..100) -> tier A..E
                                 |
                                 v
        PostgreSQL: events, trip_features, trip_scores, incidents
                                 |
              +------------------+--------------------+
              v                                       v
   Driver app (X-API-Key = driver)          Insurer views (X-API-Key = insurer)
   GET /v1/me/summary  (score, tier,        GET /v1/insurer/overview
       premium multiplier, trend)           GET /v1/insurer/drivers
   GET /v1/me/trips, /v1/me/trips/{id}      GET /v1/insurer/drivers/{driver_id}
   label trips, confirm incidents           POST /v1/trips/{id}/reprocess
```

Trip lifecycle (`trips.status`): `uploading` -> `processing` -> `done` or `failed`
(`failure_reason` explains quality-check failures). The app polls
`GET /v1/trips/{id}/status` after ending a trip.

## 3. Repository layout

```
.
|-- README.md                    this file (main entry point)
|-- docker-compose.yml           services: db (PostgreSQL 16, creates drivescore_test) and api
|-- .github/workflows/ci.yml     CI: ruff format/check, ty, pytest on Postgres
|-- docs/
|   |-- roadmap.md               phased plan, one line = one small PR
|   |-- data-model.md            detailed data model: ER diagram, tables, allowed values
|   `-- handoff.md               older team handoff guide (stale, see limitations)
|-- contracts/                   older hand-written API contract (stale, replaced by OpenAPI)
|-- backend/                     FastAPI service (see backend/README.md)
|   |-- app/
|   |   |-- main.py              app, CORS, router mounting, /health, model load on startup
|   |   |-- config.py            pydantic-settings; all env variables
|   |   |-- database.py          sync SQLAlchemy engine and session
|   |   |-- models.py            8 typed ORM tables (Mapped), with column comments
|   |   |-- values.py            Literal types for allowed values (status, tier, ...)
|   |   |-- schemas.py           API contract: Pydantic models with field docs (see /docs)
|   |   |-- features.py          TripFeatures: feature contract with the model team
|   |   |-- auth.py              API key hashing, driver and insurer dependencies
|   |   |-- pipeline/            loading + quality checks, signal, events + crash, feature_calc,
|   |   |                        process (process_trip)
|   |   |-- services/scoring.py  driver score, scoreable trips, passenger stats, explanations
|   |   |-- classify.py          transit / driver / unknown classification
|   |   |-- model.py             model plug-in point, FEATURE_ORDER, score/tier/multiplier
|   |   `-- routers/
|   |       |-- ingestion.py     register, consent, trip start / chunks / end / status
|   |       |-- driver.py        /me summary, trips, trip detail, labelling
|   |       |-- insurer.py       /insurer overview, drivers, driver detail
|   |       |-- incidents.py     /me/incidents create, confirm, list
|   |       `-- admin.py         reprocess a trip, delete my data
|   |-- Dockerfile               API image (uv, non-root user)
|   |-- migrations/              Alembic env + versions/ (0001-0004)
|   |-- scripts/                 seed.py, simulate.py, export_openapi.py
|   |-- data/transit_lines.geojson   HK transit lines for classification
|   |-- data/raw/                raw sensor chunks at runtime (gitignored)
|   |-- contract/openapi.json    exported OpenAPI contract (+ examples/)
|   |-- docker/initdb.sql        creates the drivescore_test database on first start
|   |-- docker/entrypoint.sh     API container start: alembic upgrade head, then uvicorn
|   |-- tests/                   pytest suite (Postgres)
|   |-- conftest.py              test DB safety check, migrations, per-test truncate
|   |-- pyproject.toml, uv.lock  dependencies and tool config (uv)
|   `-- .env.example             environment template
`-- mobile/                      Expo / React Native app
    |-- App.tsx                  single screen: register, record, score, last trip
    |-- app.json                 permissions (location, motion, background)
    `-- src/
        |-- api/client.ts        typed API client (API_BASE is hardcoded)
        |-- sensors/SensorManager.ts   accelerometer / gyroscope / GPS subscriptions
        |-- sensors/TripDetector.ts    trip start/end by speed, chunking and upload
        |-- storage/TripStorage.ts     AsyncStorage helpers (not wired into App.tsx)
        `-- types.ts             sensor sample types (some legacy types are unused)
```

## 4. Tech stack

| Area | Choice | Version |
|---|---|---|
| Language | Python | >=3.12, <3.13 |
| Web framework | FastAPI (sync handlers) + uvicorn | 0.115.0, 0.31.0 |
| Validation / settings | Pydantic, pydantic-settings | 2.9.0, 2.5.0 |
| Database | PostgreSQL (Docker image `postgres:16`) | 16 |
| ORM / driver | SQLAlchemy (sync), psycopg 3 | 2.0.35, >=3.3.6 |
| Migrations | Alembic | 1.13.0 |
| Signal processing | numpy, pandas, scipy | 1.26.4, 2.2.3, 1.13.1 |
| Model | pluggable pickle (scikit-learn style), placeholder rules by default | n/a |
| Mobile | Expo SDK ~51, React Native 0.74.0, React 18.2.0, TypeScript ~5.3.3 | see `mobile/package.json` |
| Mobile libs | expo-sensors ~13.0, expo-location ~17.0, expo-notifications ~0.28, async-storage 1.23.1, react-native-maps 1.14.0 | |
| Package manager | uv (backend), npm (mobile) | |
| Lint / format / types | ruff, ty (ruff line length 100) | latest via `uv.lock` |
| Tests | pytest 8.4.2, httpx 0.27.0, pytest-asyncio 0.24.0 | |
| CI | GitHub Actions: ruff format --check, ruff check, ty check, pytest | Postgres 16 service |

Note: `expo-notifications` and `react-native-maps` are installed but not used by the current
screen.

## 5. Quick start

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 for you)
- Docker (for PostgreSQL)
- Node.js and npm (mobile app only), and Expo Go or a simulator

### Option A: everything in Docker

Needs Docker only (no local Python).

```bash
# from the repo root; compose refuses to start `api` if either key is unset
export INSURER_API_KEY=change-me DRIVER_API_KEY_SALT=change-me-too   # or put both in a root .env
docker compose up -d --build

# demo data (the script targets http://localhost:8000, valid inside the container)
docker compose exec api python scripts/seed.py
```

The `api` container waits for a healthy `db`, runs `alembic upgrade head` (see
`backend/docker/entrypoint.sh`), then serves on `0.0.0.0:8000`. Check it with
`curl localhost:8000/health` and `docker compose logs api`. Raw chunks live in the `rawdata`
volume (`/data/raw`); put a trained `model.pkl` in the `models` volume (`/models`), otherwise
the placeholder rules are used. Phones on the same network reach the API at
`http://<laptop LAN IP>:8000` (see [Mobile app](#mobile-app)).

### Option B: local dev (compose db + uv)

```bash
# 1. PostgreSQL only (from the repo root); also creates the drivescore_test database
docker compose up -d db

# 2. Dependencies and environment
cd backend
uv sync
cp .env.example .env
#   edit .env: set INSURER_API_KEY and DRIVER_API_KEY_SALT (see table below), and set
#   DATABASE_URL=postgresql+psycopg://drivescore:drivescore@localhost:5432/drivescore
#   TEST_DATABASE_URL=postgresql+psycopg://drivescore:drivescore@localhost:5432/drivescore_test
#   (backend/.env.example is still on SQLite: replace the DATABASE_URL line and add the
#   TEST_DATABASE_URL line; the app only works with PostgreSQL.)

# 3. Create the schema (the app does not create tables itself)
uv run alembic upgrade head

# 4. Run the API
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000/docs for the interactive API docs (field descriptions and examples
come from `app/schemas.py`) and http://localhost:8000/health for a liveness check.

`docker/initdb.sql` only runs on an empty volume. If your Postgres volume already existed,
create the test database with
`docker compose exec db createdb -U drivescore drivescore_test` (or `docker compose down -v`
to reset everything).

#### Environment variables (`backend/app/config.py`)

| Variable | Default | Meaning |
|---|---|---|
| `INSURER_API_KEY` | none, **required** | Shared secret for insurer endpoints and reprocess. The app will not start without it. |
| `DRIVER_API_KEY_SALT` | none, **required** | Salt for hashing driver API keys (SHA-256). Changing it invalidates all existing driver keys. |
| `DATABASE_URL` | `postgresql+psycopg://drivescore:drivescore@localhost:5432/drivescore` | SQLAlchemy URL of the main database. |
| `TEST_DATABASE_URL` | unset | Database used by pytest; its name must end in `_test`. |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:19006` | Comma-separated allowed origins. |
| `DATA_DIR` | `./data/raw` | Where raw gzip chunks are written (`<DATA_DIR>/<trip_id>/<seq>.json.gz`). |
| `MODEL_PATH` | `./models/model.pkl` | Optional pickled model, loaded once at startup. |
| `TRIP_MIN_DISTANCE_KM` | `1.0` | Quality check: minimum trip distance. |
| `TRIP_MAX_GPS_GAP_S` | `30.0` | Quality check: maximum gap between GPS fixes. |
| `TRIP_MIN_DURATION_S` | `60.0` | Quality check: minimum trip duration. |

### Demo data

With the API running (Option A: seed with `docker compose exec api python scripts/seed.py`;
Option B: in another terminal from `backend/`):

```bash
# Seed 30 drivers (12 calm, 10 moderate, 8 aggressive), 3 to 8 synthetic trips each.
# Takes a few minutes because every trip uploads real chunks and is processed.
uv run python scripts/seed.py

# Or generate trips yourself. Without --api-key it registers a new driver and gives consent.
uv run python scripts/simulate.py --type calm --count 2
uv run python scripts/simulate.py --type aggressive --count 3 --api-key <driver api key>
```

Both scripts (both included in the API image) talk to `http://localhost:8000/v1` (hardcoded `BASE_URL`). Simulated chunks set
`car_connected=true`, so trips classify as driver trips and are scored immediately. The
synthetic profiles are `calm`, `moderate` and `aggressive`.

Try the reports (replace the key with your `INSURER_API_KEY`):

```bash
curl -H "X-API-Key: change-me-insurer-key" http://localhost:8000/v1/insurer/overview
curl -H "X-API-Key: change-me-insurer-key" "http://localhost:8000/v1/insurer/drivers?sort=score_asc"
```

### Export the API contract

```bash
cd backend && uv run python scripts/export_openapi.py   # writes contract/openapi.json
```

### Mobile app

```bash
cd mobile
npm install
npx expo start        # or: npm run ios / npm run android
npm run ts:check      # TypeScript check
```

The app registers a driver on first launch, records consent automatically (version "1.0"),
stores the id and API key in AsyncStorage, and shows a score plus the last trip.

**API_BASE is hardcoded.** `mobile/src/api/client.ts` line 1 is
`const API_BASE = 'http://localhost:8000/v1';`. That works for a simulator on the same
machine only. On a real phone, change it to your computer's LAN address (for example
`http://192.168.1.20:8000/v1`), and make sure both devices are on the same network. The
API must listen on all interfaces: compose `api` already does (`0.0.0.0:8000`); for local
uvicorn use `--host 0.0.0.0` as above. The phone reaches the API at
`http://<laptop LAN IP>:8000`. A config-driven value is roadmap item E1.

## 6. API overview

All routes are under `/v1` except `/health`. Interactive docs at `/docs`; machine-readable
contract in `backend/contract/openapi.json`.

### Authentication model

- Everything except register and `/health` needs an `X-API-Key` header.
- **Driver key.** `POST /v1/drivers/register` returns `driver_id` and a random `api_key`
  once. Only a salted SHA-256 hash is stored. POC identity rule: **one device = one driver**;
  each install registers once and keeps its key. There is no login, logout or separate
  device model.
- **Insurer key.** A single shared secret from `INSURER_API_KEY`, compared in constant time.
- Every `/v1/me/...` and trip route is scoped to the authenticated driver (other drivers' trip
  ids return 404).

### Endpoints

| Group | Method | Path | Auth | Purpose |
|---|---|---|---|---|
| Health | GET | `/health` | none | Liveness check |
| Ingestion | POST | `/v1/drivers/register` | none | Create a driver; returns `driver_id`, `api_key` (optional emergency contact in body) |
| Ingestion | POST | `/v1/consent` | driver | Record PDPO consent (`version`) |
| Ingestion | POST | `/v1/trips/start` | driver | Open a trip, returns `trip_id`; 403 if no consent |
| Ingestion | POST | `/v1/trips/{trip_id}/chunks` | driver | Upload one IMU + GPS chunk (`seq`, `imu[]`, `gps[]`, `car_connected`); idempotent per `seq`; only while status is `uploading` |
| Ingestion | POST | `/v1/trips/{trip_id}/end` | driver | Close the trip and start background processing |
| Ingestion | GET | `/v1/trips/{trip_id}/status` | driver | `uploading`, `processing`, `done` or `failed` (+ `failure_reason`) |
| Driver reports | GET | `/v1/me/summary` | driver | 90-day score, confidence, tier, premium multiplier, trend, trip count, distance |
| Driver reports | GET | `/v1/me/trips` | driver | Trip list (`limit` 1..200, `offset`), with type, score, `needs_confirmation` |
| Driver reports | GET | `/v1/me/trips/{trip_id}` | driver | Trip detail: score, events, downsampled route (about 100 points), text explanation |
| Driver reports | POST | `/v1/me/trips/{trip_id}/label` | driver | Label a trip `driver` or `passenger` (user label wins over auto-classification) |
| Incidents | POST | `/v1/me/incidents` | driver | Create an incident (crash) from the client |
| Incidents | POST | `/v1/me/incidents/{incident_id}/confirm` | driver | Confirm as `ok`, `help_needed` or `no_response` |
| Incidents | GET | `/v1/me/incidents` | driver | Latest 50 incidents |
| Insurer | GET | `/v1/insurer/overview` | insurer | Total drivers, 90-day trip count, tier distribution, average multiplier |
| Insurer | GET | `/v1/insurer/drivers` | insurer | All drivers; filter `tier`, sort `score_desc` (default), `score_asc`, `multiplier_desc`, `multiplier_asc` |
| Insurer | GET | `/v1/insurer/drivers/{driver_id}` | insurer | Driver detail: event counts, last 20 trips, model version, passenger share, `flagged_for_review` |
| Admin | POST | `/v1/trips/{trip_id}/reprocess` | insurer | Delete events, features, score, incidents of a trip and re-run the pipeline |
| Admin | DELETE | `/v1/me` | driver | Delete all of the driver's data and raw files (PDPO erasure) |

All datetimes in responses are timezone-aware UTC and end in `Z` (for example
`2026-01-02T03:04:05Z`). Naive datetimes sent by a client are read as UTC.

Errors use FastAPI's `{"detail": "..."}` shape. 401 wrong key (422 if the `X-API-Key` header is
missing), 403 consent required, 404 unknown or foreign trip, 400 wrong trip state (for
example uploading to a trip that is no longer `uploading`).

Chunk payload (`t` is epoch milliseconds; accelerometer in g, gyroscope in rad/s):

```json
{
  "seq": 0,
  "imu": [{"t": 1760000000000, "ax": 0.0, "ay": 0.0, "az": 1.0, "gx": 0.0, "gy": 0.0, "gz": 0.0}],
  "gps": [{"t": 1760000000000, "lat": 22.28, "lon": 114.15, "speed": 8.3, "accuracy": 5.0}],
  "car_connected": true
}
```

## 7. Processing pipeline

Entry point: `process_trip(trip_id)` in `backend/app/pipeline/process.py`, run as a FastAPI
`BackgroundTasks` job after `/end`. Fixed thresholds live next to the code as named constants
or in the `CONFIG` dict in `app/classify.py`.

### 7.1 Order of operations

1. Load all chunk files; drop duplicate timestamps; sort; compute the Bluetooth ratio.
2. Classify the trip (unless the user already labelled it). Classification runs **before**
   the quality check so an underground MTR ride, which has a long GPS gap, becomes "transit"
   instead of "failed".
3. Transit and user-labelled passenger trips are stored as `done` and not scored.
4. Quality check, signal processing, events, crash detection, features, model, score.

### 7.2 Quality checks

A failed check sets the trip to `failed` with a readable `failure_reason`.

| Check | Threshold |
|---|---|
| IMU samples | at least 100 |
| GPS points | at least 10 |
| Largest GPS gap | at most `TRIP_MAX_GPS_GAP_S` (30 s) |
| Duration (IMU span) | at least `TRIP_MIN_DURATION_S` (60 s) |
| Distance (haversine over GPS) | at least `TRIP_MIN_DISTANCE_KM` (1.0 km) |

### 7.3 Signal processing

1. **Resample** IMU to 50 Hz with linear interpolation.
2. **Gravity removal** (orientation-free): subtract a centred 10 s rolling median from each of
   the six raw axes, so the phone can be mounted in any pose for this step.
3. **Car frame** (all channels in g):
   - `accel_forward` = dv/dt of GPS speed over a 2 s window, interpolated onto the IMU
     timeline, divided by 9.81
   - `accel_lateral` = gravity-free gyro `gz` (yaw rate, rad/s) x GPS speed / 9.81
   - `accel_vertical` = gravity-free `az`
4. **Low-pass**: 4th-order zero-phase Butterworth, 5 Hz cutoff, on the three car-frame
   channels to remove road vibration.

### 7.4 Events

Each event stores type, time, peak value in g (where relevant) and the nearest GPS position.
For the g-based events, one event is emitted per contiguous run above the threshold, at its
peak.

| Event type | Rule |
|---|---|
| `harsh_brake` | `accel_forward` < -0.4 g |
| `harsh_accel` | `accel_forward` > 0.3 g |
| `sharp_corner` | abs(`accel_lateral`) > 0.35 g |
| `speeding` | nearest GPS speed > 13.9 m/s (50 km/h, fixed HK urban default `SPEEDING_THRESHOLD_MS`) for a run longer than 10 s; one event per run, at the run start |

### 7.5 Crash detection

Creates an `incidents` row (`type="crash"`, `confirmed` null) with a small sensor snapshot
summary when all of the following hold for a group of samples:

1. Acceleration magnitude of the gravity-free raw axes exceeds `CRASH_PEAK_G` = 4.0 g
   (peaks within 1 s are grouped into one candidate).
2. GPS speed falls to `CRASH_STOP_SPEED_MS` = 1.0 m/s or less within
   `CRASH_STOP_WINDOW_S` = 5 s after the peak.
3. The phone then stays still: acceleration magnitude standard deviation at most 0.5 over
   the 35 s following the peak (5 s stop window + 30 s still, `CRASH_STILL_DURATION_S` = 30 s;
   at least 10 IMU samples).

The driver can then confirm the incident (`ok`, `help_needed`, `no_response`) through
`/v1/me/incidents/{id}/confirm`.

### 7.6 Trip classification (`app/classify.py`)

Evaluated in this order; the first match wins. Thresholds are in `CONFIG`.

| Order | Rule | Result |
|---|---|---|
| 1 | At least 70% of GPS points lie within 30 m of one transit line in `data/transit_lines.geojson` | `transit`, `label_source=rules`, `transit_line` = line name |
| 2 | A GPS gap longer than 30 s whose before and after points are both within 30 m of an underground line | `transit`, `transit_line="underground (GPS gap)"` |
| 3 | Fraction of chunks with `car_connected=true` is above 0.80 | `driver`, `label_source=bluetooth` |
| 4 | Otherwise | `unknown`, with `driver_likelihood` |

`driver_likelihood` = 0.3 base, plus 0.5 if the mean variance of gyro x/y/z is below 0.01
(a stable, probably mounted phone), capped at 1.0. It is informational; it does not decide
scoring.

The geojson contains 9 hand-drawn HK routes (seven MTR / rail lines, the tram and the Star
Ferry), accurate enough for a demo, not for production.

Users can override any label with `POST /v1/me/trips/{id}/label` (`driver` or `passenger`).
User labels are never overwritten by reprocessing. Labelling an unscored finished trip as
`driver` re-runs the pipeline to produce a score.

### 7.7 Features

Stored per trip in `trip_features.features` (JSON). The model sees only the ten values in
`FEATURE_ORDER` (`app/model.py`), in this exact order:

| # | Feature | Definition |
|---|---|---|
| 1 | `distance_km` | Sum of haversine distances between GPS points |
| 2 | `duration_min` | IMU time span in minutes |
| 3 | `night_driving_share` | Share of IMU samples with Hong Kong hour 23 to 05 (23:00 to 05:59) |
| 4 | `harsh_brake_per_100km` | Event count / max(distance, 0.1 km) x 100 |
| 5 | `harsh_accel_per_100km` | same |
| 6 | `sharp_corner_per_100km` | same |
| 7 | `speeding_per_100km` | same (speeding runs) |
| 8 | `mean_speed_ms` | Mean GPS speed (missing speed = 0) |
| 9 | `max_speed_ms` | Max GPS speed |
| 10 | `speeding_time_share` | Share of GPS points above 13.9 m/s |

The stored JSON also holds `events_per_100km` (dict) and a downsampled `route` (up to about
100 points), which are used by the API but are not model inputs. The pipeline validates the
computed features against the `TripFeatures` model in `app/features.py` before storing them.

## 8. Scoring

### 8.1 From confidence to premium

The model returns `confidence` in 0..1 = probability that the driver is risky.

`score = round(100 * (1 - confidence))` (100 = safest), then:

| Tier | Score | Premium multiplier |
|---|---|---|
| A | 90 to 100 | 0.80 |
| B | 75 to 89 | 0.90 |
| C | 60 to 74 | 1.00 |
| D | 40 to 59 | 1.15 |
| E | 0 to 39 | 1.30 |

### 8.2 Driver score (what the premium uses)

The premium uses the driver-level score, never a single trip:

- Window: trips created in the last 90 days with status `done` and a stored score.
- Weighting: average of trip scores weighted by each trip's `distance_km` (truncated to an
  integer); tier and multiplier come from that average.
- No eligible trips (or zero total distance): default score 60, tier C, multiplier 1.00.
- `trend`: compares the average trip score of the older half with the newer half; a
  difference over 2 points gives `improving` or `worsening`, otherwise `stable`.
- Insurer detail also reports `passenger_share` (share of transit and passenger trips) and
  sets `flagged_for_review` above 40%.

### 8.3 Which trips count

| Trip type | Counts toward the score? |
|---|---|
| `driver` (Bluetooth or user label) | Yes |
| `unknown`, labelled `driver` by the user | Yes |
| `unknown`, not labelled | No. It is still scored and shown in the app with `needs_confirmation=true`; if it stays unlabelled for 7 days (`UNCONFIRMED_EXPIRY_DAYS`) it stops asking and never counts |
| `transit`, `passenger` | No (saved, never scored) |

### 8.4 Model: placeholder and plug-in contract

`app/model.py` has two modes:

- **Placeholder (default).** `model_version = "placeholder"`. Weighted sum of capped event
  rates: `0.3 * min(brake/10, 1) + 0.3 * min(accel/10, 1) + 0.2 * min(corner/10, 1) +
  0.2 * min(speeding_time_share/0.2, 1)`.
- **Real model.** If the file at `MODEL_PATH` (default `backend/models/model.pkl`, gitignored)
  exists at startup, it is unpickled once and used with `model_version = "pkl-model"`.

Contract for the model team: `TripFeatures` in `app/features.py` (field names, units,
descriptions) and `FEATURE_ORDER` in `app/model.py` (the order of the model input vector).

1. Train on the 10 features in `FEATURE_ORDER`, in that order. Do not reorder or rename them;
   changing `FEATURE_ORDER` or a `TripFeatures` field is a coordinated change.
2. The pickled object must expose `predict_proba(X)` (the probability of column 1, "risky",
   is used) or `predict(X)` returning a value in 0..1. `X` is a list with one row of 10 floats.
3. It must be loadable in the backend environment (numpy 1.26.4, pandas 2.2.3, scipy 1.13.1;
   add scikit-learn to `pyproject.toml` if your pickle needs it).
4. Invalid output (outside 0..1) or an exception raises `ModelPredictionError` and the trip
   is marked `failed`; a pickle that fails to load stops the API at startup. This is
   intentional: fail loudly rather than score with a broken model.
5. The model is loaded only at startup. Restart the API after replacing the file, then use
   `POST /v1/trips/{id}/reprocess` to rescore old trips.

Only unpickle files you trust; pickle can execute code.

## 9. Data model

PostgreSQL, 8 tables, managed by Alembic. Ids are strings such as `drv-<12 hex>` and
`trp-<12 hex>`. All timestamps are `timestamptz` (timezone-aware UTC) and DB sessions are
pinned to UTC.

Detailed reference (ER diagram, every table and column, allowed values, trip lifecycle):
[docs/data-model.md](docs/data-model.md).

Where things live:

- `backend/app/models.py`: database truth (typed `Mapped` tables, column comments).
- `backend/app/values.py`: allowed values as `Literal` types, shared by models and schemas.
- `backend/app/schemas.py`: API contract with field descriptions (browse it at `/docs`,
  exported to `backend/contract/openapi.json`).
- `backend/app/features.py`: `TripFeatures`, the contract with the model team.
- `backend/migrations/`: schema history.

| Table | Key columns | Relations / notes |
|---|---|---|
| `drivers` | `id`, `api_key_hash`, optional `emergency_contact_name`, `emergency_contact_phone`, `created_at` | Root of all driver data |
| `consents` | `id`, `driver_id`, `version`, `granted_at` | FK to `drivers`; required before `trips/start` |
| `trips` | `id`, `driver_id`, `status`, `started_at`, `ended_at`, `failure_reason`, `trip_type`, `label_source`, `driver_likelihood`, `transit_line`, `bluetooth_connected_ratio`, `created_at` | FK to `drivers`; `trip_type`: driver / passenger / transit / unknown; `label_source`: bluetooth / rules / user |
| `trip_chunks` | `id`, `trip_id`, `seq`, `file_path`, `received_at` | FK to `trips`; unique `(trip_id, seq)` gives idempotent uploads |
| `events` | `id`, `trip_id`, `type`, `time`, `peak_g`, `lat`, `lon` | FK to `trips`; harsh_brake, harsh_accel, sharp_corner, speeding |
| `trip_features` | `id`, `trip_id` (unique), `features` (JSON) | One row per trip; model input and route |
| `trip_scores` | `id`, `trip_id` (unique), `confidence`, `score`, `tier`, `model_version`, `created_at` | One row per scored trip |
| `incidents` | `id`, `driver_id`, `trip_id` (nullable), `type`, `time`, `lat`, `lon`, `peak_g`, `confirmed`, `sensor_snapshot` (JSON), `created_at` | FK to `drivers` and `trips`; `confirmed`: ok / help_needed / no_response |

Raw sensor data is not in the database; it lives as gzip JSON files on disk
(`DATA_DIR/<trip_id>/<seq>.json.gz`), referenced by `trip_chunks.file_path`.

### Schema changes (Alembic)

Revisions so far: `0001_baseline` (all 8 tables), `0002_timestamptz` (timestamps become
timezone-aware), `0003_column_comments` (column comments from
`app/models.py`), `0004_fk_indexes` (indexes on foreign-key columns).

Never edit an applied revision; add a new one.

```bash
cd backend
# 1. edit app/models.py
uv run alembic revision --autogenerate -m "describe change"
# 2. review the generated file in migrations/versions/ (autogenerate is a draft)
uv run alembic upgrade head
```

`tests/test_migrations.py` fails if the models drift from the migrations, so CI catches a
forgotten revision.

## 10. Privacy (PDPO)

Designed with Hong Kong's Personal Data (Privacy) Ordinance in mind. This is a design
intent for the POC, not legal advice.

- **Consent first.** `POST /v1/trips/start` returns 403 until the driver has recorded
  consent (`POST /v1/consent`, versioned).
- **Right to erasure.** `DELETE /v1/me` removes the driver's raw chunk files and every row
  tied to them (events, features, scores, chunks, trips, incidents, consents, the driver).
- **No protected attributes.** The model features are driving behaviour only (distance,
  duration, night share, event rates, speeds). No name, age, gender or similar is collected
  or used. The only optional personal fields are emergency contact name and phone.
- **Pseudonymous insurer view.** Insurer endpoints identify drivers by `driver_id` only.
  They return tier, score, multiplier, event counts and trip summaries, not raw sensor data
  or names.
- **Data minimisation.** The driver API key is stored only as a salted hash.

## 11. Development

### Tests

Run from `backend/` against PostgreSQL (`docker compose up -d db` first):

```bash
uv run pytest -q
```

How the test setup protects you (`backend/conftest.py`):

- Tests use `TEST_DATABASE_URL` (default
  `postgresql+psycopg://drivescore:drivescore@localhost:5432/drivescore_test`).
- **Safety check:** the database name must end in `_test`, otherwise pytest aborts, because
  every test TRUNCATEs all tables.
- The schema is built once per session with `alembic upgrade head`, so migrations are
  exercised on every run, and tables are truncated before each test.
- `DATA_DIR` points to a fresh temporary directory, so tests never touch
  `backend/data/raw/`.
- Test insurer key and salt are set automatically.

The suite covers the API, pipeline, classification, crash detection, scoring integration,
model plug-in, config loading and migration drift.

### Lint, format, types

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ty check
npm --prefix ../mobile run ts:check     # mobile TypeScript
```

Limits: functions at most 100 lines, files at most 500 lines, line length 100. Ruff enforces
complexity (C901, max 8) and at most 5 arguments (PLR0913/PLR0917).

### CI (`.github/workflows/ci.yml`)

On every pull request and on pushes to `main`, with a PostgreSQL 16 service:
`uv sync --locked`, `ruff format --check`, `ruff check`, `ty check`, `pytest -q`.

### Workflow

- One roadmap line equals one small pull request, branched from `main`.
- PRs are merged manually on GitHub after CI is green.
- Conventional commit messages with the roadmap id, for example
  `feat(backend): PostgreSQL with Alembic baseline, tests on Postgres (A4)`.
- API changes: update `app/schemas.py`, regenerate `contract/openapi.json`, and update
  `mobile/src/api/client.ts` in the same PR.

## 12. Assumptions and known limitations

This is a hackathon POC. Be aware of the following.

**Architecture**
- Sync FastAPI with plain `def` handlers; processing runs in `BackgroundTasks` threads. No job
  queue: if the API restarts mid-processing, that trip stays `processing` until reprocessed.
- Raw chunks are stored on local disk, so only a single API instance works. Multiple
  instances need object storage (roadmap D5).
- The API container binds `0.0.0.0:8000` on purpose so phones on the LAN can reach it; there
  is no TLS or reverse proxy.
- No insurer web dashboard yet (phase F). Insurer views are API endpoints.
- Timestamps are timezone-aware UTC (`timestamptz`; API datetimes end in `Z`). Night driving
  converts to Asia/Hong_Kong.
- `backend/.env.example` is still on SQLite; set the PostgreSQL `DATABASE_URL` and
  `TEST_DATABASE_URL` yourself (see Option B).

**Signal processing**
- The lateral acceleration uses the gyro `gz` axis as yaw rate, so it assumes the phone's
  z axis is roughly vertical (phone lying flat or mounted upright in a typical pose). Other
  orientations will under- or over-report cornering. Gravity removal and the forward
  acceleration (from GPS speed) do not depend on orientation.
- Speeding uses a fixed 50 km/h, not the real road limit (TODO: OSM limits).
- Thresholds are hand-picked, not calibrated on real HK data.
- Crash detection uses fixed rules and always needs driver confirmation; there is no
  emergency notification flow yet.
- Transit detection uses 9 hand-drawn lines. Bus, minibus and taxi rides are not detected
  and fall to `unknown`.

**Mobile**
- `API_BASE` is hardcoded to localhost (E1).
- The app does **not** send `car_connected` yet (E2), so real trips classify as `unknown` and
  do not count toward the score until labelled `driver`. Only the simulator sends it.
- The app has no screens for labelling trips (E3), incidents, or data deletion, although the
  API supports them.
- Registration and consent happen automatically on first launch; there is no consent screen.
- Offline queueing helpers exist in `src/storage/TripStorage.ts` but are not used; a failed
  final upload is retried 3 times and then dropped.
- `mobile/src/types.ts` still holds legacy upload types that do not match the current API;
  `src/api/client.ts` is the source of truth. Its `TripListItem` lacks the newer
  classification fields.
- Styling is plain React Native; NativeWind is planned (E4).

**Security and data**
- Anyone can call `register`; there is no rate limiting. One shared insurer key, no
  per-user insurer accounts.
- The model is loaded with `pickle`; only deploy trusted model files.
- `POST /v1/me/incidents` does not check that `trip_id` belongs to the driver (C1).
- Insurer listing computes each driver's score in a loop, which will not scale beyond
  hundreds of drivers.

**Docs**
- `docs/handoff.md` and `contracts/` describe an earlier API design (`POST /trips`,
  `TripUpload`) and are stale. Use `backend/contract/openapi.json` and `/docs` (G1 will
  rewrite them).

## 13. Roadmap

Full plan and status in [docs/roadmap.md](docs/roadmap.md). One line is one small PR.

- Done: A1 uv tooling, A2 lint baseline, A3 CI, A4 PostgreSQL + Alembic, A5 Docker image and
  compose for the API, A6 Pydantic v2 and timezone-aware timestamps, A8 typed models, A10
  readable schema (allowed values, field docs, TripFeatures, data-model.md), A9 foreign-key
  indexes, A7 size limits (pipeline package, routers split), C2 pipeline error path fix.
- Next (phase A): A11 cleanups.
- Bugs: C1 incident trip ownership check.
- Mobile (phase E): configurable `API_BASE`, send `car_connected`, optional trip labelling,
  NativeWind.
- Insurer dashboard (phase F): staff login, overview, drivers list and detail, trip map,
  incidents (Jinja2 + HTMX + Alpine.js + UnoCSS, served by the API).
- Docs (phase G): regenerate handoff and contracts from the OpenAPI export.

Backend-only details: [backend/README.md](backend/README.md).

## 14. Team

Roles only; add names and contacts here.

| Role | Owns |
|---|---|
| Data / Mobile | Sensor collection, trip detection, chunk upload, driver app screens |
| Model | Risk model behind `app/model.py` (`FEATURE_ORDER` contract), training data, calibration |
| UI | Insurer dashboard and driver app design |
| Backend | API, pipeline, classification, scoring rules, database, CI, contracts |
