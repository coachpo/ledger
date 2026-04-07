# Ledger Backend

FastAPI backend for the portfolio-tracking MVP described in `../docs/`.

## Local Development

```bash
uv sync
docker compose up -d db
PUBLIC_BASE_URL=http://127.0.0.1:28000 uv run uvicorn app.main:app --reload --port 28000
uv run uvicorn app.worker.main:app --port 8010
```

Copy `.env.example` when you want an explicit local config. The backend now expects PostgreSQL everywhere; the default local connection is `postgresql+psycopg://ledger:ledger@localhost:25432/ledger`, so local `uv run uvicorn ...` startup requires PostgreSQL already running on that port. CORS is enabled for local Vite dev hosts by default and can be overridden through `CORS_ALLOWED_ORIGINS`. When you run webhook backtests against the separate TradingAgents worker, `PUBLIC_BASE_URL` must be set to an absolute backend URL so the worker can resolve report-download and callback endpoints, and the backend environment must include a supported TradingAgents provider credential such as `OPENAI_API_KEY`.

The test suite creates and drops temporary PostgreSQL databases. Set `TEST_DATABASE_URL` or `DATABASE_URL` to a PostgreSQL connection with permission to connect to `postgres` and create/drop databases when you run `uv run pytest` outside Docker.

## Docker Compose

`docker-compose.yml` starts PostgreSQL for local development, exposes it on host port
`25432`, and points the API container at the internal `db:5432` service address.

```bash
docker compose up --build
```

The API is exposed on `http://localhost:8000`.
PostgreSQL is exposed on `localhost:25432`.

To reset the container-managed PostgreSQL data:

```bash
docker compose down -v
```
