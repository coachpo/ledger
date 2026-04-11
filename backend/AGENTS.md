# BACKEND GUIDE

> Inherits root rules from `/AGENTS.md`. Local layer docs live under `app/*/AGENTS.md` and `tests/AGENTS.md`.

## OVERVIEW
FastAPI + SQLAlchemy + Pydantic backend for portfolio tracking. Routers stay thin, services own business rules and transaction boundaries, shared formatting/error helpers live in `app/core`, PostgreSQL initialization is composed in `app/db/session.py` with validation/upgrades/repair helpers split across `app/db/`, and the live request path now includes template compilation, report generation/upload/download, `reports.*` placeholder resolution, symbol-name caching, persisted backtest runs launched through `BacktestCycleService`, orchestration management for roles and characters, and backtest orchestration snapshots used by the internal LangGraph path.

## CHILD DOCS
- `app/core/AGENTS.md` — settings, error envelope, normalization helpers
- `app/db/AGENTS.md` — engine/session lifecycle and PostgreSQL-only upgrade rules
- `app/api/AGENTS.md` — route-handler delegation and dependency wiring
- `app/services/AGENTS.md` — service orchestration, orchestration service, template compiler, quote-provider wiring, transaction ownership
- `app/langgraph/AGENTS.md` — internal LangGraph runner, analyzer boundary, graph-state rules
- `app/schemas/AGENTS.md` — request/response validation, backtest launch semantics, and serialization
- `app/models/AGENTS.md` — ORM entities, constraints, indexes, cache tables, and orchestration snapshots
- `app/repositories/AGENTS.md` — SQLAlchemy query/repository patterns and orchestration lookups
- `tests/AGENTS.md` — pytest fixtures, isolated PostgreSQL databases, and high-signal regression tests

## STRUCTURE
```text
backend/
├── app/core/                   # config, errors, formatting, constants
├── app/db/                     # engine/session/init + PostgreSQL upgrade helpers
├── app/api/                    # APIRouter modules + dependency wiring
├── app/services/               # CRUD, orchestration, backtest lifecycle/cycle engine, templates, market data, trading rules, provider protocol
├── app/langgraph/              # internal LangGraph runner for backtest analysis
├── app/repositories/           # persistence queries
├── app/models/                 # SQLAlchemy entities + constraints/indexes
├── app/schemas/                # CamelModel request/response contracts
└── tests/                      # pytest integration tests with isolated PostgreSQL databases
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| API route handlers | `app/api/AGENTS.md` | route handler rules, service delegation, error translation |
| Service construction | `app/api/dependencies.py` | constructs CRUD, template, report, orchestration, market-data, and quote-provider services |
| Orchestration management | `app/api/orchestration.py`, `app/services/orchestration_service.py`, `app/schemas/orchestration.py` | roles, characters, mention catalog, versioned updates, validation |
| Backtest lifecycle | `app/api/backtests.py`, `app/api/backtest_callbacks.py`, `app/services/backtest_service.py`, `app/services/backtest_cycle_service.py`, `app/services/backtest_engine.py` | create/list/cancel/delete, callback ingress, launch path, cycle orchestration, results |
| LangGraph execution flow | `app/langgraph/AGENTS.md`, `app/langgraph/runner.py` | internal prompt analysis and trade-decision generation |
| Shared config / errors / normalization | `app/core/AGENTS.md` | env aliases, `ApiError`, decimal/symbol/currency helpers |
| DB init/session | `app/db/AGENTS.md` | engine/session caches, `init_db()`, PostgreSQL upgrades |
| Service internals | `app/services/AGENTS.md` | transactions, orchestration, template compiler, report workflows, symbol lookup cache, market-data fallback |
| API payload shape | `app/schemas/AGENTS.md` | Pydantic validation, serialization, camelCase aliasing, orchestration and backtest payloads |
| Persistence / constraints | `app/models/AGENTS.md`, `app/repositories/AGENTS.md` | ORM entities, report/cache tables, orchestration models, data access queries |
| Core test coverage | `tests/AGENTS.md` | CRUD, templates, reports, orchestration, backtests, market-data, DB-upgrade coverage |

## CONVENTIONS
- Each route module declares `APIRouter(prefix=..., tags=[...])`, accepts integer ids, and delegates to a service.
- `app/api/dependencies.py` is the composition root for request-scoped `Session` objects, CRUD services, `TemplateCompilerService`, `OrchestrationService`, and `YahooFinanceQuoteProvider`.
- Schemas inherit `CamelModel`; external JSON is camelCase, extra fields are forbidden, decimals serialize to strings, and datetimes serialize as UTC `Z` timestamps.
- Shared normalization and decimal parsing live in `app/core/formatting.py`; use `normalize_symbol`, `normalize_currency`, `parse_decimal_string`, `to_utc`, and `utcnow` instead of ad-hoc helpers.
- Shared domain errors come from `app/core/errors.py`; routes and services should raise `ApiError` helpers rather than raw framework exceptions.
- Services return read schemas via `*.model_validate(...)` and own `commit()/rollback()` around multi-step writes.
- `OrchestrationService` owns versioned role/character CRUD, disabled-role checks, reserved-handle checks, and the mention catalog that merges seeded builtin targets with enabled characters.
- `ReportService` owns slug normalization, timestamped report-name generation for compiled reports, external JSON creation, filtered list retrieval, markdown-upload validation, and download-by-slug semantics.
- `BacktestService` validates portfolio/template inputs, selects the largest deposit balance, optionally creates the default template, resolves internal-vs-legacy callback settings, persists the backtest row, and launches `BacktestCycleService.start_backtest()` on a daemon thread.
- `BacktestCycleService` owns the live cycle path, including prompt-report preparation, internal LangGraph execution, legacy callback validation/handling, deterministic test-mode behavior, and `_run_state` persistence.
- LangGraph-backed execution lives in `app/langgraph/` and is invoked directly from `BacktestCycleService` without a worker HTTP hop.
- LLM-provider calls for backtests must stay inside official SDK clients (`ChatOpenAI`, `OpenAI`) rather than ad-hoc raw HTTP request code.

## ANTI-PATTERNS
- Do not put business rules in routers or repositories.
- Do not raise raw `HTTPException` for domain errors; use `ApiError` helpers from `app/core/errors.py`.
- Do not hand-build camelCase payloads; let `CamelModel` serialize them.
- Do not skip normalization or decimal parsing on symbols, currencies, or numeric strings.
- Do not change template placeholder behavior, symbol lookup behavior, or CSV contracts without updating `tests/test_api.py` and the frontend callers.
- Do not change report compile/upload/download contracts, report filters, report placeholder behavior, or report slug rules without updating `tests/test_api.py` and the frontend callers.
- Do not change orchestration role/character contracts, mention catalog behavior, or snapshot upgrade rules without updating orchestration tests and callers.
- Do not bypass `BacktestCycleService`, `TradingOperationService`, or `ReportService` from backtest workflows just to write simulation-specific rows directly.
- Do not document legacy callback mode as the normal backtest path.
- Do not move LangGraph execution into routers or bypass `BacktestCycleService`; the service remains the lifecycle boundary.
- Do not add raw `httpx`/`requests` model-calling code in backend application paths when the provider offers an official library.

## COMMANDS
```bash
uv sync
uv run uvicorn app.main:app --reload
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
- `tests/test_orchestration_api.py` covers role and character CRUD, duplicate/reserved/disabled validation, mention catalog behavior, and version bump expectations.
- `tests/test_backtests_api.py`, `tests/test_backtest_cycle_service.py`, `tests/test_backtest_engine.py`, and `tests/test_backtest_service.py` cover backtest CRUD, callback-state validation, service kickoff wiring, crash recovery, parquet cache behavior, schedule generation, and deterministic simulation flows.
- `tests/test_backtest_orchestration_snapshot.py` covers the snapshot table definition plus legacy upgrade behavior for `backtest_orchestration_snapshots`.
- `backend/alembic/` exists as scaffolding only; schema changes still live in `app/db/upgrades.py`.
