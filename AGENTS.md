# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-12
**Commit:** 154e3d8
**Branch:** main

## OVERVIEW

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

SignalDeck Core ships with statically resident extensions: the codebase contains the extension registrars, routes, tools, and hooks, and runtime state decides which surfaces are enabled. This is a Core-plus-driver model, not a marketplace or hot-loading plugin system.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

SignalDeck is a dual-stack universal agents workflow/pipeline platform with a FastAPI backend and a React/Vite frontend tracked directly in this repository. Executable agent workflows are accepted only as Workflow Packages. The statically resident `signaldeck.finance` Finance Workspace extension supplies first-party portfolio data, reports, market data, trading tools, and finance-owned runtime tools that packages can use. The statically resident `signaldeck.digital_oracle` extension is default enabled and tool-only in this upgrade, owning `signaldeck.prediction_markets.lookup`, `signaldeck.sec_filings.lookup`, and `signaldeck.market_sentiment.lookup` with unchanged tool keys and OpenAI function names.

Future upgrade work must keep the platform-core versus extension-owned boundary explicit. Decide intentionally whether a capability belongs in generic platform contracts or in statically resident extension ownership, then keep routes, tools, registries, docs, and tests aligned to that choice.

## CHILD DOCS

- `backend/AGENTS.md`, `backend/app/*/AGENTS.md`, `backend/tests/AGENTS.md` — backend layer, runtime, persistence, schema, worker, and test rules
- `backend/app/agents/{tool_catalog,runtime_tools,mcp}/AGENTS.md` — server tool metadata, native runtime dispatch, and MCP safety boundaries
- `backend/app/extensions/signaldeck_finance/AGENTS.md`, `backend/app/extensions/signaldeck_digital_oracle/AGENTS.md` — first-party extension ownership
- `.github/workflows/AGENTS.md` — CI gates, container publishing, and cleanup workflow rules
- `docs/AGENTS.md` — live docs ownership, obsolete-content rules, and platform/extension documentation boundary
- `frontend/AGENTS.md`, `frontend/e2e/AGENTS.md` — frontend shell, browser tests, and startup conventions
- `frontend/src/extensions/AGENTS.md`, `frontend/src/hooks/AGENTS.md`, `frontend/src/lib/**/AGENTS.md` — extension runtime, query hooks, API/type/platform-authoring contracts
- `frontend/src/components/**/AGENTS.md`, `frontend/src/pages/AGENTS.md` — reusable UI, feature UI, form/dialog helpers, and routed page-family rules
- `frontend/src/pages/extensions/AGENTS.md`, `frontend/src/pages/model-connections/AGENTS.md`, `frontend/src/pages/memory/AGENTS.md`, `frontend/src/pages/scheduled-tasks/AGENTS.md`, `frontend/src/pages/portfolios/AGENTS.md`, `frontend/src/pages/reports/AGENTS.md`, `frontend/src/pages/templates/AGENTS.md`, `frontend/src/pages/workflow-packages/AGENTS.md`, `frontend/src/pages/runs/AGENTS.md`, `frontend/src/pages/runs/detail-sections/AGENTS.md` — deeper route-family hotspots

## STRUCTURE

```text
signaldeck/
├── backend/              # FastAPI app, SQLAlchemy models, services, pytest suite
├── frontend/             # React/Vite app, TanStack Query, Vitest, Playwright, shadcn/ui
├── docs/                 # canonical owner docs plus requirements and architecture-audit evidence
├── demo/                 # grounded Workflow Package YAML examples
├── .github/workflows/    # CI quality gates, Docker image publish, cleanup
└── start.sh              # local orchestrator for db/backend/scheduler/frontend with fallback ports
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Bootstrap a fresh clone | `backend/pyproject.toml`, `frontend/package.json`, `README.md`, `start.sh` | install with `uv sync` and `pnpm install`, then prefer `./start.sh` |
| Start the full stack locally | `start.sh`, `backend/docker-compose.yml`, `README.md` | defaults to Postgres `25432`, backend `28000`, frontend `25173`; starts `python -m app.workers.run_scheduler`; stops prior SignalDeck instances before restart and may fall back to `25433/25434`, `28001/28002`, or `25174` |
| Demo Workflow Package YAML | `demo/tradingagents_advisory_research.yaml`, `demo/digital_oracle_researcher.yaml` | grounded package inputs for manual import/testing across TradingAgents and Digital Oracle flows |
| Cross-app E2E startup | `frontend/e2e/AGENTS.md`, `frontend/playwright.config.ts`, `frontend/scripts/start-playwright-*.mjs` | Playwright uses backend `8001` and frontend `4173` with dedicated startup helpers |
| Backend bootstrap | `backend/app/main.py`, `backend/app/api/router.py`, `backend/app/api/platform_router.py` | app factory plus extension-gated `/api/v1` and current `/api/*` composition |
| Backend agent-platform flow | `backend/app/api/workflow_packages.py`, `backend/app/api/schedules.py`, `backend/app/api/model_connections.py`, `backend/app/api/extensions.py`, `backend/app/api/memory.py`, `backend/app/api/tools.py`, `backend/app/api/runs.py` | Workflow Packages, Scheduled Tasks, Model Connections, Extensions, Memory, Tools metadata, and Runs |
| Backend extension ownership | `backend/app/extensions/AGENTS.md`, `backend/app/extensions/signaldeck_finance/AGENTS.md`, `backend/app/extensions/signaldeck_digital_oracle/AGENTS.md`, `backend/app/services/extension_service.py` | statically resident extension registry/state plus private Finance Workspace and Digital Oracle registrar ownership |
| Backend runtime tools, MCP, schedules, memory, and traces | `backend/app/agents/AGENTS.md`, `backend/app/agents/{tool_catalog,runtime_tools,mcp}/AGENTS.md`, `backend/app/services/agent_execution_service.py`, `backend/app/services/run_service.py`, `backend/app/services/workflow_package_schedule_service.py`, `backend/app/workers/run_scheduler.py`, `backend/app/api/memory.py`, `backend/app/core/telemetry.py` | server-declared tools, native runtime tools, due schedule materialization, MCP snapshots/dispatch, platform-core memory API, Logfire trace ids/spans, and memory writes |
| Backend preserved v1 flow | `backend/app/extensions/signaldeck_finance/api_routers.py`, `backend/app/api/portfolios.py`, `backend/app/api/balances.py`, `backend/app/api/positions.py`, `backend/app/api/trading_operations.py`, `backend/app/api/market_data.py`, `backend/app/api/templates.py`, `backend/app/api/reports.py` | preserved finance routes registered behind `signaldeck.finance` gates |
| Frontend app shell | `frontend/src/App.tsx`, `frontend/src/routes.ts`, `frontend/src/routes.metadata.ts`, `frontend/src/extensions/runtime-helpers.ts`, `frontend/src/components/layout.tsx` | query client, router provider, metadata-driven shell/nav rendering, extension route assembly, and theme toggle |
| Frontend shared route shells | `frontend/src/components/shared/AGENTS.md`, `frontend/src/hooks/AGENTS.md` | inventory/workspace/split-inspector shells plus reusable view/filter/selection/inspector state hooks for shared route chrome |
| Frontend extension runtime | `frontend/src/extensions/AGENTS.md`, `frontend/src/pages/extensions/AGENTS.md`, `frontend/src/extensions/runtime.tsx`, `frontend/src/extensions/runtime-helpers.ts`, `frontend/src/hooks/use-extensions.ts` | frontend route/nav/tool filtering plus statically resident extension state UI |
| Frontend agent-platform UI | `frontend/src/pages/workflow-packages/AGENTS.md`, `frontend/src/pages/scheduled-tasks/AGENTS.md`, `frontend/src/pages/model-connections/AGENTS.md`, `frontend/src/pages/runs/AGENTS.md`, `frontend/src/pages/memory/AGENTS.md` | Workflow Packages, Scheduled Tasks, Model Connections, Runs, and Memory; Tools appear as package-authoring metadata, not a standalone browser route |
| Frontend preserved product UI | `frontend/src/pages/portfolios/AGENTS.md`, `frontend/src/pages/templates/AGENTS.md`, `frontend/src/pages/reports/AGENTS.md` | preserved portfolio, template, and report routes |
| Frontend reports and templates | `frontend/src/components/templates/AGENTS.md`, `frontend/src/components/forms/AGENTS.md`, `frontend/src/lib/runtime-inputs.ts`, `frontend/src/lib/report-grouping.ts` | runtime inputs, placeholder browsing, grouping, upload, and report generation UI |
| Backend tests | `backend/tests/AGENTS.md`, `backend/tests/test_api.py`, `backend/tests/test_workflow_package_preflight.py`, `backend/tests/test_workflow_package_runtime_api.py`, `backend/tests/test_workflow_package_run_contracts.py`, `backend/tests/test_runtime_tools.py`, `backend/tests/test_mcp_runtime.py`, `backend/tests/test_runtime_db_upgrades.py`, `backend/tests/test_legacy_backend_cutover.py` | preserved v1 CRUD plus package validation, Scheduled Tasks, runtime, MCP, rerun/fork, DB-upgrade, and cutover regression coverage |
| Docs ownership and audit evidence | `docs/AGENTS.md`, `docs/requirements/*.md`, `docs/architecture-audit/README.md` | six canonical owner docs stay live; requirements companions and architecture-audit files are evidence/context, not new product scope |
| CI quality gates | `.github/workflows/ci.yml`, `.github/workflows/docker-images.yml`, `.github/workflows/cleanup.yml` | version sync, frozen backend/frontend installs, quality gates, frontend E2E, arm64 GHCR images, cleanup |

## CODE MAP

| Symbol / Entry | Location | Role |
|---|---|---|
| `create_app` | `backend/app/main.py` | FastAPI app factory, exception handlers, CORS, healthcheck |
| `api_router` | `backend/app/api/router.py` | mounts `signaldeck.finance` route registrations under `/api/v1` |
| `platform_router` | `backend/app/api/platform_router.py` | mounts live `/api/*` routers for extensions, memory, model connections, tools, workflow packages, schedules, and runs |
| `get_bundled_extension_registry` | `backend/app/extensions/registry.py` | declares statically resident extension identity, initial enabled seeding, and private registrar paths |
| `ExtensionService` | `backend/app/services/extension_service.py` | resolves slim extension state, toggles `/api/extensions`, and filters ToolCatalog/runtime tool registries |
| `router` | `frontend/src/routes.ts` | flat route table for `/`, `/extensions`, finance routes, `/workflow-packages`, `/scheduled-tasks`, `/model-connections`, `/memory`, and `/runs` |
| `assembleFinanceWorkspaceRoutes` | `frontend/src/extensions/runtime-helpers.ts` | converts Finance Workspace route entries into guarded React Router entries |
| `Layout` | `frontend/src/components/layout.tsx` | sidebar shell, breadcrumbs, route labels, extension-aware nav groups, template/package editor full-height layout |
| `configure_logfire` | `backend/app/core/telemetry.py` | optional Logfire setup plus trace/span id formatting used by package run execution |

## CONVENTIONS

- Backend JSON is camelCase externally and snake_case internally; `CamelModel` owns aliasing and `extra="forbid"` request validation.
- Backend error envelopes are `{code, message, details[]}`; frontend `ApiRequestError` parsing depends on that exact shape.
- Money, quantities, and market values cross the API as strings; backend parsing lives in `backend/app/core/formatting.py`, while frontend conversion lives in shared formatting and analytics helpers.
- Portfolio create/update/read payloads no longer carry `baseCurrency`/`base_currency`; finance cash, positions, trades, template available balance, and quote currency checks use backend `PORTFOLIO_CURRENCY` (`USD`) while row-level currency fields still cross the API as strings.
- Query invalidation is centralized in `frontend/src/lib/query-keys.ts`; ids are normalized to strings, and portfolio, template, report, and agent-platform caches live under dedicated namespaces.
- `frontend/src/routes.metadata.ts` is the contract for route archetype, shell mode, width mode, ownership, and visible state variants; `Layout` consumes it, while shared inventory/workspace/split-inspector shells stay prop-driven so pages do not rebuild route chrome or teach shared shells to re-read metadata.
- Template placeholder paths are a cross-stack contract spanning backend services/schemas and frontend types/editor code; the live roots are `inputs`, `portfolios`, and `reports`.
- Reports are point-in-time markdown snapshots keyed by unique `slug`; canonical `source` origins are `compiled`, `uploaded`, `external`, and `agent`. `external` stays limited to true external user/API-created reports. Historical agent-memory reports are report-domain history only; canonical memory writes and lookup use platform-core memory tables and tools.
- Logfire is configured in `backend/app/core/telemetry.py` with `send_to_logfire="if-token-present"`; run execution stores formatted trace ids and per-invocation span ids but still works without a Logfire token.
- Legacy orchestration, Studio, Tryout, runtime-v2 routes, and retired legacy global authoring routes are not mounted live. Keep docs aligned with the package-first browser routes for Workflow Packages, Scheduled Tasks, Model Connections, Extensions, Memory, and Runs, plus backend Tools metadata at `/api/tools`.
- `signaldeck.finance` is the statically resident first-party Finance Workspace extension. It is enabled by default, owns the preserved `/api/v1` finance route families, and gates finance route/nav/tool visibility through backend and frontend extension state.
- `signaldeck.digital_oracle` is a separate statically resident bundled extension, also enabled by default, and owns only `signaldeck.prediction_markets.lookup`, `signaldeck.sec_filings.lookup`, and `signaldeck.market_sentiment.lookup` in this upgrade. It adds no route or nav surface.
- Public `/api/extensions` state is only `key`, `label`, and `enabled`; registry and scaffold details stay private wiring.
- When planning upgrades, decide explicitly whether behavior belongs in platform core or in extension-owned seams, then update registries, route gates, runtime tools, docs, and tests together instead of letting finance-specific behavior silently redefine shared contracts.
- Workflow Packages are the canonical platform authoring root. Package-private agents, output schemas, capability profiles, private MCP configs, and workflow graphs live inside package artifacts; persistence is artifact-only, while launch/preflight/rerun/fork readiness is evaluated late against live Model Connections, extension state, and package secret bindings.
- Package-private HTTP operation nodes and MCP configs are artifact/runtime data, not fake agents or global authoring surfaces. Browser-visible manifest reads and exports omit database ids, run history, package secret bindings, and private MCP `env`, `headers`, and `query` values.
- Scheduled Tasks are the package-first automation surface for recurring Workflow Package runs. They live at `/api/schedules` and `/scheduled-tasks`, use structured recurrence plus IANA timezones instead of raw cron, and materialize fires into ordinary queued runs through the scheduler worker.
- Global Tools are read-only server-declared metadata at `/api/tools`; packages reference tool keys through local capability profiles. Finance Workspace native tools cover market quote/history/OHLCV, indicators, fundamentals, news, social sentiment, insider data, positions, and report lookup, and are filtered by enabled extension state. Digital Oracle tools cover prediction markets, SEC filings, and market sentiment, and keep their existing tool keys and OpenAI function names. Platform-core memory tools use `signaldeck.memory.write` / `signaldeck.memory.lookup` and stay visible when bundled extensions are disabled.
- Tool-call recovery and provider retries are typed runtime contracts: bounded model-feedback correction is only for pre-dispatch argument/schema failures, while transient provider retries are recorded as provider retry metadata and never overload tool-call retry metadata.
- Workflow package authoring is YAML-manifest based; backend parsers reject legacy `spec.skills`, YAML aliases/anchors/merge keys, unsupported tags, non-finite numbers, duplicate refs, and raw global ids.
- Test-writing rule: skip dedicated “proves not” tests for ordinary removal-only checks when manual confirmation already verifies the outcome. Keep absence assertions only when the absence itself is the shipped contract, such as removed-route or slim-contract guarantees.
- Application LLM calls must use official SDKs rather than raw HTTP requests; the current backend path uses the official `OpenAI` Python client.

## ANTI-PATTERNS

- Do not bypass backend services, extension state gates, or private extension registrars from routes or frontend code.
- Do not reintroduce plugin-manifest metadata into public extension contracts, run dependency payloads, frontend extension state, OpenAPI, or live docs.
- Do not invent snake_case API fields, ad-hoc query keys, duplicate placeholder/type contracts, or hard-coded extension visibility rules.
- Do not treat quote/history warnings as fatal when the degraded path is already defined.
- Do not change CSV import, template placeholder, template compile payloads, or runtime-input flow without updating backend tests and frontend callers together.
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
(cd backend && uv run uvicorn app.main:app --reload --port 28000)
(cd frontend && pnpm dev)
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

- `start.sh` is the authoritative local orchestrator; it defaults to `25432/28000/25173`, stops prior SignalDeck instances before restart, may start PostgreSQL on `25432`, `25433`, or `25434`, starts the scheduler worker beside Uvicorn, and injects `DATABASE_URL` plus `VITE_API_BASE_URL`.
- Supported schema repair is code-based in `backend/app/db/`; startup repair targets live tables and treats retired global authoring tables as drop-only cleanup targets, not compatibility backfill surfaces. Do not create migration instructions around a reappearing Alembic scaffold.
- Playwright runs against backend `8001` and frontend `4173`; the backend startup helper starts both Uvicorn and the scheduler worker, while the frontend helper serves the built preview.
- Backend requires Python 3.13+; frontend targets Node 24 and pnpm 10.
- Root CI currently runs `version-sync`, `backend-quality`, `frontend-quality`, and `frontend-e2e`; Docker image publishing and cleanup live in separate workflows.
- Root CI uses `uv sync --frozen` for backend jobs and `pnpm install --frozen-lockfile` for frontend jobs; `version-sync` checks `backend/VERSION` against `backend/pyproject.toml` and `frontend/VERSION` against `frontend/package.json`.
- Docker image publishing builds backend and frontend linux/arm64 images for GHCR; cleanup keeps at least 3 recent workflow runs and deletes untagged backend/frontend container package versions.
- `docs/AGENTS.md` governs the six canonical owner docs: `prd.md`, `requirements.md`, `spec.md`, `data-model.md`, `test-plan.md`, and `docs/AGENTS.md`. Requirements companions and architecture-audit files are evidence/context, pending design notes are historical context only, and live code remains source of truth for docs updates.
