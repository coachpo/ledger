# Architecture Gap Register

This register continues the audit sequence from `00-contract-baseline.md`, `01-audit-checklist.md`, `02-current-architecture.md`, and `02-current-architecture-diagrams.md`. It records deviations between the contract target and the inspected implementation. Current behavior that is overbuilt or retained only for non-contract legacy compatibility is classified as a gap, not as behavior to preserve.

Severity scale:

| Severity | Meaning |
| --- | --- |
| P1 | Blocks the clean package-first architecture or carries notable security or runtime risk. |
| P2 | Material cleanup or precision issue that should be fixed before more platform surface is added. |
| P3 | Lower risk cleanup that can follow once higher priority gaps are closed. |

<table>
<thead>
<tr>
<th>ID</th>
<th>Area</th>
<th>Current state</th>
<th>Expected target</th>
<th>Severity</th>
<th>Category</th>
<th>Recommended action</th>
<th>Breaking-change impact</th>
<th>Evidence</th>
</tr>
</thead>
<tbody>
<tr>
<td>GAP-001</td>
<td>Legacy and global authoring ballast</td>
<td>Global authoring entities are no longer mounted as live routes, but model, repository, schema, frontend type, and runtime-blocked helper code remains resident. `backend/app/models/__init__.py` still imports and exports `Agent`, `Capability`, `McpServer`, `OutputSchema`, and `Workflow`. The entity files `backend/app/models/agent.py`, `workflow.py`, `capability.py`, `mcp_server.py`, and `output_schema.py` still define standalone tables. Matching repository and schema modules still exist. Frontend package-local authoring helpers still import legacy global `AgentRead` and `WorkflowRead` wire types from `frontend/src/lib/types/agent.ts` and `frontend/src/lib/types/workflow.ts`. `backend/app/services/legacy_authoring.py::raise_legacy_global_authoring_runtime_blocked` preserves a blocked runtime helper.</td>
<td>Workflow Packages are the only executable authoring root. Global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration-v2, and runtime-v2 should be deleted from live code paths instead of preserved, aliased, or wrapped.</td>
<td>P1</td>
<td>Removal cleanup</td>
<td>Remove global authoring ORM, repository, schema, frontend wire-type, and helper surfaces that are not needed by the package artifact model. Keep package-private agent, output schema, capability profile, MCP config, and graph data inside Workflow Package artifacts only. Do not add compatibility aliases.</td>
<td>Internal schema and code cleanup. It intentionally breaks removed global authoring internals. No live public route should be preserved because `backend/app/api/platform_router.py` mounts only platform routes and `backend/tests/test_legacy_backend_cutover.py` already guards removed routes.</td>
<td>`00-contract-baseline.md` says delete global authoring roots. `02-current-architecture.md` proves route removal only. Code evidence: `backend/app/models/__init__.py`; `backend/app/models/agent.py::Agent`; `backend/app/models/workflow.py::Workflow`; `backend/app/models/capability.py::Capability`; `backend/app/models/mcp_server.py::McpServer`; `backend/app/models/output_schema.py::OutputSchema`; `backend/app/repositories/agent.py`; `backend/app/repositories/workflow.py`; `backend/app/repositories/capability.py`; `backend/app/repositories/mcp_server.py`; `backend/app/repositories/output_schema.py`; `backend/app/schemas/agent.py`; `backend/app/schemas/workflow.py`; `backend/app/schemas/capability.py`; `backend/app/schemas/mcp_server.py`; `backend/app/schemas/output_schema.py`; `backend/app/services/legacy_authoring.py`; `frontend/src/lib/types/agent.ts`; `frontend/src/lib/types/workflow.ts`; `frontend/src/components/platform-authoring/workflow-builder/workflow-builder-wizard.tsx`; `frontend/src/lib/platform-authoring/workflows/codec.ts`.</td>
</tr>
<tr>
<td>GAP-002</td>
<td>Startup repair and migration ballast for retired surfaces</td>
<td>`backend/app/db/session.py::init_db` calls `upgrade_legacy_schema` and describes the step as compatibility repairs. `backend/app/db/upgrades.py` remains the PostgreSQL startup repair authority for live tables, but it also retains broad legacy cleanup and repair logic for retired product surfaces, including legacy runtime tables and global authoring table statements. `backend/tests/test_runtime_db_upgrades.py` still tests cleanup of legacy skill storage and global agents.</td>
<td>Keep current PostgreSQL startup repair for live tables only. Delete speculative migration ballast for product surfaces that have no users and no release contract.</td>
<td>P1</td>
<td>Migration ballast</td>
<td>Split live startup repair from retired-surface cleanup. Keep repairs for current tables such as runs, schedules, extension state, model connections, package secrets, runtime inputs, and memory. Remove retired global authoring and old backend cleanup paths once their absence is proven by route and table checks.</td>
<td>Potentially breaks startup recovery for unreleased draft databases that still contain retired tables. That is acceptable under the no-users baseline. It must not break current PostgreSQL startup repair for live tables.</td>
<td>`00-contract-baseline.md` says delete speculative migration ballast while keeping `backend/app/db/` as schema authority. Code evidence: `backend/app/db/session.py::init_db`; `backend/app/db/upgrades.py::_LEGACY_BACKEND_TABLES`; `backend/app/db/upgrades.py::_AGENT_PLATFORM_TABLE_STATEMENTS`; `backend/app/db/upgrades.py::upgrade_legacy_schema`; `backend/tests/test_runtime_db_upgrades.py::test_init_db_deletes_legacy_skill_storage_and_global_agents_idempotently`; current live repair evidence in `02-current-architecture.md` under Persistence And Schema Authority.</td>
</tr>
<tr>
<td>GAP-003</td>
<td>Workflow Package export precision and secret-adjacent MCP fields</td>
<td>`backend/app/services/workflow_package_export.py::_MCP_EXPORT_KEYS` allows `env`, `headers`, and `query` in exported MCP server definitions. `build_safe_package_definition` removes forbidden keys such as `apiKey`, `secretPayload`, `encrypted`, and `password`, but preserves inline MCP connection material. Backend tests assert that package secret binding raw values are absent while `${{ secrets.* }}` references remain, and a security test asserts raw inline HTTP/SSE header and query values remain. Frontend workflow-package export preview coverage also expects inline MCP `env`, `headers`, and `query` values containing `sk-live-*` tokens to appear in the visible YAML preview.</td>
<td>Exports should match the current live contract and avoid preserving model/package secrets or secret-adjacent inline connection material unless that behavior is explicitly accepted. Long-term Workflow Package import/export compatibility is out of scope.</td>
<td>P1</td>
<td>Contract precision and security</td>
<td>Define the export contract precisely. Decide whether MCP `headers`, `query`, and `env` are public exportable config or secret-bearing material. If they are not public config, remove them from export output and update export tests. Keep the finding scoped to export precision and inline MCP values, not to package secret-binding raw values.</td>
<td>May break current export round trips for packages that rely on inline MCP HTTP/SSE headers or query values. Under the baseline, that compatibility should not override secret absence and current-contract clarity.</td>
<td>`00-contract-baseline.md` says secrets are absent from exports and long-term import/export compatibility is out of scope. Code evidence: `backend/app/services/workflow_package_export.py::_MCP_EXPORT_KEYS`; `backend/app/services/workflow_package_export.py::build_safe_package_definition`; `backend/tests/test_workflow_package_export.py::test_secret_binding_export_omission`; `backend/tests/test_workflow_package_export_security.py::test_export_preserves_inline_http_sse_values_without_synthesizing_secret_metadata`; `frontend/src/pages/workflow-packages/preflight-launch-export.test.tsx`; `frontend/src/pages/workflow-packages/AGENTS.md`.</td>
</tr>
<tr>
<td>GAP-004</td>
<td>Run finalization lease and status precision</td>
<td>`RunQueueService` owns `claim_next_run`, `heartbeat_run`, `release_run_lease`, and `recover_stale_leases`, including lease owner checks for heartbeat and release. `RunSchedulerWorker` heartbeats while `RunService.execute_claimed_run` runs and releases the lease afterward. `RunService.execute_claimed_run` confirms the run is `running` before execution, but final success and failure writes are performed inside `RunService`, not through `RunQueueService` and not visibly tied to the active lease owner in the inspected code.</td>
<td>Queue ownership should make the terminal write contract precise. Either finalization stays in `RunService` with explicit reviewed invariants, or terminal status updates move behind a queue-owned method that checks the active lease owner and running state.</td>
<td>P2</td>
<td>Needs targeted review</td>
<td>Do a focused concurrency review around stale lease recovery, heartbeat loss, exception finalization, and terminal status commits. Add or adjust tests only if the review proves an actual race. Do not treat this audit finding as runtime-bug evidence by itself.</td>
<td>No intended public API break. The likely impact is internal service boundary and test clarification. If a race is proven, the fix could change how stale or concurrently recovered runs are finalized.</td>
<td>`01-audit-checklist.md` assigns queue ownership to `RunQueueService`. Code evidence: `backend/app/services/run_queue_service.py::claim_next_run`; `heartbeat_run`; `release_run_lease`; `recover_stale_leases`; `backend/app/workers/run_scheduler.py::RunSchedulerWorker._execute_claimed_run`; `_heartbeat_until_finished`; `backend/app/services/run_service.py::execute_claimed_run`; `backend/app/services/run_service.py::_execute_run_with_trace`; coverage anchors in `backend/tests/test_workflow_package_runtime_api.py`, `backend/tests/test_workflow_package_run_contracts.py`, and `backend/tests/test_runtime_repositories.py`.</td>
</tr>
</tbody>
</table>

## Register Notes

The register does not recommend compatibility aliases, wrappers, or shims for removed global authoring surfaces. The baseline has no users, so cleanup should favor current package-first architecture over preserving draft paths.

`GAP-004` is deliberately marked `needs targeted review`. The inspected code shows a service-boundary precision issue, not enough evidence to claim a confirmed lease race or status overwrite bug.
