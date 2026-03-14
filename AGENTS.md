# PROJECT KNOWLEDGE BASE

**Generated:** 2026-03-14 22:59:05 EET
**Commit:** 31fe512
**Branch:** main

## OVERVIEW
Ledger is a dual-stack portfolio tracker split across backend and frontend submodules. Core flows cover portfolio CRUD, balances, positions, delayed market data, CSV imports, simulated BUY/SELL/DIVIDEND/SPLIT operations, and a stock-analysis workspace built around reusable LLM configs, prompt templates, snippets, conversations, responses, and versions.

## CHILD DOCS
- `backend/AGENTS.md` — backend architecture, commands, and layer routing
- `backend/app/core/AGENTS.md` — config, error envelope, normalization helpers
- `backend/app/db/AGENTS.md` — session lifecycle and in-code SQLite upgrades
- `backend/app/api/AGENTS.md` — route handler boundaries and DI
- `backend/app/services/AGENTS.md` — service transaction ownership and quote-provider wiring
- `backend/app/services/stock_analysis/AGENTS.md` — context building, prompt rendering, parser rules
- `backend/app/services/providers/AGENTS.md` — OpenAI/Anthropic/Gemini adapter contracts
- `backend/app/schemas/AGENTS.md` — Pydantic validation and camelCase aliasing
- `backend/app/models/AGENTS.md` — ORM constraints, indexes, relationships
- `backend/app/repositories/AGENTS.md` — query/repository patterns
- `backend/tests/AGENTS.md` — pytest fixtures, temp SQLite, high-signal backend tests
- `frontend/AGENTS.md` — frontend architecture, router shell, pnpm/test workflow
- `frontend/src/lib/AGENTS.md` — API client, query keys, analytics, formatting
- `frontend/src/hooks/AGENTS.md` — TanStack Query hook patterns and invalidation rules
- `frontend/src/components/AGENTS.md` — routed screens, layout shell, shared component boundaries
- `frontend/src/components/portfolios/AGENTS.md` — portfolio workspace pages, sections, dialogs

## STRUCTURE
```text
ledger/
├── backend/              # git submodule: FastAPI app, SQLAlchemy models, pytest suite
├── frontend/             # git submodule: React/Vite app, TanStack Query, Vitest, Playwright, shadcn/ui
├── docs/                 # requirements, API design, data model, test plan; reference material only
├── .github/workflows/    # CI quality gates + Docker smoke/publish jobs
├── artifacts/            # generated browser artifacts/screenshots; not source
├── .gitmodules           # backend/frontend submodule remotes
└── start.sh              # boots backend + frontend together
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Bootstrap a fresh clone | `.gitmodules` + `git submodule update --init --recursive` | CI and local dev both rely on recursive submodules |
| Start both apps locally | `start.sh` | backend `8000`, frontend `5173`, reuses a healthy backend |
| Cross-app E2E startup | `frontend/playwright.config.ts` + `frontend/scripts/start-playwright-*.mjs` | Playwright uses backend `8001`, frontend `4173` |
| Backend app bootstrap | `backend/app/main.py`, `backend/app/api/router.py`, `backend/app/api/dependencies.py` | app factory, error handlers, router composition, DI |
| Backend infrastructure | `backend/app/core/AGENTS.md`, `backend/app/db/AGENTS.md` | settings, error envelope, normalization, session/init/SQLite upgrades |
| Backend service work | `backend/app/services/AGENTS.md`, `backend/app/services/stock_analysis/AGENTS.md`, `backend/app/services/providers/AGENTS.md` | CRUD flows, market data, stock-analysis orchestration, provider adapters |
| Backend data contracts | `backend/app/schemas/AGENTS.md`, `backend/app/models/AGENTS.md`, `backend/app/repositories/AGENTS.md` | Pydantic schemas, ORM entities, SQLAlchemy queries |
| Backend test hotspots | `backend/tests/AGENTS.md` | fixture setup + API, stock-analysis, schema, provider tests |
| Frontend app shell | `frontend/src/App.tsx`, `frontend/src/routes.ts`, `frontend/src/components/layout.tsx`, `frontend/AGENTS.md` | query client, flat router shell, and a sidebar with six destinations |
| Frontend shared logic | `frontend/src/lib/AGENTS.md`, `frontend/src/hooks/AGENTS.md` | API wrapper, query keys, analytics, formatting, TanStack Query hooks |
| Frontend routed screens | `frontend/src/components/AGENTS.md` | dashboard, LLM config/template/snippet pages, responses browser, layout/error boundary |
| Portfolio UI | `frontend/src/components/portfolios/AGENTS.md` | portfolio list/detail, balances, positions, trades, dialogs |
| Frontend tests / E2E | `frontend/vite.config.ts`, `frontend/src/test/setup.ts`, `frontend/playwright.config.ts` | Vitest uses jsdom; Playwright runs on backend `8001` / frontend `4173` |
| CI quality gates | `.github/workflows/ci.yml` | backend quality, frontend quality, then Docker smoke builds |
| Product / scope reference | `docs/spec.md`, `docs/requirements.md`, `docs/api-design.md`, `docs/data-model.md`, `docs/test-plan.md` | reference only; do not override live code paths |

## CODE MAP
| Symbol / Entry | Location | Role |
|---|---|---|
| `create_app` | `backend/app/main.py` | FastAPI app factory + lifecycle |
| `api_router` | `backend/app/api/router.py` | mounts all `/api/v1` routers |
| `get_settings` | `backend/app/core/config.py` | cached settings / env alias resolution |
| `upgrade_local_sqlite_schema` | `backend/app/db/session.py` | in-code SQLite upgrades; no Alembic |
| `QuoteProvider` / `YahooFinanceQuoteProvider` | `backend/app/services/quote_provider.py` | quote/history provider contract + Yahoo Finance adapter |
| `MarketDataService` | `backend/app/services/market_data_service.py` | quote/history fetch + cache/warnings |
| `TradingOperationService` | `backend/app/services/trading_operation_service.py` | BUY/SELL/DIVIDEND/SPLIT rules |
| `StockAnalysisService` | `backend/app/services/stock_analysis/service.py` | settings, conversations, responses, versions |
| `AnalysisContextService` | `backend/app/services/stock_analysis/context.py` | live context + placeholder rendering |
| `LlmGatewayService` | `backend/app/services/llm_gateway_service.py` | provider-backed stock-analysis requests |
| `App` | `frontend/src/App.tsx` | query client, router provider, toaster, error boundary |
| `router` | `frontend/src/routes.ts` | flat route table for dashboard, portfolios, LLM inputs, and responses |
| `queryKeys` / `invalidatePortfolioScope` | `frontend/src/lib/query-keys.ts` | canonical cache naming + invalidation |
| `request` / `ApiRequestError` | `frontend/src/lib/api.ts` | typed fetch wrapper + structured errors |
| `useStockAnalysis*` hooks | `frontend/src/hooks/use-stock-analysis.ts` | settings, conversations, responses, versions, and preview |
| `PortfolioDetailPage` | `frontend/src/components/portfolios/portfolio-detail-page.tsx` | balances/positions/trades workspace |
| `ResponsesPage` | `frontend/src/components/responses-page.tsx` | response browser with portfolio/conversation filters |

## CROSS-STACK CONVENTIONS
- Backend JSON is camelCase externally and snake_case internally; `CamelModel` owns aliasing and `extra="forbid"` validation.
- Money/quantity decimals cross the API as strings; backend parses with `app/core/formatting.py`, while frontend conversion usually lives in shared formatting/analytics helpers and any remaining page-level parsing stays localized.
- Error responses use a structured envelope: `code`, `message`, and optional `details`; routes raise `ApiError` helpers rather than raw `HTTPException`.
- Market data and stock-analysis are best-effort: quote/history warnings and `partial_failure` runs should preserve usable responses when possible.
- Global stock-analysis resources live under `/stock-analysis/*` (`llm-configs`, `prompt-templates`, `snippets`); portfolio settings, conversations, responses, and versions stay under `/portfolios/{id}/stock-analysis/*`.
- Prompt preview and persisted stock-analysis records distinguish `single` / `follow_up` steps from the two-step `fresh_analysis` / `compare_decide_reflect` workflow.
- Query invalidation is centralized in `frontend/src/lib/query-keys.ts`; do not invent ad-hoc keys in components.
- Backend and frontend are git submodules; root workflows always check them out with `submodules: recursive`.
- `docs/`, `artifacts/`, `frontend/dist/`, and similar generated/reference directories are not the source of truth over live code.

## ANTI-PATTERNS
- Do not bypass backend services or call provider adapters directly from routes or frontend code.
- Do not invent snake_case API fields, ad-hoc query keys, or portfolio-local copies of global LLM resources.
- Do not treat quote/history warnings or stock-analysis partial failures as fatal when the degraded path is already defined.
- Do not trigger trading-operation mutations from stock-analysis output; responses stay advisory only.
- Do not implement documented out-of-scope features from `docs/`: auth, short selling, FIFO/tax lots, realtime quote streaming, autonomous execution, or external research ingestion.
- Do not treat `docs/` or generated assets as authoritative over live backend/frontend code paths.
- Do not ignore submodule state when cloning, updating CI, or reviewing backend/frontend diffs.

## COMMANDS
```bash
git submodule update --init --recursive
python -m pip install -e './backend[dev]'
(cd frontend && pnpm install)
./start.sh
(cd backend && python -m uvicorn app.main:app --reload)
(cd backend && ruff check app tests && black --check app tests && isort --check-only app tests && mypy app && pytest)
(cd frontend && pnpm lint && pnpm typecheck && pnpm build)
(cd frontend && pnpm test:run)
(cd frontend && pnpm exec playwright install --with-deps chromium && pnpm test:e2e)
```

## NOTES
- Backend requires Python 3.13+ per `backend/pyproject.toml`; frontend CI uses Node 24 and pnpm 10.
- `start.sh` validates dependencies, reuses an existing healthy backend, and exports `VITE_API_BASE_URL` for the frontend dev server.
- Backend test hotspots are `backend/tests/test_api.py`, `backend/tests/test_stock_analysis.py`, `backend/tests/test_stock_analysis_schema.py`, `backend/tests/test_openai_responses_service.py`, and `backend/tests/test_provider_schema_free_paths.py`.
- Frontend unit coverage currently sits in `frontend/src/lib/*.test.ts`; route and CRUD coverage lives in `frontend/e2e/*.spec.ts`.
- Playwright uses backend `8001` and frontend `4173`, which differs from local dev ports `8000` and `5173`.
