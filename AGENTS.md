# PROJECT KNOWLEDGE BASE

**Generated:** 2026-03-21
**Commit:** 8fd7fee
**Branch:** main

## OVERVIEW
Ledger is a dual-stack portfolio tracker split across `backend/` and `frontend/` git submodules. The live surface spans portfolio CRUD, deposit/withdrawal balances, aggregate positions, delayed market data, CSV imports, symbol-name lookup caching, simulated BUY/SELL/DIVIDEND/SPLIT workflows, text-template authoring/compilation, point-in-time report generation/upload/download, `{{reports...}}` placeholder reuse inside templates, and an experimental backtest workspace that runs LLM-guided historical simulations over saved portfolios.

## CHILD DOCS
- `backend/AGENTS.md` — backend architecture, validation flow, and layer routing
- `backend/app/core/AGENTS.md` — config, error envelope, normalization helpers
- `backend/app/db/AGENTS.md` — session lifecycle and PostgreSQL-only init/report-upgrade rules
- `backend/app/api/AGENTS.md` — route handler boundaries and dependency wiring
- `backend/app/services/AGENTS.md` — service ownership, template/report workflows, quote-provider wiring
- `backend/app/services/providers/AGENTS.md` — dormant provider adapter contracts
- `backend/app/schemas/AGENTS.md` — Pydantic validation and camelCase aliasing
- `backend/app/models/AGENTS.md` — ORM constraints, indexes, relationships, cache tables
- `backend/app/repositories/AGENTS.md` — query/repository patterns
- `backend/tests/AGENTS.md` — pytest fixtures, isolated PostgreSQL databases, report/template/backtest regression coverage
- `frontend/AGENTS.md` — frontend architecture, router shell, and report/backtest-aware validation workflow
- `frontend/src/lib/AGENTS.md` — API client, query keys, analytics, formatting, template and backtest contracts
- `frontend/src/lib/api/AGENTS.md` — domain API modules, upload/download boundaries, and route-path helpers
- `frontend/src/lib/types/AGENTS.md` — shared wire types for portfolios, templates, reports, backtests, and trading
- `frontend/src/hooks/AGENTS.md` — TanStack Query hook patterns and invalidation rules
- `frontend/src/components/AGENTS.md` — layout shell, theme system, shared components, forms, portfolio and backtest UI
- `frontend/src/components/backtests/AGENTS.md` — backtest result widgets, charts, badges, and trade-log tables
- `frontend/src/components/ui/AGENTS.md` — shadcn/ui primitives, sidebar context, and shared variant helpers
- `frontend/src/components/shared/AGENTS.md` — reusable tables, metrics, error boundaries, and shared field schemas
- `frontend/src/components/portfolios/AGENTS.md` — portfolio workspace sections, dialogs, tables, trades
- `frontend/src/pages/AGENTS.md` — dashboard, portfolio, template, report, and backtest routes
- `frontend/src/pages/backtests/AGENTS.md` — backtest list/config/detail orchestration and polling behavior
- `frontend/src/pages/portfolios/AGENTS.md` — portfolio list/detail orchestration and quote-enriched workspace rules
- `frontend/src/pages/templates/AGENTS.md` — template list/editor flows, debounce preview, and placeholder browser rules
- `frontend/src/pages/reports/AGENTS.md` — report list/detail flows, markdown render/edit/download behavior

## STRUCTURE
```text
ledger/
├── backend/              # git submodule: FastAPI app, SQLAlchemy models, pytest suite
├── frontend/             # git submodule: React/Vite app, TanStack Query, Vitest, Playwright, shadcn/ui
├── docs/                 # refreshed reference docs; still secondary to live code
├── .github/workflows/    # CI quality gates, Docker smoke build, image publish/cleanup
├── artifacts/            # generated screenshots and review artifacts; not source
├── .gitmodules           # backend/frontend submodule remotes
└── start.sh              # local orchestrator: db on 25432, backend on 28000, frontend on 25173
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Bootstrap a fresh clone | `.gitmodules` + `git submodule update --init --recursive` | CI and local development both rely on recursive submodules |
| Start the full stack locally | `start.sh`, `backend/docker-compose.yml` | cleans occupied ports, starts Postgres on `25432`, backend on `28000`, frontend on `25173` |
| Cross-app E2E startup | `frontend/playwright.config.ts`, `frontend/scripts/start-playwright-*.mjs` | Playwright uses backend `8001` and frontend `4173` |
| Backend bootstrap | `backend/app/main.py`, `backend/app/api/router.py`, `backend/app/api/dependencies.py` | app factory, router composition, DI |
| Backend template flow | `backend/app/api/templates.py`, `backend/app/services/template_compiler_service.py` | placeholder tree, inline compile, stored template compile |
| Backend reports flow | `backend/app/api/reports.py`, `backend/app/services/report_service.py`, `backend/app/schemas/report.py` | compile from template, upload markdown, download by slug |
| Backend backtests flow | `backend/app/api/backtests.py`, `backend/app/services/backtest_service.py`, `backend/app/services/backtest_engine.py` | create/list/cancel/delete lifecycle, background simulation, results aggregation |
| Backend DB upgrades | `backend/app/db/session.py` | portfolio/report upgrades, balance `operation_type`, market-quote `name`, obsolete-table cleanup |
| Backend tests | `backend/tests/AGENTS.md`, `backend/tests/test_api.py`, `backend/tests/test_backtests_api.py`, `backend/tests/test_backtest_engine.py` | CRUD, templates, reports, backtests, market-data fallback, cache behavior, legacy-schema upgrades |
| Frontend app shell | `frontend/src/App.tsx`, `frontend/src/routes.ts`, `frontend/src/components/layout.tsx` | query client, router provider, layout shell, theme toggle |
| Frontend API/type contracts | `frontend/src/lib/api/AGENTS.md`, `frontend/src/lib/types/AGENTS.md` | request helpers, upload/download rules, and shared wire types |
| Frontend portfolio UI | `frontend/src/components/portfolios/AGENTS.md` | balances, positions, trades, dialogs, tables |
| Frontend template UI | `frontend/src/pages/templates/editor.tsx`, `frontend/src/hooks/use-templates.ts`, `frontend/src/lib/api/templates.ts` | editor, preview, placeholder browser, CRUD |
| Frontend reports UI | `frontend/src/pages/reports/AGENTS.md`, `frontend/src/hooks/use-reports.ts`, `frontend/src/lib/api/reports.ts` | list/detail pages, upload/generate/delete, download/edit flows |
| Frontend backtests UI | `frontend/src/pages/backtests/AGENTS.md`, `frontend/src/hooks/use-backtests.ts`, `frontend/src/components/backtests/AGENTS.md` | configuration form, 5s status polling, charts, trade log, report links |
| Frontend tests / E2E | `frontend/vite.config.ts`, `frontend/src/test/setup.ts`, `frontend/playwright.config.ts`, `frontend/e2e/*.spec.ts` | local jsdom unit setup plus Chromium E2E on `8001`/`4173`, including report and backtest flows |
| CI quality gates | `.github/workflows/ci.yml`, `.github/workflows/docker-images.yml`, `.github/workflows/cleanup.yml` | quality jobs, Docker smoke/publish workflows, artifact/package cleanup |

## CODE MAP
| Symbol / Entry | Location | Role |
|---|---|---|
| `create_app` | `backend/app/main.py` | FastAPI app factory, exception handlers, CORS, healthcheck |
| `api_router` | `backend/app/api/router.py` | mounts all `/api/v1` routers, including templates, reports, and backtests |
| `init_db` | `backend/app/db/session.py` | creates tables and repairs supported legacy schemas |
| `PositionService` | `backend/app/services/position_service.py` | position CRUD plus symbol-name cache lookups |
| `TemplateCompilerService` | `backend/app/services/template_compiler_service.py` | resolves `{{inputs...}}`, `{{portfolios...}}`, and `{{reports...}}` placeholders against live data |
| `ReportService` | `backend/app/services/report_service.py` | report CRUD, upload validation, unique slug/name generation |
| `BacktestService` | `backend/app/services/backtest_service.py` | backtest CRUD, deposit-balance selection, optional default-template creation, background launch |
| `BacktestEngine` | `backend/app/services/backtest_engine.py` | NYSE schedule generation, parquet history cache, OpenAI Responses calls, report/trade attribution, results metrics |
| `TextTemplateService` | `backend/app/services/text_template_service.py` | stored template CRUD and uniqueness checks |
| `QuoteProvider` / `YahooFinanceQuoteProvider` | `backend/app/services/quote_provider.py` | quote/history provider contract + Yahoo Finance adapter |
| `App` | `frontend/src/App.tsx` | query client, router provider, theme provider, toaster, error boundary |
| `router` | `frontend/src/routes.ts` | flat route table for dashboard, portfolios, templates, reports, and backtests |
| `queryKeys` / `invalidatePortfolioScope` | `frontend/src/lib/query-keys.ts` | canonical cache naming + portfolio invalidation |
| `queryKeys.backtests` / `useBacktest` | `frontend/src/lib/query-keys.ts`, `frontend/src/hooks/use-backtests.ts` | backtest list/detail caching plus 5s polling while runs are active |
| `request` / `ApiRequestError` | `frontend/src/lib/api-client.ts` | typed fetch wrapper + structured error parsing |
| `Layout` | `frontend/src/components/layout.tsx` | sidebar shell, breadcrumbs, special full-height template-editor layout |
| `TemplateEditorPage` | `frontend/src/pages/templates/editor.tsx` | template editing, inline compile preview, placeholder browser |
| `ReportListPage` | `frontend/src/pages/reports/list.tsx` | generate from template, upload markdown, browse/delete/download reports |
| `BacktestDetailPage` | `frontend/src/pages/backtests/detail.tsx` | active-run progress, completed result charts, trade log, report links |
| `BacktestConfigPage` | `frontend/src/pages/backtests/config.tsx` | existing/new portfolio launch flow, benchmark selection, LLM/commission config |

## CONVENTIONS
- Backend JSON is camelCase externally and snake_case internally; `CamelModel` owns aliasing and `extra="forbid"` request validation.
- Backend error envelopes are `{code, message, details[]}`; frontend `ApiRequestError` parsing depends on that exact shape.
- Money, quantities, and market values cross the API as strings; backend parsing lives in `backend/app/core/formatting.py`, while frontend conversion lives in shared formatting and analytics helpers.
- Balance records carry `operationType` (`DEPOSIT` or `WITHDRAWAL`); `BUY`, `SELL`, and `DIVIDEND` operations can only use deposit balances, `SPLIT` uses no balance, and portfolio cash calculations subtract withdrawal balances.
- Portfolio slugs are lowercase underscore identifiers, unique at create time, and intentionally absent from the update contract.
- Symbol-name lookup and market-data fetches are best-effort: cache reuse and warning paths should preserve a usable response whenever possible.
- Query invalidation is centralized in `frontend/src/lib/query-keys.ts`; do not invent ad-hoc keys inside hooks or components.
- Template placeholder paths are a cross-stack contract spanning `backend/app/services/template_compiler_service.py`, `backend/app/schemas/text_template.py`, `frontend/src/lib/types/text-template.ts`, and `frontend/src/pages/templates/editor.tsx`; the live roots are `inputs`, `portfolios`, and `reports`.
- Report placeholder selectors support both exact names and dynamic selectors such as `reports.latest`, `reports.latest("TICKER")`, `reports[index]`, and `reports.by_tag("tag").latest`; valid no-match selectors compile to an empty string, malformed selectors compile to explicit sentinel text.
- Reports are point-in-time markdown snapshots keyed by unique `slug`; compiled reports derive timestamped snake_case names from templates, uploaded reports accept optional author/description/tags metadata, direct JSON creation is supported, and all three sources download by slug.
- Backtests are a live API/UI feature, not a dormant stock-analysis leftover: each run stores per-backtest LLM config, selected deposit balance, recent activity, result curves, and terminal errors on the `backtests` row.
- Backtest execution reuses the existing report and trading infrastructure: generated reports are tagged with `backtest_<id>`, simulated trades carry `trading_operations.backtest_id`, and interrupted `PENDING`/`RUNNING` jobs are marked failed during `init_db()` startup repair.
- Backend and frontend are git submodules; root workflows always check them out with `submodules: recursive`.

## ANTI-PATTERNS
- Do not bypass backend services or call provider adapters directly from routes or frontend code.
- Do not invent snake_case API fields, ad-hoc query keys, or duplicate placeholder/type contracts.
- Do not treat quote/history warnings as fatal when the degraded path is already defined.
- Do not change CSV import, template placeholder, or template compile payloads without updating backend tests and frontend callers.
- Do not change report slug/name/source/download behavior, report filters, or `reports.*` placeholder output without updating backend tests, frontend callers, and template-editor guidance.
- Do not document backtests as absent or dormant; `/api/v1/backtests` and `/backtests/*` are live surfaces backed by dedicated services, pages, hooks, and E2E coverage.
- Do not bypass `TradingOperationService` or `ReportService` when changing backtest execution semantics; the simulation engine depends on those shared contracts for attribution and cleanup.
- Do not treat `docs/`, `artifacts/`, `frontend/dist/`, or cache directories as the source of truth over live code.
- Do not ignore submodule state when cloning, updating CI, or reviewing backend/frontend diffs.

## COMMANDS
```bash
git submodule update --init --recursive
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
- `start.sh` is the authoritative local orchestrator; unlike the raw backend/frontend dev defaults, it binds backend/frontend to `28000/25173` and injects `VITE_API_BASE_URL` for the frontend process.
- Supported schema repair is code-based in `backend/app/db/session.py`; the leftover `backend/alembic/` tree is not the source of truth.
- Playwright still runs against backend `8001` and frontend `4173`, so route/E2E issues should always be checked in that environment too; the Playwright backend startup script also sets `BACKTEST_TEST_MODE=1` for deterministic backtest runs.
- Backend requires Python 3.13+; frontend targets Node 24 and pnpm 10.
- CI currently runs backend lint/format/type/test checks, then frontend lint/build/E2E, then an amd64 Docker smoke build. Local frontend typecheck and unit tests are available even though they are not both enforced in `ci.yml` yet, and both report and backtest flows have dedicated E2E coverage in `frontend/e2e/reports.spec.ts` and `frontend/e2e/backtests.spec.ts`.
