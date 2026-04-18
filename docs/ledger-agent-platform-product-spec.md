# Ledger Agent Platform v2 Technical Spec

## Metadata

Status: Draft
Supersedes: previous contents of `docs/ledger-agent-platform-product-spec.md`
References: `docs/ledger-orchestration-product-spec.md`, `docs/ledger-orchestration-product-prd.md`, `docs/ledger-orchestration-product-design.md`, `docs/orchestration-demo-runbook.md`, `backend/app/services/orchestration_service.py`, `backend/app/services/workflow_spec_service.py`, `backend/app/services/agent_runtime_service.py`, `backend/app/services/runtime_seed_catalog.py`, `backend/app/services/runtime_seed_bootstrap.py`, `backend/app/db/upgrades.py`, `backend/app/schemas/runtime.py`, `backend/app/schemas/orchestration.py`
Source of truth notes: this spec defines the implementation-ready v2 target. When current code and this target disagree, current code still defines shipped behavior until cutover gates are passed.

## Scope

This spec defines the BC-breaking v2 contract for runtime-owned execution, versioned agent and workflow specs, persona profiles, capability registry, tryout, Studio, approval lifecycle, trace lifecycle, and simulation integration.

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

`simulation | tryout | studio | api`

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

### Simulation compatibility cycle status

`RUNNING | WAITING_APPROVAL | COMPLETED | FAILED | CANCELLED`

### Simulation execution owner

`legacy_path | runtime_v2`

## Baseline and adjacent-code truth

### Shipped baseline

1. Simulations own execution through `SimulationService`, `SimulationCycleService`, and `SimulationEngine`.
2. Orchestration roles and characters are prompt/config and mention surfaces.
3. `SimulationRead` still exposes `orchestrationPatternKey`, callback-aware statuses, and `_run_state` redaction semantics.
4. `simulation_orchestration_snapshots` is the cycle-level orchestration audit store.

### Already-present v2-adjacent code

1. Four supported pattern keys already exist, including tool-enabled variants.
2. Seeded tools, bundles, connectors, and revision metadata already exist in `seeds.py`.
3. Role and character `capabilityBundleKeys` already exist and already affect runtime resolution.
4. Snapshot records already persist execution mode, resolved versions, tool traces, and approval traces.

These four facts are migration inputs, not future ideas.

## Required v2 invariants

1. Runtime, not simulations, owns execution state.
2. Agent specs and workflow specs are versioned and validated before execution.
3. Capability resolution is deterministic and backend-owned.
4. Approval state is explicit, queryable, and persisted.
5. Tryout defaults to ephemeral execution.
6. Studio is a client of the runtime, not a second engine.
7. Simulations invoke one runtime run per cycle.

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
9. `final_output_contract` nullable when the agent cannot run as `execution_kind=single_agent`
10. `default_capability_bundle_keys`
11. `default_persona_profile_keys`
12. `created_at`
13. `updated_at`

Seeded current agents (`position_analyst`, `risk_reviewer`, `decision_writer`) must appear as immutable `origin=seeded` records.

`agent_specs.final_output_contract` follows the same shape rules as workflow final output contracts.

Single-agent rule:

1. A run with `executionKind=single_agent` requires the selected agent spec to have a non-null `final_output_contract`.
2. If an agent spec has null `final_output_contract`, it may be used only as a workflow step agent, not as a direct single-agent run target.

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
11. `execution_mode` nullable; required only for historical-compatibility seeded workflows
12. `default_tool_ids`
13. `allowed_capability_bundle_keys`
14. `connector_ids`
15. `review_mode` nullable; required only for historical-compatibility seeded workflows
16. `approval_policy_overrides`
17. `created_at`
18. `updated_at`

Current supported pattern keys must migrate 1:1 into seeded immutable workflow specs:

1. `seeded_internal_simulation_v1`
2. `seeded_internal_simulation_tool_enabled_v1`

`final_output_contract` must be a structured object with at least:

1. `kind` (`json_schema | markdown | text`)
2. `schema` nullable unless `kind=json_schema`
3. `description`

`mention_policy` must be a structured object with at least:

1. `version`
2. `allowCharacterPersonas`
3. `allowedBuiltinHandles`

During migration, seeded workflow `mention_policy` rows must mirror the live `PatternMentionPolicy(version, allow_characters, allowed_builtin_handles)` semantics exactly.

`graph_definition` must explicitly encode topology order. For seeded simulation mirrors, it must preserve the current seeded topology `agent_order` exactly.

`execution_mode`, `default_tool_ids`, `allowed_capability_bundle_keys` (mirroring current `allowed_bundle_keys`), `connector_ids`, and `review_mode` must preserve the current `SimulationPatternSpec` and `SeededTopology` values exactly for seeded workflow mirrors.

For historical-compatibility seeded workflows, `execution_mode` currently supports `structured_output | tool_enabled` and remains seeded-compatibility metadata.

For v2-native workflows, `execution_mode` must be null and execution behavior is derived from `graph_definition` plus the frozen step plan.

For historical-compatibility seeded workflows, `review_mode` remains seeded-compatibility metadata and a semantic input to the seeded execution adapter until the historical migration phase closes.

For v2-native workflows, `review_mode` must be null and equivalent reviewer behavior must be expressed only through `graph_definition`.

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
2. Historical-migration simulations may reference only seeded workflow rows pinned to that version.

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

1. Deleting a legacy role or character archives the imported persona profile version during the historical migration phase.
2. Archived imported personas remain resolvable for pinned historical runs and traces, but cannot be attached to new workflow specs.

### `persona_projection_events`

Required fields:

1. `id`
2. `persona_profile_key`
3. `persona_profile_version`
4. `legacy_entity_type` (`role | character`)
5. `legacy_entity_key`
6. `legacy_source_version`
7. `operation` (`create | reproject | deprecate | archive`)
8. `actor`
9. `note` nullable
10. `created_at`

Projection audit rule:

1. Every imported-persona create, reproject, deprecate, or archive operation writes one `persona_projection_events` row in the same transaction as the persona version change.
2. This audit record is the source of truth for imported-persona projection provenance.

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

Connector lifecycle semantics:

1. Connector lifecycle currently supports `placeholder | approved`.
2. `placeholder` means the connector remains listed and reviewable but is not granted for execution when selected.
3. `approved` means the connector is granted for execution when selected, subject to the normal approval contract.

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
9. `caller_scope_key` nullable; for simulations this must be `cycle_date.isoformat()`
10. `caller_identity_key` nullable; required only when a non-simulation caller uses caller-scoped concurrency or listing
11. `attempt_number`
12. `status`
13. `input_hash`
14. `output_hash` nullable
15. `retention_class` (`ephemeral | persistent`)
16. `expires_at` nullable
17. `trace_summary`
18. `approval_summary`
19. `created_at`
20. `updated_at`

Required uniqueness rules:

1. `caller_type=simulation` requires `caller_id`, `caller_scope_key`, and `attempt_number`.
2. `(caller_type, caller_id, caller_scope_key, attempt_number)` must be unique.
3. At most one run in `QUEUED | RUNNING | WAITING_APPROVAL` may exist for a given simulation `(caller_type, caller_id, caller_scope_key)`.
4. Retrying or rerunning the same simulation cycle must create a new run with `attempt_number + 1`; prior attempts remain immutable.
5. Non-simulation callers may have multiple concurrent active runs unless a caller-specific policy uses `caller_identity_key` to restrict them.

Canonical `TraceSummary` object:

1. `eventCount`
2. `toolCallCount`
3. `warningCount`
4. `lastEventAt` nullable

Canonical `ApprovalSummary` object:

1. `totalCount`
2. `pendingCount`
3. `approvedCount`
4. `deniedCount`
5. `expiredCount`

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
6. `actor` nullable while status is `PENDING | EXPIRED`
7. `reason` nullable while status is `PENDING`
8. `resolved_at` nullable
9. `created_at`

Approval row status rules:

1. `PENDING` rows store `actor=null` and `reason=null`.
2. `APPROVED` and `DENIED` rows require both `actor` and `reason`.
3. `EXPIRED` rows store `actor=null` and require a system-generated `reason`.

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

1. `normalized_trade_decisions` is required only for simulation callers.
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

Native resolved-version shapes:

1. `resolved_builtin_versions` entries use `canonical_target_id`, `handle`, `revision`.
2. `resolved_role_versions` entries use `canonical_target_id`, `role_id`, `version`.
3. `resolved_character_versions` entries use `canonical_target_id`, `character_id`, `version`.
4. `resolved_bundle_versions` entries use `bundle_key`, `revision`.
5. `resolved_tool_versions` entries use `tool_id`, `revision`.
6. `resolved_connector_versions` entries use `connector_id`, `revision`.

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

1. `originalText`
2. `sourceHandle`
3. `canonicalTargetId`
4. `targetType`
5. `mentionOrder`
6. `personaProfileKey`
7. `personaProfileVersion`
8. `legacyRoleId` nullable
9. `legacyRoleVersion` nullable
10. `legacyCharacterId` nullable
11. `legacyCharacterVersion` nullable

Legacy snapshot compatibility rule:

1. `runtime_run_artifacts.resolved_mentions` is a native v2 artifact and is not the same object as snapshot `resolved_mentions`.
2. The rollback-window snapshot mirror must project into the current legacy snapshot shape, not reuse the native artifact object shape directly.
3. That projection uses native `originalText`, `sourceHandle`, `canonicalTargetId`, `targetType`, `legacyRoleId`, `legacyRoleVersion`, `legacyCharacterId`, `legacyCharacterVersion`, and `mentionOrder` to synthesize the legacy snapshot row shape without inference.

Snapshot `resolved_mentions` compatibility shape:

1. `original_text`
2. `handle`
3. `canonical_target_id`
4. `target_type`
5. `role_id` nullable
6. `role_version` nullable
7. `character_id` nullable
8. `character_version` nullable
9. `mention_order`

Snapshot version-entry compatibility shapes:

1. `resolved_builtin_versions` entries use `canonical_target_id`, `handle`, `revision`.
2. `resolved_role_versions` entries use `canonical_target_id`, `role_id`, `version`.
3. `resolved_character_versions` entries use `canonical_target_id`, `character_id`, `version`.
4. `resolved_bundle_versions` entries use `bundle_key`, `revision`.
5. `resolved_tool_versions` entries use `tool_id`, `revision`.
6. `resolved_connector_versions` entries use `connector_id`, `revision`.

### Compatibility store

`simulation_orchestration_snapshots` remains available during migration as a compatibility mirror for simulation callers. It is not the long-term runtime store.

### `simulations` migration additions

Required migration-era fields on `simulations`:

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

1. New rows created after the schema rollout must persist `launch_mode` directly from `SimulationCreate.launchMode`.
2. Existing rows are not auto-classified from `webhook_url` alone.
3. Rows with null `launch_mode` remain compatibility rows and are not eligible for runtime-backed internal execution.
4. Historical classification is one audited migration job that consumes an operator-reviewed manifest keyed by `simulation_id`.
5. That manifest is the authoritative classification source for `launch_mode` and `execution_owner`.
6. For classified internal rows using supported seeded patterns, the job also writes `workflow_spec_key` from the persisted `orchestration_pattern_key` and pins `workflow_spec_version=1`.
7. Historical rows whose pattern key cannot be mapped to a historical-compatibility seeded workflow remain on the current path and are not eligible for runtime-backed internal execution.
8. New or classified rows pin `execution_owner` to `legacy_path` or `runtime_v2`.
9. Once pinned, `execution_owner` remains fixed for the lifetime of that simulation.

Routing authority rule:

1. `launch_mode` is the compatibility transport class.
2. `execution_owner` is the pinned execution-path authority.

Create-time routing matrix:

1. `launchMode=legacy_callback` pins `execution_owner=legacy_path`.
2. `launchMode=internal` with `historical simulation cutover flag=false` pins `execution_owner=legacy_path`.
3. `launchMode=internal` with `historical simulation cutover flag=true` pins `execution_owner=runtime_v2` only when the selected or defaulted workflow resolves to a historical-compatibility seeded workflow.
4. Otherwise `launchMode=internal` pins `execution_owner=legacy_path` during the historical migration phase.

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
2. `POST /api/v2/studio/agent-specs` for `origin=managed` only
3. `GET /api/v2/studio/agent-specs/{key}/versions`
4. `GET /api/v2/studio/agent-specs/{key}/versions/{version}`
5. `PATCH /api/v2/studio/agent-specs/{key}/versions/{version}`
6. `GET /api/v2/studio/workflow-specs`
7. `POST /api/v2/studio/workflow-specs` for `origin=managed` only
8. `GET /api/v2/studio/workflow-specs/{key}/versions`
9. `GET /api/v2/studio/workflow-specs/{key}/versions/{version}`
10. `PATCH /api/v2/studio/workflow-specs/{key}/versions/{version}`
11. `GET /api/v2/studio/persona-profiles`
12. `POST /api/v2/studio/persona-profiles` for `origin=managed` only
13. `GET /api/v2/studio/persona-profiles/{key}/versions`
14. `GET /api/v2/studio/persona-profiles/{key}/versions/{version}`
15. `PATCH /api/v2/studio/persona-profiles/{key}/versions/{version}`

Version-history list response contract:

1. `GET .../{key}/versions` returns `{ items }`.
2. Each item includes `version`, `status`, `origin`, and `createdAt`.
3. Items are ordered by `version DESC`.

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
5. Generic lifecycle routes reject `origin=seeded` and `origin=imported`.
6. Imported versions are created, advanced, or archived only by the audited projection path.
7. Generic create and patch routes for agent specs, workflow specs, and persona profiles reject `origin=seeded` and `origin=imported`.

### Capability APIs

1. `GET /api/v2/studio/capabilities`
2. `GET /api/v2/studio/capabilities/{key}/versions`
3. `GET /api/v2/studio/capabilities/{key}/versions/{version}`
4. `POST /api/v2/studio/capabilities` for `origin=managed` only
5. `PATCH /api/v2/studio/capabilities/{key}/versions/{version}` for `origin=managed` only

Managed capability lifecycle rule:

1. Managed capabilities use the same draft, activate, deprecate, and archive lifecycle routes as the other versioned Studio resources.
2. Seeded capabilities remain read-only through Studio mutation routes.

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
10. `GET /api/v2/runtime/approvals`
11. `GET /api/v2/runtime/trace-events`

`GET /api/v2/runtime/runs` must support filters for `callerType`, `callerId`, `callerScopeKey`, `callerIdentityKey`, and `workflowSpecKey`.

`GET /api/v2/runtime/approvals` must support filters for `runId`, `callerType`, `callerId`, `workflowSpecKey`, `capabilityKey`, and `status`.

`GET /api/v2/runtime/trace-events` must support filters for `runId`, `callerType`, `callerId`, `workflowSpecKey`, `capabilityKey`, and `eventType`.

`POST /api/v2/runtime/runs` request body must include:

1. `callerType`
2. `callerId` nullable
3. `callerScopeKey` nullable
4. `callerIdentityKey` nullable
5. `executionKind`
6. `workflowSpecKey` nullable when `executionKind=single_agent`
7. `workflowSpecVersion` nullable when `executionKind=single_agent`
8. `agentSpecKey` nullable when `executionKind=workflow`
9. `agentSpecVersion` nullable when `executionKind=workflow`
10. `inputs`
11. `personaProfileRefs` optional
12. `persistRun` optional; defaults to `true`

Public create semantics:

1. `POST /api/v2/runtime/runs` creates and starts a run, then returns the current run envelope without waiting for terminal completion.
2. Callers use `GET /api/v2/runtime/runs/{runId}`, `.../artifacts`, `.../trace`, and approval reads/lists to observe subsequent state.
3. Public HTTP callers may not create runs with `callerType=simulation`, `callerType=studio`, or `callerType=tryout`; those caller types are reserved for internal services and dedicated APIs.

Historical-migration workflow eligibility rule:

1. Public non-simulation callers may not create historical-compatibility seeded workflow runs during the historical migration phase.
2. Those callers may create only v2-native workflow runs or single-agent runs.

Tryout caller reservation rule:

1. `callerType=tryout` is created only by the dedicated tryout APIs.
2. Public HTTP callers that need ephemeral interactive execution must use `/api/v2/tryouts/*`, not `/api/v2/runtime/runs`.

`POST /api/v2/runtime/runs` response body must include:

1. `runId`
2. `status`
3. `expiresAt` nullable

`POST /api/v2/runtime/approvals/{approvalId}/approve` request body must include:

1. `actor`
2. `reason`

`POST /api/v2/runtime/approvals/{approvalId}/deny` request body must include:

1. `actor`
2. `reason`

Approval action response body must include:

1. `approvalId`
2. `status`
3. `runId`
4. `resolvedAt`
5. `runStatus`

Review-list response envelope:

1. List endpoints return `{ items, nextCursor }`.
2. `nextCursor` is null when no further page exists.

Minimum approval list item fields:

1. `approvalId`
2. `runId`
3. `status`
4. `capabilityKey`
5. `stepKey`
6. `callerType`
7. `callerId`
8. `createdAt`

Minimum trace-event list item fields:

1. `runId`
2. `eventIndex`
3. `eventType`
4. `stepKey` nullable
5. `capabilityKey` nullable
6. `callerType`
7. `callerId`
8. `createdAt`

Ordering and pagination rule:

1. Approval lists sort by `createdAt DESC` unless a later API version adds another explicit sort.
2. Trace-event lists sort by `eventIndex ASC` within a run-filtered result, otherwise by `createdAt DESC`.

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
11. `traceSummary`
12. `approvalSummary`

Canonical `TerminalError` object:

1. `code`
2. `message`

`terminalError` returns the canonical `TerminalError` object for terminal `FAILED` runs and null otherwise.

Minimum `GET /api/v2/runtime/runs/{runId}/artifacts` response fields:

1. `runId`
2. `finalOutput` nullable
3. `terminalError` nullable
4. `reportMarkdown` nullable
5. `normalizedTradeDecisions` nullable
6. `entryPromptHash`
7. `fullUserPromptHash`
8. `authoredEntryPromptBody` nullable
9. `compiledEntryPromptBody` nullable
10. `executionContextBody` nullable
11. `promptReportSlug` nullable
12. `rawMentionHandles`
13. `resolvedMentions`
14. `mentionedTargetOutputs`
15. `resolvedPersonaProfileRefs`
16. `resolvedWorkflowAgentRefs` nullable
17. `resolvedCapabilities`
18. `resolvedBuiltinVersions`
19. `resolvedRoleVersions`
20. `resolvedCharacterVersions`
21. `resolvedBundleVersions`
22. `resolvedToolVersions`
23. `resolvedConnectorVersions`
24. `traceSummary`
25. `approvalSummary`

Artifact summary derivation rule:

1. `traceSummary` and `approvalSummary` on artifact reads are derived from the canonical `runtime_runs.trace_summary` and `runtime_runs.approval_summary` fields.
2. Artifact reads must not invent an artifact-local summary that disagrees with the run record.

Minimum `GET /api/v2/runtime/approvals/{approvalId}` response fields:

1. `approvalId`
2. `status`
3. `capabilityKey`
4. `stepKey`
5. `summary`
6. `allowedActions`

Approval read field shapes:

1. `summary` is an object with `approvalMode`, `displayName`, and `transport` nullable unless connector.
2. `allowedActions` is an array drawn from `approve | deny` and is empty once the approval is no longer pending.

`POST /api/v2/runtime/runs/{runId}/cancel` response body must include:

1. `runId`
2. `status`
3. `approvalSummary`

Minimum `GET /api/v2/runtime/runs/{runId}/trace` response contract:

1. Returns `{ items }`.
2. Each item uses the same minimum trace-event list item schema.
3. Items are ordered by `eventIndex ASC`.

Executor adapter contract:

1. `AgentRuntimeService` must invoke an execution adapter selected by caller type and workflow shape.
2. `SimulationLangGraphExecutionAdapter` is the v2 adapter that translates a runtime-owned simulation run into the current `SimulationLangGraphRequest` contract.
3. `GenericWorkflowExecutionAdapter` executes non-simulation workflow runs from `graph_definition` plus the frozen step plan.
4. `SingleAgentExecutionAdapter` executes `executionKind=single_agent` runs.
5. If a non-simulation caller supplies `callerIdentityKey`, create must reject a new run with HTTP 409 when caller policy forbids another active run for the same `(callerType, callerIdentityKey)`.

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
12. `resolvedWorkflowAgentRefs` nullable when `executionKind=single_agent`

Executor determinism rule:

1. For workflow execution, adapters must execute from the frozen `resolvedWorkflowAgentRefs` plan.
2. If an adapter implementation does not receive that plan inline, it must load the same frozen plan by `runId` before execution.
3. Adapters must not re-read mutable workflow definitions to rebuild step-level capability or approval semantics at execution time.
4. For workflow execution, step-level capability and approval semantics come from each step's `capabilityRefs` in `resolvedWorkflowAgentRefs`.
5. `resolvedCapabilities` is the flattened run-level effective set used for preflight checks, inspection, and caller summaries; it is not the authoritative source for step execution order or step-local approval overrides.

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
3. `finalOutput` nullable
4. `reportMarkdown` nullable
5. `traceSummary`
6. `approvalSummary`
7. `expiresAt` when `persistRun=false`
8. `terminalError` nullable

Tryout paused-run rule:

1. When tryout execution pauses in `WAITING_APPROVAL`, `finalOutput` and `reportMarkdown` are null.
2. `traceSummary` and `approvalSummary` describe the partial run state up to the pause.
3. `terminalError` is null while the run remains resumable.

Tryout summary derivation rule:

1. `traceSummary` and `approvalSummary` on tryout execute/read/persist responses are derived from the canonical `runtime_runs` summary fields for that run.
2. Tryout reads must return the same summary values visible through `GET /api/v2/runtime/runs/{runId}` for the same run.

Tryout rollback-window eligibility rule:

1. During the historical migration phase, `/api/v2/tryouts/*` may execute only v2-native workflows or single-agent runs.
2. Historical-compatibility seeded workflow specs are rejected from tryout during the historical migration phase.

Tryout persistence rules:

1. `persist` is idempotent.
2. `persist` preserves the same `runId` and clears `expiresAt`.
3. `persist` is allowed from terminal states and from `WAITING_APPROVAL`.
4. If an ephemeral tryout expires while still active or waiting approval, runtime must append an expiration trace event, mark pending approvals `EXPIRED`, transition the run to `CANCELLED`, and then delete ephemeral artifacts on schedule.
5. `DELETE /api/v2/tryouts/{runId}` must cancel any active ephemeral run, expire pending approvals, and remove ephemeral artifacts.

Tryout read/persist response contract:

1. `GET /api/v2/tryouts/{runId}` returns the same response shape as tryout execute.
2. `POST /api/v2/tryouts/{runId}/persist` returns the same response shape as tryout execute after clearing `expiresAt`.

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
6. Cancelling a `WAITING_APPROVAL` run expires every still-pending approval for that run before the run is marked `CANCELLED`.

## Simulation integration rules

### Breaking target contract

During migration, `SimulationCreate` accepts both:

1. `orchestrationPatternKey` as the v1 compatibility field
2. `workflowSpecKey` plus optional `workflowSpecVersion` as the v2 field
3. `launchMode`

Canonicalization rule:

1. If only `orchestrationPatternKey` is provided, service must map it to the identical seeded workflow spec key.
2. If only `workflowSpecKey` is provided, it must be a historical-compatibility seeded workflow key and service must persist a reversible compatibility mapping to the current pattern-key field until the historical migration phase closes.
3. If both are provided, they must resolve to the same seeded workflow key or validation fails.
4. `workflowSpecVersion` must be resolved and pinned at simulation creation time; all cycles in that simulation reuse the pinned version.
5. If `launchMode=legacy_callback`, `workflowSpecKey` and `workflowSpecVersion` must be omitted or validation fails.
6. During the historical migration phase, a historical-compatibility seeded internal simulation that omits `workflowSpecVersion` must pin `workflowSpecVersion=1` even if a newer seeded version is `ACTIVE`.
7. If both selector families are omitted, compatibility defaulting resolves `orchestrationPatternKey="seeded_internal_simulation_v1"`; internal runtime-backed creation maps that default to `workflowSpecKey="seeded_internal_simulation_v1"` and pins `workflowSpecVersion=1` during the historical migration phase.

Webhook compatibility rule during mixed mode:

1. Existing `webhookUrl` and `webhookTimeout` request/read fields remain part of the simulation compatibility surface during the historical migration phase.
2. For `launchMode=internal`, omitted values continue to materialize/read as `webhookUrl="internal://ledger"` and `webhookTimeout=600` during the historical migration phase.
3. For `launchMode=internal`, supplied values do not influence runtime routing and must round-trip unchanged as compatibility metadata.
4. For `launchMode=legacy_callback`, current webhook validation and callback delivery behavior remain authoritative.

Legacy callback cancel rule:

1. For `launchMode=legacy_callback`, `POST /api/v1/simulations/{id}/cancel` preserves the current baseline rule and only allows cancellation from `PENDING` or `RUNNING`.
2. Callback-era `currentCycleStatus` values such as `AWAITING_CALLBACK` or `PROCESSING_CALLBACK` do not independently change that status-based cancel rule.

Retained legacy callback route contract:

1. `POST /api/v1/simulations/{simulationId}/cycles/{cycleDate}/report` accepts `CycleReportUpload` with `name`, `content`, and `tags`, and returns the created report slug.
2. `POST /api/v1/simulations/{simulationId}/cycles/{cycleDate}/trades` accepts `CycleTradesRequest` with `decisions` and optional `reportSlug`, and returns trade execution results.
3. `POST /api/v1/simulations/{simulationId}/cycles/{cycleDate}/complete` returns completion status, cycle counts, and next-cycle metadata.
4. These routes remain compatibility ingress throughout the historical migration phase and are not the default browser-driven launch path.

`SimulationRead` adds:

1. `currentRunId` nullable during migration
2. `lastCompletedRunId` nullable
3. `workflowSpecKey` nullable during migration
4. `workflowSpecVersion` nullable during migration
5. `launchMode` nullable during classification
6. `launchModeClassifiedAt` nullable during classification
7. `launchModeClassifiedBy` nullable during classification
8. `executionOwner` nullable during classification

Existing `webhookUrl` and `webhookTimeout` fields remain on the compatibility read surface during the historical migration phase.

Run-id lifecycle rules:

1. Creating a cycle run sets `currentRunId` to that active run id.
2. Retrying the same cycle replaces `currentRunId` with the new attempt run id.
3. When a cycle run reaches `SUCCEEDED | FAILED | CANCELLED`, `lastCompletedRunId` is updated to that terminal run id.
4. `currentRunId` is cleared after a terminal run unless the next cycle run has already been created.

Simulation compatibility state mapping:

1. For `executionOwner=runtime_v2`, a newly created simulation remains `SimulationRead.status=PENDING` until the first runtime cycle run is created.
2. For `executionOwner=runtime_v2`, runtime `QUEUED | RUNNING` -> `SimulationRead.status=RUNNING`, `currentCycleStatus=RUNNING`.
3. For `executionOwner=runtime_v2`, runtime `WAITING_APPROVAL` -> `SimulationRead.status=RUNNING`, `currentCycleStatus=WAITING_APPROVAL`.
4. For `executionOwner=runtime_v2`, runtime cycle success on a non-terminal cycle -> `SimulationRead.status=RUNNING`, `currentCycleStatus=COMPLETED` until the next cycle begins.
5. For `executionOwner=runtime_v2`, runtime cycle success on the final cycle -> `SimulationRead.status=COMPLETED`, `currentCycleStatus=COMPLETED`.
6. For `executionOwner=runtime_v2`, runtime `FAILED` -> `SimulationRead.status=FAILED`, `currentCycleStatus=FAILED`.
7. For `executionOwner=runtime_v2`, runtime `CANCELLED` -> `SimulationRead.status=CANCELLED`, `currentCycleStatus=CANCELLED`.
8. For `launchMode=legacy_callback`, preserve current callback-era `status` semantics.
9. For `launchMode=legacy_callback`, preserve current callback-era `currentCycleStatus` semantics including `AWAITING_CALLBACK` and `PROCESSING_CALLBACK`.
10. For `launchMode=null`, preserve current compatibility-path read semantics until explicit classification occurs.
11. `executionOwner` is the pinned execution-path source of truth for that simulation once classification or create-time routing completes.

Pre-run internal `PENDING` rule:

1. If `executionOwner=runtime_v2`, `SimulationRead.status=PENDING`, and `currentRunId=null`, the simulation has not created its first runtime cycle run yet.
2. In that state, `POST /api/v1/simulations/{id}/cancel` cancels the simulation directly without creating a runtime run.
3. Startup repair treats that state as a stale pre-run internal simulation and fails it with a restart error rather than leaving it pending.

For `executionOwner=runtime_v2`, `POST /api/v1/simulations/{id}/cancel` must cancel a run in `QUEUED | RUNNING | WAITING_APPROVAL`.

Simulation approval discovery rule:

1. When `currentCycleStatus=WAITING_APPROVAL`, `currentRunId` must be non-null.
2. Runtime run read must expose `pendingApprovalIds` for that run.
3. Simulation detail uses those ids to load approval reads and render actions.

Simulation post-resume completion rule:

1. When an approval resolves a simulation-owned runtime run to success, `SimulationRuntimeAdapter.completeCycle(...)` must store the cycle report, apply trade decisions, update `_run_state`, update `currentRunId` / `lastCompletedRunId`, and advance or finalize the schedule.
2. This completion hook is required for both first-pass success and approval-resumed success.

### Runtime handoff contract

Simulation adapter must submit:

1. `callerType=simulation`
2. `callerId=simulation.id`
3. `workflowSpecKey` and optional version
4. `callerScopeKey=cycleDate.isoformat()`
5. cycle context refs including `portfolioId`, `cycleDate`, `benchmarkSymbols`, and prompt/report context

The runtime service derives `attemptNumber` for simulation callers from existing run history for the same `(callerType, callerId, callerScopeKey)`.

Runtime must return:

1. `runId`
2. `status`
3. `reportMarkdown`
4. `normalizedTradeDecisions`
5. `finalOutput` structured according to `workflow_specs.final_output_contract`
6. `traceSummary`
7. `approvalSummary`

Simulation-side services remain responsible for storing reports, applying trades, and preserving current read semantics such as `_run_state` redaction.

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
4. Legacy response shape and canonical target ids remain frozen throughout the historical migration phase.

Legacy orchestration validation parity rules:

1. Legacy role delete rejection when characters still reference the role remains authoritative during migration.
2. Legacy disabled-role rejection on character create or update remains authoritative during migration.
3. Legacy reserved builtin handle rejection remains authoritative during migration.

Builtin and mention-policy migration rules:

1. Seeded builtins `librarian` and `explore` must preserve their handles and bundle refs exactly during migration.
2. Seeded workflow specs must preserve current mention-policy behavior, including allowed builtin handles and whether character-style persona refs are allowed.
3. Imported personas preserve upstream legacy role or character version in `legacy_source_version` while persona `version` remains the append-only projection version.
4. Deleting a legacy role or character archives the imported persona version rather than hard-deleting it during the historical migration phase.

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
7. Add explicit compatibility projections from runtime artifacts into `simulation_orchestration_snapshots`.

### Phase 1: Studio and tryout

1. Ship Studio authoring and inspection.
2. Ship tryout execution.
3. Leave simulations on the current path.
4. Retain ephemeral tryouts for 24 hours by default; `persist` converts them into normal runtime runs.
5. Studio may author managed personas in this phase, but imported personas remain permanently read-only historical projections.

### Phase 2: simulation cutover

1. Add `historical simulation cutover flag` feature flag.
2. When false, current simulation execution remains authoritative.
3. When true, only `launchMode=internal` simulations submit runtime requests.
4. `launchMode=legacy_callback` remains on the retained legacy callback compatibility ingress throughout the historical migration phase.
5. During this phase, `simulation_orchestration_snapshots` mirrors runtime compatibility trace and approval data for simulation detail surfaces.
6. During this phase, simulation rows must preserve reversible `orchestrationPatternKey` compatibility.
7. During this phase, simulations may reference only seeded workflow specs whose keys exactly match the current supported pattern keys.
8. During this phase, simulation runs must use the pinned workflow version resolved at create time.
9. During this phase, runtime compatibility mirror writes must overwrite the existing snapshot row for the same `(simulation_id, cycle_date)` with the latest attempt projection.
10. Existing rows must be explicitly classified before mixed-mode cutover; `webhook_url` alone is not a safe classifier.
11. Rows that remain unclassified stay on the current path until explicitly migrated or recreated.
12. The latest-attempt mirror policy must be implemented as an update/upsert of the existing unique cycle row.
13. The audited classification job must be exercised in migration tests and audited in the DB upgrade path.
14. Existing or newly created simulations pin `execution_owner`, and enabling the runtime flag applies only to simulations pinned to `runtime_v2` after the flag state is observed.

### Phase 3: cleanup

1. Remove raw mention-based execution semantics from runtime.
2. Deprecate simulation-owned execution internals after historical migration phase closes.
3. Remove `orchestrationPatternKey` from the public create contract only after historical migration phase closes and all reversible mappings are no longer required.

## Historical fallback rules

1. Historical fallback flips `historical simulation cutover flag` to false.
2. Existing runtime tables remain intact and readable.
3. New or still-unclassified simulations resume the current execution path after rollback.
4. Reversible mapping from `workflowSpecKey` to current pattern-key contract must remain available throughout the historical migration phase.
5. No destructive table removal or irreversible backfill is allowed before the historical migration phase closes.
6. Because rollback is blocked until all non-terminal `runtime_v2` simulations finish or are cancelled, rollback does not re-home any pinned `runtime_v2` simulation.

Historical fallback precondition:

1. Default policy blocks rollback while any non-terminal `runtime_v2` simulation exists.
2. Operators must cancel those simulations or let them finish on the runtime path before the flag is flipped.

Historical fallback guard note:

1. The archived cutover plan assumed operators would block fallback while non-terminal `runtime_v2` simulations remained active.
2. That safeguard is historical migration context, not an enduring runtime API or table contract.

## Failure semantics

1. Unknown workflow spec, agent spec, persona profile, or capability key fails before execution starts.
2. Approval denial fails the pending step and the run unless the workflow explicitly defines a recoverable branch.
3. Tryout with `persistRun=false` must still expose trace and approval data until TTL expiry.
4. Simulation adapter failures must preserve current `FAILED` behavior and error-message reporting.
5. Resuming a run without a valid checkpoint must fail closed.
6. Expired ephemeral tryouts must emit `RUN_EXPIRED` and mark pending approvals `EXPIRED` before cleanup.

Startup repair semantics:

1. Application startup must run a runtime repair pass in the same DB initialization phase that currently repairs interrupted simulations.
2. `runtime_runs` left in `QUEUED` or `RUNNING` are marked `FAILED` with `terminal_error_code="interrupted_runtime"` and a restart message.
3. `runtime_runs` left in `WAITING_APPROVAL` remain resumable.
4. Runtime-backed simulations with `execution_owner=runtime_v2`, `status=PENDING`, and `currentRunId=null` are treated as stale pre-run internal simulations and are marked `FAILED` with a restart `errorMessage`.
5. Other runtime-backed simulations affected by startup repair must update `status=FAILED`, `currentCycleStatus=FAILED`, and a restart `errorMessage`, preserve `_run_state` redaction semantics, clear `currentRunId`, keep `lastCompletedRunId` unchanged, and avoid schedule advancement.
6. Runtime-backed simulations affected by startup repair must update their compatibility snapshots using the same failure projection rules defined elsewhere in this spec.

## Runtime-to-snapshot projection rules

When `callerType=simulation` and `workflowSpecKey` is a historical-compatibility seeded workflow key, runtime compatibility projection must populate current snapshot fields as follows:

Initial projection writes prompt-hash and resolved-mention fields after run creation. Terminal projection updates the same unique cycle row after completion, failure, or cancellation with final trace and approval data.

1. `runtime_run_artifacts.prompt_report_slug` -> `simulation_orchestration_snapshots.prompt_report_slug`
2. `workflowSpecKey` -> `simulation_orchestration_snapshots.orchestration_pattern_key`
3. `workflow_specs.mention_policy.version` -> `simulation_orchestration_snapshots.pattern_policy_version`
4. `runtime_run_artifacts.entry_prompt_hash` -> `simulation_orchestration_snapshots.entry_prompt_hash`
5. `runtime_run_artifacts.full_user_prompt_hash` -> `simulation_orchestration_snapshots.full_user_prompt_hash`
6. runtime execution mode -> `simulation_orchestration_snapshots.execution_mode`
7. `runtime_run_artifacts.resolved_builtin_versions` -> `simulation_orchestration_snapshots.resolved_builtin_versions`
8. `runtime_run_artifacts.resolved_role_versions` -> `simulation_orchestration_snapshots.resolved_role_versions`
9. `runtime_run_artifacts.resolved_character_versions` -> `simulation_orchestration_snapshots.resolved_character_versions`
10. `runtime_run_artifacts.resolved_bundle_versions` -> `simulation_orchestration_snapshots.resolved_bundle_versions`
11. `runtime_run_artifacts.resolved_tool_versions` -> `simulation_orchestration_snapshots.resolved_tool_versions`
12. `runtime_run_artifacts.resolved_connector_versions` -> `simulation_orchestration_snapshots.resolved_connector_versions`
13. `runtime_run_artifacts.mentioned_target_outputs` -> `simulation_orchestration_snapshots.mentioned_target_outputs`
14. compatibility projection of `runtime_run_artifacts.resolved_mentions` -> `simulation_orchestration_snapshots.resolved_mentions`
15. runtime trace projection -> `simulation_orchestration_snapshots.tool_call_trace`
16. runtime approval projection -> `simulation_orchestration_snapshots.approval_trace`

When a runtime-backed simulation run is cancelled from `WAITING_APPROVAL`, the latest-attempt terminal projection must overwrite `simulation_orchestration_snapshots.approval_trace` with the expired approvals for that cancelled attempt.

Compatibility `approval_trace` shape rule:

1. Snapshot `approval_trace` remains a compatibility mirror using lowercase status values.
2. Each entry includes at least `call_index`, `tool_id`, `status`, `kind`, and `transport` nullable unless connector metadata is absent.
3. Cancellation from `WAITING_APPROVAL` updates the latest-attempt mirror so previously terminal approval entries are preserved and still-pending entries become `status="expired"`.

Compatibility `tool_call_trace` shape rule:

1. Snapshot `tool_call_trace` remains a compatibility mirror using snake_case keys.
2. Each entry includes at least `call_index`, `tool_id`, `status`, `latency_ms`, `argument_hash`, and optional `result_hash` / `error_code`.

## Acceptance criteria

1. A runtime run can be created, traced, approved, and inspected without a simulation row.
2. Current seeded pattern keys have a documented and tested 1:1 mapping to seeded workflow specs.
3. A simulation can invoke the runtime and still preserve current report, trade, and `_run_state`-redaction behavior.
4. Raw `@handle` execution is no longer the canonical runtime contract after cutover.
5. Historical fallback from runtime-backed simulations to current simulation execution is provably reversible during the historical migration phase.
6. Template-driven simulations preserve current prompt/report compilation semantics through explicit runtime artifacts and compatibility projection.

## Test mapping

### Current parity coverage that must stay green

1. `backend/tests/test_orchestration_api.py` for role/character compatibility and catalog behavior.
2. `backend/tests/test_workflow_specs_api.py` for Studio/Tryout workflow inventory and managed lifecycle behavior.
3. `backend/tests/test_runtime_seed_bootstrap.py` for seeded-registry and no-seeded-workflow bootstrap behavior.
4. `backend/tests/test_runtime_db_upgrades.py` for upgraded-database cleanup and compatibility behavior.
5. `backend/tests/test_runtime_api.py` and `backend/tests/test_runtime_artifacts.py` for runtime read compatibility and persisted artifact behavior.
6. Upgrade-path tests in the code-based DB upgrade suite for seeded-spec cleanup and persona-profile imports.

### New v2 coverage required

1. Agent-spec CRUD and version lifecycle tests.
2. Workflow-spec CRUD, graph validation, and seeded pattern mapping tests.
3. Persona-profile migration and compatibility-compiler tests.
4. Capability-registry seeded-vs-managed tests.
5. Runtime run state-machine tests.
6. Approval-request, approve, deny, and expiry tests.
7. Tryout ephemerality and explicit-save tests.
8. Snapshot-to-runtime-trace equivalence tests during migration.
9. Simulation cutover tests with feature flag on and off.
10. Historical fallback tests that prove the current path still works after reverting the flag.
11. Code-based upgrade tests for seeded spec reseeding, idempotent migrations, and mixed v1/v2 data.
12. Simulation `WAITING_APPROVAL` polling and cancel tests.
13. Per-cycle run uniqueness, lookup, and rerun-attempt tests.
14. Template compile to persona-ref compatibility pipeline tests.
15. Tryout TTL expiry and persist-idempotency tests.
16. Snapshot latest-attempt overwrite policy tests.
17. Workflow-version pinning and rollback-window seeded-version restriction tests.
18. Approval discovery read-contract tests for simulation detail.
19. Seeded workflow parity tests for `execution_mode`, `default_tool_ids`, `connector_ids`, and topology order.
20. `launchMode` classification and mixed-mode read-contract tests.
21. Approval-resumed simulation completion-hook tests.
22. Imported persona archive-on-delete tests.
23. Seeded workflow parity tests for current `allowed_bundle_keys` -> v2 `allowed_capability_bundle_keys` mapping and conservative `review_mode`.
24. Historical-row classification tests proving `webhook_url` alone does not determine `launchMode`.
25. Non-simulation executor-adapter contract tests.
26. Connector transport/lifecycle registry tests.
27. Nullable historical `launchMode` read-contract tests.
28. Snapshot projector update/upsert tests for existing unique cycle rows.
29. Concurrent non-simulation run tests covering nullable caller ids and `caller_identity_key` policies.
30. Approval-resume tests proving pinned persona/capability versions do not drift after run creation.
31. Workflow step agent-version pinning tests.
32. Explicit persona-ref shape and version reuse tests.
33. Typed capability handoff tests for `resolvedCapabilities`.
34. Historical internal backfill tests for `workflow_spec_key` and pinned `workflow_spec_version=1`.
35. Workflow graph edge and terminal-behavior tests.
36. Step-level capability precedence tests.
37. Approval override precedence tests for registry default vs workflow override vs step effective mode.
38. Historical fallback guard tests proving flag flip is blocked while runtime-backed simulation runs remain active.
39. Version lifecycle tests for append-only non-`DRAFT` versions and single-`ACTIVE` resolution.
40. Imported persona lineage tests covering versioned parent linkage and role reassignment.
41. Mixed-mode webhook compatibility tests for internal vs legacy-callback simulations.
42. Approval-denied edge vs fail-run state transition tests.
43. Execution-owner pinning tests proving flag flips do not re-home in-flight simulations.
44. Global mentionable-handle uniqueness and reserved-builtin-handle tests.
45. Imported enabled-parity tests for disabled roles, disabled characters, and mention catalog eligibility.
46. Omitted-selector compatibility-default tests for `seeded_internal_simulation_v1`.
47. Imported projection ordering tests for role update before dependent character reprojection.
48. Legacy callback route-contract tests for `/report`, `/trades`, and `/complete` compatibility ingress.
49. Legacy orchestration validation parity tests for role-in-use delete rejection, disabled-role character writes, and reserved handle rejection.
50. Persisted `final_output` and terminal-error reload tests for runtime run and artifact reads.
51. Legacy mention-catalog contract parity tests during migration.
52. Runtime approval review-list tests filtered by run, caller, workflow, capability, and status.
53. Runtime trace-event review-list tests filtered by run, caller, workflow, capability, and event type.
54. Imported persona projection-audit tests covering create, reproject, and archive events.
55. Single-agent output-contract validation tests for agents with and without `final_output_contract`.
56. `TerminalError` response-shape tests for run, artifact, and tryout reads.
57. Version-history list endpoint tests for agents, workflows, personas, and capabilities.
58. Artifacts endpoint parity tests covering prompt, mention, version-set, and final-output fields.
59. Runtime run-create request/response contract tests.
60. Approval approve/deny request/response contract tests.
61. Cancel-from-`WAITING_APPROVAL` tests proving pending approvals become `EXPIRED` before cancellation completes.
62. Public create-and-poll semantics tests for `POST /api/v2/runtime/runs`.
63. Connector lifecycle semantics tests for `placeholder` vs `approved` behavior.
64. `TraceSummary` and `ApprovalSummary` schema tests for run, artifact, and tryout reads.
65. Cancel response contract tests for `POST /api/v2/runtime/runs/{runId}/cancel`.
66. Approval read `summary` and `allowedActions` contract tests.
67. Approval row status tests for `PENDING`, `APPROVED`, `DENIED`, and `EXPIRED` actor/reason semantics.
68. Public runtime create rejection tests for reserved internal caller types.
69. Tryout `GET` and `persist` response-shape tests, including paused `WAITING_APPROVAL` runs.
70. Cancellation snapshot-projection tests for runtime-backed simulation runs.
71. Tryout caller-type reservation tests proving `/api/v2/runtime/runs` rejects public `callerType=tryout`.
72. Summary parity tests proving run, artifact, and tryout reads expose the same canonical summaries for a run.
73. Snapshot `approval_trace` compatibility-shape tests, including lowercase `expired` entries on cancellation.
74. Snapshot `resolved_mentions` and resolved-version compatibility-shape tests.
75. Snapshot `tool_call_trace` compatibility-shape tests with snake_case keys.
76. Startup repair tests for interrupted `runtime_runs` and runtime-backed simulations.
77. Historical fallback guard tests for the archived non-terminal `runtime_v2` safeguard assumption.
78. Legacy-callback cancel-eligibility tests preserving current `PENDING`/`RUNNING`-only behavior.
79. Internal simulation pre-run `PENDING` compatibility tests.
80. Legacy snapshot `resolved_mentions` projection tests proving exact `role_id` / `character_id` recovery from native runtime artifacts.
81. Executor step-plan tests proving adapters use `resolvedWorkflowAgentRefs` rather than flattened `resolvedCapabilities` for step-local semantics.
82. Historical classification manifest tests proving `launch_mode` / `execution_owner` are sourced from an operator-reviewed manifest.
83. Generic workflow adapter tests for non-simulation workflow execution.
84. Historical fallback guard tests for non-terminal pinned `runtime_v2` simulations even when no active runtime run exists.
85. `execution_mode` nullability tests for v2-native workflows and seeded-only enum parity for historical-compatibility workflows.
86. `executionOwner`-based simulation state-mapping tests proving legacy-path internal rows do not inherit runtime semantics.
87. Managed-only create/patch tests for agent specs, workflow specs, and persona profiles.
88. Non-simulation seeded-workflow rejection tests during the historical migration phase.
89. Seeded lifecycle-route rejection tests for agent specs, workflow specs, and persona profiles.
90. Tryout seeded-workflow rejection tests during the historical migration phase.
91. Create-time routing-matrix tests for `launchMode` and workflow selector/default combinations.
92. Startup repair tests for stale pre-run internal `PENDING` simulations with `execution_owner=runtime_v2` and `currentRunId=null`.
