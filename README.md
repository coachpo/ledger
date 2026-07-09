# SignalDeck

SignalDeck is a self-hosted mini-Jenkins for LLM agents: YAML Workflow Packages define multi-agent pipelines, manual or scheduled launches enqueue runs, and operators inspect execution evidence, outputs, templates, and reports from one FastAPI + React/Vite stack.

## Repository Layout

- `backend/` — FastAPI, SQLAlchemy, Pydantic, PostgreSQL-backed API and tests
- `frontend/` — React 19, Vite, TanStack Query, Vitest, and Playwright app
- `docs/` — concise product, development, data-model, and static extension guidance
- `demo/` — grounded Workflow Package YAML examples
- `.github/workflows/` — root CI and Docker image workflows
- `start.sh` — local Docker Compose launcher for the root combined stack

## What Ships

- Browser routes for Templates, Reports, Workflow Packages, Scheduled Tasks, Model Connections, and Runs
- `/api/v1/templates` and `/api/v1/reports` from the static `signaldeck.finance` backend extension
- `/api/workflow-packages`, `/api/schedules`, `/api/model-connections`, `/api/tools`, and `/api/runs`
- Static runtime-tool extensions: `signaldeck.finance` for finance workspace/tools and `signaldeck.digital_oracle` for Digital Oracle tools

## Workflow Runner Contract

Workflow Packages are the only executable authoring root. Package manifests use `signaldeck.workflowPackage/v1` YAML and keep agents, output schemas, capability profiles, private MCP configs, HTTP operation nodes, and workflow graphs package-private.

Model Connections are global encrypted provider bindings. Tools are read-only server-declared metadata from `/api/tools`; packages reference canonical owner-qualified tool keys through local capability profiles. Package exports omit secret-bearing private MCP `env`, `headers`, and `query` values along with database ids, run history, package secret binding rows, and raw secret values.

Scheduled Tasks use structured recurrence and IANA timezones to materialize due fires into ordinary queued runs. Runs store immutable executable snapshots, queue/progress state, invocation evidence, operation evidence, retry/failure metadata, trace ids when configured, final output, and rerun lineage. `POST /api/runs/{id}/cancel` cancels queued runs immediately; running runs stop cooperatively at step boundaries.

## Prerequisites

- Docker with `docker compose` for the containerized local stack
- Python 3.13+, Node 24+, pnpm 10+, and uv for validation commands
- An LLM provider key for live model-backed execution

## Run The Full Stack Locally

```bash
./start.sh
```

`start.sh` is the source of truth for the local/demo stack. It builds the root combined image, starts PostgreSQL/pgvector plus the app container, runs Nginx, FastAPI, and the scheduler worker inside the app container, and publishes only `http://localhost:${APP_PORT:-8080}`.

Open:

- App: `http://localhost:${APP_PORT:-8080}`
- Health: `http://localhost:${APP_PORT:-8080}/health`
- Readiness: `http://localhost:${APP_PORT:-8080}/ready`

Stop with `Ctrl+C`, or run:

```bash
docker compose -f docker-compose.yml down
docker compose -f docker-compose.yml down -v
```

## Direct Compose

```bash
docker compose -f docker-compose.yml up --build --remove-orphans
docker compose -f docker-compose.yml down
docker compose -f docker-compose.yml down -v
```

The root Dockerfile and root Compose stack are local/demo only. They keep PostgreSQL and the backend private to Docker networking by default and expose the app through Nginx.

## Production Images

CI publishes supported backend and frontend images from `backend/Dockerfile` and `frontend/Dockerfile`:

- `ghcr.io/<owner>/signaldeck-backend`
- `ghcr.io/<owner>/signaldeck-frontend`

Published images include Docker Buildx provenance and SBOM attestations on non-PR pushes. The root combined image is not a production artifact and refuses `SIGNALDECK_RUNTIME_MODE=production`, `prod`, or `staging`.

### Split deployment topology

Production runs as three container roles:

- `backend` serves the FastAPI HTTP API.
- `scheduler` runs `python -m app.workers.run_scheduler` from the same backend image.
- `frontend` serves the browser app and proxies `/api` traffic to the backend.

The scheduler container is required in production. Launches only enqueue runs; without the scheduler worker those runs stay `queued` forever. Multiple scheduler replicas are safe because coordination uses a PostgreSQL advisory lock, so only one worker owns a lease slot at a time.

The example compose requires `SIGNALDECK_IMAGE_TAG`; pin it to an immutable published tag (a release tag once one exists, or an image digest/sha tag from the Docker Images workflow) rather than a mutable `latest` tag. It also requires `SIGNALDECK_API_TOKEN`; deployments that rely only on an authenticated reverse proxy should remove that environment entry deliberately.

See [docker/compose.production.example.yml](docker/compose.production.example.yml) for the supported split-image example.

## Runtime Configuration

- `SIGNALDECK_RUNTIME_MODE` defaults to `local`; production images set it to `production`.
- `DATABASE_URL` is required in production and should point at managed PostgreSQL 16+. Provider-style `postgresql://` and `postgres://` URLs are accepted and normalized to the `postgresql+psycopg://` driver automatically; the `pgvector` extension is not required.
- `AGENT_PLATFORM_ENCRYPTION_KEY` protects stored model-connection and package-secret values; production rejects the local placeholder.
- `SIGNALDECK_API_TOKEN` enables bearer-token protection.
- `PUBLIC_BASE_URL` is the externally reachable app origin when absolute links are needed.
- `CORS_ALLOWED_ORIGINS` should list allowed browser origins for separate-origin frontend deployments; same-origin reverse-proxy deployments do not need CORS.
- `MCP_RUNTIME_ENABLED` defaults to `false`. In the split production topology set it on the `scheduler` container — the scheduler executes runs, so MCP settings on the API container alone have no effect.
- `MCP_RUNTIME_TIMEOUT` controls MCP runtime request timeouts in seconds and defaults to `5`.
- `BACKEND_UPSTREAM` (frontend image only) is the `host:port` the bundled nginx proxies `/api/` to; the image default `127.0.0.1:8000` only works when backend and frontend share a network namespace, so compose deployments set it to `backend:8000`.
- `RUN_SCHEDULER=true|false` only affects the root local/demo image entrypoint; production deployments run the scheduler as a separate container.
- `SIGNALDECK_RUN_RETENTION_DAYS` controls run-history retention and is disabled unless set.

## Security

Set `SIGNALDECK_API_TOKEN` and send `Authorization: Bearer <token>`, or place SignalDeck behind an authenticated reverse proxy such as oauth2-proxy, Tailscale, or another access gateway.
Use HTTPS, managed PostgreSQL, backups, and non-placeholder secret values before exposing the app outside a trusted network.

## Backup

Use a libpq-style PostgreSQL URL for database tools:

```bash
pg_dump "$POSTGRES_URL" > signaldeck.sql
psql "$POSTGRES_URL" < signaldeck.sql
```

**Back up `AGENT_PLATFORM_ENCRYPTION_KEY` with every `pg_dump`. SignalDeck currently uses a single-key Fernet encryption model; losing that key makes stored model-connection and package-secret values undecryptable, API reads can return 500, there is no rotation or re-encryption tool yet, and the only recovery path is re-entering every secret. Generate a high-entropy key with `openssl rand -base64 32`.**

## Schema Changes

SignalDeck has no migration framework; schema changes require rebuilding the database.

## Validation

```bash
# Backend
(cd backend && uv run ruff check app tests && uv run black --check app tests && uv run isort --check-only app tests && uv run mypy app && uv run pytest)

# Frontend
(cd frontend && pnpm lint)
(cd frontend && pnpm typecheck)
(cd frontend && pnpm build)
(cd frontend && pnpm test:run)
(cd frontend && pnpm exec playwright install --with-deps chromium && pnpm test:e2e)
```

## CI/CD Workflows

- `ci.yml` runs version sync, backend quality, frontend quality, and frontend E2E.
- Backend CI installs with `uv sync --frozen`; frontend CI installs with `pnpm install --frozen-lockfile`.
- `docker-images.yml` builds and publishes backend/frontend linux/amd64 and linux/arm64 images for GitHub Container Registry with SBOM/provenance metadata on non-PR pushes.

## Versioning

- `backend/pyproject.toml` is the backend package version surface.
- `frontend/package.json` is the frontend package version surface.
- `backend/VERSION` must mirror the backend package version.
- `frontend/VERSION` must mirror the frontend package version.

## More Detail

- `backend/README.md` covers backend-specific development details.
- `AGENTS.md` is the repository-wide agent guide.
- `docs/product.md`, `docs/development.md`, `docs/data-model.md`, and `docs/writing-extensions.md` cover the shipped product shape, repo toolchain, persistence shape, and static extension contract.
