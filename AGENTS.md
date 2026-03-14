# PROJECT KNOWLEDGE BASE

**Generated:** 2026-03-14 12:20:37 EET
**Commit:** 546da97
**Branch:** main

## OVERVIEW
Ledger is a dual-stack portfolio tracker stitched together from backend and frontend git submodules. Core flows cover portfolio CRUD, balances, positions, delayed market data, CSV imports, simulated BUY/SELL/DIVIDEND/SPLIT operations, and a stock-analysis workflow built around reusable LLM configs, prompt templates, snippets, conversations, runs, and versions.

## CHILD DOCS
- `backend/AGENTS.md` — backend structure, route/service/schema/test rules
- `backend/app/services/AGENTS.md` — service-layer transaction, cache, CSV, LLM config, prompt-template, and snippet rules
- `backend/app/services/stock_analysis/AGENTS.md` — context building, single/two-step execution, parser, defaults, mappers
- `backend/app/services/providers/AGENTS.md` — provider adapter contracts for OpenAI, Anthropic, and Gemini
- `backend/app/api/AGENTS.md` — route handler rules, service delegation, error translation
- `backend/app/schemas/AGENTS.md` — Pydantic schema validation, serialization, camelCase aliasing
- `backend/app/models/AGENTS.md` — ORM entity constraints, indexes, relationships
- `backend/app/repositories/AGENTS.md` — data access layer query patterns

Frontend does not currently ship nested `AGENTS.md` files in this snapshot. Use the code locations in **Where To Look** instead.

## STRUCTURE
```text
ledger/
├── backend/              # git submodule: FastAPI app, SQLAlchemy models, pytest suite
├── frontend/             # git submodule: React/Vite app, TanStack Query, Vitest, Playwright, shadcn
├── docs/                 # product/API/data-model refs + requirements + test plan
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
| Backend stock-analysis orchestration | `backend/app/services/stock_analysis/AGENTS.md` | prompt rendering, single/two-step runs, version materialization |
| Backend provider adapters | `backend/app/services/providers/AGENTS.md` | OpenAI chat/responses, Anthropic, Gemini contracts |
| Frontend app shell | `frontend/src/App.tsx`, `frontend/src/routes.ts`, `frontend/src/components/layout.tsx` | query client, router, and seven-route sidebar shell |
| Frontend shared logic | `frontend/src/lib/api.ts`, `frontend/src/lib/query-keys.ts`, `frontend/src/lib/portfolio-analytics.ts` | API contract, cache naming, derived portfolio metrics |
| Portfolio feature work | `frontend/src/components/portfolios/*.tsx` | list/detail pages, balances, positions, trades, dialogs |
| Stock-analysis UI | `frontend/src/components/stock-analysis/*.tsx`, `frontend/src/components/llm-configs.tsx`, `frontend/src/components/prompt-templates.tsx`, `frontend/src/components/snippets.tsx`, `frontend/src/components/responses-page.tsx` | global inputs, run builder, response browsing |
| Quality gates | `.github/workflows/ci.yml`, `backend/tests/test_api.py`, `backend/tests/test_stock_analysis.py`, `backend/tests/test_stock_analysis_schema.py`, `backend/tests/test_openai_responses_service.py`, `backend/tests/test_provider_schema_free_paths.py`, `frontend/src/lib/*.test.ts`, `frontend/e2e/smoke.spec.ts`, `frontend/e2e/functional.spec.ts` | backend quality + provider/schema checks, frontend unit and e2e tests |
| Product/reference docs | `docs/spec.md`, `docs/api-design.md`, `docs/data-model.md`, `docs/requirements.md` | business constraints live here |

## CODE MAP
| Symbol / Entry | Location | Role |
|---|---|---|
| `create_app` | `backend/app/main.py` | FastAPI app factory + lifecycle |
| `api_router` | `backend/app/api/router.py` | mounts all `/api/v1` routers |
| `upgrade_local_sqlite_schema` | `backend/app/db/session.py` | in-code SQLite schema upgrades; no Alembic |
| `MarketDataService` | `backend/app/services/market_data_service.py` | quote/history fetch + cache/warnings |
| `TradingOperationService` | `backend/app/services/trading_operation_service.py` | BUY/SELL/DIVIDEND/SPLIT rules |
| `UserSnippetService` | `backend/app/services/user_snippet_service.py` | global prompt-snippet CRUD |
| `StockAnalysisService` | `backend/app/services/stock_analysis/service.py` | settings, conversations, runs, versions |
| `AnalysisContextService` | `backend/app/services/stock_analysis/context.py` | context snapshots + placeholder rendering |
| `LlmGatewayService` | `backend/app/services/llm_gateway_service.py` | routes provider-backed stock-analysis requests |
| `App` | `frontend/src/App.tsx` | query client, router provider, error boundary, toaster |
| `router` | `frontend/src/routes.ts` | route table for dashboard, portfolios, LLM inputs, run builder, and responses |
| `Layout` | `frontend/src/components/layout.tsx` | responsive sidebar shell with seven route entries |
| `PortfolioListPage` | `frontend/src/components/portfolios/portfolio-list-page.tsx` | portfolio CRUD entry point |
| `PortfolioDetailPage` | `frontend/src/components/portfolios/portfolio-detail-page.tsx` | positions, balances, and trades workspace |
| `RunBuilderPage` | `frontend/src/components/stock-analysis/run-builder-page.tsx` | portfolio selection, conversation management, run execution |
| `ResponsesPage` | `frontend/src/components/responses-page.tsx` | response browser with portfolio/conversation filters |
| `request` / `ApiRequestError` | `frontend/src/lib/api.ts` | typed fetch wrapper + structured errors |
| `queryKeys` / `invalidatePortfolioScope` | `frontend/src/lib/query-keys.ts` | portfolio + stock-analysis cache naming/invalidation |
| `useStockAnalysis*` hooks | `frontend/src/hooks/use-stock-analysis.ts` | conversations, settings, runs, responses, preview, and execution hooks |

## CROSS-STACK CONVENTIONS
- Backend JSON is camelCase externally and snake_case internally.
- Decimal money/quantity values cross the API as strings; convert with shared helpers, not ad-hoc parsing.
- Market data and stock analysis are best-effort: quote/history warnings and stock-analysis partial failures should keep the UI/history usable when possible.
- LLM configs, prompt templates, and user snippets are global resources; portfolio settings, conversations, runs, and versions are portfolio-scoped.
- Prompt preview renders saved or inline templates against live portfolio context without calling a provider.
- `single_prompt` runs persist request/response history without creating versions; `two_step_workflow` runs materialize versioned analyses.
- Backend and frontend live as git submodules; root workflows check them out with `submodules: recursive`.
- Frontend currently exposes a flat 7-route sidebar app shell rather than a nested portfolio workspace route tree.
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
(cd frontend && pnpm typecheck && pnpm lint && pnpm build)
(cd frontend && pnpm test:run)
(cd frontend && pnpm test)
(cd frontend && pnpm exec playwright install --with-deps chromium && pnpm test:e2e)
```

## NOTES
- No root package manifest; backend and frontend toolchains are independent submodules.
- CI checks out submodules recursively, then runs backend quality, frontend lint/build/test, and Docker smoke builds.
- Backend test hotspots live in `backend/tests/test_api.py`, `backend/tests/test_stock_analysis.py`, `backend/tests/test_stock_analysis_schema.py`, `backend/tests/test_openai_responses_service.py`, and `backend/tests/test_provider_schema_free_paths.py`.
- Stock analysis supports `single_prompt` and `two_step_workflow` modes plus global reusable snippets.
- Frontend uses flat 7-route sidebar navigation with TanStack Query for all server state.
- SQLite is the zero-config local default; PostgreSQL comes via `DATABASE_URL`.
- Local dev ports (`8000`/`5173`) differ from Playwright ports (`8001`/`4173`).
- Test plan documented in `docs/test-plan.md`.
