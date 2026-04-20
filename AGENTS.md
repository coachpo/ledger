# PROJECT KNOWLEDGE BASE

**Generated:** 2026-04-18
**Commit:** 500880e
**Branch:** agents

## OVERVIEW
Ledger is a dual-stack portfolio workspace with a FastAPI backend and a React/Vite frontend tracked directly in this repository. The live product surface spans portfolio CRUD, balances, positions, delayed market data, trading operations, template authoring and compile preview, point-in-time reports, and the current agent-platform routes for agents, skills, MCP servers, output schemas, workflows, and runs.

## CHILD DOCS
- `backend/AGENTS.md` — backend architecture, validation flow, and layer routing
- `backend/app/core/AGENTS.md` — config, error envelope, normalization helpers
- `backend/app/db/AGENTS.md` — session lifecycle and PostgreSQL-only upgrade rules
- `backend/app/api/AGENTS.md` — route handler boundaries and dependency wiring
- `backend/app/services/AGENTS.md` — service ownership, template/report behavior, and quote-provider wiring
- `backend/app/schemas/AGENTS.md` — Pydantic validation and camelCase aliasing
- `backend/app/models/AGENTS.md` — ORM constraints, indexes, relationships, cache tables, and runtime metadata
- `backend/app/repositories/AGENTS.md` — query/repository patterns and lookups
- `backend/tests/AGENTS.md` — pytest fixtures, isolated PostgreSQL databases, and regression coverage
- `frontend/AGENTS.md` — frontend architecture, router shell, agent-platform surfaces, and validation workflow
- `frontend/src/lib/AGENTS.md` — API client, query keys, formatting, runtime-input helpers, and shared contracts
- `frontend/src/lib/api/AGENTS.md` — domain API modules, v1 request helpers, upload/download boundaries
- `frontend/src/lib/types/AGENTS.md` — shared wire types for portfolios, templates, reports, and the agent-platform domains
- `frontend/src/hooks/AGENTS.md` — TanStack Query hook patterns and invalidation rules
- `frontend/src/components/AGENTS.md` — layout shell, theme system, shared components, forms, and feature UI
- `frontend/src/components/forms/AGENTS.md` — cross-route dialog forms for portfolios and report generation
- `frontend/src/components/templates/AGENTS.md` — template-editor placeholder and runtime-input components
- `frontend/src/components/ui/AGENTS.md` — shadcn/ui primitives, sidebar context, and shared variant helpers
- `frontend/src/components/shared/AGENTS.md` — reusable tables, metrics, error boundaries, and shared field schemas
- `frontend/src/components/portfolios/AGENTS.md` — portfolio workspace sections, dialogs, tables, and trades
- `frontend/src/pages/AGENTS.md` — dashboard, portfolio, template, report, and agent-platform routes
- `frontend/src/pages/agents/AGENTS.md` — agents list and editor routes
- `frontend/src/pages/skills/AGENTS.md` — skills list and editor routes
- `frontend/src/pages/mcp-servers/AGENTS.md` — MCP servers list and editor routes
- `frontend/src/pages/output-schemas/AGENTS.md` — output schemas list and editor routes
- `frontend/src/pages/workflows/AGENTS.md` — workflows list, editor, and run-launch routes
- `frontend/src/pages/runs/AGENTS.md` — runs list and detail routes
- `frontend/src/pages/portfolios/AGENTS.md` — portfolio list/detail orchestration and quote-enriched workspace rules
- `frontend/src/pages/templates/AGENTS.md` — template list/editor flows, debounce preview, runtime inputs, and placeholder browser rules
- `frontend/src/pages/reports/AGENTS.md` — report list/detail flows, grouping, markdown render/edit/download behavior

## STRUCTURE
```text
ledger/
├── backend/              # FastAPI app, SQLAlchemy models, services, pytest suite
├── frontend/             # React/Vite app, TanStack Query, Vitest, Playwright, shadcn/ui
├── docs/                 # agent-platform design, UI, migration, and cutover-reference notes; secondary to live code
├── .github/workflows/    # CI quality gates, Docker image publish, cleanup
└── start.sh              # local orchestrator with backend/frontend/db reuse and fallback ports
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Bootstrap a fresh clone | `backend/pyproject.toml`, `frontend/package.json`, `README.md`, `start.sh` | install with `uv sync` and `pnpm install`, then prefer `./start.sh` |
| Start the full stack locally | `start.sh`, `backend/docker-compose.yml`, `README.md` | defaults to Postgres `25432`, backend `28000`, frontend `25173`; may reuse a healthy backend or fall back to `25433/25434`, `28001/28002`, or `25174` |
| Cross-app E2E startup | `frontend/playwright.config.ts`, `frontend/scripts/start-playwright-*.mjs` | Playwright uses backend `8001` and frontend `4173` with dedicated startup helpers |
| Backend bootstrap | `backend/app/main.py`, `backend/app/api/router.py`, `backend/app/api/platform_router.py` | app factory plus preserved `/api/v1` and current `/api/*` composition |
| Backend agent-platform flow | `backend/app/api/agents.py`, `backend/app/api/skills.py`, `backend/app/api/mcp_servers.py`, `backend/app/api/output_schemas.py`, `backend/app/api/workflows.py`, `backend/app/api/runs.py` | agents, skills, MCP servers, output schemas, workflows, and runs |
| Backend preserved v1 flow | `backend/app/api/portfolios.py`, `backend/app/api/balances.py`, `backend/app/api/positions.py`, `backend/app/api/trading_operations.py`, `backend/app/api/market_data.py`, `backend/app/api/templates.py`, `backend/app/api/reports.py` | preserved portfolio, trading, market-data, template, and report routes |
| Frontend app shell | `frontend/src/App.tsx`, `frontend/src/routes.ts`, `frontend/src/components/layout.tsx` | query client, router provider, layout shell, theme toggle, sidebar navigation |
| Frontend agent-platform UI | `frontend/src/pages/agents/AGENTS.md`, `frontend/src/pages/skills/AGENTS.md`, `frontend/src/pages/mcp-servers/AGENTS.md`, `frontend/src/pages/output-schemas/AGENTS.md`, `frontend/src/pages/workflows/AGENTS.md`, `frontend/src/pages/runs/AGENTS.md` | agents, skills, MCP servers, output schemas, workflows, and runs |
| Frontend preserved product UI | `frontend/src/pages/portfolios/AGENTS.md`, `frontend/src/pages/templates/AGENTS.md`, `frontend/src/pages/reports/AGENTS.md` | preserved portfolio, template, and report routes |
| Frontend reports and templates | `frontend/src/pages/reports/AGENTS.md`, `frontend/src/pages/templates/AGENTS.md`, `frontend/src/lib/runtime-inputs.ts` | markdown reports, compile preview, runtime input maps |
| Backend tests | `backend/tests/AGENTS.md`, `backend/tests/test_api.py`, `backend/tests/test_runtime_api.py`, `backend/tests/test_runtime_artifacts.py`, `backend/tests/test_runtime_db_upgrades.py`, `backend/tests/test_legacy_backend_cutover.py` | preserved v1 CRUD plus current platform and cutover regression coverage |
| CI quality gates | `.github/workflows/ci.yml`, `.github/workflows/docker-images.yml`, `.github/workflows/cleanup.yml` | version sync, backend quality, frontend quality, frontend E2E, image publish, cleanup |

## CODE MAP
| Symbol / Entry | Location | Role |
|---|---|---|
| `create_app` | `backend/app/main.py` | FastAPI app factory, exception handlers, CORS, healthcheck |
| `api_router` | `backend/app/api/router.py` | mounts live `/api/v1` routers for portfolios, balances, positions, trading, market data, templates, and reports |
| `platform_router` | `backend/app/api/platform_router.py` | mounts live `/api/*` routers for agents, skills, MCP servers, output schemas, workflows, and runs |
| `router` | `frontend/src/routes.ts` | flat route table for dashboard, portfolios, templates, reports, and the current agent-platform routes |
| `Layout` | `frontend/src/components/layout.tsx` | sidebar shell, breadcrumbs, route labels, template-editor full-height layout |

## CONVENTIONS
- Backend JSON is camelCase externally and snake_case internally; `CamelModel` owns aliasing and `extra="forbid"` request validation.
- Backend error envelopes are `{code, message, details[]}`; frontend `ApiRequestError` parsing depends on that exact shape.
- Money, quantities, and market values cross the API as strings; backend parsing lives in `backend/app/core/formatting.py`, while frontend conversion lives in shared formatting and analytics helpers.
- Query invalidation is centralized in `frontend/src/lib/query-keys.ts`; ids are normalized to strings, and portfolio, template, report, and agent-platform caches live under dedicated namespaces.
- Template placeholder paths are a cross-stack contract spanning backend services/schemas and frontend types/editor code; the live roots are `inputs`, `portfolios`, and `reports`.
- Reports are point-in-time markdown snapshots keyed by unique `slug`; compiled reports derive timestamped snake_case names from templates, uploaded reports accept optional metadata, and all report sources download by slug.
- Legacy orchestration, Studio, Tryout, and runtime-v2 routes are retired. Keep docs aligned with the current agent-platform routes for agents, skills, MCP servers, output schemas, workflows, and runs.
- Application LLM calls must use official SDKs rather than raw HTTP requests; the current backend path uses `ChatOpenAI` and the official `OpenAI` Python client.

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
- `start.sh` is the authoritative local orchestrator; it defaults to `25432/28000/25173`, may reuse a healthy backend, may start PostgreSQL on `25432`, `25433`, or `25434`, and injects `DATABASE_URL` plus `VITE_API_BASE_URL`.
- Supported schema repair is code-based in `backend/app/db/`; `backend/alembic/` is only a placeholder scaffold, not the migration source of truth.
- Playwright runs against backend `8001` and frontend `4173`; the backend and frontend startup helpers launch dedicated E2E servers on those fixed ports.
- Backend requires Python 3.13+; frontend targets Node 24 and pnpm 10.
- Root CI currently runs `version-sync`, `backend-quality`, `frontend-quality`, and `frontend-e2e`; Docker image publishing and cleanup live in separate workflows.
- `docs/` currently contains three orchestration-focused reference docs; keep them aligned with live agent-platform and preserved-product code, not retired simulation routes.
