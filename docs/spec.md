# Technical Specification

> Status: Live technical reference for branch `main` at `f9ae90d`.

## Overview

SignalDeck is a dual-stack FastAPI and React/Vite application with preserved portfolio/report/template workflows and a package-first agent platform. Backend JSON is camelCase externally and snake_case internally. Preserved product routes live under `/api/v1` as the bundled `signaldeck.finance` extension, enabled by default; platform routes live under `/api/*`.

## Runtime Topology

- Root startup is managed by `start.sh` with PostgreSQL `25432`, backend `28000`, frontend `25173`, and the scheduler worker as a sibling backend process; fallback ports are `25433/25434`, `28001/28002`, and `25174`.
- Manual backend startup expects PostgreSQL from `backend/docker-compose.yml`, which defines only the `db` service, plus a separate `uv run python -m app.workers.run_scheduler` process when queued Workflow Package runs should execute.
- Playwright starts dedicated E2E servers on backend `8001` and frontend `4173` through frontend startup scripts; the backend helper also launches the scheduler worker.
- Backend requires Python 3.13+, frontend targets Node 24 and pnpm 10.

## Backend Architecture

- `backend/app/main.py` owns app creation, exception handlers, CORS, and health.
- `backend/app/api/router.py` is the `/api/v1` composition host for the bundled finance workspace routes.
- `backend/app/api/platform_router.py` mounts current `/api/*` routers for workflow packages, model connections, extensions, tools, and runs.
- `backend/app/extensions/signaldeck_finance/` contributes the current finance/product/provider surfaces as `signaldeck.finance`, with startup and reset/seed defaults keeping it enabled.
- Backend extension registry data is private operational wiring: extension key, label, initial enabled seed, registrar paths, and owner keys for route, tool, runtime, provider, and hook gating.
- `backend/app/api/dependencies.py` is the service composition root.
- `backend/app/core/telemetry.py` owns optional Logfire setup and trace/span id formatting for persisted run metadata.
- `backend/app/db/` owns PostgreSQL session lifecycle and startup schema repair; Alembic is not the live migration authority.

## Key Backend Services

- Portfolio, balance, position, CSV import, trading operation, market data, template, report, and provider services are finance workspace contributions. Core memory services are platform-owned and remain available when finance is disabled.
- Workflow package, model connection, extension-state, tool catalog, core memory, and run services own platform authoring, validation, live bindings, enable/disable state, execution evidence, reruns, forks, and read-only historical replay lineage.
- Model execution goes through the platform Model Gateway. `AgentExecutionService` builds normalized requests, the gateway selects `openai_chat_completions` or `openai_responses` protocol adapters from the resolved `protocolProfile`, and adapter code owns official SDK calls, provider wire payloads, usage parsing, tool-call conversion, and provider error normalization.
- Runtime tool and MCP boundaries live under `backend/app/agents/`; package-private MCP configs are validated and dispatched only through service-owned security boundaries.
- Application LLM calls go through official SDK clients inside service-owned integration boundaries.

## Frontend Architecture

- `frontend/src/App.tsx` creates the TanStack Query client, theme provider, error boundary, and router provider.
- `frontend/src/routes.ts` defines flat routes for dashboard, portfolios, templates, reports, Workflow Packages, Model Connections, and Runs. Phase 1 keeps `/workflow-packages/:packageId/run` as the dedicated `Launch Workflow Package` page.
- `frontend/src/components/layout.tsx` owns sidebar labels, breadcrumbs, and the app shell.
- API helpers live under `frontend/src/lib/api/`; wire types live under `frontend/src/lib/types/`; query keys live in `frontend/src/lib/query-keys.ts`.
- Platform authoring helpers under `frontend/src/lib/platform-authoring/` keep schema/value/ref/manifest transforms out of routed pages.

## Domain Contracts

- Workflow Packages are canonical for platform authoring. Use `/api/workflow-packages`, `/workflow-packages*`, `signaldeck.workflowPackage/v1`, and package-local agents, output schemas, capability profiles, and workflow graphs. Private MCP configs are flat inline `env`, `headers`, and `query` manifest text, and that export/import contract is intentionally breaking.
- Removed global authoring routes include `/api/agents`, `/api/capabilities`, `/api/mcp-servers`, `/api/output-schemas`, `/api/workflows`, `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, and `/workflows*`. They are not aliases or redirects.
- Package exports keep private MCP `env`, `headers`, and `query` values inline and still omit database ids and run history.
- Model Connections own live provider endpoint, model id, `protocolProfile`, declared or probed `capabilities`, output/tool/reasoning/streaming policy defaults, probe cache metadata, timeout, encrypted API key material, and reachability-test metadata. Public reads are secret-safe and keep `apiStyle` only as historical compatibility metadata derived from `protocolProfile`.
- Capability-aware preflight derives package requirements from output schemas, package-local capability-profile tool grants, and runtime needs. Unsupported required capabilities are blockers before run creation; optional or inconclusive states surface as warnings.
- Tools are read-only server-declared metadata exposed through the core `/api/tools` host and referenced by package-local capability profiles. Current finance tool entries appear only while `signaldeck.finance` is enabled; `signaldeck.memory.write` and `signaldeck.memory.lookup` are platform-core tools.
- `signaldeck.finance` supports enable/disable state only and is enabled by default during `init_db()` and reset/seed startup. `/api/extensions` exposes only `key`, `label`, and `enabled`.
- Runs persist package lineage in `runs`, `run_steps`, `run_agent_invocations`, `run_operation_invocations`, and `run_forks`; optional Logfire spans populate stored trace ids and invocation span ids, but execution still works without a Logfire token. Run memory evidence persists in `run_memory_events`, and run extension data is dependency-only with only extension key, surfaces, and fields.

## Data Flow Highlights

1. Portfolio detail loads portfolio, balances, positions, operations, and quote enrichment through TanStack Query.
2. Template preview debounces source/runtime-input changes, then compiles via backend placeholder resolution.
3. Report generation compiles templates into immutable markdown snapshots with generated slug/name values.
4. Reusable report-series loops use a stable runtime input such as `inputs.analysis_tag` plus matching report `metadata.tags`; `reports.by_tag(inputs.analysis_tag).latest.*` selects the latest prior report in the same series.
5. Report content selected through `.content` is recompiled, so edited historical reports can affect later compiles; circular report references render explicit sentinels instead of looping.
6. Workflow package editors are authoring-only surfaces that validate `signaldeck.workflowPackage/v1` YAML, package-local references, global tool keys, and model connection keys before save.
7. The dedicated launch page at `/workflow-packages/:packageId/run` reads launch metadata, runs capability-aware preflight gating, posts the selected workflow key with `parameters`, queues a run, and polls backend-owned progress/queue state with package provenance and persisted memory evidence while the scheduler worker claims queued runs.
8. Run creation freezes the selected package artifact and the non-secret effective runtime profile for each resolved Model Connection. Fresh launches bind to live connections; reruns and forks replay the stored runtime profile by default while still requiring live secrets and current readiness checks.
9. Rerun drafts from root launch parameters and creates a descendant run with edited `parameters`; fork drafts from a selected source agent invocation and creates a descendant run with edited `invocationInput`, copied upstream context, and `resumeStepIndex` as the execution boundary.

## CI And Verification

- `version-sync` checks `backend/VERSION` against `backend/pyproject.toml` and `frontend/VERSION` against `frontend/package.json`.
- Backend CI runs ruff, black, isort, mypy, and pytest after `uv sync --frozen`.
- Frontend CI runs lint, typecheck, build, unit tests, and Playwright after `pnpm install --frozen-lockfile`.
- Docker image publishing builds backend and frontend linux/arm64 images for GHCR.
- Cleanup keeps at least 3 recent workflow runs and removes untagged backend/frontend package versions.
