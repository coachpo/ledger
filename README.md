# Ledger

Ledger is a monorepo for a portfolio-tracking stack with a FastAPI backend, a React/Vite frontend, markdown report workflows, orchestration roles and characters, and v2 runtime, Studio, and Tryout surfaces.

## Repository Layout

- `backend/` — FastAPI, SQLAlchemy, Pydantic, PostgreSQL-backed API and tests
- `frontend/` — React 19, Vite, TanStack Query, Vitest, and Playwright app
- `docs/` — orchestration design, PRD, and spec notes; secondary to live code
- `.github/workflows/` — root CI, Docker image, and cleanup workflows
- `start.sh` — local full-stack startup helper with backend/frontend/db fallback logic

## What Ships

- Frontend routes for `portfolios`, `templates`, `reports`, `tryout`, `studio`, and `orchestration`
- Backend `/api/v1` resource routes for portfolios, balances, positions, trading operations, market data, templates, reports, and orchestration
- Backend `/api/v2` routes for runtime runs, approvals, Studio inspection reads, Tryout execution, and spec catalogs

## Prerequisites

- Python 3.13+
- Node 24+
- pnpm 10+
- uv
- lsof
- Docker with `docker compose`
- An LLM provider key if you want live model-backed runtime and Tryout execution

## Run the Full Stack Locally

### 1. Install backend dependencies

```bash
(cd backend && uv sync)
```

### 2. Install frontend dependencies

```bash
(cd frontend && pnpm install)
```

### 3. Optionally export runtime provider settings

If you only want the UI, API, and local database running, skip this step.

If you want live model-backed runtime or Tryout execution, export the provider settings before startup:

```bash
export OPENAI_API_KEY="your-provider-key"
export RUNTIME_AGENT_API_KEY="$OPENAI_API_KEY"
export RUNTIME_AGENT_MODEL="gpt-5.4-mini"
export RUNTIME_AGENT_BASE_URL="http://127.0.0.1:8080/v1"   # optional override
export RUNTIME_AGENT_TEMPERATURE="0"
```

### 4. Start everything with the local helper

```bash
./start.sh
```

`start.sh` is the source of truth for local development.

It will:

- prefer PostgreSQL on `25432`, then fall back to `25433` or `25434` if needed
- prefer the backend on `28000`, then fall back to `28001` or `28002` if the requested port is occupied by a non-Ledger service
- prefer the frontend on `25173`, then fall back to `25174` if needed
- reuse a healthy Ledger backend already listening on the requested backend port
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

- The normal browser-facing execution surfaces are `Tryout`, `Studio`, and the backend v2 runtime APIs.
- Runtime execution inherits its provider settings from the backend process, so export `RUNTIME_AGENT_*` variables before starting the backend if you want live model calls.
- Playwright uses dedicated backend and frontend startup helpers on ports `8001` and `4173` for E2E coverage.
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

- `ci.yml` runs root validation: version sync, backend quality, frontend quality, and frontend E2E
- `docker-images.yml` builds backend and frontend container images for GitHub Container Registry
- `cleanup.yml` deletes old workflow runs and untagged container packages

## Versioning

- `backend/pyproject.toml` is the backend package version surface
- `frontend/package.json` is the frontend package version surface
- `backend/VERSION` must mirror the backend package version
- `frontend/VERSION` must mirror the frontend package version

The VERSION files are lightweight mirrors used for repository-level checks; this repo does not add a separate release system here.

## More Detail

- `backend/README.md` covers backend-specific development details
- `AGENTS.md` maps the repo’s live surfaces and nested documentation hierarchy
- `docs/ledger-orchestration-product-design.md`, `docs/ledger-orchestration-product-prd.md`, and `docs/ledger-orchestration-product-spec.md` capture the current orchestration-oriented product notes
