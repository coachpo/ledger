# Architecture Gap Summary

This summary explains the highest value deviations found after the descriptive audit in `02-current-architecture.md` and `02-current-architecture-diagrams.md`. It uses the contract target from `00-contract-baseline.md` and the inspection prompts from `01-audit-checklist.md`.

## Top Deviations

1. Legacy and global authoring code is still present even though live routes are removed. The route layer is clean, but `backend/app/models/__init__.py` still imports `Agent`, `Capability`, `McpServer`, `OutputSchema`, and `Workflow`; entity modules such as `backend/app/models/agent.py` and `backend/app/models/workflow.py` still define global authoring tables; matching repository and schema modules still exist; frontend package-local authoring helpers still import legacy global types from `frontend/src/lib/types/agent.ts` and `frontend/src/lib/types/workflow.ts`; and `backend/app/services/legacy_authoring.py` preserves a runtime-blocked helper. The target is deletion, not preservation.

2. Startup repair still mixes live PostgreSQL repair with retired-surface cleanup. `backend/app/db/session.py::init_db` calls `upgrade_legacy_schema` as compatibility repair. `backend/app/db/upgrades.py` remains the current schema authority, but it also carries old backend table cleanup and global authoring repair statements. `backend/tests/test_runtime_db_upgrades.py::test_init_db_deletes_legacy_skill_storage_and_global_agents_idempotently` proves that retired cleanup is still part of the tested behavior.

3. Workflow Package export needs a sharper public contract for inline MCP connection fields. `backend/app/services/workflow_package_export.py::_MCP_EXPORT_KEYS` includes `env`, `headers`, and `query`. The export sanitizer removes obvious forbidden secret keys, while `backend/tests/test_workflow_package_export.py` confirms package secret binding raw values are omitted and `${{ secrets.* }}` references remain. `backend/tests/test_workflow_package_export_security.py` confirms raw inline HTTP/SSE header and query values remain, and `frontend/src/pages/workflow-packages/preflight-launch-export.test.tsx` expects `sk-live-*` inline MCP values in the visible export preview. This is a contract-precision and security gap, not evidence that package secret-binding raw values leak.

4. Run finalization ownership should be reviewed before the queue contract hardens. `backend/app/services/run_queue_service.py` owns claim, heartbeat, release, and stale lease recovery. `backend/app/workers/run_scheduler.py` heartbeats while `RunService.execute_claimed_run` runs, then releases the lease. `backend/app/services/run_service.py::_execute_run_with_trace` writes terminal success and failure states directly. The audit should treat this as a precision gap that needs targeted review, not as a proven runtime bug.

## Cleanup And Removal Opportunities

The strongest cleanup opportunity is to remove global authoring ballast as one bounded workstream. That includes global authoring ORM classes, repository modules, schema modules, frontend global-authoring wire types, and the runtime-blocked helper. Package-private agents, output schemas, capability profiles, MCP configs, and workflow graphs should remain artifact data inside Workflow Packages.

Startup repair should be trimmed more carefully. `backend/app/db/` is still the live PostgreSQL repair authority, and current tables need startup repair coverage. The gap is the retained repair logic for retired product surfaces that have no users and no release contract. Cleanup should preserve live repairs for runs, schedules, extension state, memory, model connections, package secrets, and runtime input registry tables.

Export cleanup should start with a decision on MCP inline fields. If `headers`, `query`, and `env` are public package configuration, the contract should say so and tests should name that distinction. If they can carry secrets, they should be removed from export output or converted to explicit secret references without adding compatibility shims for older draft exports.

The run finalization item should start as a focused review. The question is whether a terminal status write can race with heartbeat loss or stale lease recovery. The current evidence shows split ownership, not a confirmed bug.

## Aligned Areas

1. Route composition is aligned. `backend/app/main.py`, `backend/app/api/platform_router.py`, and `backend/app/api/router.py` keep platform `/api/*` routes separate from extension-owned `/api/v1/*` contributions.

2. Package-first launch queueing is aligned. `backend/app/api/workflow_packages.py`, `backend/app/services/workflow_package_service.py`, and `backend/app/services/run_service.py::create_workflow_package_launch` create queued run rows rather than executing packages inline.

3. Scheduled task materialization is aligned. `backend/app/api/schedules.py`, `backend/app/services/workflow_package_schedule_materializer.py`, and `backend/app/workers/run_scheduler.py` keep structured recurrence and due-fire materialization backend-owned.

4. Extension slim state and gating are aligned. `backend/app/services/extension_service.py::_to_read_model` exposes only `key`, `label`, and `enabled`, while `frontend/src/extensions/runtime-helpers.ts` filters route, navigation, and tool visibility from backend extension state.

5. Digital Oracle is aligned as tool-only. `backend/app/extensions/registry.py` registers Digital Oracle server and runtime tools only, and `frontend/src/extensions/signaldeck-digital-oracle/scaffold.ts` has empty route and navigation contributions.

6. Frontend route and navigation gating are aligned. `frontend/src/routes.ts`, `frontend/src/routes.metadata.ts`, `frontend/src/extensions/runtime-helpers.ts`, and `frontend/src/routes.test.tsx` keep platform routes, extension routes, removed-route 404 behavior, and `/api/*` browser route absence covered.

7. CI quality gates are aligned. `.github/workflows/ci.yml` runs backend lint, format, type, and test checks; frontend lint, type, build, and unit checks; and Chromium E2E after the quality jobs.

## Fix First Rationale

Fix `GAP-001` and `GAP-002` first because they keep retired authoring concepts resident in the codebase and startup path. If those stay, future work may mistake them for supported extension points or persistence contracts.

Fix `GAP-003` next because export output is a trust boundary. The current behavior may be intentional for public connection config, but the baseline requires secrets to be absent from exports and does not require long-term draft export compatibility.

Review `GAP-004` before changing queue internals. It is worth checking before more worker behavior lands, but the audit should not turn a precision concern into a bug claim without targeted concurrency evidence.
