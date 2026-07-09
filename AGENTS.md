# SignalDeck Agent Guide

SignalDeck is a trusted single-user mini-Jenkins for LLM agents: YAML Workflow Packages define multi-agent pipelines, manual or scheduled launches enqueue runs, and operators inspect run evidence and outputs.
Prefer clean current architecture over compatibility shims, legacy stubs, or speculative compatibility paths; no user auth/RBAC, multi-tenant accounts, plugin marketplace, Studio, Tryout, orchestration, runtime-v2, memory, fork, or portfolio scope unless explicitly re-scoped.

## Communication
- Do not send optional progress commentary; report required results, blockers, and final status.
- Do not revert or stage user changes you did not make.

## Directory Overview
- `backend/`: FastAPI, SQLAlchemy models, services, runtime tools, scheduler worker, and pytest suite.
- `frontend/`: React/Vite app, TanStack Query, shadcn/ui, Vitest, and Playwright E2E.
- `docs/`: concise product/data docs plus retained extension-writing guidance.
- `demo/`: grounded Workflow Package YAML examples.
- `.github/workflows/`: CI gates and Docker image publishing.
- `start.sh`, `Dockerfile`, `docker-compose.yml`: local/demo combined stack wrapper.

## Current Product Shape
- Workflow Packages are the only agent-workflow authoring root; package-local agents, output schemas, capability profiles, private MCP configs, HTTP operation nodes, and workflow graphs live in package YAML artifacts.
- Scheduled Tasks target Workflow Packages, use structured recurrence plus IANA timezones, and materialize due fires into ordinary queued runs.
- Model Connections are global encrypted provider/model bindings; Tools are read-only server-declared metadata at `/api/tools`.
- Runs store immutable package snapshots, inputs, per-step evidence, operation evidence, queue/progress state, retry/failure metadata, rerun lineage, and final outputs.
- `signaldeck.finance` is a static backend extension for templates, reports, finance providers, and finance runtime tools.
- `signaldeck.digital_oracle` is a static tool-only backend extension.
- Templates and Reports remain preserved product surfaces under `/api/v1` and browser routes `/templates` and `/reports`.

## API And Data Conventions
- Backend JSON is camelCase externally and snake_case internally; `CamelModel` owns aliases and request validation.
- Error envelopes are `{code, message, details[]}`.
- Money, quantities, and market values cross the API as strings.
- Secret values must never appear in reads, exports, run details, logs, diagnostics, or metadata.
- Schema changes = rebuild DB: there is no migration framework; `backend/app/db/` uses `create_all`, bundled seeds, and startup recovery.

## Validation
```bash
(cd backend && uv sync)
(cd frontend && pnpm install)
(cd backend && uv run ruff check app tests && uv run black --check app tests && uv run isort --check-only app tests && uv run mypy app && uv run pytest)
(cd frontend && pnpm lint)
(cd frontend && pnpm typecheck)
(cd frontend && pnpm build)
(cd frontend && pnpm test:run)
(cd frontend && pnpm exec playwright install --with-deps chromium && pnpm test:e2e)
git diff --check
```

## Local Stack
```bash
./start.sh
docker compose -f docker-compose.yml down
docker compose -f docker-compose.yml down -v
```
`start.sh` is the authoritative local/demo launcher and exposes only `http://localhost:${APP_PORT:-8080}`.

## Secure Deployment
Set `SIGNALDECK_API_TOKEN` or put the app behind an authenticated reverse proxy before exposing it outside a trusted network.
Use the supported backend/frontend production images with managed PostgreSQL, HTTPS, backups, and non-placeholder `AGENT_PLATFORM_ENCRYPTION_KEY` values; the root combined image is local/demo only.
