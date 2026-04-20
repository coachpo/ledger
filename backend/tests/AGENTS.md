# BACKEND TESTS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers `backend/tests/`.

## OVERVIEW
`backend/tests/` is the behavioral spec for the shipped backend surface: preserved portfolio, template, report, trading, and market-data APIs; the current agent-platform APIs; startup schema upgrades; and destructive cutover assertions. Tests run against isolated PostgreSQL databases and a real FastAPI app instance.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Fixture setup | `conftest.py` | isolated PostgreSQL `DATABASE_URL`, `init_db()`, `TestClient`, dependency override cleanup |
| Shared stock-analysis builders | `agent_platform_stock_analysis.py` | reusable `TradingDecision` schema, agent payloads, and workflow builders for runtime tests |
| API regression coverage | `test_api.py` | preserved CRUD, templates, reports, trading rules, market-data fallback, and platform validation |
| Agent-platform run coverage | `test_runtime_api.py` | workflow execution, run detail/list, budgets, optional agents, and stock-analysis flows |
| Runtime artifact coverage | `test_runtime_artifacts.py` | persisted step outputs, trace linkage, and run-detail artifact assertions |
| Model and repository coverage | `test_runtime_models.py`, `test_runtime_repositories.py` | current agent-platform metadata, uniqueness, and version-pinning expectations |
| DB-upgrade and cutover coverage | `test_runtime_db_upgrades.py`, `test_legacy_backend_cutover.py` | startup repairs, legacy table cleanup, and removed-route/module guarantees |
| Focused helper coverage | `test_refactor_helpers.py` | targeted helper regressions when small backend refactors need coverage |

## CONVENTIONS
- Tests create an isolated PostgreSQL database per test run, monkeypatch `DATABASE_URL`, then call `init_db(database_url)`.
- The app fixture uses `create_app(init_database=False)` so fixtures, not app startup, control DB initialization.
- Helper functions inside the test modules build portfolios, templates, reports, and platform fixtures explicitly instead of hiding setup behind opaque shared state.
- Quote-provider behavior is exercised through `app.dependency_overrides` on the FastAPI app rather than through real network calls.
- `TEST_DATABASE_URL` or `DATABASE_URL` must point to a PostgreSQL server where the test user can connect to `postgres` and create/drop databases.

## ANTI-PATTERNS
- Do not rely on shared DB state across tests.
- Do not hit real provider APIs or network services from this suite.
- Do not change preserved product contracts, current agent-platform contracts, or DB-upgrade behavior without updating the corresponding regression files.
- Do not leave dependency overrides behind after a test; `conftest.py` clears them for a reason.

## VALIDATION
```bash
cd backend
uv run pytest
```

## NOTES
- Pytest config is implicit through `backend/pyproject.toml`; there is no separate `pytest.ini`.
- `test_api.py` covers preserved `/api/v1` behavior plus current agent-platform validation paths.
- `test_runtime_api.py`, `test_runtime_artifacts.py`, `test_runtime_models.py`, `test_runtime_repositories.py`, and `test_runtime_db_upgrades.py` lock the current agent-platform persistence and execution contracts.
- `test_legacy_backend_cutover.py` proves retired backend routes return `404` and removed modules stay absent.
