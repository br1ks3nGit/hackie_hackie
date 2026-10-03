# AGENTS.md - Kimi Code CLI

Instruction file for Kimi Code CLI sessions in this repo.
Nothing is coded without user authorization. User instructions override this file.

Project: DriveScore - usage-based car insurance (hackathon POC). Phone sensors record trips, the
backend detects driving events and scores risk, and the score sets the premium multiplier.
Roadmap and open decisions: docs/roadmap.md - read it before planning any task.

## Layout
- `backend/` - FastAPI app: JSON API (`/v1`) for mobile, HTML dashboard (`/dashboard`) for
  insurers, processing pipeline, tests. Run all Python commands from here.
- `backend/contract/openapi.json` - generated API contract (source of truth; regenerate with
  `scripts/export_openapi.py` after any API change).
- `mobile/` - Expo / React Native (TypeScript) app.
- `contracts/`, `docs/handoff.md` - stale team docs describing an older `/trips` API. Do not code
  against them; update them when touching the API.

## Stack
Python 3.12, FastAPI, Pydantic v2, sync only (plain `def` handlers, no async DB). PostgreSQL via
SQLAlchemy 2.x sync sessions; schema changes only through Alembic revisions; tests run against real
Postgres. Processing with numpy/pandas/scipy runs as FastAPI BackgroundTasks. Dashboard: Jinja2 +
HTMX + Alpine.js + UnoCSS. Mobile: Expo SDK 51, React Native 0.74, TypeScript, NativeWind.

## Tooling (from backend/)
- Install: `uv sync`
- Tests: `uv run pytest -q` (must not write to real `data/raw/`; point DATA_DIR at a tmp dir)
- Lint: `uv run ruff check --fix .` then `uv run ruff format .`
- Types: `uv run ty check`
- Dashboard CSS: `npx unocss "app/templates/**/*.html" -o app/static/css/uno.css`
- Mobile types: `npm --prefix mobile run ts:check`

## Hard Limits
Functions <= 100 lines; cyclomatic complexity <= 8; positional parameters <= 5; line length 100;
files <= 500 lines. Ruff enforces complexity (C901, max 8) and argument counts (PLR0913/PLR0917,
max 5). The pipeline is the `app/pipeline/` package; routes are split by audience
(`routers/driver.py`, `insurer.py`, `incidents.py`, `ingestion.py`, `admin.py`).

## Hard Rules
1. No secrets in code. Config via env / `app/config.py` only; never commit `.env`.
2. No `print` / debug noise on production paths; use `logging` with lazy `%s` args. No
   `console.log` in shipped mobile or dashboard code.
3. No SQL built with string formatting. ORM or parameterized queries; one transaction for
   multi-table updates.
4. Never edit an applied Alembic migration; add a new revision.
5. Add or update tests when behavior changes. Tests must pass before merge.
6. Type hints on new or changed Python code; strict TypeScript in mobile.
7. Keep the backend sync: no `async def` route handlers; long work goes in BackgroundTasks.
8. Every `/v1/me/...` query is scoped to the authenticated device/driver; client-supplied ids must
   be checked for ownership. Insurer views show driver ids only, no PII.
9. Every dashboard route requires the staff login.
10. PDPO: no data accepted before consent; `DELETE /v1/me` removes all raw files and rows for the
    driver; no protected attributes (gender, age) in features.
11. API changes are contract changes: update `schemas.py`, regenerate `contract/openapi.json`, and
    update `mobile/src/api/client.ts` types in the same PR.

## Orchestration
The main session is the director: it plans, delegates, reviews, and decides. Work runs autonomously
end to end; the user is consulted only at the escalation points below.

Kimi subagent types (Agent tool):
- `explore`: read-only search, review, and web lookups.
- `plan`: read-only implementation planning.
- `coder`: edits files, runs commands, makes commits.
- `AgentSwarm`: fans one task template out over many files in parallel.

### Team
| Role | Subagent | Job |
|---|---|---|
| web-researcher | explore | Docs, versions, API lookups |
| designer | explore (spec/review), coder (assets) | Design system, UI specs, UI review |
| coder | coder | All code: API, pipeline, migrations, Docker, dashboard, mobile, tests |
| linter | coder | Ruff format + safe fixes (Python only) |
| reviewer | explore | Read-only diff review: bugs, security, hard rules |
| database-reviewer | explore | Schema, migration, and query review (only when DB code changes) |
| committer | coder | Local conventional commits |
| pr-checker | explore | Pre-PR checks + PR draft |

Review roles must stay read-only: always use `explore`, never `coder`, for reviewer,
database-reviewer, designer (review mode), and pr-checker.

### Pipeline (per PR)
Small incremental PRs from docs/roadmap.md (aim under ~400 changed lines). The user merges PRs
manually on GitHub.
1. Plan: confirm the increment; split into steps, each one commit. Branch off an up-to-date `main`.
   Per user direction, Kimi work uses branches KA1, KA2, and so on, unless the user says otherwise.
2. Prepare (parallel, only if needed): web-researcher for unknowns; designer (spec mode) for UI.
3. Build: coder implements the step with tests.
4. Verify: linter (if Python changed), then reviewer, plus designer (review mode) if UI changed,
   plus database-reviewer if models, migrations, or queries changed.
5. Fix loop: findings back to coder. Max 2 rounds per step; after that, escalate.
6. Commit: committer once lint is clean, tests pass, and reviewers approve.
7. Repeat per step, then pr-checker. Ask the user to approve push + PR. Tick the increment in
   docs/roadmap.md in the same PR. Do not start the next increment on an unmerged branch.

### Escalate to the user only for
- `git push` and PR creation (merging is always done by the user on GitHub)
- Destructive or irreversible actions
- Product or design decisions the spec does not answer
- A step that still fails after 2 fix rounds

### Delegation discipline
Compact briefs: goal, file paths, acceptance criteria. Point to files; never paste file contents
into a brief. Agents return short structured reports (verdict + `file:line` findings). Workers
never delegate; the hierarchy stays one level deep. Skip steps that do not apply. Reuse earlier
results instead of re-reading unchanged files.

## Git Rules
- Local commits: allowed without asking, via committer.
- `git push` and `gh pr create`: always ask the user first. Never merge PRs; never force-push or
  rewrite published history; never commit secrets.
- Branch off `main` for feature work; do not commit to `main`.

## Code Rules
- Simplest working solution. No over-engineering, no speculative features.
- No abstractions for single-use operations.
- Query logic shared by the JSON API and the dashboard lives in `app/services/`, not duplicated in
  routers.
- Read a file before editing it. Prefer editing existing files over creating new ones.
- No error handling for scenarios that cannot happen.
- Fail fast with clear, actionable messages; never swallow exceptions silently; roll back the
  session on a DB error before writing again.

## Output
Be concise. Code first; explanation after, only if non-obvious. No em dashes, smart quotes, or
decorative Unicode in code or files. Test code before declaring done.
