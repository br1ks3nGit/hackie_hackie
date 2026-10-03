# DriveScore Roadmap

One line = one small PR. The user merges PRs manually on GitHub. Tick the box in the PR that
completes the increment. Order matters inside a phase; phases A and B come first.

## Decisions

Made:
- Async backend: async route handlers + SQLAlchemy async with asyncpg on PostgreSQL.
- CPU-bound pipeline runs in a separate worker process, not on the API event loop.
- POC identity: device = driver. Each install registers once and uses its id + key; no driver
  login/logout, no separate device model.
- Insurer dashboard: Jinja2 + HTMX + Alpine.js + UnoCSS (`presetWind`), served by the FastAPI app,
  behind a basic staff login (credentials from env).
- Mobile styling: NativeWind, sharing token names with the dashboard's UnoCSS config.

Open (the director escalates these when the increment needs them):
- D1 Job queue for the worker (needed by B4). Recommended: procrastinate (PostgreSQL-backed, async,
  no Redis). Alternative: arq (needs Redis).
- D4 Dashboard charts (needed by F2): Chart.js (simple) or uPlot (fast for long time series).
- D5 Raw chunk storage: local disk works for one API instance; object storage (S3 / MinIO) is
  needed before running more than one instance. Not needed for the POC.

## Phase A - Foundation
- [x] A1 Tooling: `backend/pyproject.toml` (uv) with pinned deps, ruff + ty config, `uv.lock`;
      drop `requirements.txt`; README and CLAUDE.md commands switch to `uv run`.
- [ ] A2 Lint baseline: ruff format + safe fixes on legacy code, no behavior change. Rules that
      need behavior changes (e.g. `utcnow`, fixed in B5) and leftover ty errors are listed as
      explicit, commented ignores so the next PR's CI starts green.
- [ ] A3 CI: GitHub Actions running ruff, ty, pytest on every PR (Postgres service added in A4).
- [ ] A4 Postgres: `docker-compose.yml` Postgres for dev, asyncpg + Alembic (async env) with a
      baseline revision from the current models, `.env.example` uses Postgres, CI Postgres service
      runs `alembic upgrade head` + an `alembic check` drift test. App still uses `create_all` and
      the sync engine until B1.

## Phase B - Async and worker
- [ ] B1 Async DB layer: async engine/session, async `get_db`, async auth dependencies; tests on
      Postgres with a tmp `DATA_DIR`; remove `create_all` in favour of migrations.
- [ ] B2 Ingestion router async (chunk file writes off the event loop).
- [ ] B3 Reports + admin routers async; shared queries moved to `app/services/`.
- [ ] B4 Job queue (D1) + worker process; `process_trip`, reprocess and relabel enqueue jobs
      instead of `BackgroundTasks`.
- [ ] B5 Timezone-aware timestamps (`timestamptz` revision), Pydantic v2 validators.

## Phase C - Known bugs
- [ ] C1 `POST /v1/me/incidents`: check the trip belongs to the driver.
- [x] C2 Pipeline error path rolls back before marking a trip failed (team, 66830b7).
- [ ] C3 `DELETE /v1/me`: delete only the driver's trip dirs, one transaction, files after commit.
- [ ] C4 Reprocess: refuse while a trip is `processing`.
- [ ] C5 Insurer driver list: one aggregate query + pagination instead of per-driver scoring.

## Phase E - Mobile
- [ ] E1 Config-driven `API_BASE` (Expo config / env) so the app works on a real phone.
- [ ] E2 Send `car_connected` (Bluetooth) with chunks so real trips score automatically
      (the simulator already sends it).
- [ ] E3 Label unknown trips (driver / passenger).
- [ ] E4 NativeWind setup and design tokens.

## Phase F - Insurer dashboard
- [ ] F1 Basic staff login (env credentials, hashed password), cookie session, CSRF, base layout,
      UnoCSS build.
- [ ] F2 Overview page: totals, tier distribution, average multiplier (HTMX partials).
- [ ] F3 Drivers list with filter, sort, pagination; driver detail.
- [ ] F4 Trip detail with Leaflet route and event markers.
- [ ] F5 Incidents page.

## Phase G - Docs
- [ ] G1 Rewrite `docs/handoff.md` and `contracts/` from the generated OpenAPI contract.
