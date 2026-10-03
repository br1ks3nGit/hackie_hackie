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
# Edit .env with your database URL and API keys
```

### 3. Start PostgreSQL

```bash
# Option A: Local PostgreSQL
createdb drivescore

# Option B: Docker
docker run --name drivescore-db -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:15
```

### 4. Run the API

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API docs at `http://localhost:8000/docs`.

### 5. Seed demo data

```bash
uv run python scripts/seed.py
```

### 6. Export OpenAPI contract

```bash
uv run python scripts/export_openapi.py
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

### Insurer reports

- `GET /v1/insurer/overview` → total drivers, tier distribution, average multiplier
- `GET /v1/insurer/drivers?tier=&sort=` → list of drivers
- `GET /v1/insurer/drivers/{driver_id}` → driver detail with event rates

### Admin

- `POST /v1/trips/{trip_id}/reprocess` → re-run pipeline for a failed trip
- `DELETE /v1/me` → delete all driver data (PDPO right to erasure)

## Model plugin

The model team implements `app/model.py`:

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
- Night driving = 23:00-05:00 local time
- Speeding threshold = 50 km/h (fixed HK urban default; one event per run > 10 s)
- Events are detected with fixed thresholds in `app/pipeline.py`
- PostgreSQL is used in production; SQLite can be used for local testing

## Testing

```bash
uv run pytest tests/ -v
```

## Project structure

```
backend/
├── app/
│   ├── main.py           # FastAPI app entry
│   ├── config.py         # Environment config
│   ├── database.py       # SQLAlchemy setup
│   ├── models.py         # Database models
│   ├── schemas.py        # Pydantic schemas
│   ├── auth.py           # API key auth
│   ├── model.py          # Model plugin interface
│   ├── pipeline.py       # Processing pipeline
│   └── routers/
│       ├── ingestion.py  # Trip upload endpoints
│       ├── reports.py    # Driver and insurer reports
│       └── admin.py      # Reprocess and delete
├── scripts/
│   ├── simulate.py       # Generate synthetic trips
│   ├── seed.py           # Seed demo drivers
│   └── export_openapi.py # Export OpenAPI JSON
├── tests/
│   ├── test_api.py
│   ├── test_model.py
│   └── test_pipeline.py
├── data/
│   └── raw/              # Raw sensor chunks (gitignored)
├── contract/
│   └── openapi.json      # Exported API contract
├── .env.example
├── pyproject.toml        # Dependencies and tool config (uv)
└── uv.lock
```
