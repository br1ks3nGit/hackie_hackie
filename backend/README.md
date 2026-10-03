# DriveScore Backend

Usage-based car insurance backend for the bolttech hackathon track (Hong Kong).

## What this is

Phone sensors measure driving behavior → a model scores risk → the score sets the premium.
This backend is the connection layer between the mobile app, the ML model, and the two dashboards (driver app and insurer dashboard).

## Quick start

### 1. Install dependencies

```bash
cd backend
uv sync
```

### 2. Set up environment

```bash
cp .env.example .env
# Edit .env: set INSURER_API_KEY, DRIVER_API_KEY_SALT and the PostgreSQL DATABASE_URL / TEST_DATABASE_URL
# (.env.example is still on SQLite; use postgresql+psycopg://drivescore:drivescore@localhost:5432/drivescore)
```

### 3. Start PostgreSQL and migrate

```bash
docker compose up -d db        # from the repo root; also creates drivescore_test
uv run alembic upgrade head    # the app does not create tables itself
```

`initdb.sql` only runs on an empty volume; with an existing volume run `docker compose exec db createdb -U drivescore drivescore_test` (or `docker compose down -v` to reset).

Schema changes go through Alembic: edit `app/models.py`, then
`uv run alembic revision --autogenerate -m "describe change"`, review the generated file in
`migrations/versions/`, and run `uv run alembic upgrade head`. Never edit an applied revision.

### 4. Run the API

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API docs at `http://localhost:8000/docs` (field descriptions and examples come from `app/schemas.py`).

### 5. Seed demo data

```bash
uv run python scripts/seed.py
```

### 6. Export OpenAPI contract

```bash
uv run python scripts/export_openapi.py
```

## Run everything with Docker

From the repo root (needs Docker only, no local Python):

```bash
export INSURER_API_KEY=change-me DRIVER_API_KEY_SALT=change-me-too   # or put both in a root .env
docker compose up -d --build
```

Compose refuses to start `api` if either key is unset. The `api` container waits for the
healthy `db`, runs `alembic upgrade head`, then serves on `0.0.0.0:8000` (reachable from phones
on the LAN, at `http://<laptop LAN IP>:8000`). Check it with `curl localhost:8000/health` and `docker compose logs api`.

Raw chunks live in the `rawdata` volume (`/data/raw`); put a trained `model.pkl` in the `models`
volume (`/models`), otherwise the app falls back to its default scoring.

Seed demo data (the script targets `http://localhost:8000`, which is valid inside the container):

```bash
docker compose exec api python scripts/seed.py
```

## Data flow

```
Mobile App ──POST /v1/trips/{id}/chunks──> Backend
                                              │
                                              v
                                        data/raw/<trip_id>/<seq>.json.gz
                                              │
                                              v
                                    BackgroundTasks processing
                                              │
                                              v
                                    Pipeline (clean, filter, detect)
                                              │
                                              v
                                    Model (predict confidence)
                                              │
                                              v
                                    Database (scores, features, events)
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    │                         │                         │
                    v                         v                         v
            Driver App               Insurer Dashboard           Model Team
         GET /v1/me/summary      GET /v1/insurer/overview      app/model.py
         GET /v1/me/trips        GET /v1/insurer/drivers       predict()
         GET /v1/me/trips/{id}   GET /v1/insurer/drivers/{id}
```

## API overview

### Ingestion (mobile app)

- `POST /v1/drivers/register` → `{driver_id, api_key}`
- `POST /v1/consent` → record PDPO consent
- `POST /v1/trips/start` → `{trip_id}`
- `POST /v1/trips/{trip_id}/chunks` → upload sensor chunk (idempotent)
- `POST /v1/trips/{trip_id}/end` → start processing
- `GET /v1/trips/{trip_id}/status` → check status

### Driver reports

- `GET /v1/me/summary` → driver score, tier, premium multiplier, trend
- `GET /v1/me/trips` → list of trips
- `GET /v1/me/trips/{trip_id}` → trip detail with events and route
- `POST /v1/me/trips/{trip_id}/label` -> label a trip `driver` or `passenger`
- `POST /v1/me/incidents`, `POST /v1/me/incidents/{incident_id}/confirm`, `GET /v1/me/incidents` -> crash incidents

### Insurer reports

- `GET /v1/insurer/overview` → total drivers, tier distribution, average multiplier
- `GET /v1/insurer/drivers?tier=&sort=` → list of drivers
- `GET /v1/insurer/drivers/{driver_id}` → driver detail with event rates

### Admin

- `POST /v1/trips/{trip_id}/reprocess` -> re-run pipeline for a trip (insurer key)
- `DELETE /v1/me` → delete all driver data (PDPO right to erasure)

## Model plugin

The model team contract is `TripFeatures` in `app/features.py` (feature names, units) plus
`FEATURE_ORDER` in `app/model.py` (order of the model input vector). The pipeline validates
the computed features against `TripFeatures` before storing them.

`app/model.py` exposes:

```python
def predict(features: dict) -> dict:
    return {
        "confidence": 0.0 - 1.0,  # probability driver is risky
        "model_version": "v1.0",
    }
```

If a file exists at `models/model.pkl`, it is loaded at startup and used.
If loading fails or the model returns invalid values, the API fails loudly.

## Scoring logic

- `confidence` (0-1) → `score` (0-100, 100 = safest) → `tier` (A-E) → `premium_multiplier` (0.80-1.30)
- Driver score = distance-weighted average of trip scores over the last 90 days
- Premium uses the driver score, not one trip

## Privacy (PDPO)

- No data accepted without consent
- Insurer endpoints show driver IDs only, no names
- `DELETE /v1/me` removes all raw files and records
- No gender, age, or protected attributes used

## Assumptions

- Orientation-free car frame: gravity removed with a 10 s rolling median; forward accel from GPS speed change, lateral accel from gyro yaw rate x GPS speed
- GPS speed is used for event detection when available
- Night driving = 23:00-05:59 Asia/Hong_Kong
- Speeding threshold = 50 km/h (fixed HK urban default; one event per run > 10 s)
- Events are detected with fixed thresholds in `app/pipeline.py`
- PostgreSQL (sync SQLAlchemy + psycopg 3) everywhere; schema is managed by Alembic (0001 baseline, 0002 timestamptz, 0003 column comments)
- Timestamps are timezone-aware UTC (`timestamptz`, DB sessions pinned to UTC); API datetimes end in `Z`
- Detailed data model (ER diagram, allowed values): [`../docs/data-model.md`](../docs/data-model.md)

## Testing

Tests run against the `drivescore_test` database (`TEST_DATABASE_URL`, default
`postgresql+psycopg://drivescore:drivescore@localhost:5432/drivescore_test`). Start it with
`docker compose up -d db`. `conftest.py` runs `alembic upgrade head` once per session, truncates
all tables before each test and points `DATA_DIR` at a temp dir. `tests/test_migrations.py` fails
if the models drift from the migrations.

```bash
uv run pytest tests/ -v
```

CI (`.github/workflows/ci.yml`) runs `ruff format --check`, `ruff check`, `ty check` and `pytest` on every PR and on pushes to `main`.

## Project structure

```
backend/
├── app/
│   ├── main.py           # FastAPI app entry
│   ├── config.py         # Environment config
│   ├── database.py       # SQLAlchemy setup
│   ├── models.py         # Database models (typed Mapped, column comments)
│   ├── values.py         # Allowed values (Literal types)
│   ├── schemas.py        # API contract: Pydantic schemas with field docs
│   ├── features.py       # TripFeatures: contract with the model team
│   ├── auth.py           # API key auth
│   ├── model.py          # Model plugin interface
│   ├── pipeline.py       # Processing pipeline
│   ├── classify.py       # Trip classification (transit / driver / unknown)
│   └── routers/
│       ├── ingestion.py  # Trip upload endpoints
│       ├── reports.py    # Driver and insurer reports
│       └── admin.py      # Reprocess and delete
├── migrations/           # Alembic env + versions
├── Dockerfile            # API image
├── docker/               # DB init script (creates drivescore_test), API entrypoint
├── alembic.ini
├── scripts/
│   ├── simulate.py       # Generate synthetic trips
│   ├── seed.py           # Seed demo drivers
│   └── export_openapi.py # Export OpenAPI JSON
├── tests/                # pytest suite (api, pipeline, classify, crash, model, migrations, config)
├── data/
│   ├── transit_lines.geojson  # HK transit lines used by classification
│   └── raw/              # Raw sensor chunks (gitignored)
├── contract/
│   └── openapi.json      # Exported API contract
├── .env.example
├── pyproject.toml        # Dependencies and tool config (uv)
└── uv.lock
```
