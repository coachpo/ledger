# Ledger

Ledger is a monorepo for a portfolio-tracking stack with a FastAPI backend, a React/Vite frontend, report generation, template compilation, and a backtest workspace.

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
- Docker with `docker compose`

## Quick Start

```bash
(cd backend && uv sync)
(cd frontend && pnpm install)
./start.sh
```

The local helper starts PostgreSQL on `25432`, the backend on `28000`, and the frontend on `25173`.

## Direct Development Commands

```bash
# Backend
(cd backend && uv run uvicorn app.main:app --reload --port 28000)

# Frontend
(cd frontend && pnpm dev)
```

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
