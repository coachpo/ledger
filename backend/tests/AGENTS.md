# BACKEND TESTS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers `backend/tests/`.

## OVERVIEW
`backend/tests/` is the behavioral spec for the shipped backend surface: preserved portfolio, template, report, trading, and market-data APIs behind `signaldeck.finance`; extension registry/state behavior; social sentiment/runtime tools; current agent-platform APIs; startup schema upgrades; and destructive cutover assertions. Tests run against isolated PostgreSQL databases and a real FastAPI app instance.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Fixture setup | `conftest.py` | isolated PostgreSQL `DATABASE_URL`, `init_db()`, `TestClient`, dependency override cleanup |
| API regression coverage | `test_api.py` | preserved CRUD, templates, reports, trading rules, market-data fallback, extension gating, platform validation, and neutral stub workflow coverage |
| Extension state coverage | `test_extensions_api.py`, `test_extension_registry.py`, `test_extension_lifecycle_matrix.py`, `test_tool_catalog_api.py` | bundled extension metadata, enable/disable state, route/tool filtering, and lifecycle matrix behavior |
| Agent-platform run coverage | `test_workflow_package_runtime_api.py`, `test_workflow_package_run_contracts.py` | package execution, run detail/list, model-binding provenance, reruns, and step replay coverage |
| Runtime artifact coverage | `test_workflow_package_runtime_artifacts.py`, `test_memory_domain_schemas.py` | persisted step outputs, Logfire trace linkage, run-detail artifacts, and memory DTO projections |
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
- `test_api.py` covers preserved `/api/v1` behavior, finance extension gating, and current agent-platform validation paths.
- Extension, tool-catalog, social-sentiment, and lifecycle tests lock bundled `signaldeck.finance` state, contribution filtering, and provider/runtime-tool contracts.
- `test_workflow_package_runtime_api.py`, `test_workflow_package_runtime_artifacts.py`, `test_workflow_package_run_contracts.py`, `test_memory_domain_schemas.py`, `test_runtime_models.py`, `test_runtime_repositories.py`, and `test_runtime_db_upgrades.py` lock the current agent-platform persistence, saved model-connection, trace metadata, memory DTO, upgrade, and execution contracts.
- `test_legacy_backend_cutover.py` proves retired backend routes return `404` and removed modules stay absent.
