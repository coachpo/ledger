# Technical Specification

> Status: Live technical reference for branch `main` at `987686e`.

## Overview

SignalDeck is a dual-stack FastAPI and React/Vite application with preserved portfolio/report/template workflows and a package-first agent platform. Backend JSON is camelCase externally and snake_case internally. Preserved product routes live under `/api/v1` as the bundled `signaldeck.finance` extension, enabled by default; platform routes live under `/api/*`.

## Runtime Topology

- Root startup is managed by `start.sh` with PostgreSQL `25432`, backend `28000`, and frontend `25173` defaults plus fallback ports `25433/25434`, `28001/28002`, and `25174`.
- Manual backend startup expects PostgreSQL from `backend/docker-compose.yml`, which defines only the `db` service.
- Playwright starts dedicated E2E servers on backend `8001` and frontend `4173` through frontend startup scripts.
- Backend requires Python 3.13+, frontend targets Node 24 and pnpm 10.

## Backend Architecture

- `backend/app/main.py` owns app creation, exception handlers, CORS, and health.
- `backend/app/api/router.py` is the `/api/v1` composition host for the bundled finance workspace routes.
- `backend/app/api/platform_router.py` mounts current `/api/*` routers for workflow packages, model connections, extensions, tools, and runs.
- `backend/app/extensions/signaldeck_finance/` contributes the current finance/product/provider surfaces as `signaldeck.finance`, with startup and reset/seed defaults keeping it enabled.
- `backend/app/api/dependencies.py` is the service composition root.
- `backend/app/core/telemetry.py` owns optional Logfire setup and trace/span id formatting for persisted run metadata.
- `backend/app/db/` owns PostgreSQL session lifecycle and startup schema repair; Alembic is not the live migration authority.

## Key Backend Services

- Portfolio, balance, position, CSV import, trading operation, market data, template, report, provider, and report-backed memory services are finance workspace contributions.
- Workflow package, model connection, extension-state, tool catalog, and run services own platform authoring, validation, live bindings, enable/disable state, execution, reruns, and step replays.
- Runtime tool and MCP boundaries live under `backend/app/agents/`; package-private MCP configs are validated and dispatched only through service-owned security boundaries.
- Application LLM calls go through official SDK clients inside service-owned integration boundaries.

## Frontend Architecture

- `frontend/src/App.tsx` creates the TanStack Query client, theme provider, error boundary, and router provider.
- `frontend/src/routes.ts` defines flat routes for dashboard, portfolios, templates, reports, Workflow Packages, Model Connections, and Runs.
- `frontend/src/components/layout.tsx` owns sidebar labels, breadcrumbs, and the app shell.
- API helpers live under `frontend/src/lib/api/`; wire types live under `frontend/src/lib/types/`; query keys live in `frontend/src/lib/query-keys.ts`.
- Platform authoring helpers under `frontend/src/lib/platform-authoring/` keep schema/value/ref/manifest transforms out of routed pages.

## Domain Contracts

- Workflow Packages are canonical for platform authoring. Use `/api/workflow-packages`, `/workflow-packages*`, `signaldeck.workflowPackage/v1`, and package-local agents, output schemas, capability profiles, and workflow graphs. Private MCP configs are flat inline `env`, `headers`, and `query` manifest text, and that export/import contract is intentionally breaking.
- Removed global authoring routes include `/api/agents`, `/api/capabilities`, `/api/mcp-servers`, `/api/output-schemas`, `/api/workflows`, `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, and `/workflows*`. They are not aliases or redirects.
- Package exports keep private MCP `env`, `headers`, and `query` values inline and still omit database ids and run history.
- Model Connections own live provider endpoint/key/default runtime settings and preserve secret-safe behavior.
- Tools are read-only server-declared metadata exposed through the core `/api/tools` host and referenced by package-local capability profiles. Current finance tool entries come from enabled `signaldeck.finance` contributions.
- `signaldeck.finance` supports enable/disable state only and is enabled by default during `init_db()` and reset/seed startup.
- Runs persist package lineage in `runs`, `run_steps`, and `run_agent_invocations`; optional Logfire spans populate stored trace ids and invocation span ids, but execution still works without a Logfire token.

## Data Flow Highlights

1. Portfolio detail loads portfolio, balances, positions, operations, and quote enrichment through TanStack Query.
2. Template preview debounces source/runtime-input changes, then compiles via backend placeholder resolution.
3. Report generation compiles templates into immutable markdown snapshots with generated slug/name values.
4. Reusable report-series loops use a stable runtime input such as `inputs.analysis_tag` plus matching report `metadata.tags`; `reports.by_tag(inputs.analysis_tag).latest.*` selects the latest prior report in the same series.
5. Report content selected through `.content` is recompiled, so edited historical reports can affect later compiles; circular report references render explicit sentinels instead of looping.
6. Workflow package editors validate `signaldeck.workflowPackage/v1` YAML, package-local references, global tool keys, and model connection keys before save.
7. Package launch reads launch metadata, posts `{version, workflowKey, parameters}`, queues a run, and polls run detail/list state with package provenance.
8. Rerun and step replay flows draft from persisted run state, then create new run/replay records through platform routes.

## CI And Verification

- `version-sync` checks `backend/VERSION` against `backend/pyproject.toml` and `frontend/VERSION` against `frontend/package.json`.
- Backend CI runs ruff, black, isort, mypy, and pytest after `uv sync --frozen`.
- Frontend CI runs lint, typecheck, build, unit tests, and Playwright after `pnpm install --frozen-lockfile`.
- Docker image publishing builds backend and frontend linux/arm64 images for GHCR.
- Cleanup keeps at least 3 recent workflow runs and removes untagged backend/frontend package versions.
