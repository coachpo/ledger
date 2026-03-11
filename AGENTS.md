# PROJECT KNOWLEDGE BASE

**Generated:** 2026-03-11 13:46:03 EET  
**Commit:** b557b60  
**Branch:** main

## OVERVIEW
Ledger is a dual-stack portfolio tracker stitched together from backend and frontend git submodules. Core flows cover portfolio CRUD, balances, positions, delayed market data, CSV imports, and simulated BUY/SELL/DIVIDEND/SPLIT operations.

## CHILD DOCS
- `backend/AGENTS.md` — backend structure, route/service/schema/test rules
- `backend/app/services/AGENTS.md` — service-layer transaction, cache, and CSV workflow rules
- `frontend/AGENTS.md` — frontend routing, build/test flow, UI boundaries
- `frontend/src/lib/AGENTS.md` — shared API/query/analytics/formatting rules
- `frontend/src/components/portfolios/AGENTS.md` — portfolio workspace feature rules

## STRUCTURE
```text
ledger/
├── backend/              # git submodule: FastAPI app, SQLAlchemy models, pytest suite
├── frontend/             # git submodule: React/Vite app, Vitest, Playwright, shadcn config
├── docs/                 # product/API/data-model refs + design explorations
├── .github/workflows/    # CI, Docker image publishing, cleanup jobs
├── artifacts/            # generated Playwright/screenshots; not source
├── .gitmodules           # backend/frontend submodule remotes
└── start.sh              # boots backend + frontend together
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Bootstrap a fresh clone | `.gitmodules` + `git submodule update --init --recursive` | backend/frontend are separate repos checked out recursively in CI |
| Start both apps locally | `start.sh` | backend `8000`, frontend `5173`; reuses a healthy backend if already running |
| Cross-app E2E startup | `frontend/playwright.config.ts` + `frontend/scripts/start-playwright-*.mjs` | Playwright uses backend `8001`, frontend `4173` |
| Backend bootstrap | `backend/app/main.py` | app factory, CORS, error handlers, `/health` |
| Backend route wiring | `backend/app/api/router.py` + `backend/app/api/dependencies.py` | v1 router composition + DI |
| Backend business rules | `backend/app/services/AGENTS.md` | service-layer hotspots, transaction boundaries, provider/cache rules |
| Frontend app shell | `frontend/src/App.tsx` + `frontend/index.html` | router/providers + pre-mount theme sync |
| Frontend shared logic | `frontend/src/lib/AGENTS.md` | API contract, query keys, analytics, formatting |
| Portfolio feature work | `frontend/src/components/portfolios/AGENTS.md` | routed workspace, dialogs, mutations, quote UX |
| Workflow/release behavior | `.github/workflows/ci.yml`, `.github/workflows/docker-images.yml` | recursive submodule checkout, quality gates, Docker smoke builds |
| Product/reference docs | `docs/spec.md`, `docs/api-design.md`, `docs/data-model.md` | business constraints live here; `docs/new_looking/` is reference material |

## CODE MAP
| Symbol / Entry | Location | Role |
|---|---|---|
| `create_app` | `backend/app/main.py` | FastAPI app factory + lifecycle |
| `api_router` | `backend/app/api/router.py` | mounts all `/api/v1` routers |
| `upgrade_local_sqlite_schema` | `backend/app/db/session.py` | in-code SQLite schema upgrades; no Alembic |
| `MarketDataService` | `backend/app/services/market_data_service.py` | quote/history fetch + cache/warnings |
| `TradingOperationService` | `backend/app/services/trading_operation_service.py` | BUY/SELL/DIVIDEND/SPLIT rules |
| `App` | `frontend/src/App.tsx` | router + providers |
| `request` / `ApiRequestError` | `frontend/src/lib/api.ts` | typed fetch wrapper + structured errors |
| `queryKeys` / `invalidatePortfolioScope` | `frontend/src/lib/query-keys.ts` | cache naming + portfolio-scope invalidation |
| `usePortfolioWorkspaceData` | `frontend/src/components/portfolios/use-portfolio-workspace-data.ts` | shared portfolio workspace data orchestration |

## CROSS-STACK CONVENTIONS
- Backend JSON is camelCase externally and snake_case internally.
- Decimal money/quantity values cross the API as strings; convert with shared helpers, not ad-hoc parsing.
- Market data is best-effort: warnings can accompany partial/empty quote results without blocking the UI.
- Backend and frontend live as git submodules; root workflows check them out with `submodules: recursive`.
- `artifacts/`, `frontend/dist/`, cache folders, and `docs/new_looking/screenshots/` are generated/reference material, not source.

## ANTI-PATTERNS
- Do not bypass backend service layers for business rules.
- Do not invent snake_case API fields in frontend contracts.
- Do not treat quote/history failures as fatal when the product expects degraded-but-working views.
- Do not implement documented out-of-scope features from `docs/`: auth, short selling, FIFO/tax lots, realtime quote streaming.
- Do not treat `docs/` or generated assets as the source of truth over live code paths.
- Do not ignore submodule state when cloning, updating CI, or reviewing backend/frontend diffs.

## COMMANDS
```bash
git submodule update --init --recursive
./start.sh
python -m pip install -e './backend[dev]'
(cd backend && uvicorn app.main:app --reload)
(cd backend && ruff check app tests && black --check app tests && isort --check-only app tests && mypy app && pytest)
(cd frontend && pnpm install)
(cd frontend && pnpm dev)
(cd frontend && pnpm lint && pnpm build && pnpm test && pnpm test:e2e)
```

## NOTES
- No root package manifest; backend and frontend toolchains are independent submodules.
- CI checks out submodules recursively, then runs backend quality, frontend quality, and Docker smoke builds.
- SQLite is the zero-config local default; PostgreSQL comes via `DATABASE_URL`.
- Local dev ports (`8000`/`5173`) differ from Playwright ports (`8001`/`4173`).
