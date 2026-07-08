# BACKEND TESTS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers `backend/tests/`.

## OVERVIEW
`backend/tests/` is the behavioral spec for the shipped backend surface: preserved template/report APIs; Finance and Digital Oracle runtime tools; static extension contract behavior; current agent-platform APIs; database bootstrap; and run rerun semantics. Tests run against isolated PostgreSQL databases and a real FastAPI app instance.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative old paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or non-goal surfaces, not live acceptance paths.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Fixture setup | `conftest.py` | isolated PostgreSQL `DATABASE_URL`, `init_db()`, `TestClient`, dependency override cleanup |
| API regression coverage | `test_api.py` | preserved templates, reports, platform validation, and neutral stub workflow coverage |
| Extension contract coverage | `test_extension_contract.py`, `test_tool_catalog_api.py` | static extension contract, installed routes/tools, and `/api/extensions` absence |
| Package preflight, MCP, and tool-contract coverage | `test_workflow_package_preflight.py`, `test_mcp_runtime.py`, `test_runtime_tools.py`, `test_runtime_tools_social_sentiment.py`, `test_workflow_run_contract_schemas.py` | package validation, package-private MCP refs, duplicate tool keys, finance/Digital Oracle runtime tool contracts, runtime tool fail-closed behavior, and run payload schema rules |
| Agent-platform run coverage | `test_workflow_package_runtime_api.py`, `test_workflow_package_run_contracts.py`, `test_run_operation_invocations.py`, `test_run_service_http_operations.py` | package execution, scheduler defaults/worker queue semantics, run detail/list progress and queue read models, model-binding provenance, reruns, and HTTP/tool operations |
| Runtime artifact coverage | `test_workflow_package_runtime_artifacts.py` | persisted step outputs and Logfire trace linkage |
| Model and repository coverage | `test_runtime_models.py`, `test_runtime_repositories.py` | current agent-platform metadata, uniqueness, current-package persistence, and run-snapshot expectations |
| DB bootstrap, export, and demo preset coverage | `test_db_bootstrap.py`, `test_workflow_package_export.py`, `test_workflow_package_export_security.py`, `test_workflow_package_demo_presets.py` | schema creation, startup recovery, export shape, and demo seed contracts |
| Formatting helper coverage | `test_formatting.py` | decimal formatting behavior |

## CONVENTIONS
- Tests create an isolated PostgreSQL database per test run, monkeypatch `DATABASE_URL`, then call `init_db(database_url)`.
- The app fixture uses `create_app(init_database=False)` so fixtures, not app startup, control DB initialization.
- Helper functions inside the test modules build templates, reports, and platform fixtures explicitly instead of hiding setup behind opaque shared state.
- Quote-provider behavior is exercised through `app.dependency_overrides` on the FastAPI app rather than through real network calls.
- For ordinary removal-only checks, prefer manual confirmation over adding standalone “proves not” tests. Keep absence assertions only when the missing surface is itself the shipped contract, such as `/api/extensions` absence or fail-closed safety behavior.
- `TEST_DATABASE_URL` or `DATABASE_URL` must point to a PostgreSQL server where the test user can connect to `postgres` and create/drop databases.

## ANTI-PATTERNS
- Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.
- Do not rely on shared DB state across tests.
- Do not hit real provider APIs or network services from this suite.
- Do not change preserved product contracts, current agent-platform contracts, or DB bootstrap behavior without updating the corresponding regression files.
- Keep removed extension metadata references limited to explicit negative-validation tests or upgrade-normalization tests. Live contract tests should assert `/api/extensions` absence, static installed extensions, installed tools, and dependency-only run records.
- Do not leave dependency overrides behind after a test; `conftest.py` clears them for a reason.

## VALIDATION
```bash
cd backend
uv run pytest
```

## NOTES
- Pytest config is implicit through `backend/pyproject.toml`; there is no separate `pytest.ini`.
- `test_api.py` covers preserved `/api/v1` behavior and current agent-platform validation paths.
- Extension, tool-catalog, and runtime-tool tests lock statically installed `signaldeck.finance` and `signaldeck.digital_oracle` contracts, installed-tool catalog behavior, and provider/runtime-tool contracts.
- `test_workflow_package_runtime_api.py`, `test_workflow_package_runtime_artifacts.py`, `test_workflow_package_run_contracts.py`, `test_run_operation_invocations.py`, `test_mcp_runtime.py`, `test_runtime_models.py`, `test_runtime_repositories.py`, and `test_db_bootstrap.py` lock the current agent-platform persistence, Scheduled Task APIs/materialization, saved model-connection, trace metadata, MCP boundaries, rerun behavior, bootstrap, and execution contracts.
