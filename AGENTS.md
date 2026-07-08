# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-25
**Commit:** 4045579
**Branch:** main

## OVERVIEW
SignalDeck is a trusted single-user, dual-stack universal agents workflow/pipeline platform with a FastAPI backend and React/Vite frontend. The repo has no external users yet, so prefer clean architecture and current best practices over compatibility shims or speculative legacy paths.

Executable agent workflows enter and run only as Workflow Packages. Standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, runtime-v2, auth/RBAC, and multi-tenant account management are removed or non-goal surfaces unless explicitly re-scoped.

Core ships statically installed extensions: `signaldeck.finance` supplies first-party Finance Workspace template/report routes, runtime tools, and providers, while `signaldeck.digital_oracle` is tool-only. Public runtime tool keys are canonical `signaldeck.<owner>.<tool_collection>.<tool>` strings, and OpenAI function names are the mechanical underscore mapping.

Keep platform-core versus extension-owned boundaries explicit. Decide intentionally whether a capability belongs in generic platform contracts or extension ownership, then align routes, tools, registries, docs, and tests.

## Compatibility, Upgrades, and Removal Policy
- Prefer clean current architecture over compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers unless the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation over dedicated “proves not” tests. Keep absence assertions only when the missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## Upstream Migration Classification
- Provider/data lookups map to extension-owned runtime tools, provider wrappers, and ToolCatalog metadata under the owning bundled extension.
- Upstream roles, prompts, personas, researchers, managers, traders, reviewers, and analysts map to Workflow Package `agents[]`; orchestration graphs and execution topology map to package `workflows[]`.
- Upstream capability sets map to package-local `capabilityProfiles`; generic web/page fetch stays package-private MCP unless product scope promotes a public extension tool.
- Similar functions from different upstream repos remain separate migration obligations. Do not reintroduce retired global authoring, orchestration, runtime-v2, auth/RBAC, or multi-tenant surfaces to close migration gaps.

## CHILD DOCS
- `backend/AGENTS.md`, `backend/app/AGENTS.md`, `backend/app/**/AGENTS.md`, `backend/tests/AGENTS.md` — backend app-layer, runtime, persistence, extension, schema, worker, and test rules
- `.github/workflows/AGENTS.md` — CI gates and container publishing workflow rules
- `docs/AGENTS.md` — live docs ownership, obsolete-content rules, and platform/extension documentation boundary
- `frontend/AGENTS.md`, `frontend/src/components/shared/docs/README.md`, `frontend/e2e/AGENTS.md` — frontend shell, design system, browser tests, and startup conventions
- `frontend/src/{hooks,lib,components,pages}/**/AGENTS.md` — hooks, shared UI, API/types, platform-authoring, and routed page-family rules

## STRUCTURE
```text
signaldeck/
├── backend/              # FastAPI app, SQLAlchemy models, services, pytest suite
├── frontend/             # React/Vite app, TanStack Query, Vitest, Playwright, shadcn/ui
├── docs/                 # canonical owner docs
├── demo/                 # grounded Workflow Package YAML examples
├── .github/workflows/    # CI quality gates and Docker image publishing
└── start.sh              # root Docker Compose wrapper for the local/demo stack
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Bootstrap a fresh clone | `README.md`, `start.sh`, `docker-compose.yml`, `Dockerfile` | for the containerized local stack, install Docker with Compose and run `./start.sh` |
| Start the full stack locally | `start.sh`, `docker-compose.yml`, `Dockerfile`, `docker/entrypoint.sh`, `docker/nginx.conf.template` | builds the root local/demo image, starts `db` and `app`, publishes only `${APP_PORT:-8080}:8080`, and keeps FastAPI/PostgreSQL internal to Docker |
| Demo Workflow Package YAML | `demo/tradingagents_advisory_research.yaml`, `demo/digital_oracle_researcher.yaml` | grounded package inputs for manual import/testing across TradingAgents and Digital Oracle flows |
| Cross-app E2E startup | `frontend/e2e/AGENTS.md`, `frontend/playwright.config.ts`, `frontend/scripts/start-playwright-*.mjs` | Playwright uses backend `8001` and frontend `4173` with dedicated startup helpers |
| Backend app layer | `backend/app/AGENTS.md`, `backend/app/main.py`, `backend/app/api/router.py`, `backend/app/api/platform_router.py` | app factory, split API roots, dependency composition, service/repository/schema layering, and worker entrypoints |
| Backend agent-platform flow | `backend/app/api/workflow_packages.py`, `backend/app/api/schedules.py`, `backend/app/api/model_connections.py`, `backend/app/api/tools.py`, `backend/app/api/runs.py` | Workflow Packages, Scheduled Tasks, Model Connections, Tools metadata, and Runs |
| Backend extension ownership | `backend/app/extensions/AGENTS.md`, `backend/app/extensions/contract.py`, `backend/app/extensions/registry.py`, `backend/app/extensions/signaldeck_finance/AGENTS.md`, `backend/app/extensions/signaldeck_digital_oracle/AGENTS.md` | static `Extension` contract plus installed Finance Workspace and Digital Oracle extension declarations |
| Backend runtime tools, MCP, schedules, and traces | `backend/app/agents/AGENTS.md`, `backend/app/agents/{tool_catalog,runtime_tools,mcp}/AGENTS.md`, `backend/app/services/agent_execution_service.py`, `backend/app/services/run_service.py`, `backend/app/services/workflow_package_schedule_service.py`, `backend/app/workers/run_scheduler.py`, `backend/app/core/telemetry.py` | server-declared tools, native runtime tools, due schedule materialization, MCP snapshots/dispatch, Logfire trace ids/spans |
| Backend preserved v1 flow | `backend/app/extensions/signaldeck_finance/__init__.py`, `backend/app/api/templates.py`, `backend/app/api/reports.py` | preserved template/report finance routes registered through the static `signaldeck.finance` extension declaration |
| Frontend app shell | `frontend/src/App.tsx`, `frontend/src/routes.ts`, `frontend/src/routes.metadata.ts`, `frontend/src/components/layout.tsx` | query client, router provider, metadata-driven shell/nav rendering, static finance routes, and theme toggle |
| Frontend shared route shells and design system | `frontend/src/components/shared/docs/README.md`, `frontend/src/components/shared/AGENTS.md`, `frontend/src/hooks/AGENTS.md` | UI/UX standards, inventory/workspace/split-inspector shells, management-list actions/selection, and reusable view/filter/selection/inspector state hooks |
| Frontend agent-platform UI | `frontend/src/pages/workflow-packages/AGENTS.md`, `frontend/src/pages/scheduled-tasks/AGENTS.md`, `frontend/src/pages/model-connections/AGENTS.md`, `frontend/src/pages/runs/AGENTS.md` | Workflow Packages, Scheduled Tasks, Model Connections, and Runs; Tools appear as package-authoring metadata, not a standalone browser route |
| Frontend preserved product UI | `frontend/src/pages/templates/AGENTS.md`, `frontend/src/pages/reports/AGENTS.md` | preserved template and report routes |
| Frontend reports and templates | `frontend/src/components/templates/AGENTS.md`, `frontend/src/components/forms/AGENTS.md`, `frontend/src/lib/runtime-inputs.ts`, `frontend/src/lib/report-grouping.ts` | runtime inputs, placeholder browsing, grouping, upload, and report generation UI |
| Backend tests | `backend/tests/AGENTS.md`, `backend/tests/test_api.py`, `backend/tests/test_workflow_package_diagnostics.py`, `backend/tests/test_workflow_package_execution_plan.py`, `backend/tests/test_workflow_package_runtime_api.py`, `backend/tests/test_workflow_package_run_contracts.py`, `backend/tests/test_runtime_tools.py`, `backend/tests/test_mcp_runtime.py`, `backend/tests/test_db_bootstrap.py` | preserved template/report APIs plus package validation, Scheduled Tasks, runtime, MCP, rerun, and DB-bootstrap coverage |
| Docs ownership | `docs/AGENTS.md`, `docs/*.md` | six canonical owner docs stay live and mirror current code |
| CI quality gates | `.github/workflows/ci.yml`, `.github/workflows/docker-images.yml` | version sync, frozen backend/frontend installs, quality gates, frontend E2E, and arm64 GHCR images |

## CODE MAP

| Symbol / Entry | Location | Role |
|---|---|---|
| `create_app` | `backend/app/main.py` | FastAPI app factory, exception handlers, CORS, healthcheck |
| `api_router` | `backend/app/api/router.py` | mounts `signaldeck.finance` route registrations under `/api/v1` |
| `platform_router` | `backend/app/api/platform_router.py` | mounts live `/api/*` routers for model connections, tools, workflow packages, schedules, and runs |
| `INSTALLED_EXTENSIONS` | `backend/app/extensions/registry.py` | declares statically installed extension instances, validates unique extension/tool keys, and builds provider bundles |
| `Extension` | `backend/app/extensions/contract.py` | static backend extension contribution contract for API routers, tool declarations/specs, providers, and dependency surfaces |
| `router` | `frontend/src/routes.ts` | flat route table for `/`, finance routes, `/workflow-packages`, `/scheduled-tasks`, `/model-connections`, and `/runs` |
| `Layout` | `frontend/src/components/layout.tsx` | sidebar shell, breadcrumbs, route labels, static nav groups, and template/package editor full-height layout |
| `configure_logfire` | `backend/app/core/telemetry.py` | optional Logfire setup plus trace/span id formatting used by package run execution |

## CONVENTIONS

- Backend JSON is camelCase externally and snake_case internally; `CamelModel` owns aliasing and `extra="forbid"` request validation.
- Backend error envelopes are `{code, message, details[]}`; frontend `ApiRequestError` parsing depends on that exact shape.
- Money, quantities, and market values cross the API as strings; backend parsing lives in `backend/app/core/formatting.py`, while frontend conversion lives in shared formatting helpers.
- Query invalidation is centralized in `frontend/src/lib/query-keys.ts`; ids are normalized to strings, and template, report, and agent-platform caches live under dedicated namespaces.
- `frontend/src/routes.metadata.ts` is the contract for route archetype, shell mode, width mode, ownership, and visible state variants; `Layout` consumes it, while shared inventory/workspace/split-inspector shells stay prop-driven so pages do not rebuild route chrome or teach shared shells to re-read metadata.
- Template placeholder paths are a cross-stack contract spanning backend services/schemas and frontend types/editor code; the live roots are `inputs` and `reports`.
- Reports are point-in-time markdown snapshots keyed by unique `slug`; canonical `source` origins are `compiled`, `uploaded`, `external`, and `agent`. `external` stays limited to true external user/API-created reports.
- Logfire is configured in `backend/app/core/telemetry.py` with `send_to_logfire="if-token-present"`; run execution stores formatted trace ids and per-invocation span ids but still works without a Logfire token.
- Legacy orchestration, Studio, Tryout, runtime-v2 routes, and retired legacy global authoring routes are not mounted live. Keep docs aligned with the package-first browser routes for Workflow Packages, Scheduled Tasks, Model Connections, and Runs, plus backend Tools metadata at `/api/tools`.
- `signaldeck.finance` is the statically installed first-party Finance Workspace extension. It owns preserved `/api/v1` template/report route families plus finance runtime tools/providers through its `EXTENSION` declaration; there is no backend enable/disable state gate.
- `signaldeck.digital_oracle` is a separate statically installed bundled extension and owns only `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, `signaldeck.digital_oracle.market_sentiment.lookup`, `signaldeck.digital_oracle.macro_rates.lookup`, `signaldeck.digital_oracle.crypto_derivatives.lookup`, `signaldeck.digital_oracle.cftc_positioning.lookup`, and `signaldeck.digital_oracle.options.lookup` in this upgrade. It adds no route or nav surface.
- There is no public extension-management API or backend enable/disable model; installed extension metadata is private Python wiring in `INSTALLED_EXTENSIONS`.
- Workflow Packages are the canonical platform authoring root. Package-private agents, output schemas, capability profiles, private MCP configs, and workflow graphs live inside package artifacts; persistence is artifact-only, while launch/preflight/rerun readiness is evaluated late against live Model Connections and package secret bindings.
- Package-private HTTP operation nodes and MCP configs are artifact/runtime data, not fake agents or global authoring surfaces. Browser-visible manifest reads and exports omit database ids, run history, package secret bindings, and private MCP `env`, `headers`, and `query` values.
- Scheduled Tasks are the package-first automation surface for recurring Workflow Package runs. They live at `/api/schedules` and `/scheduled-tasks`, use structured recurrence plus IANA timezones instead of raw cron, and materialize fires into ordinary queued runs through the scheduler worker.
- Global Tools are read-only server-declared metadata at `/api/tools`; packages reference only canonical owner-qualified extension tool keys through local capability profiles. `/api/tools` returns all tools declared by statically installed extensions. The live public keys are `signaldeck.finance.market_data.quote_lookup`, `signaldeck.finance.market_data.history_lookup`, `signaldeck.finance.market_data.ohlcv_lookup`, `signaldeck.finance.indicators.lookup`, `signaldeck.finance.fundamentals.lookup`, `signaldeck.finance.news.lookup`, `signaldeck.finance.social_sentiment.lookup`, `signaldeck.finance.insider_data.lookup`, `signaldeck.finance.reports.lookup`, `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, `signaldeck.digital_oracle.market_sentiment.lookup`, `signaldeck.digital_oracle.macro_rates.lookup`, `signaldeck.digital_oracle.crypto_derivatives.lookup`, `signaldeck.digital_oracle.cftc_positioning.lookup`, and `signaldeck.digital_oracle.options.lookup`. OpenAI function names are the mechanical underscore mapping from canonical keys, for example `signaldeck.finance.market_data.quote_lookup` -> `signaldeck_finance_market_data_quote_lookup`, and `signaldeck.digital_oracle.prediction_markets.lookup` -> `signaldeck_digital_oracle_prediction_markets_lookup`.
- Tool-call recovery and provider retries are typed runtime contracts: bounded model-feedback correction is only for pre-dispatch argument/schema failures, while transient provider retries are recorded as provider retry metadata and never overload tool-call retry metadata.
- Workflow package authoring is YAML-manifest based; backend parsers reject legacy `spec.skills`, YAML aliases/anchors/merge keys, unsupported tags, non-finite numbers, duplicate refs, and raw global ids.

## ANTI-PATTERNS

- Do not present auth, authorization, RBAC, login/session flows, user/account lifecycle, organizations, or multi-tenant account management as live scope or backlog scope unless the product is explicitly re-scoped.
- Do not bypass backend services or the static `Extension`/`INSTALLED_EXTENSIONS` contract from routes or frontend code.
- Do not reintroduce plugin-manifest metadata into public extension contracts, run dependency payloads, frontend contracts, OpenAPI, or live docs.
- Do not invent snake_case API fields, ad-hoc query keys, duplicate placeholder/type contracts, or hard-coded extension visibility rules.
- Do not treat quote/history warnings as fatal when the degraded path is already defined.
- Do not change template placeholder, template compile payloads, or runtime-input flow without updating backend tests and frontend callers together.
- Do not change report slug/name/source/download behavior, report filters, or `reports.*` placeholder output without updating backend tests, frontend callers, and template-editor guidance.
- Do not hide retired Studio, Tryout, or orchestration surfaces behind stale docs or direct URLs.
- Do not document simulations pages or modules as live shipped surfaces; they are no longer part of the browser-facing product.
- Do not migrate extension-owned behavior into generic platform docs, registries, route ownership, or runtime contracts without an explicit shared-contract decision and coordinated test updates.
- Do not add raw `httpx`/`requests` LLM calling paths in application code when an official provider SDK exists.
- Do not treat docs, Alembic scaffolds, frontend build output, or cache directories as the source of truth over live code.

## COMMANDS

```bash
(cd backend && uv sync)
(cd frontend && pnpm install)
./start.sh
docker compose -f docker-compose.yml down
```

## VALIDATION

```bash
(cd backend && uv run ruff check app tests && uv run black --check app tests && uv run isort --check-only app tests && uv run mypy app && uv run pytest)
(cd frontend && pnpm lint)
(cd frontend && pnpm typecheck)
(cd frontend && pnpm build)
(cd frontend && pnpm test:run)
(cd frontend && pnpm exec playwright install --with-deps chromium && pnpm test:e2e)
```

## NOTES

- `start.sh` is the authoritative local stack launcher. It wraps the root `docker-compose.yml`, builds the current local/demo app image, starts PostgreSQL/pgvector in Docker, runs Nginx/FastAPI/scheduler inside the app container, and exposes only `http://localhost:${APP_PORT:-8080}` on the host.
- Database bootstrap is code-based in `backend/app/db/`; `create_all` builds the schema, bundled package seeds load from SQL files, and startup recovery marks in-flight runs terminal. Do not add compatibility backfills or migration instructions around a reappearing Alembic scaffold.
- Playwright runs against backend `8001` and frontend `4173`; the backend startup helper starts both Uvicorn and the scheduler worker, while the frontend helper serves the built preview.
- Backend requires Python 3.13+; frontend targets Node 24 and pnpm 10.
- Root CI currently runs `version-sync`, `backend-quality`, `frontend-quality`, and `frontend-e2e`; Docker image publishing lives in a separate workflow.
- Root CI uses `uv sync --frozen` for backend jobs and `pnpm install --frozen-lockfile` for frontend jobs; `version-sync` checks `backend/VERSION` against `backend/pyproject.toml` and `frontend/VERSION` against `frontend/package.json`.
- Docker image publishing builds backend and frontend linux/arm64 images for GHCR.
- `docs/AGENTS.md` governs the six canonical owner docs: `prd.md`, `requirements.md`, `spec.md`, `data-model.md`, `test-plan.md`, and `docs/AGENTS.md`. Live code remains source of truth for docs updates.
