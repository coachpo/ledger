# SignalDeck

English | [简体中文](README_CN.md)

SignalDeck is a self-hosted pipeline runner for LLM agents — a mini-Jenkins where the jobs are multi-agent workflows instead of build scripts. It is for anyone who wants to define agent pipelines in YAML, run them manually or on a schedule, and see exactly what happened afterwards.

(The repository is named `ledger`; the product inside is SignalDeck.)

## How it works

- You write a **Workflow Package**: one YAML file describing a pipeline — its inputs, the agents involved, the tools they may call, and how the steps connect (sequence, fan-out, loop, plain HTTP calls).
- You add a **Model Connection**: a saved LLM provider binding (endpoint, model, API key, encrypted at rest) that packages reference by name.
- You launch runs from the web UI, or attach a **Scheduled Task**: a recurrence rule (interval, daily, weekly, or monthly, timezone-aware) that fires runs automatically.
- Every run keeps evidence: step status, each agent invocation with its resolved input and output, HTTP calls, token usage, retries, failures, and the final result. Runs execute from an immutable snapshot of the package, so what you inspect is what actually ran.
- Outputs can become **Reports**: markdown snapshots generated from templates, editable and downloadable from the UI.

The stack is a FastAPI + PostgreSQL backend and a React/Vite frontend.

## Quick start

You need Docker with Compose v2, and an API key for an LLM provider.

```bash
git clone https://github.com/coachpo/ledger.git
cd ledger
./start.sh
```

This builds the combined local image, starts PostgreSQL and the app, and serves everything at `http://localhost:8080` (override with `APP_PORT`). Stop with `Ctrl+C`; tear down with `docker compose down` (add `-v` to also drop the database).

First run:

1. Open `http://localhost:8080`, go to **Model Connections**, and add your LLM provider and API key.
2. Two demo packages are seeded at startup. Open **Workflow Packages**, pick one — *Digital Oracle Researcher* is the simpler of the two — and launch a run.
3. Watch it under **Runs** and drill into the step-by-step evidence.

The YAML sources for both demo packages live in [`demo/`](demo/); they double as reference examples for writing your own. If you prefer plain Compose over the launcher, `docker compose up --build --remove-orphans` does the same thing.

## Deploying for real

The root image is local/demo only and refuses to start in production mode. CI publishes split images instead:

- `ghcr.io/<owner>/signaldeck-backend` — the API; the same image started with `python -m app.workers.run_scheduler` is the scheduler worker
- `ghcr.io/<owner>/signaldeck-frontend` — the browser app, with nginx proxying `/api` to the backend

Production runs three containers: backend, scheduler, frontend. The scheduler is not optional — launches only enqueue runs, and without a scheduler worker they stay `queued` forever. Multiple scheduler replicas are safe; coordination uses a PostgreSQL advisory lock.

Start from [`docker/compose.production.example.yml`](docker/compose.production.example.yml). Pin `SIGNALDECK_IMAGE_TAG` to an immutable tag or digest, and set:

- `DATABASE_URL` — managed PostgreSQL 16+.
- `AGENT_PLATFORM_ENCRYPTION_KEY` — encrypts stored API keys and package secrets. **Back this key up alongside every database dump.** It is a single Fernet key with no rotation tool yet; if you lose it, every stored secret has to be re-entered. `openssl rand -base64 32` generates a good one.
- `SIGNALDECK_API_TOKEN` — bearer-token protection for the whole API. SignalDeck is single-user software with no login system, so either set this or put the app behind an authenticated reverse proxy (oauth2-proxy, Tailscale, and similar).
- `MCP_RUNTIME_ENABLED` — set it on the *scheduler* container if your packages use MCP tools. It defaults to off, and setting it on the API container alone does nothing, because the scheduler is what executes runs.

Two more things worth knowing before you commit data to it:

- There is no migration framework. The schema is created with SQLAlchemy `create_all`, and schema-changing upgrades mean rebuilding the database.
- Run history grows unbounded unless you set `SIGNALDECK_RUN_RETENTION_DAYS`.

Back up with ordinary PostgreSQL tooling (`pg_dump` / `psql`), plus the encryption key above.

## Development

Backend: FastAPI, SQLAlchemy, Pydantic on PostgreSQL, managed with uv (Python 3.13+). Frontend: React 19, Vite, TanStack Query, tested with Vitest and Playwright (Node 24+, pnpm 10+).

```bash
# Backend
(cd backend && uv sync)
(cd backend && uv run ruff check app tests && uv run mypy app && uv run pytest)

# Frontend
(cd frontend && pnpm install)
(cd frontend && pnpm lint && pnpm typecheck && pnpm test:run)
```

CI runs the full gate (formatting, types, unit tests, Playwright E2E, Docker image builds); `docs/development.md` has the exact commands and toolchain pins.

## Repository layout

- `backend/` — API, scheduler worker, and tests
- `frontend/` — web UI
- `demo/` — example Workflow Package YAML
- `docs/` — product shape, data model, development, and extension guide
- `docker/` — production compose example and root-image support files

## Design notes

A few deliberate choices, condensed from `docs/`:

- Trusted single-user app. No accounts, RBAC, or multi-tenancy; access control is the bearer token or your reverse proxy.
- Workflow Packages are self-contained. Agents, output schemas, capability profiles (the package-local lists naming which server-declared tools a package may use), and private MCP configs live inside the package rather than in shared global tables.
- Tool integrations are static Python extensions compiled into the backend: `signaldeck.finance` (market data, news, sentiment, and report tools) and `signaldeck.digital_oracle` (prediction markets, SEC filings, macro, and derivatives tools). There is no plugin marketplace; adding tools means adding code — see `docs/writing-extensions.md`.
- Secrets never leave the server. API keys and package secrets are encrypted at rest, and package exports and run provenance strip secret-bearing values, database ids, and run history.
