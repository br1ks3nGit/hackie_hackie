> **DEPRECATED - reference only.** This document describes the original design and is kept for the team's reference. The current contract is `backend/contract/openapi.json` and the live docs at `/docs`. The API no longer accepts or returns coordinates.

# DriveScore API Contract

## Base URL

```
Local dev: http://localhost:8000
Production: TBD
```

## Endpoints

### Health Check

```
GET /health
```

Returns `{"status": "ok"}`.

---

### Upload a Trip

```
POST /trips
```

Accepts a `TripUpload` payload. Stores raw trip data and queues it for scoring.

**Response:**

```json
{
  "trip_id": "uuid",
  "status": "received",
  "received_at": "2026-10-03T12:00:00Z"
}
```

---

### Get Trip Score

```
GET /trips/{trip_id}
```

Returns the scored result for a trip, including detected events and risk score.

**Response:** `TripScore`

---

### Get Driver Summary

```
GET /drivers/{user_id}/summary
```

Returns aggregated score and recent trips for a driver.

**Response:** `DriverSummary`

---

### List Trips for Insurer Dashboard

```
GET /trips?user_id={user_id}&limit=50&offset=0
```

Returns paginated list of trips. Intended for the insurer dashboard.

---

## Integration Notes

### For the ML teammate

The backend calls the scoring service in `app/services/scoring_service.py`. Replace the placeholder heuristics with the real model by implementing:

```python
def score_trip(trip: TripUpload, baseline: Optional[dict] = None) -> TripScore:
    ...
```

Input: raw sensor arrays, metadata, and the user's baseline stats.  
Output: `TripScore` with events, risk score, and an `is_outlier` flag.

Outlier detection is used to filter trips that do not match the driver's typical patterns. Outliers are marked `needs_review` and excluded from the baseline and overall score.

### For the UI/dashboard teammate

Build the dashboard against:

- `GET /drivers/{user_id}/summary` for the driver profile view
- `GET /trips?user_id=...` for trip lists
- `GET /trips/{trip_id}` for trip detail with map events

All score values are 0–100 where lower is safer.

### For the mobile app

Upload completed trips to `POST /trips`. The app should batch upload when connectivity returns.

