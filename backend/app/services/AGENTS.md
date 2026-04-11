# BACKEND SERVICES GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers service-layer rules.

## OVERVIEW
`app/services/` holds the backend's business workflows plus a few stateless integration boundaries. Persistence-backed domain services own repository orchestration and transactions, while `quote_provider.py` stays stateless, `template_compiler_service.py` resolves the live placeholder contract, `orchestration_service.py` owns role/character management and mention catalogs, the backtest trio spans lifecycle kickoff, cycle orchestration, and simulation math, and the internal LangGraph execution layer lives in sibling `app/langgraph/`.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Portfolio CRUD / existence checks | `portfolio_service.py` | shared portfolio lookup boundary for other services |
| Balance workflows | `balance_service.py` | balance CRUD + validation |
| Position workflows | `position_service.py` | manual position CRUD plus symbol-name lookup cache |
| CSV import preview/commit | `csv_import_service.py` | atomic preview/commit contract |
| Trading simulation rules | `trading_operation_service.py` | BUY/SELL/DIVIDEND/SPLIT + balance/position effects |
| Quote/history/cache logic | `market_data_service.py` | `QuoteProvider`, fallback cache, stale/warning behavior |
| Orchestration roles and characters | `orchestration_service.py` | versioned role and character CRUD, mention catalog, reserved-handle and disabled-role checks |
| Backtest lifecycle | `backtest_service.py` | create/cancel/delete lifecycle, deposit-balance selection, default-template creation, daemon-thread launch of `BacktestCycleService.start_backtest()` |
| Backtest cycle orchestration | `backtest_cycle_service.py` | orchestration-pattern-key runner selection, mention-policy enforcement, prompt-report loading, internal LangGraph execution, mentioned-target output assembly, legacy callback handling, `_run_state` persistence |
| Backtest engine internals | `backtest_engine.py` | schedule generation, prompt report creation, market-data loading, trade execution, equity tracking, final metrics |
| Template placeholder resolution | `template_compiler_service.py` | `{{portfolios...}}` and `{{reports...}}` trees, inline compile, stored compile, dynamic selectors, report re-compilation |
| Stored template CRUD | `text_template_service.py` | unique-name checks, CRUD, compile lookup |
| Report workflows | `report_service.py` | compile from template, external create, upload markdown, slug/name generation, filters, CRUD, download lookup |
| Quote provider contract | `quote_provider.py` | provider protocol, DTOs, Yahoo Finance adapter, provider errors |
| Internal analysis execution | `../langgraph/AGENTS.md`, `../langgraph/runner.py` | internal LangGraph runner returns analysis reports and trade decisions |
| DI entrypoint | `../api/dependencies.py` | service construction + provider wiring |
| Service test hotspots | `../../tests/test_api.py`, `../../tests/test_backtests_api.py`, `../../tests/test_orchestration_api.py`, `../../tests/test_backtest_cycle_service.py`, `../../tests/test_backtest_engine.py`, `../../tests/test_backtest_orchestration_snapshot.py` | CRUD, templates, market-data, symbol cache, orchestration, backtest lifecycle, snapshot upgrade behavior, engine behavior |

## CONVENTIONS
- Persistence-backed domain services are constructed with a `Session` and compose repositories or dependent services in `__init__`.
- Public methods validate portfolio, balance, or position existence before mutating related state.
- Multi-step writes commit once inside the service and rollback on exceptions; routers should not manage those transactions.
- Return API-facing read models via `*.model_validate(...)`, not ORM objects.
- `quote_provider.py` owns the provider protocol and data-transfer objects; concrete HTTP response shapes should not leak into service methods.
- `PositionService` may consult the quote provider to resolve symbol names and caches successful lookups in `symbol_name_cache`; lookup failures should not block manual position CRUD.
- `TemplateCompilerService` resolves the `{{portfolios...}}` and `{{reports...}}` placeholder contract against repositories and powers inline preview compile, stored-template compile, exact-name report embeds, dynamic report selectors, and report-content re-compilation with cycle detection.
- `ReportService` treats compiled reports as timestamped snapshots, uploaded reports as slug-addressed markdown documents with optional metadata, and external JSON reports as first-class persisted sources.
- `OrchestrationService` owns versioned orchestration roles and characters, enforces stable keys and handles, protects reserved builtin targets, and returns the mention catalog used by the public API.
- `MarketDataService` is best-effort: provider failures become warnings or cached fallbacks when possible.
- `BacktestService` selects the largest deposit balance, optionally creates the default backtest template, persists the `backtests` row, resolves internal-vs-legacy callback settings, and starts `BacktestCycleService.start_backtest()` on a daemon thread.
- `BacktestCycleService` is the live execution path: it selects the runner from the orchestration pattern key, enforces mention policy, prepares cycle prompt reports, invokes the internal LangGraph runner, assembles mentioned-target output, stores `_run_state` inside `backtest.results`, and advances or finalizes the run.
- `BACKTEST_TEST_MODE` is set in Playwright and read by `BacktestCycleService`; test mode swaps in `DeterministicQuoteProvider` and deterministic cycle decisions instead of calling the live LangGraph runner.
- `BacktestEngine` reuses `TemplateCompilerService`, `ReportService`, and `TradingOperationService` instead of introducing simulation-only report or trade paths; it prepares prompt reports, applies trades, records equity, and computes final metrics.
- `app/services/` stops at backend-side orchestration; `app/langgraph/` owns internal prompt analysis and decision generation.
- Official SDKs own LLM I/O: `app/langgraph/runner.py` uses `ChatOpenAI` and the official `OpenAI` client, while service-layer code should never make raw HTTP model calls itself.

## ANTI-PATTERNS
- Do not commit from routers or repositories when a service already owns the workflow.
- Do not bypass repository or service helpers inside trade flows just to mutate ORM models inline.
- Do not treat quote-provider failures as fatal if the existing cache and warning path should keep the request usable.
- Do not change CSV preview or commit payloads without updating backend tests and frontend callers.
- Do not change template placeholder paths or compile payloads without updating backend tests, frontend types, and the template editor.
- Do not change report compile/upload/download contracts, slug generation, or `reports.<name>.content` cycle handling without updating backend tests and frontend callers.
- Do not change orchestration role/character contracts, mention catalog behavior, or snapshot upgrade rules without updating backend tests and callers.
- Do not launch `BacktestEngine` or `BacktestCycleService` directly from routes when `BacktestService` already owns lifecycle validation and kickoff wiring.
- Do not document legacy callback mode as the default launch path.
- Do not move LangGraph graph state into persistence-backed service models; keep the graph execution boundary narrow and execution-focused.
- Do not introduce raw `httpx`/`requests` LLM calling paths in service code; route provider calls through the official SDK boundary in `app/langgraph/`.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest tests/test_api.py tests/test_backtests_api.py tests/test_orchestration_api.py tests/test_backtest_cycle_service.py tests/test_backtest_engine.py
```

## NOTES
- `TradingOperationService` may delete positions on full sell-down and supports DIVIDEND/SPLIT as well as BUY/SELL.
- `MarketDataService` caches quotes by provider/symbol/as-of and recomputes staleness when falling back to cached rows.
- `ReportService` lists newest-first, accepts markdown uploads up to 2 MB, supports direct external JSON creation, and stores optional author/description/tags/analysis metadata in JSONB.
- `OrchestrationService` keeps role/character versions on every edit, forbids reserved builtin handles, and builds a mention catalog from seeded builtin targets plus enabled characters whose roles are enabled.
- `BacktestEngine` stores market history to parquet under `settings.market_data_cache_dir`, tags generated reports with `backtest_<id>`, and writes `trading_operations.backtest_id` so cleanup can stay query-driven.
- `BacktestCycleService` stores internal progress under `results._run_state`; `BacktestRead` hides that internal-only payload until final results are available.
