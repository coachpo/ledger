# PROJECT KNOWLEDGE BASE

**Generated:** 2026-03-13 23:19:29 EET
**Commit:** 1151d40
**Branch:** main

## OVERVIEW
Ledger is a dual-stack portfolio tracker stitched together from backend and frontend git submodules. Core flows cover portfolio CRUD, balances, positions, delayed market data, CSV imports, simulated BUY/SELL/DIVIDEND/SPLIT operations, and a stock-analysis workflow built around reusable LLM configs, prompt templates, conversations, runs, and versions.

## CHILD DOCS
- `backend/AGENTS.md` — backend structure, route/service/schema/test rules
- `backend/app/services/AGENTS.md` — service-layer transaction, cache, CSV, LLM config, and prompt-template rules
- `backend/app/services/stock_analysis/AGENTS.md` — context building, two-step execution, parser, defaults, mappers
- `backend/app/services/providers/AGENTS.md` — provider adapter contracts for OpenAI, Anthropic, and Gemini
- `backend/app/api/AGENTS.md` — route handler rules, service delegation, error translation
- `backend/app/schemas/AGENTS.md` — Pydantic schema validation, serialization, camelCase aliasing
- `backend/app/models/AGENTS.md` — ORM entity constraints, indexes, relationships
- `backend/app/repositories/AGENTS.md` — data access layer query patterns
- `frontend/AGENTS.md` — frontend routing, build/test flow, UI boundaries
- `frontend/src/lib/AGENTS.md` — shared API/query/analytics/formatting rules
- `frontend/src/components/ui/AGENTS.md` — generic UI primitive rules, shadcn/Radix-Nova conventions
- `frontend/src/components/portfolios/AGENTS.md` — portfolio workspace feature rules
- `frontend/src/components/portfolios/stock-analysis-workspace/AGENTS.md` — stock-analysis workspace state/query/card orchestration

## STRUCTURE
```text
ledger/
├── backend/              # git submodule: FastAPI app, SQLAlchemy models, pytest suite
├── frontend/             # git submodule: React/Vite app, Vitest, Playwright, shadcn config
├── docs/                 # product/API/data-model refs + requirements
├── .github/workflows/    # CI, Docker image publishing, cleanup jobs
├── artifacts/            # generated Playwright/screenshots; not source
├── .gitmodules           # backend/frontend submodule remotes
└── start.sh              # boots backend + frontend together
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Bootstrap a fresh clone | `.gitmodules` + `git submodule update --init --recursive` | backend/frontend are separate repos checked out recursively in CI |
| Start both apps locally | `start.sh` | backend `8000`, frontend `5173`; accepts host/port env vars and reuses a healthy backend |
| Cross-app E2E startup | `frontend/playwright.config.ts` + `frontend/scripts/start-playwright-*.mjs` | Playwright uses backend `8001`, frontend `4173` |
| Backend bootstrap | `backend/app/main.py` | app factory, CORS, error handlers, `/health` |
| Backend route wiring | `backend/app/api/router.py` + `backend/app/api/dependencies.py` | v1 router composition + DI |
| Backend stock-analysis orchestration | `backend/app/services/stock_analysis/AGENTS.md` | prompt rendering, two-step runs, version materialization |
| Backend provider adapters | `backend/app/services/providers/AGENTS.md` | OpenAI chat/responses, Anthropic, Gemini contracts |
| Frontend app shell | `frontend/src/App.tsx` + `frontend/index.html` | router/providers + pre-mount theme sync |
| Frontend shared logic | `frontend/src/lib/AGENTS.md` | API contract, query keys, analytics, formatting |
| Portfolio feature work | `frontend/src/components/portfolios/AGENTS.md` | routed workspace, dialogs, quote UX, stock-analysis entry points |
| Stock-analysis workspace UI | `frontend/src/components/portfolios/stock-analysis-workspace/AGENTS.md` | portfolio settings, conversations, runs, timeline |
| Shared LLM input management | `frontend/src/components/portfolios/stock-analysis-inputs-page.tsx` | global config/template CRUD route |
| Quality gates | `.github/workflows/ci.yml`, `backend/tests/test_api.py`, `backend/tests/test_stock_analysis.py`, `frontend/e2e/app.spec.ts` | backend lint/typecheck/tests, frontend lint/build/e2e |
| Product/reference docs | `docs/spec.md`, `docs/api-design.md`, `docs/data-model.md`, `docs/requirements.md` | business constraints live here |

## CODE MAP
| Symbol / Entry | Location | Role |
|---|---|---|
| `create_app` | `backend/app/main.py` | FastAPI app factory + lifecycle |
| `api_router` | `backend/app/api/router.py` | mounts all `/api/v1` routers |
| `upgrade_local_sqlite_schema` | `backend/app/db/session.py` | in-code SQLite schema upgrades; no Alembic |
| `MarketDataService` | `backend/app/services/market_data_service.py` | quote/history fetch + cache/warnings |
| `TradingOperationService` | `backend/app/services/trading_operation_service.py` | BUY/SELL/DIVIDEND/SPLIT rules |
| `StockAnalysisService` | `backend/app/services/stock_analysis/service.py` | settings, conversations, runs, versions |
| `AnalysisContextService` | `backend/app/services/stock_analysis/context.py` | context snapshots + placeholder rendering |
| `LlmGatewayService` | `backend/app/services/llm_gateway_service.py` | routes provider-backed stock-analysis requests |
| `App` | `frontend/src/App.tsx` | router + providers + lazy stock-analysis routes |
| `request` / `ApiRequestError` | `frontend/src/lib/api.ts` | typed fetch wrapper + structured errors |
| `queryKeys` / `invalidatePortfolioScope` | `frontend/src/lib/query-keys.ts` | portfolio + stock-analysis cache naming/invalidation |
| `usePortfolioWorkspaceData` | `frontend/src/components/portfolios/use-portfolio-workspace-data.ts` | shared portfolio workspace data orchestration |
| `useStockAnalysisWorkspace` | `frontend/src/components/portfolios/stock-analysis-workspace/use-stock-analysis-workspace.ts` | stock-analysis workspace state orchestration |
| `StockAnalysisInputsPage` | `frontend/src/components/portfolios/stock-analysis-inputs-page.tsx` | global LLM config + prompt template management |

## CROSS-STACK CONVENTIONS
- Backend JSON is camelCase externally and snake_case internally.
- Decimal money/quantity values cross the API as strings; convert with shared helpers, not ad-hoc parsing.
- Market data and stock analysis are best-effort: quote/history warnings and stock-analysis partial failures should keep the UI/history usable when possible.
- LLM configs and prompt templates are global resources; portfolio settings, conversations, runs, and versions are portfolio-scoped.
- Prompt preview renders saved or inline templates against live portfolio context without calling a provider.
- Backend and frontend live as git submodules; root workflows check them out with `submodules: recursive`.
- `artifacts/`, `frontend/dist/`, and cache folders are generated/reference material, not source.

## ANTI-PATTERNS
- Do not bypass backend service layers or call provider adapters directly from routes.
- Do not invent snake_case API fields, ad-hoc query keys, or portfolio-local copies of global LLM resources.
- Do not treat quote/history failures or stock-analysis partial failures as fatal when degraded paths already exist.
- Do not implement documented out-of-scope features from `docs/`: auth, short selling, FIFO/tax lots, realtime quote streaming.
- Do not treat `docs/` or generated assets as the source of truth over live code paths.
- Do not ignore submodule state when cloning, updating CI, or reviewing backend/frontend diffs.

## COMMANDS
```bash
git submodule update --init --recursive
python -m pip install -e './backend[dev]'
(cd frontend && pnpm install)
./start.sh
(cd backend && python -m uvicorn app.main:app --reload)
(cd backend && ruff check app tests && black --check app tests && isort --check-only app tests && mypy app && pytest)
(cd frontend && pnpm lint && pnpm build)
(cd frontend && pnpm test)
(cd frontend && pnpm test:watch)
(cd frontend && pnpm exec playwright install --with-deps chromium && pnpm test:e2e)
```

## NOTES
- No root package manifest; backend and frontend toolchains are independent submodules.
- CI checks out submodules recursively, then runs backend quality, frontend lint/build/e2e, and Docker smoke builds.
- `backend/tests/test_api.py` and `backend/tests/test_stock_analysis.py` are the main backend integration hotspots.
- Stock analysis now supports `single_prompt` and `two_step_workflow` modes plus global reusable snippets.
- SQLite is the zero-config local default; PostgreSQL comes via `DATABASE_URL`.
- Local dev ports (`8000`/`5173`) differ from Playwright ports (`8001`/`4173`).
