# Ledger Backend

FastAPI backend for Ledger’s portfolio, report, and current agent-platform surfaces.

## Local Development

For the easiest full-stack path, run `../start.sh` from the repo root.

If you want the backend on its own:

```bash
uv sync
docker compose up -d db
uv run uvicorn app.main:app --reload --port 28000
```

The backend expects PostgreSQL everywhere. The default local connection is `postgresql+psycopg://ledger:ledger@localhost:25432/ledger`, so manual `uv run uvicorn ...` startup assumes PostgreSQL is already running on that port. CORS is enabled for common local Vite dev hosts by default and can be overridden through `CORS_ALLOWED_ORIGINS`.

## Model Connections

Keep `AGENT_PLATFORM_ENCRYPTION_KEY` set so stored model-connection secrets remain encrypted at rest.

## Live API Surfaces

- `/health` for backend health
- `/api/v1` for portfolios, balances, positions, trading operations, market data, templates, and reports
- `/api/*` for agents, capabilities, MCP servers, model connections, output schemas, workflows, and runs
- `/api/capabilities` for capability CRUD with `toolGrants`

## Tests

The test suite creates and drops temporary PostgreSQL databases. Set `TEST_DATABASE_URL` or `DATABASE_URL` to a PostgreSQL connection with permission to connect to `postgres` and create/drop databases when you run `uv run pytest` outside Docker.

```bash
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest
```

## Docker Compose

`docker-compose.yml` starts PostgreSQL for local development, exposes it on host port `25432`, and points the API container at the internal `db:5432` service address.

```bash
docker compose up --build
```

The API container is exposed on `http://localhost:8000`.
PostgreSQL is exposed on `localhost:25432`.

To reset the container-managed PostgreSQL data:

```bash
docker compose down -v
```

## Notes

- `app/db/upgrades.py` is the supported schema-repair path; `alembic/` is scaffolding only.
- Playwright E2E starts a dedicated backend on port `8001` through `frontend/scripts/start-playwright-backend.mjs` and forwards the current environment into that process.
- For repo-wide setup, validation, and frontend wiring, see the root `README.md`.
