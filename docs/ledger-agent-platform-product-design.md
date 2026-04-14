# Ledger Agent Platform v2 Design

## Metadata

Status: Draft
Supersedes: previous contents of `docs/ledger-agent-platform-product-design.md`
References: `docs/ledger-orchestration-product-design.md`, `docs/ledger-orchestration-product-prd.md`, `docs/ledger-orchestration-product-spec.md`, `docs/orchestration-demo-runbook.md`, `backend/app/services/backtest_service.py`, `backend/app/services/backtest_cycle_service.py`, `backend/app/services/backtest_engine.py`, `backend/app/services/orchestration_service.py`, `backend/app/langgraph/seeds.py`, `backend/app/langgraph/runner.py`, `backend/app/models/backtest_orchestration_snapshot.py`
Source of truth notes: this is the target architecture for v2. It is grounded in the current in-process backend boundary and the current LangGraph execution adapter, but it intentionally breaks the backtest-owned execution model.

## Design intent

Ledger v2 keeps execution in-process and backend-owned, but moves execution authority into a generic runtime layer. The runtime becomes the owner of runs, traces, approvals, and capability resolution. Backtests, tryout, and Studio all become callers of the same runtime.

## Design principles

1. One runtime, multiple callers.
2. Graph-first execution, not chat-first execution.
3. Schema-first capability and approval contracts.
4. Explicit traces and approvals as first-class persisted artifacts.
5. Seeded immutable definitions and managed mutable definitions must coexist cleanly.

## Baseline, adjacent code, target

### Shipped baseline

1. `BacktestService` launches execution.
2. `BacktestCycleService` owns mention resolution, capability resolution, snapshot writes, and lifecycle flow.
3. `BacktestEngine` prepares prompt/report context and applies backtest-side persistence.
4. `BacktestLangGraphRunner` executes the internal analysis path.
5. `OrchestrationService` owns role/character CRUD, mention-catalog assembly behavior, and orchestration validation.

### Already-present v2-adjacent code

1. Seeded agents, topologies, patterns, tools, bundles, and placeholder connectors already exist.
2. Tool-enabled execution already exists beside structured-output execution.
3. Snapshot audit coverage already records execution mode, version resolution, tool traces, and approval traces.
4. Roles and characters already carry capability-bundle refs and already influence execution through runtime resolution.

### Proposed v2 target

1. Introduce a generic `AgentRuntimeService`.
2. Introduce explicit `AgentSpecService`, `WorkflowSpecService`, `PersonaProfileService`, and `CapabilityRegistryService`.
3. Move caller-specific orchestration setup behind adapters rather than embedding execution inside backtest lifecycle services.
4. Introduce `TryoutService` and Studio read models on top of the runtime.

## Target architecture overview

### 1. Spec domain

`AgentSpecService` owns versioned agent definitions.

`WorkflowSpecService` owns versioned workflow graphs and step rules.

`PersonaProfileService` owns non-executable authoring profiles and compatibility migrations from current roles, characters, and builtin mention targets.

Versioning policy:

1. New edits create or update `DRAFT` versions only.
2. Activated versions are immutable and remain available for pinned historical runs.
3. Version omission resolves to the single `ACTIVE` version for a key.
4. At most one `DRAFT` version may exist per key.
5. Activating a draft atomically deprecates the prior active version for that key.

### 2. Capability domain

`CapabilityRegistryService` owns tools, connectors, bundles, approval metadata, and origin semantics.

Registry split:

1. Seeded entries: code-owned, immutable, versioned by revision.
2. Managed entries: DB-owned, admin/internal-writable, versioned by explicit record version.

### 3. Runtime domain

`AgentRuntimeService` owns run creation, step execution, trace persistence, approval gating, and final output normalization.

It uses the existing LangGraph runner through an adapter boundary rather than replacing it with a second worker.

### 4. Caller adapters

1. `BacktestRuntimeAdapter`: converts one backtest cycle context into one runtime request and translates runtime output back into current backtest-side persistence operations.
2. `TryoutService`: builds ephemeral runtime requests from Studio inputs.
3. `StudioQueryService`: exposes spec, run, trace, approval, and capability inspection read models, including review by run, caller, workflow, and capability.

## Ownership boundaries

1. Runtime service owns execution state, run state, trace state, and approval state.
2. Runtime checkpoint store owns paused execution state for approval resume.
3. Backtest services own portfolio lifecycle, report lifecycle, trade application, and compatibility surfaces.
4. Orchestration service remains the owner of legacy role, character, and mention-catalog assembly behavior during migration only.
5. Capability registry owns capability metadata and approval policy, not the runner.
6. LangGraph runner remains an execution adapter that returns output and trace data; it does not become the system of record.
7. Backtest compatibility adapter owns mapping runtime state into current `BacktestRead` fields and polling semantics during migration.

## Runtime shape

Recommended runtime flow:

1. Caller submits `RunCreate` with caller metadata, workflow spec or agent spec ref, input payload, and context refs.
2. Runtime resolves spec versions and expands seeded or managed capability references.
3. Runtime creates the run row, step plan, and initial trace shell.
4. Runtime executes step by step, persisting `runtime_trace_events` as it progresses.
5. When approval is required, runtime persists a checkpoint row plus a pending approval row, transitions the run to `WAITING_APPROVAL`, and returns control.
6. Approval endpoints load the latest checkpoint, resolve the pending approval, and resume the same run in-process.
7. Runtime completes with normalized output plus persisted trace and approval summaries on the runtime run record.

Public-vs-internal execution contract rule:

1. The public `POST /api/v2/runtime/runs` endpoint is an async create-and-poll API.
2. Rich terminal payloads such as report markdown, trade decisions, final output, and summaries come from internal service contracts or caller-specific convenience APIs, not from the minimal public create response.
3. `TryoutService` is the synchronous convenience entry point for interactive execution.
4. `BacktestRuntimeAdapter` uses the internal runtime service contract rather than the minimal public HTTP create contract.
5. Public HTTP callers do not create `callerType=tryout` runs through `POST /api/v2/runtime/runs`; the dedicated tryout APIs own that caller type.

Summary read rule:

1. `traceSummary` and `approvalSummary` are canonical run-level summaries owned by `runtime_runs`.
2. Run, artifact, and tryout reads surface those same summaries; they are not independently computed per endpoint.

Approval control-flow rule:

1. Approval `APPROVED` resumes the same run on the original step path.
2. Approval `DENIED` resumes the same run only when the current step defines an explicit `approval_denied` edge.
3. Approval `DENIED` without an `approval_denied` edge fails the run.
4. Explicit cancel during `WAITING_APPROVAL` cancels the run.
5. Canceling a `WAITING_APPROVAL` run expires any still-pending approvals before the run is finalized as cancelled.
6. Public approve/deny endpoints return approval resolution metadata plus the resumed run status; callers poll the run read for terminal payloads.

Backtest compatibility state mapping during migration:

1. A newly created `executionOwner=runtime_v2` backtest remains `BacktestRead.status=PENDING` until its first runtime cycle run is created.
2. For `executionOwner=runtime_v2`, runtime `QUEUED` or `RUNNING` -> `BacktestRead.status=RUNNING`, `currentCycleStatus=RUNNING`.
3. For `executionOwner=runtime_v2`, runtime `WAITING_APPROVAL` -> `BacktestRead.status=RUNNING`, `currentCycleStatus=WAITING_APPROVAL`.
4. For `executionOwner=runtime_v2`, runtime `SUCCEEDED` on a non-terminal cycle -> `BacktestRead.status=RUNNING`, `currentCycleStatus=COMPLETED` until the next cycle begins.
5. For `executionOwner=runtime_v2`, runtime `SUCCEEDED` on the final cycle -> `BacktestRead.status=COMPLETED`, `currentCycleStatus=COMPLETED`.
6. For `executionOwner=runtime_v2`, runtime `FAILED` -> `BacktestRead.status=FAILED`, `currentCycleStatus=FAILED`.
7. For `executionOwner=runtime_v2`, runtime `CANCELLED` -> `BacktestRead.status=CANCELLED`, `currentCycleStatus=CANCELLED`.

`POST /api/v1/backtests/{id}/cancel` must also be the endpoint that cancels a `WAITING_APPROVAL` `executionOwner=runtime_v2` cycle during migration.

Pre-run internal `PENDING` rule:

1. If `executionOwner=runtime_v2`, `BacktestRead.status=PENDING`, and `currentRunId=null`, the backtest has not created its first runtime cycle run yet.
2. In that state, `POST /api/v1/backtests/{id}/cancel` cancels the backtest directly without creating a runtime run.
3. Startup repair treats that state like a stale pre-run internal backtest and fails it with a restart error rather than leaving it pending.

## Roles, characters, and persona profiles

This is the most important compatibility boundary.

1. Roles, characters, and builtin mention targets are not removed from day one.
2. They stop being the runtime contract.
3. They migrate into `persona_profiles`.
4. Legacy-projected personas use `origin=imported`.

Availability parity rule:

1. `persona_profiles.enabled` is the v2 selectable/mentionable flag.
2. Imported role-template personas mirror legacy role `enabled`.
3. Imported character personas mirror legacy character `enabled`.
4. Imported character personas are mentionable only when both the character persona and its parent role-template persona are enabled.
5. Seeded builtin personas are always enabled.

Handle namespace rule:

1. Mentionable handles are globally unique across imported, seeded, and managed personas.
2. Seeded builtin handles remain permanently reserved.
3. Non-mentionable personas may use null handles.

Recommended mapping:

1. Role row -> imported persona profile of kind `role_template` with key `imported.role.{role_key}`.
2. Character row -> imported persona profile of kind `character_profile` with key `imported.character.{handle}`, stable handle identity, `canonicalTargetId`, versioned parent persona ref, and prompt append fragment.
3. Seeded builtins `librarian` and `explore` -> seeded persona profiles of kind `builtin_profile` with keys `builtin.{handle}`.
4. Current `capabilityBundleKeys` -> persona-profile default capability hints.
5. Current `@handle` authoring -> compatibility compiler that resolves shorthand into explicit persona-profile refs before runtime execution.

The runtime never uses raw `@handle` parsing as its canonical contract in v2.

Template and prompt pipeline:

1. Backtest adapter continues to use the existing template compiler and prompt-report generation flow.
2. Adapter persists authored template text, compiled prompt body, execution context body, and prompt-report slug in runtime artifacts.
3. Compatibility compiler runs after template compile and before runtime invocation.
4. Compiler resolves raw `@handle` values into explicit persona-profile refs and stores both the raw handle list and ordered resolved-mention objects in runtime artifacts.
5. Runtime executes against explicit persona-profile refs and compiled prompt artifacts, not against raw template mentions.

Migration source-of-truth rule:

1. `/api/v1/orchestration/*` remains the write authority for imported role and character personas during migration.
2. Writes through legacy orchestration APIs must project into `persona_profiles`.
3. Studio shows imported personas as read-only historical projections.
4. After the rollback window closes, managed and v2-native personas are edited only through `persona_profiles`, while imported personas remain read-only historical projections and legacy orchestration APIs are deprecated.
5. The projection path preserves one active imported version per key by creating the next imported version and atomically deprecating the previously active imported version.
6. A legacy role update projects the new imported role-template version before projecting any affected imported character versions that reference it.
7. Legacy orchestration validations remain authoritative during migration, including role-in-use delete rejection, disabled-role rejection on character writes, and reserved builtin handle enforcement.
8. The compatibility read contract for `GET /api/v1/orchestration/mentions/catalog` remains frozen during migration: it returns seeded builtins plus enabled imported characters whose parent imported roles are enabled, and it does not surface managed personas.

## Backtest integration design

Backtests remain responsible for:

1. Portfolio selection.
2. Cycle dates and benchmark context.
3. Report creation and trade lifecycle.

Backtests stop being responsible for:

1. Workflow graph ownership.
2. Generic trace ownership.
3. Approval lifecycle.

Backtest adapter flow:

1. Backtest computes one cycle context.
2. Adapter resolves and pins `workflowSpecVersion` when the backtest is created; all cycles in that backtest use the same pinned workflow spec version.
3. Adapter maps current `orchestrationPatternKey` or future `workflowSpecKey` to that pinned workflow spec ref.
4. Adapter submits one runtime request per cycle.
5. Runtime run identity is `(callerType=backtest, callerId=backtest.id, callerScopeKey=cycleDate.isoformat(), attemptNumber)`.
6. Compatibility mirror policy: `backtest_orchestration_snapshots` stores the latest attempt only for a cycle, while full attempt history remains in runtime tables.
7. Runtime returns report markdown, normalized trade decisions, and trace refs for that cycle.
8. Backtest service continues report and trade persistence.

Attempt numbering rule:

1. `attemptNumber` is runtime-derived for backtest callers from existing run history for the same `(callerType, callerId, callerScopeKey)`.
2. Callers do not submit `attemptNumber` in the create request.

Workflow-spec parity rule for seeded backtest patterns:

1. Seeded workflow specs must explicitly carry the current `BacktestPatternSpec` execution contract: topology/agent order, `review_mode`, `execution_mode`, `default_tool_ids`, current `allowed_bundle_keys` mapped into v2 `allowed_capability_bundle_keys`, and `connector_ids`.
2. In v2, topology order belongs to the workflow graph definition, not to agent specs.
3. For rollback-compatible seeded workflows, `execution_mode` and `review_mode` remain seeded-compatibility metadata and semantic inputs to the seeded execution adapter until the rollback window closes.
4. For v2-native workflows, both fields are null and equivalent behavior must be expressed only through `graph_definition`.

Backtest run-id lifecycle during migration:

1. Creating a cycle run sets `currentRunId` to the active attempt for that cycle.
2. Retrying a cycle creates a new run with `attemptNumber + 1` and replaces `currentRunId` with the new run id.
3. When a cycle run reaches a terminal state, `lastCompletedRunId` is updated to that run id.
4. `currentRunId` is cleared after a terminal cycle run unless the next cycle has already been created and assigned.

Execution-owner pinning rule:

1. Each backtest pins `executionOwner` at create time or historical classification time.
2. `executionOwner=legacy_path` keeps that backtest on the current path for all remaining cycles.
3. `executionOwner=runtime_v2` keeps that backtest on the runtime path for all remaining cycles.
4. Flag flips affect only newly created or newly classified eligible backtests; they do not re-home an in-flight backtest.

Create-time routing matrix:

1. `launchMode=legacy_callback` always pins `executionOwner=legacy_path`.
2. `launchMode=internal` with the runtime flag disabled pins `executionOwner=legacy_path`.
3. `launchMode=internal` with the runtime flag enabled pins `executionOwner=runtime_v2` only when the selected or defaulted workflow resolves to a rollback-compatible seeded workflow.
4. Otherwise `launchMode=internal` pins `executionOwner=legacy_path` until the rollback window closes or a later migration step explicitly changes the rule.

Legacy callback coexistence rule:

1. During the rollback window, `AGENT_RUNTIME_V2_BACKTESTS_ENABLED` applies only to persisted `launchMode=internal` backtests.
2. `launchMode=legacy_callback` remains on the retained legacy callback compatibility ingress and preserves current callback-aware statuses and endpoint behavior.
3. V2 keeps persisted `launchMode` as the compatibility transport class and persisted `executionOwner` as the pinned execution-path source of truth.
4. Webhook URL alone is not a safe historical source of truth because live internal-mode rows may also persist client callback URLs.
5. Historical rows remain on the current path until an explicit migration/classification step writes persisted `launchMode`.

Mixed-mode webhook compatibility rule:

1. Existing `webhookUrl` and `webhookTimeout` fields remain visible on the backtest compatibility surface during the rollback window.
2. For `launchMode=internal`, omitted values continue to materialize as `internal://ledger` and `600` during the rollback window.
3. For `launchMode=internal`, supplied values are compatibility metadata only and do not participate in runtime routing.
4. For `launchMode=legacy_callback`, existing webhook delivery behavior remains authoritative.

Legacy callback cancel rule:

1. `launchMode=legacy_callback` keeps the current cancel semantics.
2. `POST /api/v1/backtests/{id}/cancel` remains limited to `PENDING` or `RUNNING` callback-mode backtests during the rollback window.

Retained legacy callback contract:

1. `POST /api/v1/backtests/{backtestId}/cycles/{cycleDate}/report` remains available and accepts `CycleReportUpload` (`name`, `content`, `tags`), returning the created report slug.
2. `POST /api/v1/backtests/{backtestId}/cycles/{cycleDate}/trades` remains available and accepts `CycleTradesRequest` (`decisions`, optional `reportSlug`), returning trade execution results.
3. `POST /api/v1/backtests/{backtestId}/cycles/{cycleDate}/complete` remains available and returns completion status, cycle counts, and next-cycle metadata.
4. These routes remain compatibility ingress only and are never the default browser-driven launch path.

Historical backtest classification rule:

1. New backtests created after the v2 backtest schema rollout persist `launchMode` directly from `BacktestCreate`.
2. Pre-rollout rows are not auto-classified from `webhook_url` alone.
3. Pre-rollout rows are classified through one audited migration job using an operator-reviewed manifest keyed by `backtest_id`, not by inference at read time.
4. Mixed-mode cutover applies only to rows with an explicit persisted `launchMode` value.

Historical classification job:

1. Pre-rollout rows are classified through one audited migration job.
2. The manifest is the authoritative classification source for `launchMode` and `executionOwner`.
3. Each classification writes `launchMode`, `executionOwner`, `launchModeClassifiedAt`, `launchModeClassifiedBy`, and a classification note.
4. For classified internal rows using supported seeded patterns, the same job also writes `workflowSpecKey` from the persisted `orchestrationPatternKey` and pins `workflowSpecVersion=1`.
5. Historical rows whose pattern key cannot be mapped to a rollback-compatible seeded workflow stay on the current path and are not eligible for runtime-backed execution.
6. Mixed-mode cutover is blocked until all rows targeted for runtime-backed execution have manifest-backed classifications.

Backtest post-resume hook:

1. Approval endpoints resume the runtime run only.
2. When a resumed backtest-owned run reaches terminal success, `BacktestRuntimeAdapter` must hand the runtime result into the same caller-side completion path that stores the cycle report, applies trades, updates `_run_state`, updates run ids, and advances or finalizes the schedule.
3. Runtime completion alone does not finalize a backtest cycle; the adapter completion hook does.

Generic executor adapter boundary:

1. `AgentRuntimeService` executes through caller-aware executor adapters, not by calling `BacktestLangGraphRunner` directly.
2. `BacktestLangGraphExecutionAdapter` translates runtime-owned backtest runs into the current `BacktestLangGraphRequest` shape.
3. `GenericWorkflowExecutionAdapter` executes v2-native workflow runs for non-backtest callers from `graph_definition` plus the frozen step plan.
4. `SingleAgentExecutionAdapter` executes `executionKind=single_agent` runs for tryout and future generic runtime callers.
5. The generic adapter contract is `ExecutionAdapterRequest -> ExecutionAdapterResult`; backtest, generic-workflow, and single-agent adapters each implement the translation into that contract.
6. The adapter request must carry execution kind, pinned spec versions, pinned persona/capability versions, caller context, and caller-scoped artifacts needed before execution.
7. The adapter result must return final output, trace/approval events, and caller-scoped artifacts without assuming backtest-specific trade/report fields.

Rollback-window non-backtest workflow rule:

1. During the rollback window, non-backtest callers may execute only v2-native workflow specs or single-agent runs.
2. Rollback-compatible seeded workflow specs are reserved to backtest execution during the rollback window.

Workflow-agent determinism rule:

1. Workflow execution must materialize a step-level resolved agent plan at run creation.
2. That resolved plan records each step's agent spec key/version plus the pinned persona and capability refs used by that step.
3. Approval resume, retry, and historical inspection reuse the resolved step plan instead of re-reading the latest workflow definition.
4. Step execution uses the frozen step-level capability refs from that plan; flattened run-level capability summaries are for preflight and inspection only.

Workflow graph contract:

1. `graph_definition` is the canonical workflow contract.
2. It defines `entryStepKey`, ordered `steps`, and explicit `edges`.
3. Each step defines its agent ref, persona refs, capability refs, success handoff, failure handoff, and approval-denied handoff.
4. Terminal behavior is explicit: a step is terminal only when marked terminal or when its selected edge targets `END`.

## Tryout and Studio design

### Tryout

1. User chooses a workflow or agent spec.
2. User provides sample inputs and optional versioned persona refs.
3. Runtime executes once.
4. Default persistence is an ephemeral run retained for 24 hours.
5. `POST /api/v2/tryouts/{runId}/persist` converts an ephemeral tryout into a normal persisted Studio-visible run.
6. Persist is idempotent and preserves the same `runId`.
7. Ephemeral tryouts may enter `WAITING_APPROVAL`; persisting them clears the expiry timer and keeps the same run identity.
8. During the rollback window, tryout may execute only v2-native workflows or single-agent runs.

### Studio

Recommended route families:

1. `/studio/agents`
2. `/studio/workflows`
3. `/studio/personas`
4. `/studio/capabilities`
5. `/studio/runs/:runId`
6. `/tryout`

Studio must not become a separate execution engine. It is an authoring and inspection shell over the runtime.

Studio mutability rule:

1. Studio mutates managed resources only.
2. Seeded resources are inspectable but read-only.
3. Imported personas are inspectable historical projections and remain read-only.

## Persistence strategy

New service-owned records should be explicit and queryable:

1. `agent_specs`
2. `workflow_specs`
3. `persona_profiles`
4. `capability_registry_entries`
5. `runtime_runs`
6. `runtime_trace_events`
7. `runtime_approvals`
8. `runtime_checkpoints`
9. `runtime_run_artifacts`
10. `persona_projection_events`
11. `runtime_control_flags`
12. `runtime_flag_change_events`

`backtest_orchestration_snapshots` remains only as a compatibility mirror for backtest callers until migration completes.

`runtime_run_artifacts` is the canonical store for prompt hashes, authored and compiled prompt bodies, explicit persona-profile refs, ordered resolved-mention objects, rendered report markdown, caller-scoped artifacts, resolved version sets, mentioned target outputs, persisted generic final output, terminal failure details, and caller-specific compatibility refs such as `prompt_report_slug`.

It also carries the resolved workflow-agent plan, explicit persona-ref set, flattened effective capability set, persisted generic `finalOutput`, and terminal failure summary needed to replay or inspect a run deterministically.

`traceSummary` and `approvalSummary` are derived from the canonical `runtime_runs` summary fields and surfaced on run, artifact, and tryout reads; they are not separate artifact-local persisted objects.

`runtime_trace_events` and `runtime_approvals` are the canonical native audit stores. `tool_call_trace` and `approval_trace` remain backtest-snapshot compatibility mirrors only.

`persona_projection_events` is the canonical audit store for imported-persona projection activity. Every imported create, reproject, deprecate, or archive operation writes one projection event in the same transaction as the imported persona version change.

Startup repair rule:

1. Application startup runs a runtime repair pass in the same DB initialization phase that currently repairs interrupted backtests.
2. Runtime-owned runs left in `QUEUED` or `RUNNING` are marked failed with a terminal interruption error.
3. Runtime-owned runs left in `WAITING_APPROVAL` remain resumable.
4. Runtime-backed backtests reflect that repair outcome by setting `status=FAILED`, `currentCycleStatus=FAILED`, and a restart error message.
5. Runtime-backed backtests clear `currentRunId`, keep `lastCompletedRunId` unchanged, preserve `_run_state` redaction behavior, and do not advance the schedule.
6. Runtime-backed backtests update snapshot mirrors through the same failure projection rules used for ordinary failure.

## Migration and rollback design

### Ship order

1. Add runtime and spec tables plus seeded immutable records.
2. Add audited write-through projection from legacy orchestration writes into imported persona profiles.
3. Add runtime APIs and Studio/Tryout surfaces.
4. Add backtest runtime adapter.
5. Cut over backtest launches behind an explicit feature flag while retaining reversible pattern-key mapping.
6. Retire backtest-owned execution after parity and rollback windows close.
7. Keep imported personas permanently read-only historical projections in Studio.

### Cutover control

Recommended feature flag: `AGENT_RUNTIME_V2_BACKTESTS_ENABLED`.

When false, current backtest-owned execution remains the authority.

When true, backtests invoke the runtime adapter, but still persist a reversible compatibility mapping to the current pattern-key contract throughout the rollback window.

If both selector fields are omitted during the rollback window, create-time compatibility defaults still resolve to `seeded_internal_backtest_v1`, and internal runtime-backed creation pins seeded workflow version `1`.

During the rollback window, backtests may only target seeded workflow specs whose keys exactly match the current supported pattern keys, and they must pin one rollback-compatible seeded version at create time.

If a rollback-window internal backtest omits `workflowSpecVersion`, create-time resolution still pins seeded version `1` rather than the latest `ACTIVE` version.

Seeded workflow version source:

1. Initial seeded workflow mirror rows use `version=1`.
2. That seeded version is pinned for rollback-window backtests and does not float to a newer active version mid-run.

### Rollback rule

Rollback flips the flag back to false.

During rollback:

1. Runtime tables remain readable.
2. New or still-unclassified backtests use the current execution path after rollback.
3. `backtest_orchestration_snapshots` remains authoritative for backtest detail compatibility.
4. Runtime-created backtests must still have enough persisted compatibility data to resolve a current pattern key.
5. No destructive schema changes happen before the rollback window closes.
6. Imported personas remain readable from `persona_profiles`, but legacy orchestration rows remain the writable source until rollback support is no longer required.
7. Because rollback is blocked until all non-terminal `runtime_v2` backtests finish or are cancelled, rollback does not re-home any pinned `runtime_v2` backtest.

Rollback quiescence rule:

1. Default policy: do not flip the backtest runtime flag while any non-terminal `runtime_v2` backtest exists.
2. Operators must either let those backtests finish on the runtime path or cancel them before rollback.

Rollback guard control path:

1. The effective backtest runtime flag lives in `runtime_control_flags` under key `AGENT_RUNTIME_V2_BACKTESTS_ENABLED`.
2. The flag is changed only through one audited operational control path.
3. That control path checks for non-terminal `runtime_v2` backtests before applying the change and rejects the operation when any remain.
4. Successful and rejected attempts both write `runtime_flag_change_events` audit rows.

Mixed-mode storage rule:

1. The `backtests` table becomes the source of truth for `launchMode`, `workflowSpecKey`, `workflowSpecVersion`, `currentRunId`, and `lastCompletedRunId`.
2. Rows without persisted `launchMode` are treated as pre-classification compatibility rows and remain on the current path.
3. Backtest read/list surfaces must expose `launchMode=null` for those compatibility rows until they are explicitly classified.

Pinned-resolution rule:

1. Run creation freezes workflow, agent, persona, bundle, tool, and connector versions before execution starts.
2. Approval resume and retry reuse the frozen versions from runtime records rather than re-resolving against the latest active registry state.
3. Step-level capability refs are resolved first against the frozen workflow plan, then intersected with workflow-level ceilings before execution.

Snapshot projector change rule:

1. V2 compatibility projection intentionally changes today’s insert-once snapshot behavior.
2. Because `backtest_orchestration_snapshots` remains unique by `(backtest_id, cycle_date)`, the projector must update/upsert the existing row for the latest attempt instead of inserting a second row.
3. The initial projection happens after run creation when prompt hashes and resolved mentions are known.
4. The terminal projection overwrites the same row after run completion, failure, or cancellation to attach final trace and approval artifacts.

Imported persona delete rule:

1. Deleting a legacy role or character archives the imported persona profile version instead of hard-deleting it during the rollback window.
2. Archived imported personas remain resolvable for pinned historical runs and traces, but cannot be selected for new workflow references.

## Rejected alternatives

1. Keeping orchestration permanently backtest-owned.
2. Introducing a separate runtime worker as the preferred path.
3. Treating roles and characters as executable code containers.
4. Making the registry wholly DB-managed and losing seeded immutable entries.

## Risks and mitigations

1. Risk: underspecified parity between current seeded patterns and seeded workflow specs. Mitigation: seeded 1:1 migration table and parity tests.
2. Risk: loss of current role/character meaning. Mitigation: persona-profile migration and compatibility authoring compiler.
3. Risk: trace duplication between runtime and backtest snapshots. Mitigation: treat snapshots as compatibility mirrors only.
4. Risk: approval resume drifts from the one-runtime design. Mitigation: runtime checkpoints remain in-process and backend-owned, not worker-owned.

## Evidence and grounding

`backend/app/services/backtest_service.py`, `backend/app/services/backtest_cycle_service.py`, `backend/app/services/backtest_engine.py`, `backend/app/services/orchestration_service.py`, `backend/app/langgraph/seeds.py`, `backend/app/langgraph/runner.py`, `backend/app/models/backtest_orchestration_snapshot.py`, `backend/app/models/orchestration_role.py`, `backend/app/models/orchestration_character.py`, `backend/tests/test_backtests_api.py`, `backend/tests/test_backtest_cycle_service.py`, `backend/tests/test_backtest_orchestration_snapshot.py`, `backend/tests/test_orchestration_api.py`, `docs/ledger-orchestration-product-design.md`, `docs/orchestration-demo-runbook.md`
