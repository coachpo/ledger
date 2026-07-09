# SignalDeck Backend

FastAPI backend for SignalDeck’s template/report and current agent-platform surfaces.

## Local Development

For the easiest full-stack path, run `./start.sh` from the repository root. It uses the root `docker-compose.yml`, builds the local/demo-only app image from the current source, and starts both `db` and `app` services inside Docker.

The public app URL is `http://localhost:${APP_PORT:-8080}`. Nginx runs inside the app container and proxies `/health`, `/ready`, `/api/`, and `/api/v1/` to the internal FastAPI backend. The backend, scheduler, and PostgreSQL/pgvector database are not exposed directly on host ports by default.

The launcher preserves the root Compose environment controls, including `APP_PORT`, `POSTGRES_PASSWORD`, `AGENT_PLATFORM_ENCRYPTION_KEY`, and `VITE_API_BASE_URL`.

If you want to work on the backend test suite directly outside the full local stack:

```bash
uv sync
uv run pytest
```

The backend expects PostgreSQL everywhere. Full-stack local startup gets it from the root Compose `db` service at `db:5432`. Backend tests that run outside Docker can use `TEST_DATABASE_URL` or `DATABASE_URL` for a specific PostgreSQL server, otherwise the test fixture starts or reuses a managed local PostgreSQL container with an available host port.

## Model Connections

Keep `AGENT_PLATFORM_ENCRYPTION_KEY` set so stored model-connection secrets remain encrypted at rest. Local development may use the default placeholder, but `SIGNALDECK_RUNTIME_MODE=production` requires explicit `DATABASE_URL` and non-placeholder `AGENT_PLATFORM_ENCRYPTION_KEY` values.

## Live API Surfaces

- `/health` for process liveness
- `/ready` for readiness; returns 200 only when the backend can connect to PostgreSQL
- `/api/v1` for templates and reports
- `/api/workflow-packages` for package-first authoring, validation, import, export, preflight, launch metadata, and launch creation
- `/api/schedules` for Scheduled Tasks targeting Workflow Packages, including create, list, detail, patch, delete, preview, run-now, and fire-history reads
- `/api/model-connections` for global live provider bindings and secret-safe connection testing
- `/api/tools` for read-only server-declared tool metadata
- `/api/runs` for global run list/detail, root-parameter reruns, and immutable run-owned executable snapshot provenance

Scheduled Tasks use structured recurrence payloads: `interval` with minutes, hours, or days, `daily` at a local time, `weekly` with unique weekday values, and `monthly` with unique day-of-month values. Schedules require a valid IANA timezone. Daily, weekly, and monthly schedules evaluate local wall-clock occurrences, roll DST spring gaps forward to the next valid minute, and fire DST fall repeated local times once at the earliest valid instant. Monthly invalid dates are skipped. Overlap policy is `skip` or `queue`; misfire policy is `skip` or `catchUpOne`, with `catchUpOne` bounded by `misfireGraceSeconds`.

Scheduled input templates are JSON objects only. The renderer allows `schedule`, `fire`, `window`, `lastRun`, and `vars` placeholders, preserves JSON types for exact placeholders, stringifies embedded placeholders, validates the rendered parameters against the package workflow input schema, and fails missing or unsupported expressions before queueing. Unsaved previews use `POST /api/schedules/preview`; saved previews use `POST /api/schedules/{scheduleId}/preview` and are ephemeral. Schedule reads intentionally omit `inputTemplate` and `templateVars`, so clients must save explicit input drafts instead of assuming detail hydration. Run now requires `idempotencyKey` and `scheduledFor`, creates a manual fire through the scheduled-run path, and returns a compact run summary. `DELETE /api/schedules/{scheduleId}` returns 204 with no response body, removes the schedule and fire rows, stops future automation, preserves existing run history, and keeps direct run artifacts readable through run-owned `scheduleProvenance`. Workflow Package deletion semantics are unchanged and still delete package-owned runs.

Rerun endpoints are `GET /api/runs/{runId}/rerun-draft` and `POST /api/runs/{runId}/reruns`; they work with root launch `parameters`.

## Tests

The test suite creates and drops temporary PostgreSQL databases. Set `TEST_DATABASE_URL` or `DATABASE_URL` to a PostgreSQL connection with permission to connect to `postgres` and create/drop databases when you run `uv run pytest` outside Docker.

Root CI runs backend quality after `uv sync --frozen`, with PostgreSQL supplied as a GitHub Actions service. The repo-level `version-sync` job also checks `backend/VERSION` against `backend/pyproject.toml`.

```bash
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest
```

## Docker Compose

The root `docker-compose.yml` is the local/demo full-stack Compose file. It starts PostgreSQL/pgvector in `db` and the combined Nginx/FastAPI/scheduler image in `app`.

```bash
docker compose -f ../docker-compose.yml up --build --remove-orphans
```

From the repository root, prefer `./start.sh`, which runs the same command and streams logs in the foreground. Only the app/Nginx port is published on the host; PostgreSQL stays on the Docker network and FastAPI stays behind Nginx in the app container.

To reset the container-managed PostgreSQL data:

```bash
docker compose -f ../docker-compose.yml down -v
```

## Notes

- `app/db/session.py` uses `create_all`, bundled package seeds, and startup recovery; there is no live Alembic path.
- Schema changes require a database reset until data must survive upgrades.
- Playwright E2E starts a dedicated backend on port `8001` through `frontend/scripts/start-playwright-backend.mjs`, sets `QUOTE_PROVIDER_BACKEND=deterministic` by default, and pairs with a built frontend preview on `4173`.
- The frontend E2E helper defaults `VITE_API_BASE_URL=http://127.0.0.1:8001/api/v1`.
- `docs/` has concise product and data-model docs, extension-writing guidance, and retained migration plans.
- Root workflows check `backend/VERSION` against `backend/pyproject.toml` and build linux/arm64 backend and frontend GHCR images.
- For repo-wide setup, validation, and frontend wiring, see the root `README.md`.
