# SignalDeck

SignalDeck is a monorepo for a portfolio-tracking stack with a FastAPI backend, a React/Vite frontend, markdown report workflows, and the current agent-platform surfaces.

## Repository Layout

- `backend/` — FastAPI, SQLAlchemy, Pydantic, PostgreSQL-backed API and tests
- `frontend/` — React 19, Vite, TanStack Query, Vitest, and Playwright app
- `docs/` — live product, platform, API, data-model, test, and runtime-input reference docs
- `.github/workflows/` — root CI and Docker image workflows
- `start.sh` — local Docker Compose launcher for the root combined stack

## What Ships

- Frontend routes for `portfolios`, `templates`, `reports`, `workflow-packages`, `scheduled-tasks`, `model-connections`, and `runs`
- Backend `/api/v1` resource routes for portfolios, balances, positions, trading operations, market data, templates, and reports
- Backend `/api/*` platform routes for workflow packages, scheduled tasks, model connections, tools, and runs, including reruns

## Workflow Package Contract

Workflow Packages are the only live platform authoring root. Package manifests use `signaldeck.workflowPackage/v1` YAML and keep agents, output schemas, capability profiles, private MCP configs, and workflow graphs package-private.

Model Connections remain global live bindings for provider credentials. Global Tools are read-only server-declared metadata from `/api/tools`; packages reference tool keys through local capability profiles. Package exports omit secret-bearing private MCP `env`, `headers`, and `query` values along with database ids and run history. Runs store immutable executable snapshots with copied package id, key, hashes, workflow identity, launch evidence, and rerun metadata.

Scheduled Tasks is the package-first automation surface for recurring Workflow Package runs. The browser route `/scheduled-tasks` and `/api/schedules` create schedules for one package and workflow, use structured interval, daily, weekly, or monthly recurrence instead of raw cron, require an IANA timezone, and materialize due fires into ordinary queued runs with schedule provenance. Scheduled inputs are JSON templates that may use allowlisted `schedule`, `fire`, `window`, `lastRun`, and `vars` placeholders; preview validates rendered parameters without creating fires or runs. Run now creates an idempotent manual fire, then sends the operator to the linked run detail for queue and execution evidence. Delete removes the schedule and its fire rows, stops future automation, preserves existing run history, and keeps direct run artifacts readable through run-owned `scheduleProvenance`. Workflow Package deletion semantics are unchanged: deleting a package still deletes its owned runs.

Rerun is the only live run-descendant write flow. It edits root launch `parameters` through `/api/runs/{runId}/reruns`.

Runtime tool keys use canonical owner-qualified names, and OpenAI function names are mechanical forms derived from those canonical keys.

## Prerequisites

- Docker with `docker compose` for the containerized local stack
- Python 3.13+, Node 24+, pnpm 10+, and uv for validation commands
- An LLM provider key if you want live model-backed agent-platform execution

## Production Release Images and Local Root Compose

The supported production container artifacts are the backend and frontend images built from `backend/Dockerfile` and `frontend/Dockerfile` by `.github/workflows/docker-images.yml` and published to GitHub Container Registry as:

- `ghcr.io/<owner>/signaldeck-backend`
- `ghcr.io/<owner>/signaldeck-frontend`

Published backend/frontend images include Docker Buildx provenance and SBOM attestations on non-PR pushes. The backend image sets `SIGNALDECK_RUNTIME_MODE=production`, rejects missing `DATABASE_URL` or placeholder `AGENT_PLATFORM_ENCRYPTION_KEY` values at startup, and exposes a Docker health check against `/ready`. The frontend image exposes a Docker health check against its static server `/health` endpoint. The root Docker setup remains additive for local/demo combined-stack runs; it is not the supported production image and does not replace the supported `backend/Dockerfile` and `frontend/Dockerfile` artifacts.

The root `Dockerfile` and root `docker-compose.yml` are labeled `local-demo-only` and are not published by CI, released to GHCR, or covered by production SBOM/provenance support. The root combined image entrypoint refuses `SIGNALDECK_RUNTIME_MODE=production`, `prod`, or `staging`; use the supported backend/frontend images for production deployments instead.

### Build and Run the Local App Image

```bash
docker build -t signaldeck .
```

The root `Dockerfile` builds one combined local app image with Nginx, the FastAPI backend, the scheduler worker, and static frontend files. PostgreSQL/pgvector is external to the app image. This image is for local evaluation and demos only; it is intentionally blocked from `production`, `prod`, and `staging` runtime modes.

```bash
docker run --rm -p 8080:8080 \
  -e DATABASE_URL='postgresql+psycopg://...' \
  -e AGENT_PLATFORM_ENCRYPTION_KEY='change-me' \
  signaldeck
```

For development against a database running on the Docker host, add `--add-host=host.docker.internal:host-gateway` and use `host.docker.internal` in `DATABASE_URL`. Do not publish database ports in production just to reach the app container.

### Compose mode

```bash
docker compose up --build
docker compose down
docker compose down -v
```

The root `docker-compose.yml` is local/demo-only and runs:

- `app`, built from the root `Dockerfile`
- `db`, using `pgvector/pgvector:pg16`
- `signaldeck-postgres-data`, a persistent named PostgreSQL volume

Compose provides PostgreSQL/pgvector for local runs only. The app connects to it through `db:5432`; the database port is internal by default. If you need host access for development, add a local-only compose override that publishes `5432`, then remove it before production use.

Only the app/Nginx port is published on the host:

- public app: `http://localhost:${APP_PORT:-8080}` mapped as `${APP_PORT:-8080}:8080`
- backend: internal only at `127.0.0.1:${BACKEND_PORT:-8000}` inside the app container
- database: internal only on the compose network

Nginx listens on `${PORT:-8080}`, serves `/usr/share/nginx/html`, falls back to `index.html` for frontend routes, and proxies `/health`, `/ready`, `/api/`, and `/api/v1/` to FastAPI. The local combined image has a Docker health check against `/ready`.

Build args:

- `VITE_API_BASE_URL=/api/v1` is the default same-origin frontend API base.

Runtime env vars:

- `SIGNALDECK_RUNTIME_MODE` defaults to `local`; the supported backend production image sets it to `production` so startup fails closed unless required runtime config is explicit. The root combined image rejects `production`, `prod`, and `staging` because it is local/demo-only.
- `DATABASE_URL` is required in `production` runtime mode and should point at the managed PostgreSQL instance.
- `AGENT_PLATFORM_ENCRYPTION_KEY` protects stored model-connection secrets; `production` runtime mode rejects the local placeholder key and requires an explicit non-placeholder value.
- `PUBLIC_BASE_URL` should be the externally reachable app origin.
- `CORS_ALLOWED_ORIGINS` should list the allowed browser origins.
- `PORT` controls the internal Nginx listen port, default `8080`.
- `BACKEND_PORT` controls the loopback-only FastAPI port, default `8000`.
- `BACKEND_CMD` overrides the default `uvicorn app.main:app --host 127.0.0.1 --port ${BACKEND_PORT:-8000}` command.
- `RUN_SCHEDULER=true|false` controls the scheduler worker, default `true`.

Compose sets safe local defaults for `SIGNALDECK_RUNTIME_MODE`, `SIGNALDECK_ROOT_IMAGE_SCOPE`, `DATABASE_URL`, `PUBLIC_BASE_URL`, `CORS_ALLOWED_ORIGINS`, `RUN_SCHEDULER`, `BACKEND_PORT`, and `PORT`. The defaults `POSTGRES_PASSWORD=signaldeck` and `AGENT_PLATFORM_ENCRYPTION_KEY=signaldeck-agent-platform-dev-key` are for local development only; do not use them as production secrets.

## Run the Full Stack Locally

### 1. Start everything with the local helper

```bash
./start.sh
```

`start.sh` is the source of truth for the containerized local/demo stack. It runs the root `docker-compose.yml`, builds the app image from the current source tree, and streams Docker Compose logs in the foreground. Press `Ctrl+C` to stop the stack.

It will:

- start the `db` service with PostgreSQL/pgvector inside Docker
- build and start the `app` service from the root `Dockerfile`
- run Nginx, the FastAPI backend, and the scheduler inside the `app` container
- publish only the app/Nginx port on the host, defaulting to `http://localhost:${APP_PORT:-8080}`
- keep the backend/API same-origin behind Nginx through `/health`, `/ready`, `/api/`, and `/api/v1/`

The helper preserves the root Compose environment controls, including `APP_PORT`, `POSTGRES_PASSWORD`, `AGENT_PLATFORM_ENCRYPTION_KEY`, and `VITE_API_BASE_URL`.

### 2. Open the app and verify the stack

Once startup finishes, open:

- App: `http://localhost:${APP_PORT:-8080}`
- Health: `http://localhost:${APP_PORT:-8080}/health`
- Readiness: `http://localhost:${APP_PORT:-8080}/ready`

The database remains internal to Docker networking. The backend remains internal to the app container and is reached through Nginx, not through a host backend port.

### 3. Configure model connections

If you only want the UI, API, and local database running, skip this step.

Keep `AGENT_PLATFORM_ENCRYPTION_KEY` set if you want stored model-connection secrets encrypted with a non-default local key.

### 4. Stop the stack

Press `Ctrl+C` in the terminal running `./start.sh`.

## Direct Compose Commands

Use this path only if you want to call Docker Compose directly instead of `./start.sh`.

```bash
docker compose -f docker-compose.yml up --build --remove-orphans
docker compose -f docker-compose.yml down
docker compose -f docker-compose.yml down -v
```

The direct Compose path uses the same local/demo-only root image and keeps database and backend ports private by default.

## Runtime Notes

- The normal browser-facing execution surfaces are Workflow Packages, Scheduled Tasks, Model Connections, and Runs, plus the preserved portfolio, template, and report routes. In Runs, rerun is for root parameters.
- Workflow package manifests use `signaldeck.workflowPackage/v1`; package-private agents, output schemas, capability profiles, private MCP configs, and workflow graphs are authored inside one package. Private MCP `env`, `headers`, and `query` fields are secret-bearing authoring/runtime config and are omitted from browser-visible manifest reads and exports.
- Keep `AGENT_PLATFORM_ENCRYPTION_KEY` set so stored model-connection secrets remain encrypted at rest.
- Playwright E2E uses Chromium only with dedicated startup helpers: backend `8001`, frontend preview `4173`, deterministic quote provider, and frontend API base `http://127.0.0.1:8001/api/v1` by default.
- `PUBLIC_BASE_URL` is not required for normal local development; only set it when you need an explicit externally reachable backend origin for downstream absolute links.

## Validation

```bash
# Backend
(cd backend && uv run ruff check app tests && uv run black --check app tests && uv run isort --check-only app tests && uv run mypy app && uv run pytest)

# Frontend
(cd frontend && pnpm lint && pnpm typecheck && pnpm build && pnpm test:run)
(cd frontend && pnpm exec playwright install --with-deps chromium && pnpm test:e2e)
```

## CI/CD Workflows

- `ci.yml` runs version sync, backend quality, frontend quality, and frontend E2E
- Backend CI installs with `uv sync --frozen`; frontend CI installs with `pnpm install --frozen-lockfile`
- `docker-images.yml` builds and publishes the supported backend/frontend linux/arm64 images for GitHub Container Registry with SBOM/provenance metadata on non-PR pushes

## Versioning

- `backend/pyproject.toml` is the backend package version surface
- `frontend/package.json` is the frontend package version surface
- `backend/VERSION` must mirror the backend package version
- `frontend/VERSION` must mirror the frontend package version

The VERSION files are lightweight mirrors used for repository-level checks; this repo does not add a separate release system here.

## More Detail

- `backend/README.md` covers backend-specific development details
- `AGENTS.md` maps the repo's live surfaces and nested documentation hierarchy
- `docs/prd.md`, `docs/requirements.md`, `docs/spec.md`, `docs/data-model.md`, `docs/test-plan.md`, and `docs/AGENTS.md` are the canonical live owner docs for product scope, requirements, technical behavior, persistence, validation, and docs governance
