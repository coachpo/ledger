# PROJECT KNOWLEDGE BASE

**Generated:** 2026-05-16
**Commit:** 86596fd
**Branch:** main

## OVERVIEW

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are retired/archive context, not live acceptance paths.

SignalDeck is a dual-stack universal agents workflow/pipeline platform with a FastAPI backend and a React/Vite frontend tracked directly in this repository. Executable agent workflows are accepted only as Workflow Packages; the bundled `signaldeck.finance` Finance Workspace extension supplies first-party portfolio data, reports, market data, trading tools, and finance-owned runtime tools that packages can use.

## CHILD DOCS

- `backend/AGENTS.md`, `backend/app/*/AGENTS.md`, `backend/tests/AGENTS.md` — backend layer, runtime, persistence, schema, and test rules
- `backend/app/extensions/signaldeck_finance/AGENTS.md` — first-party Finance Workspace extension ownership
- `docs/AGENTS.md` — live docs ownership, status metadata, and obsolete-content rules
- `frontend/AGENTS.md`, `frontend/e2e/AGENTS.md`, `frontend/scripts/AGENTS.md` — frontend shell, E2E, and startup-helper rules
- `frontend/src/extensions/AGENTS.md`, `frontend/src/styles/AGENTS.md`, `frontend/src/test/AGENTS.md` — extension runtime, theme, and Vitest setup rules
- `frontend/src/lib/**/AGENTS.md`, `frontend/src/hooks/AGENTS.md` — API, type, platform-authoring, and query-hook contracts
- `frontend/src/components/**/AGENTS.md`, `frontend/src/pages/**/AGENTS.md` — reusable UI, feature UI, live routes, and page-family rules
- `frontend/retired/global-authoring/src/pages/*/AGENTS.md` — archive-only global-authoring guide tree; do not treat as live route ownership

## STRUCTURE

```text
signaldeck/
├── backend/              # FastAPI app, SQLAlchemy models, services, pytest suite
├── frontend/             # React/Vite app, TanStack Query, Vitest, Playwright, shadcn/ui
├── docs/                 # prd, spec, API, data-model, test, run-input, platform, and memory design docs
├── .github/workflows/    # CI quality gates, Docker image publish, cleanup
└── start.sh              # local orchestrator with backend/frontend/db reuse and fallback ports
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Bootstrap a fresh clone | `backend/pyproject.toml`, `frontend/package.json`, `README.md`, `start.sh` | install with `uv sync` and `pnpm install`, then prefer `./start.sh` |
| Start the full stack locally | `start.sh`, `backend/docker-compose.yml`, `README.md` | defaults to Postgres `25432`, backend `28000`, frontend `25173`; stops prior SignalDeck instances before restart and may fall back to `25433/25434`, `28001/28002`, or `25174` |
| Cross-app E2E startup | `frontend/e2e/AGENTS.md`, `frontend/playwright.config.ts`, `frontend/scripts/start-playwright-*.mjs` | Playwright uses backend `8001` and frontend `4173` with dedicated startup helpers |
| Backend bootstrap | `backend/app/main.py`, `backend/app/api/router.py`, `backend/app/api/platform_router.py` | app factory plus extension-gated `/api/v1` and current `/api/*` composition |
| Backend agent-platform flow | `backend/app/api/workflow_packages.py`, `backend/app/api/model_connections.py`, `backend/app/api/extensions.py`, `backend/app/api/tools.py`, `backend/app/api/runs.py` | Workflow Packages, Model Connections, Extensions, Tools, and Runs |
| Backend extension ownership | `backend/app/extensions/AGENTS.md`, `backend/app/extensions/signaldeck_finance/AGENTS.md`, `backend/app/services/extension_service.py` | bundled extension registry/state and private `signaldeck.finance` registrar ownership |
| Backend runtime tools, MCP, and traces | `backend/app/agents/AGENTS.md`, `backend/app/services/agent_execution_service.py`, `backend/app/services/run_service.py`, `backend/app/core/telemetry.py` | server-declared tools, native runtime tools, MCP snapshots/dispatch, Logfire trace ids/spans, memory writes |
| Backend preserved v1 flow | `backend/app/extensions/signaldeck_finance/api_routers.py`, `backend/app/api/portfolios.py`, `backend/app/api/balances.py`, `backend/app/api/positions.py`, `backend/app/api/trading_operations.py`, `backend/app/api/market_data.py`, `backend/app/api/templates.py`, `backend/app/api/reports.py` | preserved finance routes registered behind `signaldeck.finance` gates |
| Frontend app shell | `frontend/src/App.tsx`, `frontend/src/routes.ts`, `frontend/src/extensions/runtime.tsx`, `frontend/src/components/layout.tsx` | query client, router provider, extension route/nav assembly, layout shell, theme toggle |
| Frontend extension runtime | `frontend/src/extensions/AGENTS.md`, `frontend/src/pages/extensions/AGENTS.md`, `frontend/src/hooks/use-extensions.ts` | frontend route/nav/tool filtering and bundled extension state UI |
| Frontend agent-platform UI | `frontend/src/pages/workflow-packages/AGENTS.md`, `frontend/src/pages/model-connections/AGENTS.md`, `frontend/src/pages/runs/AGENTS.md` | Workflow Packages, Model Connections, and Runs |
| Frontend preserved product UI | `frontend/src/pages/portfolios/AGENTS.md`, `frontend/src/pages/templates/AGENTS.md`, `frontend/src/pages/reports/AGENTS.md` | preserved portfolio, template, and report routes |
| Frontend reports and templates | `frontend/src/pages/reports/AGENTS.md`, `frontend/src/pages/templates/AGENTS.md`, `frontend/src/lib/runtime-inputs.ts` | markdown reports, compile preview, runtime input maps |
| Backend tests | `backend/tests/AGENTS.md`, `backend/tests/test_api.py`, `backend/tests/test_agent_manifest_*.py`, `backend/tests/test_workflow_manifest_*.py`, `backend/tests/test_runtime_tools.py`, `backend/tests/test_mcp_runtime.py`, `backend/tests/test_memory_reports.py` | preserved v1 CRUD plus manifest, runtime, MCP, memory, platform, and cutover regression coverage |
| CI quality gates | `.github/workflows/ci.yml`, `.github/workflows/docker-images.yml`, `.github/workflows/cleanup.yml` | version sync, frozen backend/frontend installs, quality gates, frontend E2E, arm64 GHCR images, cleanup |

## CODE MAP

| Symbol / Entry | Location | Role |
|---|---|---|
| `create_app` | `backend/app/main.py` | FastAPI app factory, exception handlers, CORS, healthcheck |
| `api_router` | `backend/app/api/router.py` | mounts `signaldeck.finance` route registrations under `/api/v1` |
| `platform_router` | `backend/app/api/platform_router.py` | mounts live `/api/*` routers for workflow packages, model connections, extensions, tools, and runs |
| `get_bundled_extension_registry` | `backend/app/extensions/registry.py` | declares bundled extension identity, initial enabled seeding, and private registrar paths |
| `ExtensionService` | `backend/app/services/extension_service.py` | resolves slim extension state, toggles `/api/extensions`, and filters ToolCatalog/runtime tool registries |
| `router` | `frontend/src/routes.ts` | flat route table with finance routes assembled from `src/extensions/runtime.tsx` plus platform/system routes |
| `assembleFinanceWorkspaceRoutes` | `frontend/src/extensions/runtime.tsx` | converts Finance Workspace route entries into guarded React Router entries |
| `Layout` | `frontend/src/components/layout.tsx` | sidebar shell, breadcrumbs, route labels, extension-aware nav groups, template/package editor full-height layout |
| `configure_logfire` | `backend/app/core/telemetry.py` | optional Logfire setup plus trace/span id formatting used by package run execution |

## CONVENTIONS

- Backend JSON is camelCase externally and snake_case internally; `CamelModel` owns aliasing and `extra="forbid"` request validation.
- Backend error envelopes are `{code, message, details[]}`; frontend `ApiRequestError` parsing depends on that exact shape.
- Money, quantities, and market values cross the API as strings; backend parsing lives in `backend/app/core/formatting.py`, while frontend conversion lives in shared formatting and analytics helpers.
- Query invalidation is centralized in `frontend/src/lib/query-keys.ts`; ids are normalized to strings, and portfolio, template, report, and agent-platform caches live under dedicated namespaces.
- Template placeholder paths are a cross-stack contract spanning backend services/schemas and frontend types/editor code; the live roots are `inputs`, `portfolios`, and `reports`.
- Reports are point-in-time markdown snapshots keyed by unique `slug`; canonical `source` origins are `compiled`, `uploaded`, `external`, and `agent`. `external` stays limited to true external user/API-created reports. Agent-created memory reports use `source="agent"`; `metadata.analysis.reviewType="agent_memory"` and `metadata.analysis.versionGroup="agent_memory/v1"` describe purpose/type, while server-owned `metadata.createdBy.type="agent"` records provenance such as `runId`, `agentKey`, and `agentVersion`.
- Logfire is configured in `backend/app/core/telemetry.py` with `send_to_logfire="if-token-present"`; run execution stores formatted trace ids and per-invocation span ids but still works without a Logfire token.
- Legacy orchestration, Studio, Tryout, runtime-v2 routes, and retired legacy global authoring routes are not mounted live. Keep docs aligned with the package-first routes for Workflow Packages, Model Connections, Extensions, Tools, and Runs.
- `signaldeck.finance` is the bundled first-party Finance Workspace extension. It is enabled by default, owns the preserved `/api/v1` finance route families, and gates finance route/nav/tool visibility through backend and frontend extension state. Public `/api/extensions` state is only `key`, `label`, and `enabled`; registry and scaffold details stay private wiring.
- Workflow Packages are the canonical platform authoring root. Package-private agents, output schemas, capability profiles, private MCP configs, and workflow graphs live inside immutable package versions.
- Global Tools are read-only server-declared metadata at `/api/tools`; packages reference tool keys through local capability profiles. Current finance-owned native tools cover market quote/history/OHLCV, indicators, fundamentals, news, social sentiment, insider data, positions, report lookup, and report memory writes, and are filtered by enabled extension state. Runtime tool keys such as `signaldeck.reports.lookup` and OpenAI function names such as `signaldeck_reports_lookup` stay unchanged.
- Workflow package authoring is YAML-manifest based; backend parsers reject legacy `spec.skills`, YAML aliases/anchors/merge keys, unsupported tags, non-finite numbers, duplicate refs, and raw global ids.
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

- `start.sh` is the authoritative local orchestrator; it defaults to `25432/28000/25173`, stops prior SignalDeck instances before restart, may start PostgreSQL on `25432`, `25433`, or `25434`, and injects `DATABASE_URL` plus `VITE_API_BASE_URL`.
- Supported schema repair is code-based in `backend/app/db/`; do not create migration instructions around a reappearing Alembic scaffold.
- Playwright runs against backend `8001` and frontend `4173`; the backend and frontend startup helpers launch dedicated E2E servers on those fixed ports.
- Backend requires Python 3.13+; frontend targets Node 24 and pnpm 10.
- Root CI currently runs `version-sync`, `backend-quality`, `frontend-quality`, and `frontend-e2e`; Docker image publishing and cleanup live in separate workflows.
- Root CI uses `uv sync --frozen` for backend jobs and `pnpm install --frozen-lockfile` for frontend jobs; `version-sync` checks `backend/VERSION` against `backend/pyproject.toml` and `frontend/VERSION` against `frontend/package.json`.
- Docker image publishing builds backend and frontend linux/arm64 images for GHCR; cleanup keeps at least 3 recent workflow runs and deletes untagged backend/frontend container package versions.
- `docs/AGENTS.md` governs the surviving docs set: `prd.md`, `requirements.md`, `spec.md`, `api-design.md`, `data-model.md`, `test-plan.md`, `run-input-schema-helptext.md`, `signaldeck-agent-platform.md`, phase-1 `signaldeck-memory-layer-design.md`, and the research/design note `advisory-research-signaldeck-upgrade-design.md`. Live code remains source of truth for docs updates.
