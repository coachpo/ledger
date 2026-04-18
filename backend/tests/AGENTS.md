# BACKEND TESTS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers `backend/tests/`.

## OVERVIEW
`backend/tests/` is the behavioral spec for the live API surface: portfolio CRUD, balances, positions, templates, reports, symbol lookup caching, market-data fallback, trading operations, orchestration, runtime, Studio, Tryout, seed compatibility, and legacy-schema upgrades. Tests run against isolated PostgreSQL databases and a real FastAPI app instance.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Fixture setup | `conftest.py` | isolated PostgreSQL `DATABASE_URL`, `init_db()`, `TestClient`, dependency override cleanup |
| API regression coverage | `test_api.py` | CRUD, templates, CSV import, trading rules, market-data fallback, DB upgrades |
| Orchestration API coverage | `test_orchestration_api.py` | role/character CRUD, mention catalog, validation, versioning |
| Runtime API coverage | `test_runtime_api.py`, `test_runtime_approvals_api.py` | public v2 runtime runs, cancel, approvals, and approval actions |
| Tryout API coverage | `test_tryouts_api.py` | execute/read/persist flows through the public v2 Tryout surface |
| Tryout service coverage | `test_tryout_service.py` | service-level execute/read/persist behavior and runtime row lifecycle |
| Studio query coverage | `test_studio_query_service.py` | Studio reads for runs, approvals, artifacts, and trace summaries |
| Runtime artifact coverage | `test_runtime_artifacts.py` | persisted artifact reads, trace summaries, and approval summaries |
| Runtime adapter coverage | `test_runtime_execution_adapters.py` | frozen execution behavior, retries, and approval waits |
| Runtime model coverage | `test_runtime_models.py`, `test_runtime_schemas.py`, `test_runtime_repositories.py` | runtime metadata registration, schemas, and uniqueness/index expectations |
| Runtime seed coverage | `test_runtime_seed_bootstrap.py`, `test_runtime_db_upgrades.py`, `test_runtime_resolution.py` | seeded mirror bootstrap, compatibility upgrades, and runtime resolution behavior |
| Studio catalog coverage | `test_agent_specs_api.py`, `test_capability_registry_api.py`, `test_persona_profiles_api.py`, `test_workflow_specs_api.py` | Studio-facing catalog lifecycle and visibility rules |

## CONVENTIONS
- Tests create an isolated PostgreSQL database per test run, monkeypatch `DATABASE_URL`, then call `init_db(database_url)`.
- The app fixture uses `create_app(init_database=False)` so fixtures, not app startup, control DB initialization.
- Helper functions inside `test_api.py` create portfolios, balances, positions, templates, and report-producing fixtures instead of relying on opaque fixtures.
- `test_tryouts_api.py` follows the same explicit-helper style and asserts the public v2 Tryout create/read/persist flow without opaque fixtures.
- Orchestration tests build roles/characters through the public API and assert versioning, reserved-handle rules, disabled-role checks, and mention-catalog behavior.
- Quote-provider behavior is exercised through `app.dependency_overrides` on the FastAPI app rather than through real network calls.
- `test_runtime_artifacts.py` and `test_runtime_execution_adapters.py` keep persisted artifact reads and frozen execution behavior deterministic with fake runtime inputs and adapters.
- `test_runtime_models.py`, `test_runtime_schemas.py`, and `test_runtime_repositories.py` verify runtime metadata registration plus current uniqueness/index expectations.
- `test_runtime_seed_bootstrap.py` proves startup bootstrap keeps seeded runtime mirrors aligned without recreating retired workflow rows.
- `TEST_DATABASE_URL` or `DATABASE_URL` must point to a PostgreSQL server where the test user can connect to `postgres` and create/drop databases.

## ANTI-PATTERNS
- Do not rely on shared DB state across tests.
- Do not hit real provider APIs or network services from this suite.
- Do not change CSV, template, report, symbol-lookup, market-data, orchestration, runtime, Tryout, Studio, or DB-upgrade contracts without updating the corresponding regression files.
- Do not change workflow-spec visibility, runtime seed compatibility, or upgrade behavior without updating `test_workflow_specs_api.py`, `test_runtime_seed_bootstrap.py`, and `test_runtime_db_upgrades.py`.
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
- `test_runtime_api.py` and `test_runtime_approvals_api.py` cover public runtime run reads, cancellation, and approval actions.
- `test_tryouts_api.py` covers Tryout execute/read/persist flows, while `test_tryout_service.py` exercises the same lifecycle at the service boundary.
- `test_runtime_artifacts.py`, `test_runtime_execution_adapters.py`, `test_runtime_models.py`, and `test_runtime_seed_bootstrap.py` cover artifact reads, frozen execution adapters, metadata/index rules, and seeded bootstrap invariants.
- `test_workflow_specs_api.py`, `test_agent_specs_api.py`, `test_capability_registry_api.py`, and `test_persona_profiles_api.py` cover the Studio-facing catalog contract.
