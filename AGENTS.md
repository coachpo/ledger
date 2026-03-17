# PROJECT KNOWLEDGE BASE

**Generated:** 2026-03-17
**Commit:** e229789
**Branch:** main

## OVERVIEW
Ledger is a dual-stack portfolio tracker split across `backend/` and `frontend/` git submodules. The live surface spans portfolio CRUD, deposit/withdrawal balances, aggregate positions, template authoring/compilation, delayed market data, CSV imports, symbol-name lookup caching, and simulated BUY/SELL/DIVIDEND/SPLIT workflows.

## CHILD DOCS
- `backend/AGENTS.md` — backend architecture, validation flow, and layer routing
- `backend/app/core/AGENTS.md` — config, error envelope, normalization helpers
- `backend/app/db/AGENTS.md` — session lifecycle and PostgreSQL-only init/upgrade rules
- `backend/app/api/AGENTS.md` — route handler boundaries and dependency wiring
- `backend/app/services/AGENTS.md` — service ownership, template compiler, quote-provider wiring
- `backend/app/services/providers/AGENTS.md` — dormant provider adapter contracts
- `backend/app/schemas/AGENTS.md` — Pydantic validation and camelCase aliasing
- `backend/app/models/AGENTS.md` — ORM constraints, indexes, relationships, cache tables
- `backend/app/repositories/AGENTS.md` — query/repository patterns
- `backend/tests/AGENTS.md` — pytest fixtures, isolated PostgreSQL databases, API regression coverage
- `frontend/AGENTS.md` — frontend architecture, router shell, validation workflow
- `frontend/src/lib/AGENTS.md` — API client, query keys, analytics, formatting, template contracts
- `frontend/src/hooks/AGENTS.md` — TanStack Query hook patterns and invalidation rules
- `frontend/src/components/AGENTS.md` — layout shell, theme system, shared components, forms, portfolio UI
- `frontend/src/components/portfolios/AGENTS.md` — portfolio workspace sections, dialogs, tables, trades
- `frontend/src/pages/AGENTS.md` — dashboard, portfolio routes, and template routes

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
| Backend DB upgrades | `backend/app/db/session.py` | slug backfill, balance `operation_type`, market-quote `name`, obsolete-table cleanup |
| Backend tests | `backend/tests/AGENTS.md`, `backend/tests/test_api.py` | CRUD, templates, market-data fallback, symbol cache, legacy-schema upgrades |
| Frontend app shell | `frontend/src/App.tsx`, `frontend/src/routes.ts`, `frontend/src/components/layout.tsx` | query client, router provider, layout shell, theme toggle |
| Frontend portfolio UI | `frontend/src/components/portfolios/AGENTS.md` | balances, positions, trades, dialogs, tables |
| Frontend template UI | `frontend/src/pages/templates/editor.tsx`, `frontend/src/hooks/use-templates.ts`, `frontend/src/lib/api/templates.ts` | editor, preview, placeholder browser, CRUD |
| Frontend tests / E2E | `frontend/vite.config.ts`, `frontend/src/test/setup.ts`, `frontend/playwright.config.ts`, `frontend/e2e/*.spec.ts` | jsdom unit tests plus Chromium E2E |
| CI quality gates | `.github/workflows/ci.yml`, `.github/workflows/docker-images.yml` | backend/frontend quality jobs, Docker smoke build, publish workflow |

## CODE MAP
| Symbol / Entry | Location | Role |
|---|---|---|
| `create_app` | `backend/app/main.py` | FastAPI app factory, exception handlers, CORS, healthcheck |
| `api_router` | `backend/app/api/router.py` | mounts all `/api/v1` routers, including templates |
| `init_db` | `backend/app/db/session.py` | creates tables and repairs supported legacy schemas |
| `PositionService` | `backend/app/services/position_service.py` | position CRUD plus symbol-name cache lookups |
| `TemplateCompilerService` | `backend/app/services/template_compiler_service.py` | resolves `{{portfolios...}}` placeholders against live data |
| `TextTemplateService` | `backend/app/services/text_template_service.py` | stored template CRUD and uniqueness checks |
| `QuoteProvider` / `YahooFinanceQuoteProvider` | `backend/app/services/quote_provider.py` | quote/history provider contract + Yahoo Finance adapter |
| `App` | `frontend/src/App.tsx` | query client, router provider, theme provider, toaster, error boundary |
| `router` | `frontend/src/routes.ts` | flat route table for dashboard, portfolios, and templates |
| `queryKeys` / `invalidatePortfolioScope` | `frontend/src/lib/query-keys.ts` | canonical cache naming + portfolio invalidation |
| `request` / `ApiRequestError` | `frontend/src/lib/api-client.ts` | typed fetch wrapper + structured error parsing |
| `Layout` | `frontend/src/components/layout.tsx` | sidebar shell, breadcrumbs, special full-height template-editor layout |
| `TemplateEditorPage` | `frontend/src/pages/templates/editor.tsx` | template editing, inline compile preview, placeholder browser |

## CONVENTIONS
- Backend JSON is camelCase externally and snake_case internally; `CamelModel` owns aliasing and `extra="forbid"` request validation.
- Money, quantities, and market values cross the API as strings; backend parsing lives in `backend/app/core/formatting.py`, while frontend conversion lives in shared formatting and analytics helpers.
- Balance records carry `operationType` (`DEPOSIT` or `WITHDRAWAL`); `BUY`, `SELL`, and `DIVIDEND` operations can only use deposit balances, `SPLIT` uses no balance, and portfolio cash calculations subtract withdrawal balances.
- Portfolio slugs are lowercase underscore identifiers, unique at create time, and intentionally absent from the update contract.
- Symbol-name lookup and market-data fetches are best-effort: cache reuse and warning paths should preserve a usable response whenever possible.
- Query invalidation is centralized in `frontend/src/lib/query-keys.ts`; do not invent ad-hoc keys inside hooks or components.
- Template placeholder paths are a cross-stack contract spanning `backend/app/services/template_compiler_service.py`, `backend/app/schemas/text_template.py`, `frontend/src/lib/types/text-template.ts`, and `frontend/src/pages/templates/editor.tsx`.
- Backend and frontend are git submodules; root workflows always check them out with `submodules: recursive`.

## ANTI-PATTERNS
- Do not bypass backend services or call provider adapters directly from routes or frontend code.
- Do not invent snake_case API fields, ad-hoc query keys, or duplicate placeholder/type contracts.
- Do not treat quote/history warnings as fatal when the degraded path is already defined.
- Do not change CSV import, template placeholder, or template compile payloads without updating backend tests and frontend callers.
- Do not treat `docs/`, `artifacts/`, `frontend/dist/`, or cache directories as the source of truth over live code.
- Do not ignore submodule state when cloning, updating CI, or reviewing backend/frontend diffs.

## COMMANDS
```bash
git submodule update --init --recursive
python -m pip install -e './backend[dev]'
(cd frontend && pnpm install)
./start.sh
(cd backend && python -m uvicorn app.main:app --reload --port 8000)
(cd frontend && pnpm dev)
```

## VALIDATION
```bash
(cd backend && ruff check app tests && black --check app tests && isort --check-only app tests && mypy app && pytest)
(cd frontend && pnpm lint)
(cd frontend && pnpm typecheck)
(cd frontend && pnpm build)
(cd frontend && pnpm test:run)
(cd frontend && pnpm exec playwright install --with-deps chromium && pnpm test:e2e)
```

## NOTES
- `start.sh` is the authoritative local orchestrator; unlike the raw backend/frontend dev defaults, it binds backend/frontend to `28000/25173` and injects `VITE_API_BASE_URL` for the frontend process.
- Playwright still runs against backend `8001` and frontend `4173`, so route/E2E issues should always be checked in that environment too.
- Backend requires Python 3.13+; frontend targets Node 24 and pnpm 10.
- CI currently runs backend lint/format/type/test checks, then frontend lint/build/E2E, then an amd64 Docker smoke build. Local frontend typecheck and unit tests are available even though they are not both enforced in `ci.yml` yet.
