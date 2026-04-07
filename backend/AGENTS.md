# BACKEND GUIDE

> Inherits root rules from `/AGENTS.md`. Local layer docs live under `app/*/AGENTS.md` and `tests/AGENTS.md`.

## OVERVIEW
FastAPI + SQLAlchemy + Pydantic backend for portfolio tracking. Routers stay thin, services own business rules and transaction boundaries, shared formatting/error helpers live in `app/core`, PostgreSQL initialization is composed in `app/db/session.py` with validation/upgrades/repair helpers split across `app/db/`, and the live request path now includes template compilation, report generation/upload/download, `reports.*` placeholder resolution, symbol-name caching, persisted backtest runs launched through `BacktestCycleService`, and a separate TradingAgents worker app under `app/worker/` for live webhook dispatch.

## CHILD DOCS
- `app/core/AGENTS.md` — settings, error envelope, normalization helpers
- `app/db/AGENTS.md` — engine/session lifecycle and PostgreSQL-only upgrade rules
- `app/api/AGENTS.md` — route-handler delegation and dependency wiring
- `app/services/AGENTS.md` — service orchestration, template compiler, quote-provider wiring, transaction ownership
- `app/worker/AGENTS.md` — separate worker entrypoint, async dispatch flow, TradingAgents adapter, callback payloads
- `app/schemas/AGENTS.md` — request/response validation and serialization
- `app/models/AGENTS.md` — ORM entities, constraints, indexes, cache tables
- `app/repositories/AGENTS.md` — SQLAlchemy query/repository patterns
- `tests/AGENTS.md` — pytest fixtures, isolated PostgreSQL databases, high-signal API tests

## STRUCTURE
```text
backend/
├── app/core/                   # config, errors, formatting, constants
├── app/db/                     # engine/session/init + PostgreSQL upgrade helpers
├── app/api/                    # APIRouter modules + dependency wiring
├── app/services/               # CRUD, backtest lifecycle/cycle engine, templates, market data, trading rules, provider protocol
├── app/worker/                 # separate FastAPI worker app for TradingAgents dispatch + callbacks
├── app/repositories/           # persistence queries
├── app/models/                 # SQLAlchemy entities + constraints/indexes
├── app/schemas/                # CamelModel request/response contracts
└── tests/                      # pytest integration tests with isolated PostgreSQL databases
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| API route handlers | `app/api/AGENTS.md` | route handler rules, service delegation, error translation |
| Service construction | `app/api/dependencies.py` | constructs CRUD, template, report, market-data, and quote-provider services |
| Backtest lifecycle | `app/api/backtests.py`, `app/api/backtest_callbacks.py`, `app/services/backtest_service.py`, `app/services/backtest_cycle_service.py`, `app/services/backtest_engine.py` | create/list/cancel/delete, callback ingress, launch path, cycle orchestration, results |
| Worker dispatch flow | `app/worker/AGENTS.md`, `app/worker/main.py`, `app/worker/service.py`, `app/worker/trading_agents_adapter.py` | separate dispatch endpoint, TradingAgents adapter, report upload, trade/complete callbacks |
| Shared config / errors / normalization | `app/core/AGENTS.md` | env aliases, `ApiError`, decimal/symbol/currency helpers |
| DB init/session | `app/db/AGENTS.md` | engine/session caches, `init_db()`, PostgreSQL upgrades |
| Service internals | `app/services/AGENTS.md` | transactions, template compiler, report workflows, symbol lookup cache, market-data fallback |
| API payload shape | `app/schemas/AGENTS.md` | Pydantic validation, serialization, camelCase aliasing, report payloads |
| Persistence / constraints | `app/models/AGENTS.md`, `app/repositories/AGENTS.md` | ORM entities, report/cache tables, data access queries |
| Core test coverage | `tests/AGENTS.md` | CRUD, templates, reports, market-data, symbol cache, DB-upgrade coverage |

## CONVENTIONS
- Each route module declares `APIRouter(prefix=..., tags=[...])`, accepts integer ids, and delegates to a service.
- `app/api/dependencies.py` is the composition root for request-scoped `Session` objects, CRUD services, `TemplateCompilerService`, and `YahooFinanceQuoteProvider`.
- Schemas inherit `CamelModel`; external JSON is camelCase, extra fields are forbidden, decimals serialize to strings, and datetimes serialize as UTC `Z` timestamps.
- Shared normalization and decimal parsing live in `app/core/formatting.py`; use `normalize_symbol`, `normalize_currency`, `parse_decimal_string`, `to_utc`, and `utcnow` instead of ad-hoc helpers.
- Shared domain errors come from `app/core/errors.py`; routes and services should raise `ApiError` helpers rather than raw framework exceptions.
- Services return read schemas via `*.model_validate(...)` and own `commit()/rollback()` around multi-step writes.
- `PositionService` can consult the quote provider for symbol names and cache them in `symbol_name_cache`; callers should treat lookup failures as optional enrichment, not fatal errors.
- `TemplateCompilerService` resolves `{{inputs...}}`, `{{portfolios...}}`, and `{{reports...}}` roots, including report re-compilation, dynamic selectors (`latest`, `latest("TICKER")`, `[index]`, `by_tag("tag").latest`), and cycle detection for `reports.<name>.content`.
- `ReportService` owns slug normalization, timestamped report-name generation for compiled reports, external JSON creation, filtered list retrieval, markdown-upload validation, and download-by-slug semantics.
- `BacktestService` validates the portfolio/template inputs, selects the largest deposit balance, optionally creates the default template, persists the backtest row, and launches `BacktestCycleService.start_backtest()` on a daemon thread.
- `BacktestCycleService` owns the live cycle path, including dispatch, callback validation, timeout handling, deterministic test-mode behavior, and `_run_state` persistence.
- Worker-side TradingAgents execution is outside `app/services/`; `app/worker/` hosts the separate FastAPI app, async dispatch service, and adapter layer that download prompt reports, upload analysis reports, and post trade/complete callbacks back into Ledger.
- Backtest rows use `status` for `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, and `CANCELLED`, while callback-specific values such as `AWAITING_CALLBACK` and `PROCESSING_CALLBACK` live in `current_cycle_status` when the cycle service path is used.
- `BacktestEngine` owns NYSE schedule generation, parquet-backed history caching, prompt-report creation, trade attribution, recent-activity updates, and final metrics aggregation.
- `init_db()` is responsible for fresh-table creation and legacy-schema cleanup, including portfolio slug backfill, `balances.operation_type`, report `slug`/`source`/`metadata`, market-quote `name`, and obsolete stock-analysis tables.
- `init_db()` also marks interrupted `PENDING`/`RUNNING`/`AWAITING_CALLBACK`/`PROCESSING_CALLBACK` backtests as failed during startup repair.
- `backend/pyproject.toml` exposes both `ledger-backend` and `ledger-backend-worker`; local orchestration uses `start.sh`, while direct worker startup uses `uvicorn app.worker.main:app --port 8010`.

## ANTI-PATTERNS
- Do not put business rules in routers or repositories.
- Do not raise raw `HTTPException` for domain errors; use `ApiError` helpers from `app/core/errors.py`.
- Do not hand-build camelCase payloads; let `CamelModel` serialize them.
- Do not skip normalization or decimal parsing on symbols, currencies, or numeric strings.
- Do not change template placeholder behavior, symbol lookup behavior, or CSV contracts without updating `tests/test_api.py` and the frontend callers.
- Do not change report compile/upload/download contracts, report filters, report placeholder behavior, or report slug rules without updating `tests/test_api.py` and the frontend callers.
- Do not bypass `BacktestCycleService`, `TradingOperationService`, or `ReportService` from backtest workflows just to write simulation-specific rows directly.
- Do not assume TradingAgents execution happens inside `app.main`; the worker runs as a separate FastAPI app and process.
- Do not reintroduce legacy stock-analysis tables or routes without updating the DB upgrade rules in `app/db/upgrades.py`.

## COMMANDS
```bash
uv sync
uv run uvicorn app.main:app --reload
uv run uvicorn app.worker.main:app --port 8010
uv run pytest tests/test_api.py
```

## VALIDATION
```bash
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest
```

## NOTES
- `tests/test_api.py` is the high-signal regression file for CRUD, templates, reports, trading operations, market-data fallback, symbol-name cache behavior, report placeholder cycles, and legacy-schema upgrades.
- `tests/test_backtests_api.py`, `tests/test_backtest_cycle_service.py`, `tests/test_backtest_engine.py`, and `tests/test_backtest_service.py` cover backtest CRUD, callback-state validation, service kickoff wiring, crash recovery, parquet cache behavior, schedule generation, and deterministic simulation flows.
- `tests/test_trading_agents_worker.py` and `tests/test_trading_agents_worker_integration.py` cover worker dispatch payloads, async/background behavior, report upload + callback round-trips, timeout failure, and `PUBLIC_BASE_URL`-driven callback URL requirements.
- Market data is intentionally best-effort: warnings are returned when quote/history fetches fail, and cached rows can be reused when currency and symbol checks still pass.
- Playwright and deterministic backend test mode both exercise the live backtest API; `BACKTEST_TEST_MODE=1` makes `BacktestCycleService` build a `DeterministicQuoteProvider` and auto-advance cycles without webhook round-trips.
- `backend/alembic/` exists as scaffolding only; schema changes still live in `app/db/upgrades.py`.
- `backend` is an ordinary tracked directory in the root repo; root CI validates it in dedicated backend and E2E jobs rather than a single monolithic step.
