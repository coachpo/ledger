# Implementation Plan

This plan turns the gap register and target architecture into incremental refactor slices. It is implementation planning only. It does not authorize compatibility shims, dual paths, route aliases, legacy DTO preservation, old table-name preservation, or startup-repair ballast outside the live contract.

## Global Guardrails

- Workflow Packages remain the only executable authoring root.
- API launch, rerun, fork, preview, and run-now paths stay queue-only.
- Worker-owned execution, heartbeats, lease recovery, and run evidence persistence stay backend-owned.
- Platform core stays separate from Finance and tool-only Digital Oracle behavior.
- Memory stays explicit-scope and package-contextual only.
- Secret-safe reads and encrypted persistence remain required.
- Breaking changes are acceptable; temporary dual paths are not.

## Slice Order

The slice order follows the requested priority. Slice 1 is explicit: lock the contract and negative legacy tests first so later cleanup can delete dead paths without preserving them “temporarily.” GAP-004 remains investigation-before-fix inside the runtime slice; the plan does not assume a bug before the review proves one.

Dependency exception for GAP-002: the plan freezes retired-table absence and live-upgrade expectations in S01, then performs final startup-repair/model deletion in S13 only after route cleanup, layer splits, and extension isolation stop importing or depending on the retired surfaces. This keeps GAP-002 treated early as a contract guard while still making the destructive cleanup depend on proven route/module absence.

## S01. Contract/Test Baseline And Negative Legacy Tests

**Goal**
Lock the live contract and removed-surface guarantees before deleting code.

**Scope**: removed backend/global-authoring routes, removed browser routes/nav entries, OpenAPI absence checks, retired-table absence/live-upgrade guards, and baseline regression commands.
**Files likely affected**: `backend/tests/test_legacy_backend_cutover.py`; `backend/tests/test_workflow_package_removed_contract_gates.py`; `backend/tests/test_runtime_db_upgrades.py`; `frontend/src/routes.test.tsx`; `frontend/e2e/navigation.spec.ts`; `frontend/e2e/shell-regression.spec.ts`.
**Code changes**: strengthen absence assertions for removed routes/modules/nav entries; add explicit retired-table/live-upgrade guard coverage for later GAP-002 cleanup; isolate negative-contract tests from happy-path platform tests; document Slice-1 verification as the gate for all later deletions.
**Tests to add/update/delete**: add/update explicit 404/OpenAPI/browser-nav absence checks and retired-table/live-repair contract tests; keep existing removed-path tests where absence is the shipped contract; delete any test that preserves retired route behavior as acceptable.
**Legacy code to delete**: stale test fixtures or assertions that treat removed global authoring/runtime surfaces or retired-table ballast as soft-deprecated instead of removed.
**Risks**: over-asserting on implementation detail instead of contract; missing one retired path and reintroducing it later; freezing the wrong live-upgrade behavior before GAP-002 cleanup.
**Verification commands**: `cd backend && uv run pytest tests/test_legacy_backend_cutover.py tests/test_workflow_package_removed_contract_gates.py tests/test_runtime_db_upgrades.py`; `cd frontend && pnpm test:run -- --run src/routes.test.tsx`; `cd frontend && pnpm test:e2e -- --grep "navigation|shell"`.
**Roll-forward strategy**: land and keep these negative tests first; every later slice must preserve them or deliberately tighten them, never weaken them; S13 may delete startup-repair ballast only after these guards stay green.

## S02. Route/API Surface Cleanup
**Goal**: remove non-contract route wiring and keep only the live `/api`, `/api/v1`, and browser route surfaces.
**Scope**: backend route registration, dependency wiring, OpenAPI exposure, and frontend live route tree metadata.
**Files likely affected**: `backend/app/api/platform_router.py`; `backend/app/api/router.py`; `backend/app/api/dependencies.py`; `backend/tests/test_api.py`; `backend/tests/test_workflow_package_openapi.py`; `frontend/src/routes.ts`; `frontend/src/routes.metadata.ts`.
**Code changes**: delete any lingering route imports or dependency hooks for removed authoring/runtime surfaces; keep finance `/api/v1` extension routing intact; keep browser routing limited to dashboard, finance, extensions, workflow-packages, scheduled-tasks, model-connections, memory, and runs.
**Tests to add/update/delete**: update OpenAPI and route-table tests to assert live prefixes only; preserve backend/frontend 404 tests; delete any test that tolerates hidden aliases or legacy route redirects.
**Legacy code to delete**: orphaned route modules, route aliases, compatibility redirects, and route metadata for removed browser families.
**Risks**: accidentally cutting live finance routes or exposing a route in OpenAPI after removing its handler.
**Verification commands**: `cd backend && uv run pytest tests/test_legacy_backend_cutover.py tests/test_workflow_package_openapi.py tests/test_api.py`; `cd frontend && pnpm test:run -- --run src/routes.test.tsx`.
**Roll-forward strategy**: finish route-table cleanup before broader refactors so later service/module movement does not have to preserve dead entrypoints.

## S03. Layer/Module Boundaries
**Goal**: move the backend toward the target API/application/domain/ports/infrastructure split without preserving old service sprawl.
**Scope**: composition root, service orchestration, repository transaction rules, and import-direction cleanup.
**Files likely affected**: `backend/app/api/dependencies.py`; `backend/app/services/workflow_package_service.py`; `backend/app/services/run_service.py`; `backend/app/services/run_queue_service.py`; `backend/app/services/extension_service.py`; `backend/app/repositories/*`; `backend/app/models/__init__.py`.
**Code changes**: create layer packages; move orchestration into application use cases; move invariants into domain modules; define ports for repositories/queue/runtime tooling; ensure repositories do not commit independently; remove live imports from retired global-authoring models.
**Tests to add/update/delete**: update `backend/tests/test_refactor_helpers.py`, `test_runtime_models.py`, and `test_runtime_repositories.py`; add focused import-boundary/static checks if needed; delete tests that validate legacy module layout rather than behavior.
**Legacy code to delete**: service glue that exists only to preserve old module placement, retired global-model exports in `models/__init__.py`, and compatibility re-export imports.
**Risks**: import cycles, transaction-boundary regressions, and partial refactors that leave two ownership paths alive.
**Verification commands**: `cd backend && uv run mypy app`; `cd backend && uv run pytest tests/test_refactor_helpers.py tests/test_runtime_models.py tests/test_runtime_repositories.py`.
**Roll-forward strategy**: move one service family at a time behind the new layer boundary and delete old imports in the same slice; do not keep compatibility re-exports.

## S04. Package Manifest Validation And Package-Local Resources
**Goal**: keep package authoring package-local and remove legacy global-authoring semantics from manifest/resource handling.
**Scope**: backend manifest parsing/compile/decompile, package-local graph resources, and frontend package-local authoring types/helpers.
**Files likely affected**: `backend/app/services/workflow_package_manifest_parser.py`; `backend/app/services/workflow_package_manifest_compiler.py`; `backend/app/services/workflow_package_manifest_decompiler.py`; `frontend/src/lib/platform-authoring/workflows/*`; `frontend/src/lib/types/agent.ts`; `frontend/src/lib/types/workflow.ts`; `frontend/src/pages/workflow-packages/*`.
**Code changes**: keep unsupported global roots invalid; remove legacy global-authoring names/assumptions from frontend helpers; keep package-private agents, output schemas, capability profiles, MCP configs, and workflow graphs inside package resources only.
**Tests to add/update/delete**: update `backend/tests/test_workflow_package_manifest_parser.py`, `test_workflow_package_manifest_compiler.py`, `test_workflow_package_manifest_decompiler.py`, and `test_workflow_package_api.py`; update frontend package-editor/launch/export tests that still reference legacy names; delete any fixture that implies standalone global authoring remains valid.
**Legacy code to delete**: frontend type adapters/imports and parser branches that preserve removed global ids or global resource roots.
**Risks**: breaking package round-trips unexpectedly or renaming frontend contracts without updating all authoring surfaces.
**Verification commands**: `cd backend && uv run pytest tests/test_workflow_package_manifest_parser.py tests/test_workflow_package_manifest_compiler.py tests/test_workflow_package_manifest_decompiler.py tests/test_workflow_package_api.py`; `cd frontend && pnpm test:run -- --run src/pages/workflow-packages`.
**Roll-forward strategy**: backend manifest rules land first, then frontend package-local type/helper renames land in one clean cut with no compatibility aliases.

## S04A. Workflow Package Export Contract And Secret-Adjacent MCP Fields
**Goal**: resolve GAP-003 with one explicit export contract instead of preserving ambiguous inline MCP behavior.
**Scope**: backend export builders, export security tests, frontend export preview/launch UI expectations, and package secret-reference rules.
**Files likely affected**: `backend/app/services/workflow_package_export.py`; `backend/tests/test_workflow_package_export.py`; `backend/tests/test_workflow_package_export_security.py`; `frontend/src/lib/api/workflow-packages.ts`; `frontend/src/pages/workflow-packages/preflight-launch-export.test.tsx`.
**Code changes**: decide whether MCP `env`, `headers`, and `query` are public config or secret-bearing fields; implement one clean export rule; keep package secret raw values and model-connection secrets absent from exports; remove preview assumptions that preserve legacy inline secret-like values if the contract rejects them.
**Tests to add/update/delete**: update backend export and export-security tests plus frontend export-preview tests to the chosen contract; delete tests that preserve secret-adjacent inline values once the contract says they are not exportable.
**Legacy code to delete**: export branches, preview assumptions, and helper behavior that keep ambiguous inline MCP material for compatibility reasons.
**Risks**: breaking current export round-trips or leaking secret-adjacent config if the contract remains ambiguous.
**Verification commands**: `cd backend && uv run pytest tests/test_workflow_package_export.py tests/test_workflow_package_export_security.py`; `cd frontend && pnpm test:run -- --run src/pages/workflow-packages/preflight-launch-export.test.tsx`.
**Roll-forward strategy**: settle the export contract before launch/runtime cleanup; once the rule is chosen, remove the losing path immediately instead of supporting both.

## S05. Launch/Preflight/Queued Run Creation
**Goal**: ensure launch and readiness paths only validate, snapshot, and queue runs.
**Scope**: package preflight, launch metadata, launch creation, rerun/fork creation, and frontend launch UX assumptions.
**Files likely affected**: `backend/app/api/workflow_packages.py`; `backend/app/services/workflow_package_service.py`; `backend/app/services/run_service.py`; `backend/app/schemas/run.py`; `frontend/src/pages/workflow-packages/launch.tsx`; `frontend/src/lib/api/workflow-packages.ts`.
**Code changes**: keep preflight/readiness separate from save/import; create immutable queued-run snapshots only; remove any remaining blocked/legacy runtime entrypoints; keep request handlers from executing workflows inline.
**Tests to add/update/delete**: update `backend/tests/test_workflow_package_preflight.py`, `test_workflow_package_runtime_api.py`, `test_workflow_package_run_contracts.py`, and `frontend/e2e/workflow-packages.spec.ts`; delete tests that accept inline execution or legacy run-creation paths.
**Legacy code to delete**: blocked legacy runtime entrypoints and helper methods that imply non-package execution roots.
**Risks**: hidden inline execution paths, stale readiness assumptions, and run-snapshot drift between launch variants.
**Verification commands**: `cd backend && uv run pytest tests/test_workflow_package_preflight.py tests/test_workflow_package_runtime_api.py tests/test_workflow_package_run_contracts.py`; `cd frontend && pnpm test:e2e -- --grep "workflow-packages"`.
**Roll-forward strategy**: land queue-only launch invariants first, then tighten frontend launch assumptions to the same contract without preserving old run-create behavior.

## S06. Worker/Runtime Execution Of Run Snapshots
**Goal**: keep execution, heartbeats, lease recovery, and run evidence persistence worker-owned while resolving GAP-004 by investigation before any fix.
**Scope**: `RunSchedulerWorker`, `RunQueueService`, `RunService.execute_claimed_run`, runtime execution providers, terminal status writes, and artifact persistence.
**Files likely affected**: `backend/app/workers/run_scheduler.py`; `backend/app/services/run_queue_service.py`; `backend/app/services/run_service.py`; `backend/app/services/run_read_projection.py`; `backend/app/core/telemetry.py`.
**Code changes**: first codify expected lease/status ownership and add targeted tests around stale recovery, heartbeat loss, and terminal writes; only if the investigation proves a bug, collapse finalization to one reviewed ownership path without duplicating queue logic in routes or ad-hoc helpers.
**Tests to add/update/delete**: update `backend/tests/test_workflow_package_runtime_api.py`, `test_workflow_package_run_contracts.py`, `test_runtime_repositories.py`, `test_run_operation_invocations.py`, and `test_workflow_package_runtime_artifacts.py`; delete tests that lock split ownership after a reviewed simplification.
**Legacy code to delete**: duplicate finalization branches, stray non-worker execution helpers, and any code path that writes terminal state outside the reviewed ownership contract.
**Risks**: race regressions, trace/evidence loss, or over-correcting a precision issue that is not actually a bug.
**Verification commands**: `cd backend && uv run pytest tests/test_workflow_package_runtime_api.py tests/test_workflow_package_run_contracts.py tests/test_runtime_repositories.py tests/test_run_operation_invocations.py tests/test_workflow_package_runtime_artifacts.py`.
**Roll-forward strategy**: stop after the investigation if no real bug is proven; if a bug is proven, land the ownership simplification and its tests in one slice with no parallel execution path left behind.

## S07. Schedules/Fire Materialization/Run-Now
**Goal**: keep Scheduled Tasks package-first, backend-owned, and queue-backed with no raw-cron compatibility leftovers.
**Scope**: schedule schemas, preview, run-now, fire materialization, provenance, and frontend scheduled-task flows.
**Files likely affected**: `backend/app/api/schedules.py`; `backend/app/services/workflow_package_schedule_service.py`; `backend/app/services/workflow_package_schedule_materializer.py`; `backend/app/services/workflow_package_schedule_inputs.py`; `frontend/src/pages/scheduled-tasks/*`; `frontend/e2e/scheduled-tasks.spec.ts`.
**Code changes**: preserve structured recurrence and IANA timezone ownership in backend code; keep previews ephemeral; keep run-now creating ordinary queued runs with fire provenance; remove old cleanup assumptions or compatibility fields tied to retired schedule shapes.
**Tests to add/update/delete**: update `backend/tests/test_runtime_repositories.py`, `test_workflow_package_run_contracts.py`, and `frontend/e2e/scheduled-tasks.spec.ts`; delete tests that preserve raw-cron or client-owned recurrence behavior.
**Legacy code to delete**: retired schedule cleanup branches, compatibility payload fields, or helper paths that bypass queued fire creation.
**Risks**: DST/provenance regressions and accidental inline execution from run-now flows.
**Verification commands**: `cd backend && uv run pytest tests/test_runtime_repositories.py tests/test_workflow_package_run_contracts.py`; `cd frontend && pnpm test:e2e -- --grep "scheduled-tasks"`.
**Roll-forward strategy**: land backend recurrence/materialization changes first, then adjust frontend detail/editor flows to the same payload and provenance rules.

## S08. Model Connections/Secrets
**Goal**: preserve encrypted persistence and write-only secret reads while removing non-contract compatibility behavior.
**Scope**: model-connection routes, schemas, services, encrypted payload handling, connection-test flows, and frontend editor/read models.
**Files likely affected**: `backend/app/api/model_connections.py`; `backend/app/models/model_connection.py`; `backend/app/schemas/model_connection.py`; `backend/app/services/model_connection_service.py`; `frontend/src/pages/model-connections/editor.tsx`; `frontend/e2e/model-connections.spec.ts`.
**Code changes**: keep public reads secret-safe; keep encryption at rest required; keep backend-owned compatibility/probe truth; remove DTO fields, editor assumptions, or helpers that leak or preserve obsolete connection metadata.
**Tests to add/update/delete**: update `backend/tests/test_runtime_repositories.py`, `backend/tests/test_api.py`, `frontend/src/pages/model-connections/editor.test.tsx`, and `frontend/e2e/model-connections.spec.ts`; delete tests that tolerate echoed secret values or client-authored compatibility profiles.
**Legacy code to delete**: secret echo helpers, obsolete compatibility-profile DTOs, and frontend preservation paths for cleared secret inputs.
**Risks**: accidental secret disclosure or breakage in saved connection edit flows.
**Verification commands**: `cd backend && uv run pytest tests/test_runtime_repositories.py tests/test_api.py`; `cd frontend && pnpm test:run -- --run src/pages/model-connections/editor.test.tsx`; `cd frontend && pnpm test:e2e -- --grep "model-connections"`.
**Roll-forward strategy**: enforce secret-safe read/write behavior first, then delete obsolete connection metadata paths and update frontend editors in the same cut.

## S09. Tools/Runtime Dispatch Separation
**Goal**: keep `/api/tools` as read-only metadata and runtime execution as a separate, grant-aware path.
**Scope**: server-declared tool catalog, runtime tool registry, MCP runtime adapters, extension-owned tool registration, and package authoring tool reads.
**Files likely affected**: `backend/app/api/tools.py`; `backend/app/agents/tool_catalog/server_declared.py`; `backend/app/agents/runtime_tools/registry.py`; `backend/app/agents/runtime_tools/memory.py`; `backend/app/agents/mcp/runtime.py`; `backend/app/extensions/registry.py`; `frontend/src/hooks/use-workflow-packages.ts`.
**Code changes**: keep catalog metadata free of execution concerns; keep runtime dispatch checking extension state, grants, and arguments; keep core memory tools platform-owned and Finance/Digital Oracle tools extension-owned; remove compatibility mappings that blur removed tool or registry boundaries.
**Tests to add/update/delete**: update `backend/tests/test_tool_catalog_api.py`, `test_runtime_tools.py`, `test_mcp_runtime.py`, and `test_extension_lifecycle_matrix.py`; delete tests that accept catalog/runtime coupling or route exposure for tool-only Digital Oracle behavior.
**Legacy code to delete**: compatibility mapping layers, stale tool-id aliases, and any catalog helpers that encode execution policy.
**Risks**: grant/filter drift between catalog and runtime dispatch or accidental route exposure for tool-only features.
**Verification commands**: `cd backend && uv run pytest tests/test_tool_catalog_api.py tests/test_runtime_tools.py tests/test_mcp_runtime.py tests/test_extension_lifecycle_matrix.py`.
**Roll-forward strategy**: freeze catalog contract first, then move runtime dispatch behind the cleaned grant/extension filters in one path.

## S10. Scoped Memory
**Goal**: keep memory explicit-scope, package-contextual, and platform-owned without reintroducing global CRUD/search semantics.
**Scope**: memory API, memory schemas, memory services/store adapters, core memory runtime tools, and single-route frontend memory UX.
**Files likely affected**: `backend/app/api/memory.py`; `backend/app/schemas/memory.py`; `backend/app/services/memory_service.py`; `backend/app/agents/runtime_tools/memory.py`; `frontend/src/pages/memory/list.tsx`; `frontend/e2e/memory.spec.ts`.
**Code changes**: require access context and concrete private scope; keep projections separated by API/model/UI visibility; keep `/memory` as a single route with inline panes only; remove unscoped search, namespace-grant authoring, and report-backed memory assumptions.
**Tests to add/update/delete**: update `backend/tests/test_api_memory.py`, `test_memory_service.py`, `test_postgres_memory_store.py`, `test_memory_domain_schemas.py`, `test_memory_layer_static_contracts.py`, and `frontend/e2e/memory.spec.ts`; delete tests that imply global memory browse or route fan-out.
**Legacy code to delete**: unscoped memory helpers, namespace-grant authoring UI/state, and stale report-memory shortcuts.
**Risks**: accidentally widening scope rules or breaking revision/event inspection while tightening access context.
**Verification commands**: `cd backend && uv run pytest tests/test_api_memory.py tests/test_memory_service.py tests/test_postgres_memory_store.py tests/test_memory_domain_schemas.py tests/test_memory_layer_static_contracts.py`; `cd frontend && pnpm test:e2e -- --grep "memory"`.
**Roll-forward strategy**: land backend scope enforcement first, then update the single-route frontend memory page to the same one-path contract.

## S11. Extensions And Finance Isolation
**Goal**: keep platform core, Finance, and tool-only Digital Oracle on clean ownership boundaries.
**Scope**: extension registry/state, extension filtering, Finance-owned routes/tools/providers, and Digital Oracle route/nav absence.
**Files likely affected**: `backend/app/extensions/registry.py`; `backend/app/services/extension_service.py`; `backend/app/extensions/signaldeck_finance/*`; `backend/app/extensions/signaldeck_digital_oracle/*`; `frontend/src/extensions/runtime-helpers.ts`; `frontend/src/extensions/signaldeck-finance/*`; `frontend/src/extensions/signaldeck-digital-oracle/*`; `frontend/src/pages/extensions/list.tsx`.
**Code changes**: keep `/api/extensions` slim; keep Finance-owned routes/tools gated by extension state; keep Digital Oracle tool-only with no route/nav contributions; remove finance leakage from platform services and remove route/nav assumptions for Digital Oracle.
**Tests to add/update/delete**: update `backend/tests/test_extensions_api.py`, `test_extension_registry.py`, `test_extension_lifecycle_matrix.py`, `test_tool_catalog_api.py`, `frontend/src/routes.test.tsx`, and `frontend/e2e/extensions.spec.ts`; delete tests that preserve private registry metadata or route exposure for tool-only extensions.
**Legacy code to delete**: public registry leakage, finance assumptions in core modules, and dormant Digital Oracle route/nav artifacts.
**Risks**: accidentally hiding live Finance behavior or exposing extension-private registry details.
**Verification commands**: `cd backend && uv run pytest tests/test_extensions_api.py tests/test_extension_registry.py tests/test_extension_lifecycle_matrix.py tests/test_tool_catalog_api.py`; `cd frontend && pnpm test:run -- --run src/routes.test.tsx`; `cd frontend && pnpm test:e2e -- --grep "extensions"`.
**Roll-forward strategy**: lock slim-state/filter tests first, then move ownership boundaries and delete leaked assumptions in the same slice.

## S12. Frontend Route/Navigation Cleanup
**Goal**: keep only live browser surfaces and package-local authoring semantics in the frontend.
**Scope**: route tree, route metadata, layout nav, workflow-package pages, package-local type naming, and removed browser route absence.
**Files likely affected**: `frontend/src/routes.ts`; `frontend/src/routes.metadata.ts`; `frontend/src/components/layout.tsx`; `frontend/src/pages/workflow-packages/*`; `frontend/src/lib/platform-authoring/*`; `frontend/src/lib/types/agent.ts`; `frontend/src/lib/types/workflow.ts`; `frontend/e2e/navigation.spec.ts`.
**Code changes**: remove retired route families/nav entries; keep the single `/memory` route; rename package-local authoring types/helpers away from misleading global-authoring semantics; split dense workflow-package editor/launch pages if needed without introducing dual UI paths.
**Tests to add/update/delete**: update `frontend/src/routes.test.tsx`, `frontend/e2e/navigation.spec.ts`, `frontend/e2e/shell-regression.spec.ts`, `frontend/e2e/workflow-packages.spec.ts`, and any workflow-package page tests; delete tests that accept hidden removed nav entries or compatibility redirects.
**Legacy code to delete**: compatibility imports, stale route metadata, dead nav items, and helper names/patterns that imply standalone global authoring routes still exist.
**Risks**: deep-link breakage on live pages or incomplete type/helper renames.
**Verification commands**: `cd frontend && pnpm test:run -- --run src/routes.test.tsx`; `cd frontend && pnpm test:e2e -- --grep "navigation|shell|workflow-packages"`; `cd frontend && pnpm build`.
**Roll-forward strategy**: land router/metadata/nav cleanup first, then complete package-local type/helper renames and page decomposition in one clean frontend path.

## S13. Persistence/Migration Cleanup
**Goal**: simplify schema authority to live-table startup repair only and delete retired-surface ballast.
**Scope**: DB init, startup repair, retired global-authoring tables/models/repos/schemas, and upgrade-contract tests.
**Files likely affected**: `backend/app/db/session.py`; `backend/app/db/upgrades.py`; `backend/app/models/__init__.py`; `backend/app/models/agent.py`; `backend/app/models/workflow.py`; `backend/app/models/capability.py`; `backend/app/models/mcp_server.py`; `backend/app/models/output_schema.py`; matching repository/schema modules.
**Code changes**: split live-table repair from retired-surface cleanup; keep current tables and queue metadata supported; delete retired global-authoring model/repository/schema code and any startup repair paths that preserve draft-only tables or old runtime surfaces.
**Tests to add/update/delete**: update `backend/tests/test_runtime_db_upgrades.py`, `test_workflow_package_db_upgrades.py`, `test_runtime_models.py`, and `test_legacy_backend_cutover.py`; delete upgrade tests whose only purpose is preserving retired global-authoring or legacy skill-storage cleanup after the clean cut lands.
**Legacy code to delete**: retired global-authoring models/repos/schemas, speculative cleanup markers, old table statements, and draft-only repair branches.
**Risks**: breaking local/dev databases that still carry retired tables or leaving one lingering import to deleted model modules.
**Verification commands**: `cd backend && uv run pytest tests/test_runtime_db_upgrades.py tests/test_workflow_package_db_upgrades.py tests/test_runtime_models.py tests/test_legacy_backend_cutover.py`; `cd backend && uv run mypy app`.
**Roll-forward strategy**: this slice depends on S01, S02, S03, and S11 staying green; prove route/table absence, import cleanup, and live upgrade coverage first, then delete retired repair/model code in one irreversible cleanup slice.

## S14. Final Test/Docs Cleanup
**Goal**: end with one clean contract path, aligned docs, and no remaining legacy-preservation bias.
**Scope**: cross-stack regression sweep, audit docs, live owner docs/tests, and deletion of any obsolete compatibility-focused fixtures left behind by earlier slices.
**Files likely affected**: `docs/architecture-audit/*`; live docs under `docs/*.md` as needed; targeted backend/frontend tests touched by prior slices; `.github/workflows/ci.yml` only as read-only verification reference.
**Code changes**: remove leftover compatibility comments/fixtures/tests/docs; ensure current docs describe only the live package-first route/API/runtime surface; do not broaden CI scope, only verify against existing gates.
**Tests to add/update/delete**: run the full backend, frontend, and E2E suites; delete redundant compatibility-focused tests that became unnecessary once removed-path contract tests and live-path tests cover the final state.
**Legacy code to delete**: any lingering compatibility fixture, doc passage, or stale test helper that preserves removed global authoring, route aliases, raw-cron assumptions, or startup-repair ballast as acceptable behavior.
**Risks**: leaving stale docs/tests that imply the old world is still partially supported.
**Verification commands**: `cd backend && uv run ruff check app tests && uv run black --check app tests && uv run isort --check-only app tests && uv run mypy app && uv run pytest`; `cd frontend && pnpm lint && pnpm typecheck && pnpm build && pnpm test:run`; `cd frontend && pnpm test:e2e`.
**Roll-forward strategy**: merge only after the full suite and docs agree on the same clean path; if any stale compatibility artifact remains, delete it rather than documenting a temporary exception.
