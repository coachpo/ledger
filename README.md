# Ledger

Ledger is a monorepo for a portfolio-tracking stack with a FastAPI backend, a React/Vite frontend, report generation, template compilation, and a simulation workspace.

## Repository Layout

- `backend/` — FastAPI, SQLAlchemy, Pydantic, PostgreSQL-backed API and tests
- `frontend/` — React 19, Vite, TanStack Query, Vitest, and Playwright app
- `docs/` — project docs and test-plan references
- `.github/workflows/` — root CI, Docker image, and cleanup workflows
- `start.sh` — local full-stack startup helper

## Prerequisites

- Python 3.13+
- Node 24+
- pnpm 10+
- uv
- lsof
- Docker with `docker compose`
- An LLM provider key if you want to run live LangGraph-backed simulations

## Run the Full Stack Locally (101 Guide)

### Step 1: Make sure you have a full source checkout

Before you run anything, make sure your checkout includes the real source files and helper scripts that the commands below rely on.

At minimum, you should have these paths:

- `start.sh`
- `backend/pyproject.toml`
- `frontend/package.json`

If any of those are missing, re-clone or restore the full repository checkout first.

### Step 2: Install backend dependencies

```bash
(cd backend && uv sync)
```

### Step 3: Install frontend dependencies

```bash
(cd frontend && pnpm install)
```

### Step 4: Export LangGraph simulation settings if you want live AI-backed simulations

If you only want the UI, backend, and local stack up, you can skip this step.

If you want the internal LangGraph simulation runner to make real model calls, export the provider settings before startup:

```bash
export OPENAI_API_KEY="your-provider-key"
export RUNTIME_AGENT_API_KEY="$OPENAI_API_KEY"
export RUNTIME_AGENT_MODEL="gpt-5.4-mini"
export RUNTIME_AGENT_BASE_URL="http://192.168.1.222:8087/v1"    # optional override
export RUNTIME_AGENT_TEMPERATURE="0"
```

### Step 5: Start everything with the local helper

```bash
./start.sh
```

`start.sh` is the source of truth for local development. It syncs the backend environment, starts PostgreSQL on `25432`, the backend on `28000`, and the frontend on `25173`.

It also:

- sets `DATABASE_URL` for the backend,
- derives `VITE_API_BASE_URL` for the frontend,
- sets `PUBLIC_BASE_URL` for the backend if you do not provide one,
- and stops listeners or Docker containers already using ports `25432`, `28000`, or `25173` before startup.

### Step 6: Open the app and verify the stack

Once startup finishes, open:

- Frontend: `http://127.0.0.1:25173/`
- Backend health: `http://127.0.0.1:28000/health`

### Step 7: Stop the stack

Press `Ctrl+C` in the terminal running `./start.sh`.

## Important LangGraph Simulation Notes

- LangGraph simulations now run inside Ledger's backend runtime; there is no separate worker process to start.
- `PUBLIC_BASE_URL` is no longer required for the normal internal simulation path, but leaving it set is harmless.
- If you need the backend reachable from another machine, set `BACKEND_HOST=0.0.0.0`, `BACKEND_PUBLIC_HOST=<your-lan-ip>`, and `PUBLIC_BASE_URL=http://<your-lan-ip>:28000` before running `./start.sh`.
- The LangGraph runner inherits its model settings from the backend process, so `RUNTIME_AGENT_*` variables must be exported before you start the backend if you want live model calls.

## Manual Startup (without `start.sh`)

Use this path only if you do not want `./start.sh` managing the stack for you.

### 1. Start PostgreSQL

```bash
(cd backend && docker compose up -d db)
```

### 2. Start the backend

```bash
(cd backend && CORS_ALLOWED_ORIGINS=http://127.0.0.1:25173,http://localhost:25173 PUBLIC_BASE_URL=http://127.0.0.1:28000 uv run uvicorn app.main:app --reload --port 28000)
```

### 3. Start the frontend

```bash
(cd frontend && VITE_API_BASE_URL=http://127.0.0.1:28000/api/v1 pnpm dev --host 127.0.0.1 --port 25173)
```

### 4. Open the app

Visit `http://127.0.0.1:25173/`.

### 5. Know what is required vs optional for local development

- When you run the frontend manually on `25173`, the backend must allow that origin via `CORS_ALLOWED_ORIGINS`, which is why the backend command above includes it explicitly.

See `backend/README.md` for backend-specific local development details.

## Validation

```bash
# Backend
(cd backend && uv run ruff check app tests && uv run black --check app tests && uv run isort --check-only app tests && uv run mypy app && uv run pytest)

# Frontend
(cd frontend && pnpm lint && pnpm typecheck && pnpm build && pnpm test:run)
(cd frontend && pnpm test:e2e)
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
