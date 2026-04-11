# BACKEND TESTS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers `backend/tests/`.

## OVERVIEW
`backend/tests/` is the behavioral spec for the live API surface: portfolio CRUD, balances, positions, templates, reports, symbol lookup caching, market-data fallback, trading operations, orchestration, backtests, callback-state validation, report-placeholder recursion, snapshot persistence, and legacy-schema upgrades. Tests run against isolated PostgreSQL databases and a real FastAPI app instance.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Fixture setup | `conftest.py` | isolated PostgreSQL `DATABASE_URL`, `init_db()`, `TestClient`, dependency override cleanup |
| API regression coverage | `test_api.py` | CRUD, templates, CSV import, trading rules, market-data fallback, DB upgrades |
| Orchestration API coverage | `test_orchestration_api.py` | role/character CRUD, mention catalog, validation, versioning |
| Backtest API coverage | `test_backtests_api.py` | schema upgrades, CRUD, cancellation, cleanup, deterministic launch wiring |
| Backtest service coverage | `test_backtest_service.py` | verifies cycle-service kickoff wiring |
| Backtest cycle-service coverage | `test_backtest_cycle_service.py` | internal cycle execution, legacy callback-state validation, deterministic cycle behavior |
| Backtest engine coverage | `test_backtest_engine.py` | NYSE schedule rules, parquet cache reuse, prompt/report handling, trade attribution, results math |
| Orchestration snapshot coverage | `test_backtest_orchestration_snapshot.py` | snapshot table registration and upgrade conversion from opaque payloads |
| LangGraph runner coverage | `test_langgraph_runner.py` | seeded/reviewer topology behavior, prompt parsing, Responses-mode streaming/input formatting, report rendering, decision translation |
| LangGraph seed coverage | `test_langgraph_seeds.py` | seeded builtin registry, mention-policy coverage |

## CONVENTIONS
- Tests create an isolated PostgreSQL database per test run, monkeypatch `DATABASE_URL`, then call `init_db(database_url)`.
- The app fixture uses `create_app(init_database=False)` so fixtures, not app startup, control DB initialization.
- Helper functions inside `test_api.py` create portfolios, balances, positions, templates, and report-producing fixtures instead of relying on opaque fixtures.
- `test_backtests_api.py` follows the same explicit-helper style and monkeypatches `BacktestService.run_backtest()` so create flows stay deterministic.
- Orchestration tests build roles/characters through the public API and assert versioning, reserved-handle rules, disabled-role checks, and mention-catalog behavior.
- Quote-provider behavior is exercised through `app.dependency_overrides` on the FastAPI app rather than through real network calls.
- `test_backtest_engine.py` uses fake history providers and temporary parquet cache directories, while `test_backtest_cycle_service.py` exercises internal cycle execution, legacy callback-state rules, and deterministic cycle advancement with fake engines.
- `test_backtest_orchestration_snapshot.py` verifies the model is registered on metadata and that legacy snapshot tables upgrade to explicit snapshot columns.
- `test_langgraph_runner.py` uses fake analyzers/clients and keeps live model calls out of the unit suite while still covering seeded/reviewer topology behavior plus Responses-mode streaming and input formatting.
- `TEST_DATABASE_URL` or `DATABASE_URL` must point to a PostgreSQL server where the test user can connect to `postgres` and create/drop databases.

## ANTI-PATTERNS
- Do not rely on shared DB state across tests.
- Do not hit real provider APIs or network services from this suite.
- Do not change CSV, template, report, symbol-lookup, market-data, orchestration, backtest, snapshot, or DB-upgrade contracts without updating the corresponding regression files.
- Do not change internal prompt parsing, report rendering, or decision translation behavior without updating `test_langgraph_runner.py` and the cycle-service tests.
- Do not leave dependency overrides behind after a test; `conftest.py` clears them for a reason.

## VALIDATION
```bash
cd backend
uv run pytest
```

## NOTES
- Pytest config is implicit through `backend/pyproject.toml`; there is no separate `pytest.ini`.
- `test_api.py` currently covers template CRUD/compile flow, quote-backed template metrics, report compile/upload/external-create/download flows, report filters, `reports.*` exact-name and dynamic-selector behavior with cycle detection, trading operations, cached quote fallback, symbol-name cache behavior, and supported legacy DB upgrades.
- `test_orchestration_api.py` covers role/character CRUD plus duplicate, reserved, disabled, and mention-catalog behavior, and it verifies version bump expectations.
- `test_backtests_api.py` covers backtest CRUD plus `trading_operations.backtest_id` upgrades, largest-deposit selection, default-template creation, cancellation/delete rules, webhook field serialization, startup repair, and the regression that hides internal `_run_state` payloads from API reads.
- `test_backtest_service.py` verifies that `BacktestService.run_backtest()` initializes `BacktestCycleService` and launches execution in a background thread.
- `test_backtest_cycle_service.py` covers internal cycle execution, callback-state validation for the legacy routes, and deterministic test-mode behavior.
- `test_backtest_orchestration_snapshot.py` covers the snapshot table definition, legacy table migration, and explicit JSON column replacement.
- `test_backtest_engine.py` covers schedule generation, parquet cache reuse, prompt report storage, trade attribution, and portfolio/benchmark result aggregation.
- `test_langgraph_runner.py` covers internal prompt parsing, seeded/reviewer topology behavior, Responses-mode streaming extraction, input formatting, label normalization, analysis report rendering, and decision translation.
- `test_langgraph_seeds.py` covers the seeded builtin registry and mention-policy behavior.
