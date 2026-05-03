# PROJECT KNOWLEDGE BASE

**Generated:** 2026-05-03
**Commit:** 1f1e841
**Branch:** main

## OVERVIEW
Ledger is a dual-stack portfolio workspace with a FastAPI backend and a React/Vite frontend tracked directly in this repository. The live product surface spans portfolio CRUD, balances, positions, delayed market data, trading operations, template authoring and compile preview, point-in-time reports, and the current agent-platform routes for YAML-authored agents/workflows, capabilities, MCP servers, model connections, output schemas, and runs.

## CHILD DOCS
- `backend/AGENTS.md` — backend architecture, validation flow, and layer routing
- `backend/app/core/AGENTS.md` — config, error envelope, normalization helpers
- `backend/app/db/AGENTS.md` — session lifecycle and PostgreSQL-only upgrade rules
- `backend/app/api/AGENTS.md` — route handler boundaries and dependency wiring
- `backend/app/agents/AGENTS.md` — server tool catalog, native runtime tools, MCP security/runtime boundaries
- `backend/app/services/AGENTS.md` — service ownership, manifest compilers, runtime execution, memory reports, and quote-provider wiring
- `backend/app/schemas/AGENTS.md` — Pydantic validation, manifest contracts, memory metadata, and camelCase aliasing
- `backend/app/models/AGENTS.md` — ORM constraints, indexes, relationships, cache tables, manifests, and run metadata
- `backend/app/repositories/AGENTS.md` — query/repository patterns, report metadata filters, and runtime lookups
- `backend/tests/AGENTS.md` — pytest fixtures, isolated PostgreSQL databases, and regression coverage
- `frontend/AGENTS.md` — frontend architecture, router shell, agent-platform surfaces, and validation workflow
- `frontend/e2e/AGENTS.md` — Playwright fixed-port startup, route-family specs, and E2E conventions
- `frontend/scripts/AGENTS.md` — Playwright backend/frontend startup helpers
- `frontend/src/styles/AGENTS.md` — Tailwind v4 imports, theme tokens, dark variant, and empty font stub
- `frontend/src/test/AGENTS.md` — Vitest jsdom setup and browser API mocks
- `frontend/src/lib/AGENTS.md` — API client, query keys, formatting, runtime-input helpers, platform-authoring helpers, and shared contracts
- `frontend/src/lib/api/AGENTS.md` — domain API modules, v1/platform request helpers, upload/download boundaries
- `frontend/src/lib/types/AGENTS.md` — shared wire types for portfolios, templates, reports, and the agent-platform domains
- `frontend/src/lib/platform-authoring/AGENTS.md` — schema/value/ref/manifest authoring helper contracts
- `frontend/src/hooks/AGENTS.md` — TanStack Query hook patterns and invalidation rules
- `frontend/src/components/AGENTS.md` — layout shell, theme system, shared components, forms, platform-authoring widgets, and feature UI
- `frontend/src/components/platform-authoring/AGENTS.md` — schema composer, generated form, refs, inspectors, and legacy workflow-builder widgets
- `frontend/src/components/forms/AGENTS.md` — cross-route dialog forms for portfolios and report generation
- `frontend/src/components/templates/AGENTS.md` — template-editor placeholder and runtime-input components
- `frontend/src/components/ui/AGENTS.md` — shadcn/ui primitives, sidebar context, and shared variant helpers
- `frontend/src/components/shared/AGENTS.md` — reusable tables, metrics, error boundaries, and shared field schemas
- `frontend/src/components/portfolios/AGENTS.md` — portfolio workspace sections, dialogs, tables, and trades
- `frontend/src/pages/AGENTS.md` — dashboard, portfolio, template, report, and agent-platform routes
- `frontend/src/pages/agents/AGENTS.md` — YAML manifest agent list/editor/run-launch routes
- `frontend/src/pages/capabilities/AGENTS.md` — capabilities list/editor routes and tool-grant flows
- `frontend/src/pages/mcp-servers/AGENTS.md` — MCP servers list and editor routes
- `frontend/src/pages/model-connections/AGENTS.md` — saved model connection list, editor, secret handling, and connection test routes
- `frontend/src/pages/output-schemas/AGENTS.md` — output schemas list/editor routes and schema composer flow
- `frontend/src/pages/workflows/AGENTS.md` — YAML manifest workflow list/editor/run-launch routes
- `frontend/src/pages/runs/AGENTS.md` — runs list and detail routes
- `frontend/src/pages/portfolios/AGENTS.md` — portfolio list/detail orchestration and quote-enriched workspace rules
- `frontend/src/pages/templates/AGENTS.md` — template list/editor flows, debounce preview, runtime inputs, and placeholder browser rules
- `frontend/src/pages/reports/AGENTS.md` — report list/detail flows, grouping, markdown render/edit/download behavior

## STRUCTURE
```text
ledger/
├── backend/              # FastAPI app, SQLAlchemy models, services, pytest suite
├── frontend/             # React/Vite app, TanStack Query, Vitest, Playwright, shadcn/ui
├── docs/                 # retained orchestration cutover-reference notes; secondary to live code
├── .github/workflows/    # CI quality gates, Docker image publish, cleanup
└── start.sh              # local orchestrator with backend/frontend/db reuse and fallback ports
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Bootstrap a fresh clone | `backend/pyproject.toml`, `frontend/package.json`, `README.md`, `start.sh` | install with `uv sync` and `pnpm install`, then prefer `./start.sh` |
| Start the full stack locally | `start.sh`, `backend/docker-compose.yml`, `README.md` | defaults to Postgres `25432`, backend `28000`, frontend `25173`; stops prior Ledger instances before restart and may fall back to `25433/25434`, `28001/28002`, or `25174` |
| Cross-app E2E startup | `frontend/e2e/AGENTS.md`, `frontend/playwright.config.ts`, `frontend/scripts/start-playwright-*.mjs` | Playwright uses backend `8001` and frontend `4173` with dedicated startup helpers |
| Backend bootstrap | `backend/app/main.py`, `backend/app/api/router.py`, `backend/app/api/platform_router.py` | app factory plus preserved `/api/v1` and current `/api/*` composition |
| Backend agent-platform flow | `backend/app/api/agents.py`, `backend/app/api/capabilities.py`, `backend/app/api/mcp_servers.py`, `backend/app/api/model_connections.py`, `backend/app/api/output_schemas.py`, `backend/app/api/workflows.py`, `backend/app/api/runs.py` | agents, capabilities, MCP servers, model connections, output schemas, workflows, and runs |
| Backend runtime tools and MCP | `backend/app/agents/AGENTS.md`, `backend/app/services/agent_execution_service.py`, `backend/app/services/run_service.py` | server-declared tools, native runtime tools, MCP snapshots/dispatch, memory writes |
| Backend preserved v1 flow | `backend/app/api/portfolios.py`, `backend/app/api/balances.py`, `backend/app/api/positions.py`, `backend/app/api/trading_operations.py`, `backend/app/api/market_data.py`, `backend/app/api/templates.py`, `backend/app/api/reports.py` | preserved portfolio, trading, market-data, template, and report routes |
| Frontend app shell | `frontend/src/App.tsx`, `frontend/src/routes.ts`, `frontend/src/components/layout.tsx` | query client, router provider, layout shell, theme toggle, sidebar navigation |
| Frontend agent-platform UI | `frontend/src/pages/agents/AGENTS.md`, `frontend/src/pages/capabilities/AGENTS.md`, `frontend/src/pages/mcp-servers/AGENTS.md`, `frontend/src/pages/model-connections/AGENTS.md`, `frontend/src/pages/output-schemas/AGENTS.md`, `frontend/src/pages/workflows/AGENTS.md`, `frontend/src/pages/runs/AGENTS.md` | agents, capabilities, MCP servers, model connections, output schemas, workflows, and runs |
| Frontend preserved product UI | `frontend/src/pages/portfolios/AGENTS.md`, `frontend/src/pages/templates/AGENTS.md`, `frontend/src/pages/reports/AGENTS.md` | preserved portfolio, template, and report routes |
| Frontend reports and templates | `frontend/src/pages/reports/AGENTS.md`, `frontend/src/pages/templates/AGENTS.md`, `frontend/src/lib/runtime-inputs.ts` | markdown reports, compile preview, runtime input maps |
| Backend tests | `backend/tests/AGENTS.md`, `backend/tests/test_api.py`, `backend/tests/test_agent_manifest_*.py`, `backend/tests/test_workflow_manifest_*.py`, `backend/tests/test_runtime_tools.py`, `backend/tests/test_mcp_runtime.py`, `backend/tests/test_memory_reports.py` | preserved v1 CRUD plus manifest, runtime, MCP, memory, platform, and cutover regression coverage |
| CI quality gates | `.github/workflows/ci.yml`, `.github/workflows/docker-images.yml`, `.github/workflows/cleanup.yml` | version sync, backend quality, frontend quality, frontend E2E, image publish, cleanup |

## CODE MAP
| Symbol / Entry | Location | Role |
|---|---|---|
| `create_app` | `backend/app/main.py` | FastAPI app factory, exception handlers, CORS, healthcheck |
| `api_router` | `backend/app/api/router.py` | mounts live `/api/v1` routers for portfolios, balances, positions, trading, market data, templates, and reports |
| `platform_router` | `backend/app/api/platform_router.py` | mounts live `/api/*` routers for agents, capabilities, MCP servers, model connections, output schemas, workflows, and runs |
| `router` | `frontend/src/routes.ts` | flat route table for dashboard, portfolios, templates, reports, and the current agent-platform routes |
| `Layout` | `frontend/src/components/layout.tsx` | sidebar shell, breadcrumbs, route labels, template/agent/workflow editor full-height layout |

## CONVENTIONS
- Backend JSON is camelCase externally and snake_case internally; `CamelModel` owns aliasing and `extra="forbid"` request validation.
- Backend error envelopes are `{code, message, details[]}`; frontend `ApiRequestError` parsing depends on that exact shape.
- Money, quantities, and market values cross the API as strings; backend parsing lives in `backend/app/core/formatting.py`, while frontend conversion lives in shared formatting and analytics helpers.
- Query invalidation is centralized in `frontend/src/lib/query-keys.ts`; ids are normalized to strings, and portfolio, template, report, and agent-platform caches live under dedicated namespaces.
- Template placeholder paths are a cross-stack contract spanning backend services/schemas and frontend types/editor code; the live roots are `inputs`, `portfolios`, and `reports`.
- Reports are point-in-time markdown snapshots keyed by unique `slug`; compiled reports derive timestamped snake_case names from templates, uploaded reports accept optional metadata, and all report sources download by slug.
- Legacy orchestration, Studio, Tryout, and runtime-v2 routes are retired. Keep docs aligned with the current agent-platform routes for agents, capabilities, MCP servers, model connections, output schemas, workflows, and runs.
- Capabilities are the canonical agent-platform term. Live docs and examples use `/api/capabilities`, `/capabilities*`, `toolGrants`, `spec.capabilities`, `CapabilityService`, `CapabilityRepository`, `ToolCatalog`, and canonical `capabilities` storage. Runtime tool keys such as `ledger.reports.lookup` and OpenAI function names such as `ledger_reports_lookup` stay unchanged.
- Agent and workflow authoring is YAML-manifest based; backend parsers reject legacy `spec.skills`, YAML aliases/anchors/merge keys, unsupported tags, non-finite numbers, duplicate refs, and non-exact version pins.
- Application LLM calls must use official SDKs rather than raw HTTP requests; the current backend path uses the official `OpenAI` Python client.

## ANTI-PATTERNS
- Do not bypass backend services or call provider adapters directly from routes or frontend code.
- Do not invent snake_case API fields, ad-hoc query keys, or duplicate placeholder/type contracts.
- Do not treat quote/history warnings as fatal when the degraded path is already defined.
- Do not change CSV import, template placeholder, template compile payloads, or runtime-input flow without updating backend tests and frontend callers together.
- Do not change report slug/name/source/download behavior, report filters, or `reports.*` placeholder output without updating backend tests, frontend callers, and template-editor guidance.
- Do not hide retired Studio, Tryout, or orchestration surfaces behind stale docs or direct URLs.
- Do not document frontend `simulations` pages or `backend/app/api/simulations.py` as live shipped surfaces; those paths are no longer part of the current browser-facing product.
- Do not add raw `httpx`/`requests` LLM calling paths in application code when an official provider SDK exists.
- Do not treat `docs/`, `backend/alembic/`, `frontend/dist/`, or cache directories as the source of truth over live code.

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
- `start.sh` is the authoritative local orchestrator; it defaults to `25432/28000/25173`, stops prior Ledger instances before restart, may start PostgreSQL on `25432`, `25433`, or `25434`, and injects `DATABASE_URL` plus `VITE_API_BASE_URL`.
- Supported schema repair is code-based in `backend/app/db/`; do not create migration instructions around a reappearing `backend/alembic/` scaffold.
- Playwright runs against backend `8001` and frontend `4173`; the backend and frontend startup helpers launch dedicated E2E servers on those fixed ports.
- Backend requires Python 3.13+; frontend targets Node 24 and pnpm 10.
- Root CI currently runs `version-sync`, `backend-quality`, `frontend-quality`, and `frontend-e2e`; Docker image publishing and cleanup live in separate workflows.
- `docs/` contains retained orchestration cutover-reference docs (`ledger-orchestration-product-*.md`); keep them secondary to live code and don’t create nested AGENTS docs there.
- `.github/workflows/` holds CI and release automation only. The root docs already cover that area, so no child AGENTS docs belong there.
