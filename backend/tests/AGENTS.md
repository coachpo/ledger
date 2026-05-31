# BACKEND TESTS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers `backend/tests/`.

## OVERVIEW
`backend/tests/` is the behavioral spec for the shipped backend surface: preserved portfolio, template, report, trading, and market-data APIs behind `signaldeck.finance`; extension registry/state behavior; social sentiment/runtime tools; current agent-platform APIs; startup schema upgrades; run rerun/fork semantics; and removed-route/module absence assertions. Tests run against isolated PostgreSQL databases and a real FastAPI app instance.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative old paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or non-goal surfaces, not live acceptance paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Fixture setup | `conftest.py` | isolated PostgreSQL `DATABASE_URL`, `init_db()`, `TestClient`, dependency override cleanup |
| API regression coverage | `test_api.py` | preserved CRUD, templates, reports, trading rules, market-data fallback, extension gating, platform validation, and neutral stub workflow coverage |
| Extension state coverage | `test_extensions_api.py`, `test_extension_registry.py`, `test_extension_lifecycle_matrix.py`, `test_tool_catalog_api.py` | slim statically resident extension state, private registry wiring, route/tool filtering, and lifecycle matrix behavior |
| Package preflight and tool-contract coverage | `test_workflow_package_preflight.py`, `test_workflow_run_contract_schemas.py` | package validation, duplicate tool keys, memory tool contracts, and run payload schema rules |
| Agent-platform run coverage | `test_workflow_package_runtime_api.py`, `test_workflow_package_run_contracts.py`, `test_run_operation_invocations.py`, `test_run_service_http_operations.py` | package execution, scheduler defaults/worker queue semantics, run detail/list progress and queue read models, model-binding provenance, reruns, invocation-input forks, HTTP/tool operations, and historical step replay read-lineage coverage |
| Runtime artifact coverage | `test_workflow_package_runtime_artifacts.py`, `test_memory_domain_schemas.py` | persisted step outputs, Logfire trace linkage, run-detail artifacts, and memory DTO projections |
| Model and repository coverage | `test_runtime_models.py`, `test_runtime_repositories.py` | current agent-platform metadata, uniqueness, current-package persistence, run-fork persistence, and run-snapshot expectations |
| DB-upgrade and removed-surface coverage | `test_runtime_db_upgrades.py`, `test_legacy_backend_cutover.py` | startup repairs, retired table cleanup, and removed-route/module guarantees |
| Focused helper coverage | `test_refactor_helpers.py` | targeted helper regressions when small backend refactors need coverage |

## CONVENTIONS
- Tests create an isolated PostgreSQL database per test run, monkeypatch `DATABASE_URL`, then call `init_db(database_url)`.
- The app fixture uses `create_app(init_database=False)` so fixtures, not app startup, control DB initialization.
- Helper functions inside the test modules build portfolios, templates, reports, and platform fixtures explicitly instead of hiding setup behind opaque shared state.
- Quote-provider behavior is exercised through `app.dependency_overrides` on the FastAPI app rather than through real network calls.
- For ordinary removal-only checks, prefer manual confirmation over adding standalone “proves not” tests. Keep absence assertions only when the missing surface is itself the shipped contract, such as removed routes/modules or slim-state guarantees.
- `TEST_DATABASE_URL` or `DATABASE_URL` must point to a PostgreSQL server where the test user can connect to `postgres` and create/drop databases.

## ANTI-PATTERNS
- Do not rely on shared DB state across tests.
- Do not hit real provider APIs or network services from this suite.
- Do not change preserved product contracts, current agent-platform contracts, or DB-upgrade behavior without updating the corresponding regression files.
- Keep removed extension metadata references limited to explicit negative-validation tests or upgrade-normalization tests. Live contract tests should assert the slim state and dependency-only run records.
- Do not leave dependency overrides behind after a test; `conftest.py` clears them for a reason.

## VALIDATION
```bash
cd backend
uv run pytest
```

## NOTES
- Pytest config is implicit through `backend/pyproject.toml`; there is no separate `pytest.ini`.
- `test_api.py` covers preserved `/api/v1` behavior, finance extension gating, and current agent-platform validation paths.
- Extension, tool-catalog, social-sentiment, and lifecycle tests lock statically resident `signaldeck.finance` state, enabled-tool filtering, and provider/runtime-tool contracts.
- `test_workflow_package_runtime_api.py`, `test_workflow_package_runtime_artifacts.py`, `test_workflow_package_run_contracts.py`, `test_run_operation_invocations.py`, `test_memory_domain_schemas.py`, `test_runtime_models.py`, `test_runtime_repositories.py`, and `test_runtime_db_upgrades.py` lock the current agent-platform persistence, Scheduled Task APIs/materialization, saved model-connection, trace metadata, memory DTOs, run-fork behavior, upgrade, and execution contracts.
- `test_legacy_backend_cutover.py` proves removed backend routes return `404` and removed modules stay absent.
