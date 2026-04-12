# Ledger Agent Platform v2 Technical Spec

## Metadata

Status: Draft
Supersedes: previous contents of `docs/ledger-agent-platform-product-spec.md`
References: `docs/ledger-orchestration-product-spec.md`, `docs/ledger-orchestration-product-prd.md`, `docs/ledger-orchestration-product-design.md`, `docs/orchestration-demo-runbook.md`, `backend/app/services/backtest_service.py`, `backend/app/services/backtest_cycle_service.py`, `backend/app/services/backtest_engine.py`, `backend/app/services/orchestration_service.py`, `backend/app/langgraph/seeds.py`, `backend/app/langgraph/runner.py`, `backend/app/models/backtest_orchestration_snapshot.py`, `backend/app/schemas/backtest.py`, `backend/app/schemas/orchestration.py`
Source of truth notes: this spec defines the implementation-ready v2 target. When current code and this target disagree, current code still defines shipped behavior until cutover gates are passed.

## Scope

This spec defines the BC-breaking v2 contract for runtime-owned execution, versioned agent and workflow specs, persona profiles, capability registry, tryout, Studio, approval lifecycle, trace lifecycle, and backtest integration.

Naming rule:

1. Persisted table/model fields use snake_case.
2. External API and object-reference payloads use camelCase.

## Vocabulary and enums

### Spec origin

`seeded | managed | imported`

### Spec lifecycle status

`DRAFT | ACTIVE | DEPRECATED | ARCHIVED`

Version lifecycle rules:

1. Versioned records are append-only once status is `ACTIVE`, `DEPRECATED`, or `ARCHIVED`.
2. `PATCH .../versions/{version}` may modify the addressed version only while its status is `DRAFT`; patching a non-`DRAFT` version fails.
3. Omitting a version in create/execute requests resolves to the single `ACTIVE` version for that key.
4. If zero or multiple `ACTIVE` versions exist for a key, version omission is invalid and validation fails.
5. At most one `ACTIVE` version may exist per `(entity_type, key)`.
6. At most one `DRAFT` version may exist per `(entity_type, key)`.

### Capability type

`tool | connector | bundle`

### Run caller type

`backtest | tryout | studio | api`

### Run execution kind

`workflow | single_agent`

### Run status

`QUEUED | RUNNING | WAITING_APPROVAL | SUCCEEDED | FAILED | CANCELLED`

### Approval status

`PENDING | APPROVED | DENIED | EXPIRED`

### Approval mode

`not_required | required`

### Trace event type

`RUN_CREATED | STEP_STARTED | STEP_COMPLETED | TOOL_CALLED | TOOL_RETURNED | APPROVAL_REQUESTED | APPROVAL_RESOLVED | RUN_COMPLETED | RUN_FAILED | RUN_CANCELLED | RUN_EXPIRED | WARNING_EMITTED`

### Backtest compatibility cycle status

`RUNNING | WAITING_APPROVAL | COMPLETED | FAILED | CANCELLED`

### Backtest execution owner

`legacy_path | runtime_v2`

## Baseline and adjacent-code truth

### Shipped baseline

1. Backtests own execution through `BacktestService`, `BacktestCycleService`, and `BacktestEngine`.
2. Orchestration roles and characters are prompt/config and mention surfaces.
3. `BacktestRead` still exposes `orchestrationPatternKey`, callback-aware statuses, and `_run_state` redaction semantics.
4. `backtest_orchestration_snapshots` is the cycle-level orchestration audit store.

### Already-present v2-adjacent code

1. Four supported pattern keys already exist, including tool-enabled variants.
2. Seeded tools, bundles, connectors, and revision metadata already exist in `seeds.py`.
3. Role and character `capabilityBundleKeys` already exist and already affect runtime resolution.
4. Snapshot records already persist execution mode, resolved versions, tool traces, and approval traces.

These four facts are migration inputs, not future ideas.

## Required v2 invariants

1. Runtime, not backtests, owns execution state.
2. Agent specs and workflow specs are versioned and validated before execution.
3. Capability resolution is deterministic and backend-owned.
4. Approval state is explicit, queryable, and persisted.
5. Tryout defaults to ephemeral execution.
6. Studio is a client of the runtime, not a second engine.
7. Backtests invoke one runtime run per cycle.

## Data model contract

### `agent_specs`

Required fields:

1. `id`
2. `key`
3. `version`
4. `origin`
5. `status`
6. `name`
7. `instructions`
8. `model_policy`
9. `default_capability_bundle_keys`
10. `default_persona_profile_keys`
11. `created_at`
12. `updated_at`

Seeded current agents (`position_analyst`, `risk_reviewer`, `decision_writer`) must appear as immutable `origin=seeded` records.

### `workflow_specs`

Persisted fields and derived read metadata:

1. `id`
2. `key`
3. `version`
4. `origin`
5. `status`
6. `name`
7. `entry_agent_key` read-only derived metadata
8. `graph_definition`
9. `final_output_contract`
10. `mention_policy`
11. `execution_mode`
12. `default_tool_ids`
13. `allowed_capability_bundle_keys`
14. `connector_ids`
15. `review_mode`
16. `approval_policy_overrides`
17. `created_at`
18. `updated_at`

Current supported pattern keys must migrate 1:1 into seeded immutable workflow specs:

1. `seeded_internal_backtest_v1`
2. `analyst_reviewer_v1`
3. `seeded_internal_backtest_tool_enabled_v1`
4. `analyst_reviewer_tool_enabled_v1`

`mention_policy` must be a structured object with at least:

1. `version`
2. `allowCharacterPersonas`
3. `allowedBuiltinHandles`

During migration, seeded workflow `mention_policy` rows must mirror the live `PatternMentionPolicy(version, allow_characters, allowed_builtin_handles)` semantics exactly.

`graph_definition` must explicitly encode topology order. For seeded backtest mirrors, it must preserve the current seeded topology `agent_order` exactly.

`execution_mode`, `default_tool_ids`, `allowed_capability_bundle_keys` (mirroring current `allowed_bundle_keys`), `connector_ids`, and `review_mode` must preserve the current `BacktestPatternSpec` and `SeededTopology` values exactly for seeded workflow mirrors.

For rollback-compatible seeded workflows, `review_mode` remains seeded-compatibility metadata and a semantic input to the seeded execution adapter until the rollback window closes.

For v2-native workflows, equivalent reviewer behavior must be expressed only through `graph_definition`.

`graph_definition` must store versioned step refs. For workflow execution it must encode, per step:

1. `stepKey`
2. `agentSpecKey`
3. `agentSpecVersion`
4. `stepPersonaProfileRefs`
5. `stepCapabilityRefs`

`stepPersonaProfileRefs` uses canonical `PersonaProfileRef` objects.

`stepCapabilityRefs` uses canonical `CapabilityRef` objects.

`graph_definition` must also encode, at minimum:

1. `entryStepKey`
2. `edges` with `fromStepKey`, `outcome`, and `toStepKey | END`
3. `terminal` marker per step or explicit `END` edge

Supported edge outcomes must include at least:

1. `success`
2. `failure`
3. `approval_denied`

`entry_agent_key` is derived read-only metadata from `graph_definition.entryStepKey` and the referenced step's `agentSpecKey`; runtime execution must not treat it as an independent source of truth.

Seeded workflow version source:

1. Initial seeded workflow mirror rows use `version=1`.
2. Rollback-window backtests may reference only seeded workflow rows pinned to that version.

Seeded agent version source:

1. Initial seeded agent mirror rows use `version=1`.
2. Future seeded agent revisions increment `version` monotonically and never rewrite historical rows.

Seeded builtin persona version source:

1. Initial seeded builtin persona mirror rows use `version=1`.
2. During migration, that version mirrors the current builtin `revision` value.
3. Future seeded builtin revisions increment `version` monotonically and never rewrite historical rows.

### `persona_profiles`

Required fields:

1. `id`
2. `key`
3. `version`
4. `origin`
5. `status`
6. `kind` (`role_template | character_profile | builtin_profile | managed_persona`)
7. `display_name`
8. `enabled`
9. `handle` nullable
10. `canonical_target_id`
11. `parent_profile_key` nullable
12. `parent_profile_version` nullable
13. `legacy_source_version` nullable
14. `system_prompt_fragment`
15. `prompt_append_fragment`
16. `default_capability_bundle_keys`
17. `created_at`
18. `updated_at`

Current role rows must map to `role_template` profiles. Current character rows must map to `character_profile` profiles.

Seeded builtins `librarian` and `explore` must map to `builtin_profile` records with the same handles.

`canonical_target_id` preserves the live mention-target identity contract:

1. Imported role-template profiles use key `imported.role.{role_key}` and canonical target id `role:{role_key}`.
2. Imported character profiles use key `imported.character.{handle}` and canonical target id `character:{handle}`.
3. Seeded builtin profiles use key `builtin.{handle}` and preserve the existing builtin canonical target id from seeds, such as `builtin:librarian` and `builtin:explore`.
4. Managed personas must have a stable canonical target id even when they are not directly mentionable.

Enabled parity rule:

1. Imported role-template `enabled` mirrors legacy role `enabled`.
2. Imported character `enabled` mirrors legacy character `enabled`.
3. Imported character selection requires both imported character `enabled=true` and parent imported role-template `enabled=true`.
4. Seeded builtin personas are always `enabled=true`.

Imported persona lineage rule:

1. An imported `character_profile` version must point to the exact `role_template` version active for that character when that imported character version was created.
2. If a legacy character change increments the upstream character version or changes the linked role version, the importer creates a new `character_profile` version with a new `(parent_profile_key, parent_profile_version)` pair.
3. Historical imported character versions keep their original parent linkage permanently.
4. `legacy_source_version` preserves the upstream legacy role or character version used to create the imported persona projection.

Imported projection path rule:

1. The audited projection path creates the next imported version and atomically deprecates the previously active imported version for that key.
2. A legacy role projection runs before any dependent imported character projections that reference that role version.

Delete and archive rule:

1. Deleting a legacy role or character archives the imported persona profile version during the rollback window.
2. Archived imported personas remain resolvable for pinned historical runs and traces, but cannot be attached to new workflow specs.

### `capability_registry_entries`

Required fields:

1. `id`
2. `key`
3. `version`
4. `origin`
5. `status`
6. `type`
7. `display_name`
8. `description`
9. `approval_mode`
10. `adapter_key` nullable when `type=bundle`
11. `config_schema` nullable when `type=bundle`
12. `bundle_members` required when `type=bundle`
13. `transport` nullable unless `type=connector`
14. `lifecycle` nullable unless `type=connector`
15. `created_at`
16. `updated_at`

Current seeded tools, bundles, and connectors must appear as immutable `origin=seeded` entries. Managed entries are mutable, but only for internal/admin-controlled surfaces.

Seeded records use `version` in the v2 tables, but that version must mirror the current code-side `revision` value during migration.

`bundle_members` must be a typed list with at least:

1. `memberType` (`tool | connector`)
2. `capabilityKey`
3. `capabilityVersion`

### `runtime_runs`

Required fields:

1. `id`
2. `caller_type`
3. `caller_id` nullable
4. `execution_kind`
5. `workflow_spec_key` nullable when `execution_kind=single_agent`
6. `workflow_spec_version` nullable when `execution_kind=single_agent`
7. `agent_spec_key` nullable when `execution_kind=workflow`
8. `agent_spec_version` nullable when `execution_kind=workflow`
9. `caller_scope_key` nullable; for backtests this must be `cycle_date.isoformat()`
10. `caller_identity_key` nullable; required only when a non-backtest caller uses caller-scoped concurrency or listing
11. `attempt_number`
12. `status`
13. `input_hash`
14. `output_hash` nullable
15. `retention_class` (`ephemeral | persistent`)
16. `expires_at` nullable
17. `trace_summary`
18. `created_at`
19. `updated_at`

Required uniqueness rules:

1. `caller_type=backtest` requires `caller_id`, `caller_scope_key`, and `attempt_number`.
2. `(caller_type, caller_id, caller_scope_key, attempt_number)` must be unique.
3. At most one run in `QUEUED | RUNNING | WAITING_APPROVAL` may exist for a given backtest `(caller_type, caller_id, caller_scope_key)`.
4. Retrying or rerunning the same backtest cycle must create a new run with `attempt_number + 1`; prior attempts remain immutable.
5. Non-backtest callers may have multiple concurrent active runs unless a caller-specific policy uses `caller_identity_key` to restrict them.

### `runtime_trace_events`

Required fields:

1. `id`
2. `run_id`
3. `event_index`
4. `event_type`
5. `step_key` nullable
6. `capability_key` nullable
7. `approval_id` nullable
8. `payload`
9. `created_at`

### `runtime_approvals`

Required fields:

1. `id`
2. `run_id`
3. `step_key`
4. `capability_key`
5. `status`
6. `actor` nullable while status is `PENDING`
7. `reason`
8. `resolved_at` nullable
9. `created_at`

### `runtime_checkpoints`

Required fields:

1. `id`
2. `run_id`
3. `checkpoint_index`
4. `step_key`
5. `serialized_state`
6. `created_at`
7. `updated_at`

### `runtime_run_artifacts`

Required fields:

1. `run_id`
2. `entry_prompt_hash`
3. `full_user_prompt_hash`
4. `authored_entry_prompt_body` nullable
5. `compiled_entry_prompt_body` nullable
6. `execution_context_body` nullable
7. `prompt_report_slug` nullable
8. `raw_mention_handles`
9. `resolved_persona_profile_refs`
10. `report_markdown` nullable
11. `normalized_trade_decisions` nullable
12. `resolved_builtin_versions`
13. `resolved_role_versions`
14. `resolved_character_versions`
15. `resolved_bundle_versions`
16. `resolved_tool_versions`
17. `resolved_connector_versions`
18. `mentioned_target_outputs`
19. `resolved_mentions`
20. `resolved_workflow_agent_refs` nullable when `execution_kind=single_agent`
21. `resolved_capabilities`
22. `final_output` nullable
23. `terminal_error_code` nullable
24. `terminal_error_message` nullable
25. `created_at`

Caller-scoped artifact rule:

1. `normalized_trade_decisions` is required only for backtest callers.
2. `prompt_report_slug` is required only for callers that generate a prompt report.
3. Tryout and Studio callers may leave caller-specific artifact fields null when they do not apply.
4. `final_output` is required for terminal `SUCCEEDED` runs across all caller types.
5. `terminal_error_code` and `terminal_error_message` are required for terminal `FAILED` runs.

Canonical `PersonaProfileRef` object:

1. `personaProfileKey`
2. `personaProfileVersion` optional on authoring/input, required after resolution
3. `canonicalTargetId`
4. `personaKind` nullable until resolution
5. `origin` nullable until resolution
6. `selectionSource` nullable until resolution
7. `parentPersonaProfileRef` nullable

`resolved_persona_profile_refs` must preserve canonical `PersonaProfileRef` objects with at least:

1. `personaProfileKey`
2. `personaProfileVersion`
3. `canonicalTargetId`
4. `personaKind`
5. `origin`
6. `selectionSource`
7. `parentPersonaProfileRef` nullable
8. `legacySourceVersion` nullable

Canonical `CapabilityRef` object:

1. `capabilityKey`
2. `capabilityVersion` optional on authoring/input, required after resolution
3. `capabilityType` nullable until resolution
4. `selectionSource` nullable until resolution
5. `effectiveApprovalMode` nullable until resolution
6. `effectiveConfig` nullable until resolution

`resolved_workflow_agent_refs` must preserve step-level workflow execution refs with at least:

1. `stepKey`
2. `agentSpecKey`
3. `agentSpecVersion`
4. `personaProfileRefs`
5. `capabilityRefs`

Each `capabilityRefs` entry must preserve canonical `CapabilityRef` objects.

`resolved_capabilities` must preserve the flattened effective run-level `CapabilityRef` set after workflow defaults, persona hints, and step selections are intersected.

Pinned-resolution rule:

1. `resolved_builtin_versions`, `resolved_role_versions`, `resolved_character_versions`, `resolved_bundle_versions`, `resolved_tool_versions`, and `resolved_connector_versions` are frozen at run creation.
2. `resolved_persona_profile_refs` and `resolved_workflow_agent_refs` are frozen at run creation.
3. `resolved_capabilities` is frozen at run creation.
4. Approval resume and later execution steps must reuse those frozen version sets instead of re-resolving from the latest registry state.

Capability precedence rule:

1. Workflow-level `default_tool_ids`, `allowed_capability_bundle_keys`, and `connector_ids` define the maximum default capability envelope for the run.
2. Step-level `capabilityRefs` select the subset used by that step.
3. Step-level refs may narrow workflow-level defaults, but may not widen workflow-level ceilings.
4. Persisted `resolved_capabilities` is the flattened run-level effective set after workflow defaults, persona hints, and step selections are intersected; external API surfaces may expose the same shape as `resolvedCapabilities`.

`approval_policy_overrides` must be a structured list with at least:

1. `stepKey`
2. `capabilityKey` nullable
3. `approvalMode`

Approval precedence rule:

1. Registry `approval_mode` defines the default requirement.
2. `approval_policy_overrides` may tighten approval at workflow-step or workflow-step-plus-capability scope.
3. Step-level capability refs persist the final `effectiveApprovalMode` after overrides are applied.
4. Overrides may tighten `not_required -> required`, but may not relax `required -> not_required`.

`resolved_mentions` must preserve ordered compatibility objects with at least:

1. `sourceHandle`
2. `canonicalTargetId`
3. `mentionOrder`
4. `personaProfileKey`
5. `personaProfileVersion`
6. `legacyRoleVersion` nullable
7. `legacyCharacterVersion` nullable

### Compatibility store

`backtest_orchestration_snapshots` remains available during migration as a compatibility mirror for backtest callers. It is not the long-term runtime store.

### `backtests` migration additions

Required migration-era fields on `backtests`:

1. `launch_mode` nullable during classification
2. `workflow_spec_key` nullable during migration
3. `workflow_spec_version` nullable during migration
4. `current_run_id` nullable during migration
5. `last_completed_run_id` nullable during migration
6. `launch_mode_classified_at` nullable during classification
7. `launch_mode_classified_by` nullable during classification
8. `launch_mode_classification_note` nullable during classification
9. `execution_owner` nullable during classification

Classification rule:

1. New rows created after the schema rollout must persist `launch_mode` directly from `BacktestCreate.launchMode`.
2. Existing rows are not auto-classified from `webhook_url` alone.
3. Rows with null `launch_mode` remain compatibility rows and are not eligible for runtime-backed internal execution.
4. Historical classification is one audited migration job that writes the classification fields above.
5. For classified internal rows using supported seeded patterns, the job also writes `workflow_spec_key` from the persisted `orchestration_pattern_key` and pins `workflow_spec_version=1`.
6. Historical rows whose pattern key cannot be mapped to a rollback-compatible seeded workflow remain on the current path and are not eligible for runtime-backed internal execution.
7. New or classified rows pin `execution_owner` to `legacy_path` or `runtime_v2`.
8. Once pinned, `execution_owner` remains fixed for the lifetime of that backtest.

Routing authority rule:

1. `launch_mode` is the compatibility transport class.
2. `execution_owner` is the pinned execution-path authority.

## Deterministic resolution rules

1. Registry keys are stable lowercase identifiers.
2. Capability resolution is a pure function of saved spec data plus registry state.
3. Duplicate bundle keys are deduplicated by key.
4. Duplicate tool or connector keys are deduplicated by key after bundle expansion.
5. Approval requirements inherit from the registry entry and may be tightened by workflow step rules, but never relaxed by persona profiles.
6. Persona profiles may contribute default capability hints, but they do not define executable steps.
7. Seeded workflow spec keys must match current supported pattern keys exactly during migration.
8. Seeded builtin profile handles must match current builtin handles exactly during migration.
9. Seeded workflow mention policies must preserve current builtin allowlists and character-allowance behavior during migration.

## API contract surface

### Spec APIs

1. `GET /api/v2/studio/agent-specs`
2. `POST /api/v2/studio/agent-specs`
3. `GET /api/v2/studio/agent-specs/{key}/versions`
4. `GET /api/v2/studio/agent-specs/{key}/versions/{version}`
5. `PATCH /api/v2/studio/agent-specs/{key}/versions/{version}`
6. `GET /api/v2/studio/workflow-specs`
7. `POST /api/v2/studio/workflow-specs`
8. `GET /api/v2/studio/workflow-specs/{key}/versions`
9. `GET /api/v2/studio/workflow-specs/{key}/versions/{version}`
10. `PATCH /api/v2/studio/workflow-specs/{key}/versions/{version}`
11. `GET /api/v2/studio/persona-profiles`
12. `POST /api/v2/studio/persona-profiles`
13. `GET /api/v2/studio/persona-profiles/{key}/versions`
14. `GET /api/v2/studio/persona-profiles/{key}/versions/{version}`
15. `PATCH /api/v2/studio/persona-profiles/{key}/versions/{version}`

Lifecycle transition actions use:

1. `POST /api/v2/studio/{resource}/{key}/drafts`
2. `POST /api/v2/studio/{resource}/{key}/versions/{version}/activate`
3. `POST /api/v2/studio/{resource}/{key}/versions/{version}/deprecate`
4. `POST /api/v2/studio/{resource}/{key}/versions/{version}/archive`

`{resource}` supports `agent-specs`, `workflow-specs`, `persona-profiles`, and `capabilities`.

Imported persona profiles are permanently read-only through Studio APIs; only the audited projection path may create new imported versions or archive them.

Lifecycle action rules:

1. `POST .../{key}/drafts` creates the next append-only `DRAFT` version from the latest version for that key and fails if a `DRAFT` already exists.
2. `activate` is valid only for a `DRAFT` version and atomically demotes the current `ACTIVE` version for that key to `DEPRECATED` before promoting the target to `ACTIVE`.
3. `deprecate` is valid only for the current `ACTIVE` version.
4. `archive` is valid for `DRAFT` or `DEPRECATED` versions, never for the current `ACTIVE` version.
5. Generic lifecycle routes reject `origin=imported`; imported versions are created, advanced, or archived only by the audited projection path.

### Capability APIs

1. `GET /api/v2/studio/capabilities`
2. `GET /api/v2/studio/capabilities/{key}/versions/{version}`
3. `POST /api/v2/studio/capabilities` for `origin=managed` only
4. `PATCH /api/v2/studio/capabilities/{key}/versions/{version}` for `origin=managed` only

### Runtime APIs

1. `POST /api/v2/runtime/runs`
2. `GET /api/v2/runtime/runs`
3. `GET /api/v2/runtime/runs/{runId}`
4. `GET /api/v2/runtime/runs/{runId}/trace`
5. `POST /api/v2/runtime/runs/{runId}/cancel`
6. `POST /api/v2/runtime/approvals/{approvalId}/approve`
7. `POST /api/v2/runtime/approvals/{approvalId}/deny`
8. `GET /api/v2/runtime/runs/{runId}/artifacts`
9. `GET /api/v2/runtime/approvals/{approvalId}`

`GET /api/v2/runtime/runs` must support filters for `callerType`, `callerId`, `callerScopeKey`, and `callerIdentityKey`.

Minimum `GET /api/v2/runtime/runs/{runId}` response fields:

1. `runId`
2. `status`
3. `callerType`
4. `callerId`
5. `callerScopeKey`
6. `attemptNumber`
7. `pendingApprovalIds`
8. `expiresAt` nullable
9. `finalOutput` nullable
10. `terminalError` nullable

Minimum `GET /api/v2/runtime/approvals/{approvalId}` response fields:

1. `approvalId`
2. `status`
3. `capabilityKey`
4. `stepKey`
5. `summary`
6. `allowedActions`

Executor adapter contract:

1. `AgentRuntimeService` must invoke an execution adapter selected by caller type and workflow shape.
2. `BacktestLangGraphExecutionAdapter` is the v2 adapter that translates a runtime-owned backtest run into the current `BacktestLangGraphRequest` contract.
3. Tryout and Studio must use a non-backtest adapter contract rather than inventing backtest-only ids or prompt-report fields.
4. If a non-backtest caller supplies `callerIdentityKey`, create must reject a new run with HTTP 409 when caller policy forbids another active run for the same `(callerType, callerIdentityKey)`.

Minimum `ExecutionAdapterRequest` fields:

1. `runId`
2. `executionKind`
3. `workflowSpecKey` nullable when `executionKind=single_agent`
4. `workflowSpecVersion` nullable when `executionKind=single_agent`
5. `agentSpecKey` nullable when `executionKind=workflow`
6. `agentSpecVersion` nullable when `executionKind=workflow`
7. `inputPayload`
8. `personaProfileRefs`
9. `resolvedCapabilities`
10. `callerContext`
11. `callerArtifacts`

`resolvedCapabilities` must be a typed list with at least:

1. `capabilityKey`
2. `capabilityVersion`
3. `capabilityType`
4. `approvalMode`
5. `transport` nullable unless connector
6. `lifecycle` nullable unless connector
7. `effectiveConfig`

Minimum `ExecutionAdapterResult` fields:

1. `status`
2. `finalOutput`
3. `traceEvents`
4. `approvalEvents`
5. `artifacts`
6. `callerArtifacts`

### Tryout API

1. `POST /api/v2/tryouts/execute`
2. `GET /api/v2/tryouts/{runId}`
3. `POST /api/v2/tryouts/{runId}/persist`
4. `DELETE /api/v2/tryouts/{runId}`

Required request fields:

1. `workflowSpecKey` or `agentSpecKey`
2. `workflowSpecVersion` or `agentSpecVersion` optional
3. `inputs`
4. `personaProfileRefs` optional, using canonical `PersonaProfileRef` objects with `personaProfileKey` and optional `personaProfileVersion`
5. `persistRun` default `false`

Required response fields:

1. `runId`
2. `status`
3. `finalOutput`
4. `reportMarkdown` nullable
5. `traceSummary`
6. `approvalSummary`
7. `expiresAt` when `persistRun=false`

Tryout persistence rules:

1. `persist` is idempotent.
2. `persist` preserves the same `runId` and clears `expiresAt`.
3. `persist` is allowed from terminal states and from `WAITING_APPROVAL`.
4. If an ephemeral tryout expires while still active or waiting approval, runtime must append an expiration trace event, mark pending approvals `EXPIRED`, transition the run to `CANCELLED`, and then delete ephemeral artifacts on schedule.
5. `DELETE /api/v2/tryouts/{runId}` must cancel any active ephemeral run, expire pending approvals, and remove ephemeral artifacts.

## Runtime state machine

Run transitions:

1. `QUEUED -> RUNNING`
2. `RUNNING -> WAITING_APPROVAL`
3. `WAITING_APPROVAL -> RUNNING`
4. `RUNNING -> SUCCEEDED`
5. `RUNNING -> FAILED`
6. `QUEUED | RUNNING | WAITING_APPROVAL -> CANCELLED`

Approval transitions:

1. `PENDING -> APPROVED`
2. `PENDING -> DENIED`
3. `PENDING -> EXPIRED`

Approval pause/resume rule:

1. Transition to `WAITING_APPROVAL` is valid only after a checkpoint row is persisted.
2. Approve or deny endpoints must load the latest checkpoint, update the approval row, append a trace event, and resume or fail the same run.
3. `DENIED` resumes the run only when the current step defines an `approval_denied` edge.
4. `DENIED` without an `approval_denied` edge transitions the run to `FAILED`.
5. Explicit cancel from `WAITING_APPROVAL` transitions the run to `CANCELLED`.

## Backtest integration rules

### Breaking target contract

During migration, `BacktestCreate` accepts both:

1. `orchestrationPatternKey` as the v1 compatibility field
2. `workflowSpecKey` plus optional `workflowSpecVersion` as the v2 field
3. `launchMode`

Canonicalization rule:

1. If only `orchestrationPatternKey` is provided, service must map it to the identical seeded workflow spec key.
2. If only `workflowSpecKey` is provided, it must be a rollback-compatible seeded workflow key and service must persist a reversible compatibility mapping to the current pattern-key field until the rollback window closes.
3. If both are provided, they must resolve to the same seeded workflow key or validation fails.
4. `workflowSpecVersion` must be resolved and pinned at backtest creation time; all cycles in that backtest reuse the pinned version.
5. If `launchMode=legacy_callback`, `workflowSpecKey` and `workflowSpecVersion` must be omitted or validation fails.
6. During the rollback window, a rollback-compatible seeded internal backtest that omits `workflowSpecVersion` must pin `workflowSpecVersion=1` even if a newer seeded version is `ACTIVE`.
7. If both selector families are omitted, compatibility defaulting resolves `orchestrationPatternKey="seeded_internal_backtest_v1"`; internal runtime-backed creation maps that default to `workflowSpecKey="seeded_internal_backtest_v1"` and pins `workflowSpecVersion=1` during the rollback window.

Webhook compatibility rule during mixed mode:

1. Existing `webhookUrl` and `webhookTimeout` request/read fields remain part of the backtest compatibility surface during the rollback window.
2. For `launchMode=internal`, omitted values continue to materialize/read as `webhookUrl="internal://ledger"` and `webhookTimeout=600` during the rollback window.
3. For `launchMode=internal`, supplied values do not influence runtime routing and must round-trip unchanged as compatibility metadata.
4. For `launchMode=legacy_callback`, current webhook validation and callback delivery behavior remain authoritative.

Retained legacy callback route contract:

1. `POST /api/v1/backtests/{backtestId}/cycles/{cycleDate}/report` accepts `CycleReportUpload` with `name`, `content`, and `tags`, and returns the created report slug.
2. `POST /api/v1/backtests/{backtestId}/cycles/{cycleDate}/trades` accepts `CycleTradesRequest` with `decisions` and optional `reportSlug`, and returns trade execution results.
3. `POST /api/v1/backtests/{backtestId}/cycles/{cycleDate}/complete` returns completion status, cycle counts, and next-cycle metadata.
4. These routes remain compatibility ingress throughout the rollback window and are not the default browser-driven launch path.

`BacktestRead` adds:

1. `currentRunId` nullable during migration
2. `lastCompletedRunId` nullable
3. `workflowSpecKey` nullable during migration
4. `workflowSpecVersion` nullable during migration
5. `launchMode` nullable during classification
6. `launchModeClassifiedAt` nullable during classification
7. `launchModeClassifiedBy` nullable during classification
8. `executionOwner` nullable during classification

Existing `webhookUrl` and `webhookTimeout` fields remain on the compatibility read surface during the rollback window.

Run-id lifecycle rules:

1. Creating a cycle run sets `currentRunId` to that active run id.
2. Retrying the same cycle replaces `currentRunId` with the new attempt run id.
3. When a cycle run reaches `SUCCEEDED | FAILED | CANCELLED`, `lastCompletedRunId` is updated to that terminal run id.
4. `currentRunId` is cleared after a terminal run unless the next cycle run has already been created.

Backtest compatibility state mapping:

1. For `launchMode=internal`, runtime `QUEUED | RUNNING` -> `BacktestRead.status=RUNNING`, `currentCycleStatus=RUNNING`.
2. For `launchMode=internal`, runtime `WAITING_APPROVAL` -> `BacktestRead.status=RUNNING`, `currentCycleStatus=WAITING_APPROVAL`.
3. For `launchMode=internal`, runtime cycle success on a non-terminal cycle -> `BacktestRead.status=RUNNING`, `currentCycleStatus=COMPLETED` until the next cycle begins.
4. For `launchMode=internal`, runtime cycle success on the final cycle -> `BacktestRead.status=COMPLETED`, `currentCycleStatus=COMPLETED`.
5. For `launchMode=internal`, runtime `FAILED` -> `BacktestRead.status=FAILED`, `currentCycleStatus=FAILED`.
6. For `launchMode=internal`, runtime `CANCELLED` -> `BacktestRead.status=CANCELLED`, `currentCycleStatus=CANCELLED`.
7. For `launchMode=legacy_callback`, preserve current callback-era `status` semantics.
8. For `launchMode=legacy_callback`, preserve current callback-era `currentCycleStatus` semantics including `AWAITING_CALLBACK` and `PROCESSING_CALLBACK`.
9. For `launchMode=null`, preserve current compatibility-path read semantics until explicit classification occurs.
10. `executionOwner` is the pinned execution-path source of truth for that backtest once classification or create-time routing completes.

`POST /api/v1/backtests/{id}/cancel` must cancel a run in `QUEUED | RUNNING | WAITING_APPROVAL`.

Backtest approval discovery rule:

1. When `currentCycleStatus=WAITING_APPROVAL`, `currentRunId` must be non-null.
2. Runtime run read must expose `pendingApprovalIds` for that run.
3. Backtest detail uses those ids to load approval reads and render actions.

Backtest post-resume completion rule:

1. When an approval resolves a backtest-owned runtime run to success, `BacktestRuntimeAdapter.completeCycle(...)` must store the cycle report, apply trade decisions, update `_run_state`, update `currentRunId` / `lastCompletedRunId`, and advance or finalize the schedule.
2. This completion hook is required for both first-pass success and approval-resumed success.

### Runtime handoff contract

Backtest adapter must submit:

1. `callerType=backtest`
2. `callerId=backtest.id`
3. `workflowSpecKey` and optional version
4. `callerScopeKey=cycleDate.isoformat()`
5. `attemptNumber`
6. cycle context refs including `portfolioId`, `cycleDate`, `benchmarkSymbols`, and prompt/report context

Runtime must return:

1. `runId`
2. `status`
3. `reportMarkdown`
4. `normalizedTradeDecisions`
5. `finalOutput` structured according to `workflow_specs.final_output_contract`
6. `traceSummary`
7. `approvalSummary`

Backtest-side services remain responsible for storing reports, applying trades, and preserving current read semantics such as `_run_state` redaction.

## Roles, characters, and mention compatibility rules

1. Existing `/api/v1/orchestration/*` APIs remain available during migration.
2. `/api/v1/orchestration/*` remains the write authority for imported role and character personas during migration.
3. Legacy orchestration writes must project into `persona_profiles`.
4. Studio can read imported personas but must not edit them; imported personas remain permanent historical projections.
5. Existing role rows migrate into `persona_profiles.kind=role_template`.
6. Existing character rows migrate into `persona_profiles.kind=character_profile`.
7. Existing builtin handles migrate into `persona_profiles.kind=builtin_profile`.
8. Current `@handle` mention authoring remains accepted only in compatibility paths.
9. New Studio-authored workflow specs must store explicit persona-profile refs rather than raw `@handle` mentions.
10. Runtime must not parse raw mention handles as its canonical contract after cutover.

Legacy mention catalog compatibility rule:

1. `GET /api/v1/orchestration/mentions/catalog` remains the compatibility read contract during migration.
2. It continues to return seeded builtin targets plus imported characters that are enabled and whose imported parent roles are enabled.
3. Managed personas do not appear in this legacy catalog.
4. Legacy response shape and canonical target ids remain frozen throughout the rollback window.

Legacy orchestration validation parity rules:

1. Legacy role delete rejection when characters still reference the role remains authoritative during migration.
2. Legacy disabled-role rejection on character create or update remains authoritative during migration.
3. Legacy reserved builtin handle rejection remains authoritative during migration.

Builtin and mention-policy migration rules:

1. Seeded builtins `librarian` and `explore` must preserve their handles and bundle refs exactly during migration.
2. Seeded workflow specs must preserve current mention-policy behavior, including allowed builtin handles and whether character-style persona refs are allowed.
3. Imported personas preserve upstream legacy role or character version in `legacy_source_version` while persona `version` remains the append-only projection version.
4. Deleting a legacy role or character archives the imported persona version rather than hard-deleting it during the rollback window.

Handle namespace rule:

1. Mentionable handles are globally unique across imported, seeded, and managed personas.
2. Seeded builtin handles are reserved and may not be reused.
3. Null handles are allowed only for non-mentionable personas.

## Migration rules

### Phase 0: schema and seeded data

1. Add runtime/spec/profile/registry tables through the existing code-based upgrade path.
2. Materialize seeded immutable agent specs, workflow specs, and capability entries from current seeds.
3. Add audited write-through projection from legacy orchestration writes into imported persona profiles.
4. Add read-only Studio listing endpoints.
5. Materialize imported persona profiles from current roles and characters.
6. Materialize seeded builtin persona profiles from builtin seeds.
7. Add explicit compatibility projections from runtime artifacts into `backtest_orchestration_snapshots`.

### Phase 1: Studio and tryout

1. Ship Studio authoring and inspection.
2. Ship tryout execution.
3. Leave backtests on the current path.
4. Retain ephemeral tryouts for 24 hours by default; `persist` converts them into normal runtime runs.
5. Studio may author managed personas in this phase, but imported personas remain permanently read-only historical projections.

### Phase 2: backtest cutover

1. Add `AGENT_RUNTIME_V2_BACKTESTS_ENABLED` feature flag.
2. When false, current backtest execution remains authoritative.
3. When true, only `launchMode=internal` backtests submit runtime requests.
4. `launchMode=legacy_callback` remains on the retained legacy callback compatibility ingress throughout the rollback window.
5. During this phase, `backtest_orchestration_snapshots` mirrors runtime trace summary for compatibility.
6. During this phase, backtest rows must preserve reversible `orchestrationPatternKey` compatibility.
7. During this phase, backtests may reference only seeded workflow specs whose keys exactly match the current supported pattern keys.
8. During this phase, backtest runs must use the pinned workflow version resolved at create time.
9. During this phase, runtime compatibility mirror writes must overwrite the existing snapshot row for the same `(backtest_id, cycle_date)` with the latest attempt projection.
10. Existing rows must be explicitly classified before mixed-mode cutover; `webhook_url` alone is not a safe classifier.
11. Rows that remain unclassified stay on the current path until explicitly migrated or recreated.
12. The latest-attempt mirror policy must be implemented as an update/upsert of the existing unique cycle row.
13. The audited classification job must be exercised in migration tests and audited in the DB upgrade path.
14. Existing or newly created backtests pin `execution_owner`, and enabling the runtime flag applies only to backtests pinned to `runtime_v2` after the flag state is observed.

### Phase 3: cleanup

1. Remove raw mention-based execution semantics from runtime.
2. Deprecate backtest-owned execution internals after rollback window closes.
3. Remove `orchestrationPatternKey` from the public create contract only after rollback window closes and all reversible mappings are no longer required.

## Rollback rules

1. Rollback flips `AGENT_RUNTIME_V2_BACKTESTS_ENABLED` to false.
2. Existing runtime tables remain intact and readable.
3. New or still-unclassified backtests resume the current execution path after rollback.
4. Reversible mapping from `workflowSpecKey` to current pattern-key contract must remain available throughout the rollback window.
5. No destructive table removal or irreversible backfill is allowed before the rollback window closes.
6. Because rollback is blocked until active runtime-backed runs drain or cancel, rollback does not re-home an in-flight `runtime_v2` backtest.

Rollback precondition:

1. Default policy blocks rollback while runtime-backed backtest runs exist in `QUEUED`, `RUNNING`, or `WAITING_APPROVAL`.
2. Operators must cancel or let those runs drain before the flag is flipped.

Rollback guard enforcement:

1. The backtest runtime flag may be changed only through one audited operational control path.
2. That control path must query for active runtime-backed backtest runs before applying the flag change.
3. If any such runs exist, the control path exits non-zero and the flag change is rejected.

## Failure semantics

1. Unknown workflow spec, agent spec, persona profile, or capability key fails before execution starts.
2. Approval denial fails the pending step and the run unless the workflow explicitly defines a recoverable branch.
3. Tryout with `persistRun=false` must still expose trace and approval data until TTL expiry.
4. Backtest adapter failures must preserve current `FAILED` behavior and error-message reporting.
5. Resuming a run without a valid checkpoint must fail closed.
6. Expired ephemeral tryouts must emit `RUN_EXPIRED` and mark pending approvals `EXPIRED` before cleanup.

## Runtime-to-snapshot projection rules

When `callerType=backtest` and `workflowSpecKey` is a rollback-compatible seeded workflow key, runtime compatibility projection must populate current snapshot fields as follows:

Initial projection writes prompt-hash and resolved-mention fields after run creation. Terminal projection updates the same unique cycle row after completion or failure with final trace and approval data.

1. `runtime_run_artifacts.prompt_report_slug` -> `backtest_orchestration_snapshots.prompt_report_slug`
2. `workflowSpecKey` -> `backtest_orchestration_snapshots.orchestration_pattern_key`
3. `workflow_specs.mention_policy.version` -> `backtest_orchestration_snapshots.pattern_policy_version`
4. `runtime_run_artifacts.entry_prompt_hash` -> `backtest_orchestration_snapshots.entry_prompt_hash`
5. `runtime_run_artifacts.full_user_prompt_hash` -> `backtest_orchestration_snapshots.full_user_prompt_hash`
6. runtime execution mode -> `backtest_orchestration_snapshots.execution_mode`
7. `runtime_run_artifacts.resolved_builtin_versions` -> `backtest_orchestration_snapshots.resolved_builtin_versions`
8. `runtime_run_artifacts.resolved_role_versions` -> `backtest_orchestration_snapshots.resolved_role_versions`
9. `runtime_run_artifacts.resolved_character_versions` -> `backtest_orchestration_snapshots.resolved_character_versions`
10. `runtime_run_artifacts.resolved_bundle_versions` -> `backtest_orchestration_snapshots.resolved_bundle_versions`
11. `runtime_run_artifacts.resolved_tool_versions` -> `backtest_orchestration_snapshots.resolved_tool_versions`
12. `runtime_run_artifacts.resolved_connector_versions` -> `backtest_orchestration_snapshots.resolved_connector_versions`
13. `runtime_run_artifacts.mentioned_target_outputs` -> `backtest_orchestration_snapshots.mentioned_target_outputs`
14. `runtime_run_artifacts.resolved_mentions` -> `backtest_orchestration_snapshots.resolved_mentions`
15. runtime trace projection -> `backtest_orchestration_snapshots.tool_call_trace`
16. runtime approval projection -> `backtest_orchestration_snapshots.approval_trace`

## Acceptance criteria

1. A runtime run can be created, traced, approved, and inspected without a backtest row.
2. Current seeded pattern keys have a documented and tested 1:1 mapping to seeded workflow specs.
3. A backtest can invoke the runtime and still preserve current report, trade, and `_run_state`-redaction behavior.
4. Raw `@handle` execution is no longer the canonical runtime contract after cutover.
5. Rollback from runtime-backed backtests to current backtest execution is provably reversible during the rollback window.
6. Template-driven backtests preserve current prompt/report compilation semantics through explicit runtime artifacts and compatibility projection.

## Test mapping

### Current parity coverage that must stay green

1. `backend/tests/test_orchestration_api.py` for role/character compatibility and catalog behavior.
2. `backend/tests/test_backtests_api.py` for callback-aware statuses, read compatibility, and `_run_state` redaction.
3. `backend/tests/test_backtest_cycle_service.py` for baseline execution behavior, mention policy, deterministic capability resolution, and approval behavior.
4. `backend/tests/test_backtest_orchestration_snapshot.py` for snapshot compatibility and upgrade behavior.
5. `backend/tests/test_langgraph_runner.py` and `backend/tests/test_langgraph_seeds.py` for runner and seeded-registry behavior.
6. Upgrade-path tests in the code-based DB upgrade suite for seeded-spec materialization and persona-profile imports.

### New v2 coverage required

1. Agent-spec CRUD and version lifecycle tests.
2. Workflow-spec CRUD, graph validation, and seeded pattern mapping tests.
3. Persona-profile migration and compatibility-compiler tests.
4. Capability-registry seeded-vs-managed tests.
5. Runtime run state-machine tests.
6. Approval-request, approve, deny, and expiry tests.
7. Tryout ephemerality and explicit-save tests.
8. Snapshot-to-runtime-trace equivalence tests during migration.
9. Backtest cutover tests with feature flag on and off.
10. Rollback tests that prove the current path still works after reverting the flag.
11. Code-based upgrade tests for seeded spec reseeding, idempotent migrations, and mixed v1/v2 data.
12. Backtest `WAITING_APPROVAL` polling and cancel tests.
13. Per-cycle run uniqueness, lookup, and rerun-attempt tests.
14. Template compile to persona-ref compatibility pipeline tests.
15. Tryout TTL expiry and persist-idempotency tests.
16. Snapshot latest-attempt overwrite policy tests.
17. Workflow-version pinning and rollback-window seeded-version restriction tests.
18. Approval discovery read-contract tests for backtest detail.
19. Seeded workflow parity tests for `execution_mode`, `default_tool_ids`, `connector_ids`, and topology order.
20. `launchMode` classification and mixed-mode read-contract tests.
21. Approval-resumed backtest completion-hook tests.
22. Imported persona archive-on-delete tests.
23. Seeded workflow parity tests for current `allowed_bundle_keys` -> v2 `allowed_capability_bundle_keys` mapping and conservative `review_mode`.
24. Historical-row classification tests proving `webhook_url` alone does not determine `launchMode`.
25. Non-backtest executor-adapter contract tests.
26. Connector transport/lifecycle registry tests.
27. Nullable historical `launchMode` read-contract tests.
28. Snapshot projector update/upsert tests for existing unique cycle rows.
29. Concurrent non-backtest run tests covering nullable caller ids and `caller_identity_key` policies.
30. Approval-resume tests proving pinned persona/capability versions do not drift after run creation.
31. Workflow step agent-version pinning tests.
32. Explicit persona-ref shape and version reuse tests.
33. Typed capability handoff tests for `resolvedCapabilities`.
34. Historical internal backfill tests for `workflow_spec_key` and pinned `workflow_spec_version=1`.
35. Workflow graph edge and terminal-behavior tests.
36. Step-level capability precedence tests.
37. Approval override precedence tests for registry default vs workflow override vs step effective mode.
38. Rollback guard tests proving flag flip is blocked while runtime-backed backtest runs remain active.
39. Version lifecycle tests for append-only non-`DRAFT` versions and single-`ACTIVE` resolution.
40. Imported persona lineage tests covering versioned parent linkage and role reassignment.
41. Mixed-mode webhook compatibility tests for internal vs legacy-callback backtests.
42. Approval-denied edge vs fail-run state transition tests.
43. Execution-owner pinning tests proving flag flips do not re-home in-flight backtests.
44. Global mentionable-handle uniqueness and reserved-builtin-handle tests.
45. Imported enabled-parity tests for disabled roles, disabled characters, and mention catalog eligibility.
46. Omitted-selector compatibility-default tests for `seeded_internal_backtest_v1`.
47. Imported projection ordering tests for role update before dependent character reprojection.
48. Legacy callback route-contract tests for `/report`, `/trades`, and `/complete` compatibility ingress.
49. Legacy orchestration validation parity tests for role-in-use delete rejection, disabled-role character writes, and reserved handle rejection.
50. Persisted `final_output` and terminal-error reload tests for runtime run and artifact reads.
51. Legacy mention-catalog contract parity tests during migration.
