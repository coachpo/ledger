# BACKEND TESTS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers `backend/tests/`.

## OVERVIEW
`backend/tests/` is the behavioral spec for the live API surface: portfolio CRUD, balances, positions, templates, reports, symbol lookup caching, market-data fallback, trading operations, backtests, callback-state validation, report-placeholder recursion, and legacy-schema upgrades. Tests run against isolated PostgreSQL databases and a real FastAPI app instance.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Fixture setup | `conftest.py` | isolated PostgreSQL `DATABASE_URL`, `init_db()`, `TestClient`, dependency override cleanup |
| API regression coverage | `test_api.py` | CRUD, templates, CSV import, trading rules, market-data fallback, DB upgrades |
| Backtest API coverage | `test_backtests_api.py` | schema upgrades, CRUD, cancellation, cleanup, deterministic launch wiring |
| Backtest service coverage | `test_backtest_service.py` | verifies cycle-service kickoff wiring |
| Backtest cycle-service coverage | `test_backtest_cycle_service.py` | callback-state validation plus deterministic cycle behavior |
| Backtest engine coverage | `test_backtest_engine.py` | NYSE schedule rules, parquet cache reuse, prompt/report handling, trade attribution, results math |

## CONVENTIONS
- Tests create an isolated PostgreSQL database per test run, monkeypatch `DATABASE_URL`, then call `init_db(database_url)`.
- The app fixture uses `create_app(init_database=False)` so fixtures, not app startup, control DB initialization.
- Helper functions inside `test_api.py` create portfolios, balances, positions, templates, and report-producing fixtures instead of relying on opaque fixtures.
- `test_backtests_api.py` follows the same explicit-helper style and monkeypatches `BacktestService.run_backtest()` so create flows stay deterministic.
- Quote-provider behavior is exercised through `app.dependency_overrides` on the FastAPI app rather than through real network calls.
- `test_backtest_engine.py` uses fake history providers and temporary parquet cache directories, while `test_backtest_cycle_service.py` exercises callback-state rules and deterministic cycle advancement with fake engines.
- `TEST_DATABASE_URL` or `DATABASE_URL` must point to a PostgreSQL server where the test user can connect to `postgres` and create/drop databases.

## ANTI-PATTERNS
- Do not rely on shared DB state across tests.
- Do not hit real provider APIs or network services from this suite.
- Do not change CSV, template, report, symbol-lookup, market-data, backtest, or DB-upgrade contracts without updating the corresponding regression files.
- Do not leave dependency overrides behind after a test; `conftest.py` clears them for a reason.

## VALIDATION
```bash
cd backend
uv run pytest
```

## NOTES
- Pytest config is implicit through `backend/pyproject.toml`; there is no separate `pytest.ini`.
- `test_api.py` currently covers template CRUD/compile flow, quote-backed template metrics, report compile/upload/external-create/download flows, report filters, `reports.*` exact-name and dynamic-selector behavior with cycle detection, trading operations, cached quote fallback, symbol-name cache behavior, and supported legacy DB upgrades.
- `test_backtests_api.py` covers backtest CRUD plus `trading_operations.backtest_id` upgrades, largest-deposit selection, default-template creation, cancellation/delete rules, webhook field serialization, startup repair, and the regression that hides internal `_run_state` payloads from API reads.
- `test_backtest_service.py` verifies that `BacktestService.run_backtest()` initializes `BacktestCycleService` and launches execution in a background thread.
- `test_backtest_cycle_service.py` covers callback-state validation plus deterministic callback-mode cycle handling for empty and populated portfolios.
- `test_backtest_engine.py` covers schedule generation, parquet cache reuse, prompt report storage, trade attribution, and portfolio/benchmark result aggregation.
