# PROJECT KNOWLEDGE BASE

**Generated:** 2026-03-11 13:26:32 EET  
**Commit:** 9d6d385  
**Branch:** dev

## OVERVIEW
Ledger is a dual-stack portfolio tracker: FastAPI backend + React/Vite frontend. Core flows: portfolio CRUD, balances, positions, delayed market data, CSV imports, and simulated BUY/SELL/DIVIDEND/SPLIT operations.

## CHILD DOCS
- `backend/AGENTS.md` — backend structure, API/service/schema/test rules
- `frontend/AGENTS.md` — frontend placement rules, build/test flow, UI vs feature boundaries
- `frontend/src/components/portfolios/AGENTS.md` — portfolio workspace feature rules

## STRUCTURE
```text
ledger/
├── backend/              # FastAPI app, SQLAlchemy models, pytest suite
├── frontend/             # React/Vite app, Vitest, Playwright, Vite configs
├── docs/                 # spec, requirements, API/data-model reference docs
├── .github/workflows/    # CI, Docker image publishing, cleanup jobs
├── artifacts/            # generated Playwright/screenshots; not source
└── start.sh              # starts backend + frontend together
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Start both apps locally | `start.sh` | backend `8000`, frontend `5173` |
| Cross-app test startup | `frontend/playwright.config.ts` + `frontend/scripts/start-playwright-*.mjs` | Playwright uses backend `8001`, frontend `4173` |
| Backend bootstrap | `backend/app/main.py` | app factory, CORS, error handlers, `/health` |
| Backend route wiring | `backend/app/api/router.py` + `backend/app/api/dependencies.py` | v1 router composition + DI |
| Frontend route shell | `frontend/src/App.tsx` | QueryClient, ThemeProvider, nested routes |
| Portfolio feature work | `frontend/src/components/portfolios/` | dense feature hotspot; see child doc |
| Shared UI primitives | `frontend/src/components/ui/` | generic wrappers with `data-slot` markers |
| API contract changes | `backend/app/schemas/` + `frontend/src/lib/api.ts` | keep both sides aligned |
| Product/reference docs | `docs/spec.md`, `docs/api-design.md`, `docs/data-model.md` | business constraints live here |

## CODE MAP
| Symbol / Entry | Location | Role |
|---|---|---|
| `create_app` | `backend/app/main.py` | FastAPI app factory + lifecycle |
| `api_router` | `backend/app/api/router.py` | mounts all `/api/v1` routers |
| `MarketDataService` | `backend/app/services/market_data_service.py` | quote/history fetch + cache/warnings |
| `TradingOperationService` | `backend/app/services/trading_operation_service.py` | buy/sell/dividend/split rules |
| `App` | `frontend/src/App.tsx` | router + providers |
| `request` / `ApiRequestError` | `frontend/src/lib/api.ts` | typed fetch wrapper + structured errors |
| `queryKeys` / `invalidatePortfolioScope` | `frontend/src/lib/query-keys.ts` | cache naming + invalidation |
| `usePortfolioWorkspaceData` | `frontend/src/components/portfolios/use-portfolio-workspace-data.ts` | shared portfolio workspace data orchestration |

## CROSS-STACK CONVENTIONS
- Backend JSON is camelCase externally, snake_case internally.
- Decimal money/quantity values cross the API as strings; convert with shared helpers, not ad-hoc parsing.
- Market data is best-effort: warnings can accompany partial/empty quote results without blocking the portfolio UI.
- `artifacts/`, cache folders, and screenshots are generated/reference material, not source.

## ANTI-PATTERNS
- Do not bypass backend service layers for business rules.
- Do not invent snake_case API fields in frontend contracts.
- Do not treat quote/history failures as fatal when the product expects degraded-but-working views.
- Do not implement documented out-of-scope features from `docs/`: auth, short selling, FIFO/tax lots, realtime quote streaming.
- Do not treat `docs/` or generated artifacts as the source of truth over live code paths.

## COMMANDS
```bash
./start.sh
python -m pip install -e './backend[dev]'
(cd backend && uvicorn app.main:app --reload)
(cd backend && ruff check app tests && black --check app tests && isort --check-only app tests && mypy app && pytest)
(cd frontend && pnpm install)
(cd frontend && pnpm dev)
(cd frontend && pnpm lint && pnpm build && pnpm test && pnpm test:e2e)
```

## NOTES
- No root package manifest; backend and frontend toolchains are independent.
- CI runs backend lint/type/test and frontend lint/build/e2e.
- SQLite is the zero-config local default; PostgreSQL comes via `DATABASE_URL`.
