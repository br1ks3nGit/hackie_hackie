# DriveScore Roadmap

One line = one small PR. The user merges PRs manually on GitHub. Tick the box in the PR that
completes the increment. Order matters inside a phase; phase A comes first.

## Decisions

Made:
- Sync backend (POC): plain `def` handlers + SQLAlchemy sync sessions with psycopg on PostgreSQL.
  The pipeline keeps running as FastAPI `BackgroundTasks` (thread pool). No async, no job queue.
- Deployment: every backend component runs in Docker (`docker compose up`: Postgres + API, which
  also serves the dashboard). The mobile app runs on phones via Expo and points at the API.
- POC identity: device = driver. Each install registers once and uses its id + key; no driver
  login/logout, no separate device model.
- Insurer dashboard: Jinja2 + HTMX + Alpine.js + UnoCSS (`presetWind`), served by the FastAPI app,
  behind a basic staff login (credentials from env).
- Mobile styling: NativeWind, sharing token names with the dashboard's UnoCSS config.

Open (the director escalates these when the increment needs them):
- D4 Dashboard charts (needed by F2): decided Chart.js (simple; uPlot only if long time series appear).
- D5 Raw chunk storage: local disk works for one API instance; object storage (S3 / MinIO) is
  needed before running more than one instance. Not needed for the POC.

## Phase A - Foundation
- [x] A1 Tooling: `backend/pyproject.toml` (uv) with pinned deps, ruff + ty config, `uv.lock`;
      drop `requirements.txt`; README and CLAUDE.md commands switch to `uv run`.
- [x] A2 Lint baseline: ruff format + safe fixes on legacy code, no behavior change. Rules that
      need behavior changes (e.g. `utcnow`, kept for the POC) and leftover ty errors are listed as
      explicit, commented ignores so the next PR's CI starts green.
- [x] A3 CI: GitHub Actions running ruff, ty, pytest on every PR (Postgres service added in A4).
- [x] A4 Postgres: psycopg + Alembic with a baseline revision from the current models, replace
      `create_all` with `alembic upgrade head`, `.env.example` uses Postgres, tests run on Postgres
      (tmp `DATA_DIR`, nothing written to the real `data/raw/`), CI Postgres service + `alembic check` drift test.
- [x] A5 Docker: backend `Dockerfile` (uv), `docker-compose.yml` with Postgres + API (migrations on
      start, `data/raw` and `models/` volumes, healthchecks), README "run everything" section.
- [x] A6 Pydantic v2 validators (`field_validator`, `min_length`, `model_dump`) and timezone-aware
      timestamps (`datetime.now(UTC)`, `timestamptz` revision); drop the DTZ ignores and the ty
      `deprecated` downgrade.
- [x] A7 Size limits: split `app/pipeline.py` and `app/routers/reports.py` under 500 lines and
      `process_trip` under 100 lines, no behavior change.
- [x] A8 Typed models: `Mapped[...]` / `mapped_column` so ty's `invalid-argument-type` and
      `invalid-assignment` rules go back to error.
- [x] A9 FK indexes: `index=True` on `trips.driver_id`, `events.trip_id`, `incidents.driver_id`,
      `incidents.trip_id`, `consents.driver_id` + revision 0004 (keeps the drift test green).
- [x] A10 Readable schema: `Literal` types for status/tier/type fields, `Field(description, examples)`
      on every API schema, typed models instead of bare dicts, a `TripFeatures` Pydantic model for
      the pipeline/model contract, table docstrings and column comments, `docs/data-model.md` with
      a Mermaid ER diagram and allowed values.
- [ ] A11 Small cleanups (single `score_to_tier` done in A7): mobile `client.ts` types match the
      API (`client.ts` `TripListItem` types done in E3), remove legacy `mobile/src/types.ts` types
      and unused deps, `backend/.env.example` on Postgres (user edit: file is agent-denied).

## Phase C - Known bugs
- [x] C1 `POST /v1/me/incidents`: check the trip belongs to the driver.
- [x] C2 Pipeline error path rolls back before marking a trip failed (team, 66830b7).

## Phase E - Mobile
- [x] E1 Config-driven `API_BASE` (Expo config / env) so the app works on a real phone.
- [x] E2 Send `car_connected` with chunks so real trips score automatically: manual "I'm driving"
      toggle for now; automatic car-audio detection is H2.
- [x] E3 Label unknown trips (driver / passenger).
- [ ] E4 NativeWind setup and design tokens.

## Phase F - Insurer dashboard
- [x] F1 Basic staff login (env credentials, hashed password), cookie session, CSRF, base layout,
      UnoCSS build.
- [x] F2 Overview page: totals, tier distribution, average multiplier (HTMX partials).
- [x] F3 Drivers list with filter, sort, pagination; driver detail. (Trip rows link to `/dashboard/trips/{id}`, which 404s until F4 lands.)
- [ ] F4 Trip detail with Leaflet route and event markers.
- [ ] F5 Incidents page.
- [ ] Later: dashboard hardening: login rate limiting/lockout, server-side session revocation,
      security headers (CSP).

## Phase G - Docs
- [ ] G1 Rewrite `docs/handoff.md` and `contracts/` from the generated OpenAPI contract.

## Phase H - Native signals (post-hackathon)
- [ ] H1 Expo development build (custom native modules).
- [ ] H2 Car audio connection sets `car_connected` automatically: iOS audio route
      (Bluetooth / CarPlay); Android Bluetooth A2DP / Android Auto with `BLUETOOTH_CONNECT`.
- [ ] H3 OS activity recognition for automatic trip start/stop: Android Activity Recognition
      Transition API `IN_VEHICLE` (`ACTIVITY_RECOGNITION` permission); iOS
      `CMMotionActivityManager` automotive (`NSMotionUsageDescription`). It does not
      distinguish driver from passenger.
