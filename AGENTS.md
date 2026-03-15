# PROJECT KNOWLEDGE BASE

**Generated:** 2026-03-15

## OVERVIEW
Ledger is a dual-stack portfolio tracker split across backend and frontend submodules. The live product surface covers portfolio CRUD, balances, positions, delayed market data, CSV imports, and simulated BUY/SELL/DIVIDEND/SPLIT operations.

## CHILD DOCS
- `backend/AGENTS.md` — backend architecture, commands, and layer routing
- `backend/app/core/AGENTS.md` — config, error envelope, normalization helpers
- `backend/app/db/AGENTS.md` — session lifecycle and PostgreSQL-only init/upgrade rules
- `backend/app/api/AGENTS.md` — route handler boundaries and dependency injection
- `backend/app/services/AGENTS.md` — service transaction ownership and quote-provider wiring
- `backend/app/services/providers/AGENTS.md` — legacy provider adapter contracts
- `backend/app/schemas/AGENTS.md` — Pydantic validation and camelCase aliasing
- `backend/app/models/AGENTS.md` — ORM constraints, indexes, relationships
- `backend/app/repositories/AGENTS.md` — query/repository patterns
- `backend/tests/AGENTS.md` — pytest fixtures and isolated PostgreSQL databases
- `frontend/AGENTS.md` — frontend architecture, router shell, pnpm/test workflow
- `frontend/src/lib/AGENTS.md` — API client, query keys, analytics, formatting
- `frontend/src/hooks/AGENTS.md` — TanStack Query hook patterns and invalidation rules
- `frontend/src/components/AGENTS.md` — layout shell, shared components, forms, portfolio UI
- `frontend/src/components/portfolios/AGENTS.md` — portfolio workspace sections, dialogs, and trades

## STRUCTURE
```text
ledger/
├── backend/              # git submodule: FastAPI app, SQLAlchemy models, pytest suite
├── frontend/             # git submodule: React/Vite app, TanStack Query, Vitest, Playwright, shadcn/ui
├── docs/                 # historical/reference documentation; verify against live code
├── .github/workflows/    # CI quality gates + Docker smoke/publish jobs
├── artifacts/            # generated browser artifacts/screenshots; not source
├── .gitmodules           # backend/frontend submodule remotes
└── start.sh              # boots backend + frontend together
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Bootstrap a fresh clone | `.gitmodules` + `git submodule update --init --recursive` | CI and local dev both rely on recursive submodules |
| Start both apps locally | `start.sh` | backend `8000`, frontend `5173`; requires PostgreSQL already running |
| Cross-app E2E startup | `frontend/playwright.config.ts` + `frontend/scripts/start-playwright-*.mjs` | Playwright uses backend `8001`, frontend `4173` |
| Backend bootstrap | `backend/app/main.py`, `backend/app/api/router.py`, `backend/app/api/dependencies.py` | app factory, router composition, DI |
| Backend infrastructure | `backend/app/core/AGENTS.md`, `backend/app/db/AGENTS.md` | settings, errors, normalization, session/init/upgrades |
| Backend service work | `backend/app/services/AGENTS.md`, `backend/app/services/providers/AGENTS.md` | CRUD flows, market data, legacy provider adapters |
| Backend data contracts | `backend/app/schemas/AGENTS.md`, `backend/app/models/AGENTS.md`, `backend/app/repositories/AGENTS.md` | schemas, ORM entities, queries |
| Backend tests | `backend/tests/AGENTS.md` | fixture setup + API and DB-upgrade coverage |
| Frontend app shell | `frontend/src/App.tsx`, `frontend/src/routes.ts`, `frontend/src/components/layout.tsx` | query client, flat router shell |
| Frontend shared logic | `frontend/src/lib/AGENTS.md`, `frontend/src/hooks/AGENTS.md` | API wrapper, query keys, analytics, TanStack Query hooks |
| Portfolio UI | `frontend/src/components/portfolios/AGENTS.md` | portfolio list/detail, balances, positions, trades, dialogs |
| Frontend tests / E2E | `frontend/vite.config.ts`, `frontend/src/test/setup.ts`, `frontend/playwright.config.ts` | Vitest uses jsdom; Playwright runs on backend `8001` / frontend `4173` |

## CODE MAP
| Symbol / Entry | Location | Role |
|---|---|---|
| `create_app` | `backend/app/main.py` | FastAPI app factory + lifecycle |
| `api_router` | `backend/app/api/router.py` | mounts all `/api/v1` routers |
| `get_settings` | `backend/app/core/config.py` | cached settings / env alias resolution |
| `init_db` | `backend/app/db/session.py` | creates tables and repairs supported legacy schemas |
| `QuoteProvider` / `YahooFinanceQuoteProvider` | `backend/app/services/quote_provider.py` | quote/history provider contract + Yahoo Finance adapter |
| `MarketDataService` | `backend/app/services/market_data_service.py` | quote/history fetch + cache/warnings |
| `TradingOperationService` | `backend/app/services/trading_operation_service.py` | BUY/SELL/DIVIDEND/SPLIT rules |
| `App` | `frontend/src/App.tsx` | query client, router provider, toaster, error boundary |
| `router` | `frontend/src/routes.ts` | flat route table for dashboard and portfolios |
| `queryKeys` / `invalidatePortfolioScope` | `frontend/src/lib/query-keys.ts` | canonical cache naming + invalidation |
| `request` / `ApiRequestError` | `frontend/src/lib/api-client.ts` | typed fetch wrapper + structured errors |
| `PortfolioDetailPage` | `frontend/src/pages/portfolios/detail.tsx` | balances/positions/trades workspace |

## CROSS-STACK CONVENTIONS
- Backend JSON is camelCase externally and snake_case internally; `CamelModel` owns aliasing and `extra="forbid"` validation.
- Money and quantity decimals cross the API as strings; backend parses with `app/core/formatting.py`, while frontend conversion lives in shared formatting and analytics helpers.
- Error responses use a structured envelope: `code`, `message`, and optional `details`; routes raise `ApiError` helpers rather than raw `HTTPException`.
- Market data is best-effort: quote/history warnings should preserve a usable response when possible.
- Query invalidation is centralized in `frontend/src/lib/query-keys.ts`; do not invent ad-hoc keys in components.
- Backend and frontend are git submodules; root workflows always check them out with `submodules: recursive`.
- `docs/`, `artifacts/`, `frontend/dist/`, and similar generated/reference directories are not the source of truth over live code.

## ANTI-PATTERNS
- Do not bypass backend services or call provider adapters directly from routes or frontend code.
- Do not invent snake_case API fields or ad-hoc query keys.
- Do not treat quote/history warnings as fatal when the degraded path is already defined.
- Do not use `docs/` or generated assets as authoritative over live backend/frontend code paths.
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
- Backend test coverage currently lives in `backend/tests/test_api.py`.
- Frontend unit coverage currently sits in `frontend/src/lib/*.test.ts`; route coverage lives in `frontend/e2e/*.spec.ts`.
- Playwright uses backend `8001` and frontend `4173`, which differs from local dev ports `8000` and `5173`.
