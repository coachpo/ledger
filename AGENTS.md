# PROJECT KNOWLEDGE BASE

**Generated:** 2026-04-12
**Commit:** d6bc942
**Branch:** main

## OVERVIEW
Ledger is a dual-stack portfolio tracker with `backend/` and `frontend/` tracked directly in this repository. The live surface spans portfolio CRUD, deposit and withdrawal balances, aggregate positions, delayed market data, CSV imports, simulated BUY/SELL/DIVIDEND/SPLIT workflows, text-template authoring and compilation with runtime inputs, point-in-time report generation and upload/download, orchestration roles and characters, and historical backtests whose analysis path now runs inside Ledger via LangGraph.

## CHILD DOCS
- `backend/AGENTS.md` — backend architecture, validation flow, and layer routing
- `backend/app/core/AGENTS.md` — config, error envelope, normalization helpers
- `backend/app/db/AGENTS.md` — session lifecycle and PostgreSQL-only init/report-upgrade rules
- `backend/app/api/AGENTS.md` — route handler boundaries, orchestration endpoints, and dependency wiring
- `backend/app/services/AGENTS.md` — service ownership, orchestration, template/report workflows, and quote-provider wiring
- `backend/app/langgraph/AGENTS.md` — internal LangGraph runner, analyzer boundary, and execution rules
- `backend/app/schemas/AGENTS.md` — Pydantic validation, backtest launch semantics, and camelCase aliasing
- `backend/app/models/AGENTS.md` — ORM constraints, indexes, relationships, cache tables, and orchestration snapshots
- `backend/app/repositories/AGENTS.md` — query/repository patterns, orchestration lookups, and cleanup helpers
- `backend/tests/AGENTS.md` — pytest fixtures, isolated PostgreSQL databases, and regression coverage
- `frontend/AGENTS.md` — frontend architecture, router shell, orchestration workspace, and validation workflow
- `frontend/src/lib/AGENTS.md` — API client, query keys, analytics, formatting, runtime-input helpers, and shared contracts
- `frontend/src/lib/api/AGENTS.md` — domain API modules, upload/download boundaries, and route-path helpers
- `frontend/src/lib/types/AGENTS.md` — shared wire types for portfolios, templates, reports, backtests, orchestration, and trading
- `frontend/src/hooks/AGENTS.md` — TanStack Query hook patterns and invalidation rules
- `frontend/src/components/AGENTS.md` — layout shell, theme system, shared components, forms, and feature UI
- `frontend/src/components/forms/AGENTS.md` — cross-route dialog forms for portfolios and report generation
- `frontend/src/components/templates/AGENTS.md` — template-editor placeholder and runtime-input components
- `frontend/src/components/backtests/AGENTS.md` — backtest result widgets, charts, badges, and trade-log tables
- `frontend/src/components/ui/AGENTS.md` — shadcn/ui primitives, sidebar context, and shared variant helpers
- `frontend/src/components/shared/AGENTS.md` — reusable tables, metrics, error boundaries, and shared field schemas
- `frontend/src/components/portfolios/AGENTS.md` — portfolio workspace sections, dialogs, tables, and trades
- `frontend/src/pages/AGENTS.md` — dashboard, portfolio, template, report, backtest, and orchestration routes
- `frontend/src/pages/orchestration/AGENTS.md` — orchestration index plus role and character CRUD routes
- `frontend/src/pages/backtests/AGENTS.md` — backtest list/config/detail orchestration and polling behavior
- `frontend/src/pages/portfolios/AGENTS.md` — portfolio list/detail orchestration and quote-enriched workspace rules
- `frontend/src/pages/templates/AGENTS.md` — template list/editor flows, debounce preview, runtime inputs, and placeholder browser rules
- `frontend/src/pages/reports/AGENTS.md` — report list/detail flows, grouping, markdown render/edit/download behavior

## STRUCTURE
```text
ledger/
├── backend/              # FastAPI app, SQLAlchemy models, services, pytest suite
├── frontend/             # React/Vite app, TanStack Query, Vitest, Playwright, shadcn/ui
├── docs/                 # reference specs, requirements, runbooks, and test plans; secondary to live code
├── .github/workflows/    # CI quality gates, Docker smoke build, image publish, cleanup
└── start.sh              # local orchestrator: defaults to db/backend/frontend on 25432/28000/25173, reuses healthy services, and falls back to 25433/25434, 28001/28002, or 25174 when needed
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Bootstrap a fresh clone | `backend/pyproject.toml`, `frontend/package.json`, `README.md`, `start.sh` | install with `uv sync` and `pnpm install`, then use `./start.sh` unless you need manual startup |
| Start the full stack locally | `start.sh`, `backend/docker-compose.yml`, `README.md` | defaults to Postgres `25432`, backend `28000`, frontend `25173`, reuses a healthy backend on the requested port, and falls back to `25433/25434`, `28001/28002`, or `25174` when needed; no separate backtest worker process exists |
| Cross-app E2E startup | `frontend/playwright.config.ts`, `frontend/scripts/start-playwright-*.mjs` | Playwright uses backend `8001`, frontend `4173`, and `BACKTEST_TEST_MODE=1` |
| Backend bootstrap | `backend/app/main.py`, `backend/app/api/router.py`, `backend/app/api/dependencies.py` | app factory, router composition, dependency injection |
| Backend orchestration flow | `backend/app/api/orchestration.py`, `backend/app/services/orchestration_service.py`, `backend/app/schemas/orchestration.py` | roles, characters, mention catalog, versioned updates, validation |
| Backend report/backtest flow | `backend/app/api/reports.py`, `backend/app/api/backtests.py`, `backend/app/services/report_service.py`, `backend/app/services/backtest_service.py`, `backend/app/services/backtest_cycle_service.py` | report CRUD, backtest launch, cycle orchestration, internal LangGraph handoff |
| Backend DB upgrades | `backend/app/db/upgrades.py`, `backend/app/db/session.py` | startup init plus supported legacy-schema repair and interrupted-backtest cleanup |
| Backend tests | `backend/tests/AGENTS.md`, `backend/tests/test_api.py`, `backend/tests/test_backtests_api.py`, `backend/tests/test_orchestration_api.py`, `backend/tests/test_backtest_orchestration_snapshot.py` | CRUD, reports, backtests, orchestration, and upgrade regressions |
| Frontend app shell | `frontend/src/App.tsx`, `frontend/src/routes.ts`, `frontend/src/components/layout.tsx` | query client, router provider, layout shell, theme toggle, sidebar navigation |
| Frontend API/type contracts | `frontend/src/lib/api/AGENTS.md`, `frontend/src/lib/types/AGENTS.md`, `frontend/src/hooks/AGENTS.md` | request helpers, query keys, wire types, and TanStack Query wrappers |
| Frontend orchestration UI | `frontend/src/pages/orchestration/AGENTS.md`, `frontend/src/hooks/use-orchestration.ts`, `frontend/src/lib/api/orchestration.ts`, `frontend/src/lib/types/orchestration.ts` | roles, characters, mention catalog, route forms |
| Frontend backtests UI | `frontend/src/pages/backtests/AGENTS.md`, `frontend/src/hooks/use-backtests.ts`, `frontend/src/components/backtests/AGENTS.md` | configuration form, internal-vs-legacy launch mode, 5s polling, charts, trade log |
| Frontend tests / E2E | `frontend/vite.config.ts`, `frontend/src/test/setup.ts`, `frontend/playwright.config.ts`, `frontend/e2e/*.spec.ts` | jsdom unit setup plus Chromium E2E |
| CI quality gates | `.github/workflows/ci.yml`, `.github/workflows/docker-images.yml`, `.github/workflows/cleanup.yml` | version-sync, backend-quality, frontend-quality, frontend-e2e, image publish, cleanup |

## CODE MAP
| Symbol / Entry | Location | Role |
|---|---|---|
| `create_app` | `backend/app/main.py` | FastAPI app factory, exception handlers, CORS, healthcheck |
| `api_router` | `backend/app/api/router.py` | mounts all `/api/v1` routers, including orchestration, templates, reports, and backtests |
| `init_db` | `backend/app/db/session.py` | composes table creation, validation, legacy upgrades, and interrupted-backtest repair |
| `OrchestrationService` | `backend/app/services/orchestration_service.py` | versioned role/character CRUD and mention-catalog assembly |
| `TemplateCompilerService` | `backend/app/services/template_compiler_service.py` | resolves `{{inputs...}}`, `{{portfolios...}}`, and `{{reports...}}` placeholders against live data |
| `ReportService` | `backend/app/services/report_service.py` | report CRUD, upload validation, unique slug/name generation |
| `BacktestService` | `backend/app/services/backtest_service.py` | backtest CRUD, deposit-balance selection, optional default-template creation, daemon-thread kickoff |
| `BacktestCycleService` | `backend/app/services/backtest_cycle_service.py` | live launch path, prompt-report loading, internal LangGraph execution, legacy callback handling, run-state persistence, cycle advancement |
| `BacktestLangGraphRunner` | `backend/app/langgraph/runner.py` | internal LangGraph runner for prompt parsing, analysis aggregation, report rendering, and decision translation |
| `router` | `frontend/src/routes.ts` | flat route table for dashboard, portfolios, templates, reports, backtests, and orchestration |
| `queryKeys` | `frontend/src/lib/query-keys.ts` | canonical cache naming, portfolio invalidation helpers, orchestration namespaces |
| `Layout` | `frontend/src/components/layout.tsx` | sidebar shell, breadcrumbs, route labels, template-editor full-height layout |
| `GenerateReportDialog` | `frontend/src/components/forms/generate-report-dialog.tsx` | shared report-generation dialog with runtime inputs |

## CONVENTIONS
- Backend JSON is camelCase externally and snake_case internally; `CamelModel` owns aliasing and `extra="forbid"` request validation.
- Backend error envelopes are `{code, message, details[]}`; frontend `ApiRequestError` parsing depends on that exact shape.
- Money, quantities, and market values cross the API as strings; backend parsing lives in `backend/app/core/formatting.py`, while frontend conversion lives in shared formatting and analytics helpers.
- Balance records carry `operationType` (`DEPOSIT` or `WITHDRAWAL`); `BUY`, `SELL`, and `DIVIDEND` operations can only use deposit balances, `SPLIT` uses no balance, and portfolio cash calculations subtract withdrawal balances.
- Query invalidation is centralized in `frontend/src/lib/query-keys.ts`; ids are normalized to strings, symbol lists are trimmed/deduplicated/sorted where relevant, and orchestration caches live under `queryKeys.orchestration.*`.
- Template placeholder paths are a cross-stack contract spanning backend services/schemas and frontend types/editor code; the live roots are `inputs`, `portfolios`, and `reports`.
- Reports are point-in-time markdown snapshots keyed by unique `slug`; compiled reports derive timestamped snake_case names from templates, uploaded reports accept optional metadata, and all report sources download by slug.
- Orchestration is a live cross-stack feature, not a hidden prototype: the frontend exposes `/orchestration` routes, the backend exposes `/api/v1/orchestration/*`, and role/character contracts live in dedicated hooks, API modules, types, schemas, models, and repositories.
- Backtests are a live API/UI feature with `launchMode` support. Internal execution is the default path, while legacy callback fields remain compatibility-only surfaces and are only required for `launchMode="legacy_callback"`.
- Backtest execution reuses the existing report and trading infrastructure, and LangGraph-backed analysis runs inside the backend process instead of a separate worker.
- Application LLM calls must use official SDKs rather than raw HTTP requests; the current backend path uses `ChatOpenAI` and the official `OpenAI` Python client.

## ANTI-PATTERNS
- Do not bypass backend services or call provider adapters directly from routes or frontend code.
- Do not invent snake_case API fields, ad-hoc query keys, or duplicate placeholder/type contracts.
- Do not treat quote/history warnings as fatal when the degraded path is already defined.
- Do not change CSV import, template placeholder, template compile payloads, or runtime-input flow without updating backend tests and frontend callers together.
- Do not change report slug/name/source/download behavior, report filters, or `reports.*` placeholder output without updating backend tests, frontend callers, and template-editor guidance.
- Do not hide shipped orchestration surfaces behind direct URLs or stale docs; the orchestration workspace is a first-class route family and API surface.
- Do not document legacy callback mode as the default backtest path or require callback fields for normal internal execution.
- Do not bypass `BacktestService`, `BacktestCycleService`, `TradingOperationService`, or `ReportService` when changing backtest execution semantics.
- Do not reintroduce a second backtest-analysis runtime when the current implementation is intentionally Ledger-native and in-process.
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
- `start.sh` is the authoritative local orchestrator; it defaults to `25432/28000/25173`, reuses a healthy backend on the requested port, falls back to `25433/25434`, `28001/28002`, or `25174` when needed, injects `VITE_API_BASE_URL`, and no longer launches a separate backtest worker process.
- Supported schema repair is code-based in `backend/app/db/`; `backend/alembic/` is only a placeholder scaffold, not the migration source of truth.
- Playwright runs against backend `8001` and frontend `4173`; the backend startup helpers also set `BACKTEST_TEST_MODE=1`, which swaps `BacktestCycleService` into deterministic cycle behavior for E2E and test flows.
- Backend requires Python 3.13+; frontend targets Node 24 and pnpm 10.
- Root CI currently runs version-sync, backend-quality, frontend-quality, and frontend-e2e checks; Docker image publishing and cleanup live in separate workflows.
