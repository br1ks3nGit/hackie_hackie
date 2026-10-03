> **DEPRECATED - reference only.** This document describes the original design and is kept for the team's reference. The current contract is `backend/contract/openapi.json` and the live docs at `/docs`. The API no longer accepts or returns coordinates.

# DriveScore Handoff Guide

This project is split across three teammates. I own the **connection layer** only: the API, the model adapter interface, and the contracts that let each team plug in.

---

## Team Roles

- **Data/Mobile team** — builds the app that collects raw sensor data and uploads it
- **Model team** — builds the ML model that scores trips
- **UI team** — builds the insurer dashboard and app screens

---

## For the Data/Mobile Team

### What you own
- Sensor collection on the device
- Trip detection and buffering
- Uploading completed trips to the backend

### What I built for you
- `mobile/src/api/client.ts` — API client for uploading trips and fetching scores
- `contracts/schemas.json` — the exact payload shape the backend expects
- `contracts/api-contract.md` — endpoint documentation

### How to connect
Send a `POST /trips` request with a `TripUpload` payload. The backend will respond immediately with a receipt, then score the trip asynchronously.

```bash
curl -X POST http://localhost:8000/trips \
  -H "Content-Type: application/json" \
  -d @sample-trip.json
```

After upload, fetch the score from:

```
GET /trips/{trip_id}
```

### What I need from you
- Make sure the uploaded payload matches `TripUpload` in `contracts/schemas.json`
- Use the `mobile/src/api/client.ts` functions or replicate them
- Do not change the field names; the dashboard and model depend on them

---

## For the Model Team

### What you own
- Training and inference for risk scoring
- Event detection
- Outlier detection

### What I built for you
- `backend/app/model_adapter.py` — the adapter interface you must implement
- `backend/app/services/scoring_service.py` — a heuristic placeholder so the pipeline runs end-to-end before your model is ready
- `backend/tests/test_integration.py` — integration test to validate the flow

### How to connect
Implement the `RiskModel` interface in `backend/app/model_adapter.py`:

```python
from app.model_adapter import RiskModel, set_model

class MyModel(RiskModel):
    def score_trip(self, trip: TripUpload, baseline: Optional[dict] = None) -> TripScore:
        # your inference code here
        ...

    def detect_outlier(self, trip: TripUpload, baseline: Optional[dict] = None) -> bool:
        # your outlier logic here
        ...

# At app startup, plug in your model:
set_model(MyModel())
```

The backend will call your model every time a trip is uploaded.

### Input you receive
- `trip`: `TripUpload` with raw accelerometer, gyroscope, GPS arrays, and metadata
- `baseline`: rolling statistics for the user (`distance_km_mean`, `distance_km_std`, etc.) or `None` for a new user

### Output you return
- `TripScore` with:
  - `risk_score`: 0–100
  - `events`: list of detected events
  - `is_outlier`: boolean
  - `status`: `scored`, `needs_review`, or `rejected`
  - `factors`: dict of model features for explainability

### What I need from you
- Keep the same function signatures
- Return the same schema
- Tell me if you need additional baseline features

---

## For the UI/Dashboard Team

### What you own
- Visual design for the insurer dashboard
- App dashboard screens
- Data visualization

### What I built for you
- Stable API endpoints
- `contracts/api-contract.md` — endpoint documentation
- `contracts/schemas.json` — response shapes

### How to connect

**Driver profile view:**

```
GET /drivers/{user_id}/summary
```

**Trip list:**

```
GET /trips?user_id={user_id}&limit=50&offset=0
```

**Trip detail with map events:**

```
GET /trips/{trip_id}
```

### Key fields to render
- `overall_score` — headline risk score
- `recent_trips` — list of scored trips
- `events` — hard brakes, hard accels, sharp turns with lat/lng for map overlays
- `is_outlier` — flag unusual trips
- `factors` — model features for tooltips and explanations

### What I need from you
- Do not change the API paths or field names
- If you need a new endpoint or field, request it here first

---

## Running the Project

### Start the backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Run the integration test

```bash
python3 -m pytest backend/tests/test_integration.py -v
```

### Start the mobile app

```bash
cd mobile
npm install
npx expo start
```

---

## Current Architecture

```
Mobile App ──POST /trips──> Backend API ──calls──> Model Adapter ──calls──> ML Model
     │                        │
     │                        │
     └──GET /trips/{id}───────┘
     └──GET /drivers/{id}/summary───────────────> Insurer Dashboard
```

The model adapter is the single point where the ML team plugs in. The data and UI teams interact only with the API.
