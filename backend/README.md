# SignalDeck Backend

FastAPI backend for SignalDeck’s portfolio, report, and current agent-platform surfaces.

## Local Development

For the easiest full-stack path, run `../start.sh` from the repo root. It owns local DB/backend/frontend startup and can fall back to DB ports `25432/25433/25434`, backend ports `28000/28001/28002`, and frontend ports `25173/25174`.

If you want the backend on its own:

```bash
uv sync
docker compose up -d db
uv run uvicorn app.main:app --reload --port 28000
```

Run `uv run python -m app.workers.run_scheduler` beside Uvicorn when you need due Scheduled Tasks materialized or queued Workflow Package runs executed.

The backend expects PostgreSQL everywhere. The default local connection is `postgresql+psycopg://signaldeck:signaldeck@localhost:25432/signaldeck`, so manual `uv run uvicorn ...` startup assumes PostgreSQL is already running on that port. Set `SIGNALDECK_DB_PORT` before `docker compose up -d db` if you need a different host port, then align `DATABASE_URL`. CORS is enabled for common local Vite dev hosts by default and can be overridden through `CORS_ALLOWED_ORIGINS`.

## Model Connections

Keep `AGENT_PLATFORM_ENCRYPTION_KEY` set so stored model-connection secrets remain encrypted at rest. Local development may use the default placeholder, but `SIGNALDECK_RUNTIME_MODE=production` requires explicit `DATABASE_URL` and non-placeholder `AGENT_PLATFORM_ENCRYPTION_KEY` values.

## Live API Surfaces

- `/health` for process liveness
- `/ready` for readiness; returns 200 only when the backend can connect to PostgreSQL
- `/api/v1` for portfolios, balances, positions, trading operations, market data, templates, and reports
- `/api/workflow-packages` for package-first authoring, validation, import, export, preflight, launch metadata, and launch creation
- `/api/schedules` for Scheduled Tasks targeting Workflow Packages, including create, list, detail, patch, delete, preview, run-now, and fire-history reads
- `/api/model-connections` for global live provider bindings and secret-safe connection testing
- `/api/tools` for read-only server-declared tool metadata
- `/api/runs` for global run list/detail, root-parameter reruns, invocation-input forks, historical replay lineage reads, and immutable run-owned executable snapshot provenance

Scheduled Tasks use structured recurrence payloads: `interval` with minutes, hours, or days, `daily` at a local time, `weekly` with unique weekday values, and `monthly` with unique day-of-month values. Schedules require a valid IANA timezone. Daily, weekly, and monthly schedules evaluate local wall-clock occurrences, roll DST spring gaps forward to the next valid minute, and fire DST fall repeated local times once at the earliest valid instant. Monthly invalid dates are skipped. Overlap policy is `skip` or `queue`; misfire policy is `skip` or `catchUpOne`, with `catchUpOne` bounded by `misfireGraceSeconds`.

Scheduled input templates are JSON objects only. The renderer allows `schedule`, `fire`, `window`, `lastRun`, and `vars` placeholders, preserves JSON types for exact placeholders, stringifies embedded placeholders, validates the rendered parameters against the package workflow input schema, and fails missing or unsupported expressions before queueing. Unsaved previews use `POST /api/schedules/preview`; saved previews use `POST /api/schedules/{scheduleId}/preview` and are ephemeral. Schedule reads intentionally omit `inputTemplate` and `templateVars`, so clients must save explicit input drafts instead of assuming detail hydration. Run now requires `idempotencyKey` and `scheduledFor`, creates a manual fire through the scheduled-run path, and returns a compact run summary. `DELETE /api/schedules/{scheduleId}` returns 204 with no response body, removes the schedule and fire rows, stops future automation, preserves existing run history, and keeps direct run artifacts readable through run-owned `scheduleProvenance`. Workflow Package deletion semantics are unchanged and still delete package-owned runs.

Rerun endpoints are `GET /api/runs/{runId}/rerun-draft` and `POST /api/runs/{runId}/reruns`; they work with root launch `parameters`. Fork endpoints are `GET /api/runs/{runId}/fork-draft?sourceInvocationId=...` and `POST /api/runs/{runId}/forks`; they work with one agent invocation `invocationInput`, persist `run_forks`, and use `resumeStepIndex` only as the execution boundary.

## Tests

The test suite creates and drops temporary PostgreSQL databases. Set `TEST_DATABASE_URL` or `DATABASE_URL` to a PostgreSQL connection with permission to connect to `postgres` and create/drop databases when you run `uv run pytest` outside Docker.

Root CI runs backend quality after `uv sync --frozen`, with PostgreSQL supplied as a GitHub Actions service on `25432`. The repo-level `version-sync` job also checks `backend/VERSION` against `backend/pyproject.toml`.

```bash
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest
```

## Docker Compose

`docker-compose.yml` is DB-only. It starts PostgreSQL for local development and exposes it on `${SIGNALDECK_DB_PORT:-25432}`.

```bash
docker compose up -d db
```

No API container is defined in compose. Start FastAPI separately with `uv run uvicorn app.main:app --reload --port 28000`.
PostgreSQL is exposed on `localhost:${SIGNALDECK_DB_PORT:-25432}`.

To reset the container-managed PostgreSQL data:

```bash
docker compose down -v
```

## Notes

- `app/db/upgrades.py` is the supported schema-repair path; `alembic/` is scaffolding only.
- Startup schema repair detaches legacy schedule rows from linked runs, backfills `scheduleProvenance` when resolvable, deletes obsolete schedule and fire rows, and no longer routes schedule cleanup through a destructive schedule cleanup path.
- Playwright E2E starts a dedicated backend on port `8001` through `frontend/scripts/start-playwright-backend.mjs`, sets `QUOTE_PROVIDER_BACKEND=deterministic` by default, and pairs with a built frontend preview on `4173`.
- The frontend E2E helper defaults `VITE_API_BASE_URL=http://127.0.0.1:8001/api/v1`.
- `docs/` has live product, platform, API, data-model, test, and runtime-input references.
- Root workflows check `backend/VERSION` against `backend/pyproject.toml`, build linux/arm64 backend and frontend GHCR images, keep at least 3 workflow runs, and delete untagged backend/frontend packages.
- For repo-wide setup, validation, and frontend wiring, see the root `README.md`.
