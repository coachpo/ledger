# Ledger

Ledger is a monorepo for a portfolio-tracking stack with a FastAPI backend, a React/Vite frontend, markdown report workflows, and the current agent-platform surfaces.

## Repository Layout

- `backend/` — FastAPI, SQLAlchemy, Pydantic, PostgreSQL-backed API and tests
- `frontend/` — React 19, Vite, TanStack Query, Vitest, and Playwright app
- `docs/` — live product, platform, API, data-model, test, and runtime-input reference docs
- `.github/workflows/` — root CI, Docker image, and cleanup workflows
- `start.sh` — local full-stack startup helper with backend/frontend/db fallback logic

## What Ships

- Frontend routes for `portfolios`, `templates`, `reports`, `workflow-packages`, `model-connections`, and `runs`
- Backend `/api/v1` resource routes for portfolios, balances, positions, trading operations, market data, templates, and reports
- Backend `/api/*` platform routes for workflow packages, model connections, tools, and runs

## Workflow Package Contract

Workflow Packages are the only live platform authoring root. Package manifests use `ledger.workflowPackage/v1` YAML and keep agents, output schemas, capability profiles, private MCP configs, and workflow graphs package-private.

Model Connections remain global live bindings for provider credentials. Global Tools are read-only server-declared metadata from `/api/tools`; packages reference tool keys through local capability profiles. Package exports omit secrets, encrypted values, database ids, and run history. Runs store immutable package id/key/version/hash provenance.

Legacy global authoring routes are unsupported. `/api/agents`, `/api/capabilities`, `/api/mcp-servers`, `/api/output-schemas`, `/api/workflows`, `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, and `/workflows*` are removed surfaces, not compatibility aliases. Runtime tool keys and OpenAI function names stay unchanged.

## Prerequisites

- Python 3.13+
- Node 24+
- pnpm 10+
- uv
- lsof
- Docker with `docker compose`
- An LLM provider key if you want live model-backed agent-platform execution

## Run the Full Stack Locally

### 1. Install backend dependencies

```bash
(cd backend && uv sync)
```

### 2. Install frontend dependencies

```bash
(cd frontend && pnpm install)
```

### 3. Set up model connections in the web UI

If you only want the UI, API, and local database running, skip this step.

Keep `AGENT_PLATFORM_ENCRYPTION_KEY` set if you want those stored secrets encrypted at rest.

### 4. Start everything with the local helper

```bash
./start.sh
```

`start.sh` is the source of truth for local development.

It will:

- prefer PostgreSQL on `25432`, then fall back to `25433` or `25434` if needed
- prefer the backend on `28000`, then fall back to `28001` or `28002` if the requested port is occupied by a non-Ledger service
- prefer the frontend on `25173`, then fall back to `25174` if needed
- stop previously running Ledger backend, frontend, and local Docker database instances before starting fresh ones
- derive `DATABASE_URL` for backend startup when you do not provide one
- derive `VITE_API_BASE_URL` for frontend startup

### 5. Open the app and verify the stack

Once startup finishes, open:

- Frontend: `http://127.0.0.1:25173/` or the fallback port printed by `start.sh`
- Backend health: `http://127.0.0.1:28000/health` or the fallback backend port printed by `start.sh`

### 6. Stop the stack

Press `Ctrl+C` in the terminal running `./start.sh`.

## Manual Startup

Use this path only if you do not want `./start.sh` managing the stack for you.

### 1. Start PostgreSQL

```bash
(cd backend && docker compose up -d db)
```

Backend compose is DB-only and exposes Postgres on `${LEDGER_DB_PORT:-25432}`.

### 2. Start the backend

```bash
(cd backend && uv run uvicorn app.main:app --reload --port 28000)
```

The default local connection is `postgresql+psycopg://ledger:ledger@localhost:25432/ledger`. If you run the frontend on `25173`, keep backend CORS aligned with that origin through `CORS_ALLOWED_ORIGINS` when you need overrides.

### 3. Start the frontend

```bash
(cd frontend && VITE_API_BASE_URL=http://127.0.0.1:28000/api/v1 pnpm dev --host 127.0.0.1 --port 25173)
```

### 4. Open the app

Visit `http://127.0.0.1:25173/`.

## Runtime Notes

- The normal browser-facing execution surfaces are Workflow Packages, Model Connections, and Runs, plus the preserved portfolio, template, and report routes.
- Workflow package manifests use `ledger.workflowPackage/v1`; package-private agents, output schemas, capability profiles, private MCP configs, and workflow graphs are authored inside one package.
- Keep `AGENT_PLATFORM_ENCRYPTION_KEY` set so stored model-connection secrets remain encrypted at rest.
- Playwright E2E uses Chromium only with dedicated startup helpers: backend `8001`, frontend preview `4173`, deterministic quote provider, and frontend API base `http://127.0.0.1:8001/api/v1` by default.
- `docs/run-input-schema-helptext.md` explains optional `title` and `description` metadata for generated run input form labels and help text.
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
- `docker-images.yml` builds backend and frontend linux/arm64 images for GitHub Container Registry
- `cleanup.yml` keeps at least 3 recent workflow runs and deletes untagged backend/frontend container packages

## Versioning

- `backend/pyproject.toml` is the backend package version surface
- `frontend/package.json` is the frontend package version surface
- `backend/VERSION` must mirror the backend package version
- `frontend/VERSION` must mirror the frontend package version

The VERSION files are lightweight mirrors used for repository-level checks; this repo does not add a separate release system here.

## More Detail

- `backend/README.md` covers backend-specific development details
- `AGENTS.md` maps the repo's live surfaces and nested documentation hierarchy
- `docs/prd.md`, `docs/requirements.md`, `docs/spec.md`, `docs/api-design.md`, and `docs/data-model.md` are current product, requirements, API, and data references
- `docs/test-plan.md` and `docs/run-input-schema-helptext.md` cover validation and generated run-input form metadata
- `docs/ledger-agent-platform.md` is the canonical package-first platform reference
- `docs/ledger-memory-layer-design.md` records the live phase 1 report-backed memory boundary
