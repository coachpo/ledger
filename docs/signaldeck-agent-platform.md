# SignalDeck Agent Platform Reference

> Status: Live package-first platform reference for branch `main` at `f9ae90d`. This is the canonical platform reference.

## Scope

SignalDeck ships a package-first agent platform beside the preserved portfolio, template, and report product areas. Users author Workflow Packages, bind package agents to global Model Connections, reference read-only global Tools, launch saved package runs from the dedicated `/workflow-packages/:packageId/run` page, and inspect persisted Runs from the browser.

This document describes shipped behavior only. Studio, Tryout, orchestration, runtime-v2, simulations, backtests, skill-contract pages, and removed global authoring routes are not live surfaces.

## Live Surfaces

| Area | Backend | Frontend |
|---|---|---|
| Workflow Packages | `/api/workflow-packages*` | authoring at `/workflow-packages*`, dedicated launch at `/workflow-packages/:packageId/run` |
| Package Secret Bindings | `/api/workflow-packages/{packageId}/secret-bindings*` | Secret Bindings tab inside the authoring-only `/workflow-packages/{packageId}` editor |
| Model Connections | `/api/model-connections*` | `/model-connections*` |
| Extensions | `/api/extensions*` | extension state consumers |
| Tools | `/api/tools` | surfaced inside package capability-profile editors |
| Runs | `/api/runs*` | `/runs*` |

Preserved finance product routes remain under `/api/v1` and `/portfolios*`, `/templates*`, and `/reports*`. They are bundled in `signaldeck.finance`, which is enabled by default and supports enable/disable state only. Generic platform capabilities remain core: Workflow Packages, Model Connections, Runs, HTTP operation nodes, package secret bindings, manifest parsing, and the `/api/tools` discovery host.

## Extensions

`/api/extensions` is a slim operational state API for bundled extensions. `GET /api/extensions` returns entries with only `key`, `label`, and `enabled`. `PATCH /api/extensions/{extensionKey}` accepts only `{enabled}`. It does not expose contribution inventories, categories, phases, versioning policy, disabled reasons, state versions, scaffold data, owner keys, or registrar details.

Backend registry and frontend scaffold data are private wiring. They may hold the extension key, label, initial enabled seed, registrar paths, and private route/nav/tool gate tags needed to assemble the app, but those details are not public API or manifest metadata. Future agents must not rebuild plugin-manifest metadata into `/api/extensions`, run details, frontend state, OpenAPI, or docs.

## Workflow Packages

Workflow Packages are the only live platform authoring root. Manifests use `signaldeck.workflowPackage/v1` YAML and store one mutable current package definition without a live status lifecycle. The editor is authoring-only: package-private agents, output schemas, capability profiles, private MCP configs, workflow graphs, and HTTP operation nodes live inside that current package artifact until the next save replaces it.

Package persistence is artifact-only for dependency references. Saving, importing, and updating a package can persist referenced Model Connection keys, extension-owned tool keys, and package secret-binding keys as artifact references without proving every live dependency is currently present or enabled. Current readiness is evaluated by launch metadata, preflight, launch, rerun, and fork flows against the stored artifact plus the live environment.

Package-local refs use local keys. Model bindings use global Model Connection keys. Tool grants use global server-declared tool keys inside package-local capability profiles. Workflow graph nodes currently ship as `kind: step`, `kind: sequence`, `kind: fanout`, `kind: loop`, and `kind: http`.

`kind: step` continues to mean local package-agent invocation through `AgentExecutionService`. `kind: http` is the shipped non-agent operation node; it compiles into `ExecutionPlanOperation` and `PackageRuntimeOperationSpec`, not into fake agents. Mixed execution steps may carry both `agents` and `operations`; final outputs still resolve from step/slot selectors such as `${{ nodes.notify_slack.outputs.webhook_result }}`.

Package import/export is manifest based. Exports keep private MCP `env`, `headers`, and `query` values inline in the package text. This is an intentional breaking change, and the old binding-based private MCP contract no longer applies. Exports still omit database ids, run history, live package status, package secret binding rows, and raw package secret binding values.

## HTTP Operation Nodes

The public manifest contract for non-agent operations is `kind: http`:

```yaml
flow:
  kind: http
  id: notify_slack
  slot: webhook_result
  method: POST
  url: ${{ inputs.webhookUrl }}
  headers:
    Authorization: ${{ secrets.slack_webhook_token }}
  query:
    ticker: ${{ inputs.ticker }}
  body:
    ticker: ${{ inputs.ticker }}
  response:
    outputSchema: webhook_response
  timeoutSeconds: 10
  optional: false
```

`id` and `slot` are lowercase package-local identifiers. `method` is normalized to uppercase and preflight allows `GET` and `POST`. `url`, `headers`, `query`, and `body` may use literal JSON-compatible values, input refs, prior-node output refs, and `${{ secrets.key }}` refs. Secret refs are valid only in those HTTP request fields and compile to `{from:"secret", key:"..."}` for runtime resolution.

The HTTP runtime is intentionally narrow. `HttpOperationExecutionService` resolves request inputs, prior slot outputs, and package secret binding values immediately before dispatch. It enforces HTTPS by default, blocks private/loopback/link-local/reserved targets by default, caps timeout/request/response sizes, disables redirects by default, and validates JSON/text responses against `response.outputSchema`. The test-only dev override path is covered by `dev_override` tests and does not weaken production defaults.

## Package Secret Bindings

Package secret bindings are package-local encrypted values used by HTTP operation nodes. They are not Workflow Package manifest fields and are never included in exports, run details, logs, compiled graph refs, agent inputs, workflow outputs, or diagnostics. Deleting a binding is a live-environment mutation: the package artifact can keep the referenced key, while later readiness and runtime checks report the missing value.

The API shape is:

- `GET /api/workflow-packages/{packageId}/secret-bindings` -> `{items:[{packageId,key,hasValue,createdAt,updatedAt}]}`
- `PUT /api/workflow-packages/{packageId}/secret-bindings/{key}` with `{value}` -> `{packageId,key,hasValue,createdAt,updatedAt}`
- `DELETE /api/workflow-packages/{packageId}/secret-bindings/{key}` -> `204`

The frontend exposes this through the package editor Secret Bindings tab. Stored values are never echoed; the UI shows known keys and stored/redacted state, clears typed values after save, and sends new values only through the update request.

## Model Connections

Model Connections are global live bindings for provider endpoint, model id, protocol profile, declared or probed capability support, runtime policies, timeout defaults, encrypted API keys, reachability-test status, and capability-probe metadata. The live protocol selector is `protocolProfile`, with `openai_chat_completions` and `openai_responses` as the shipped profiles. `apiStyle` may still appear as derived historical compatibility metadata, but it is not the primary live concept.

Capability states use `supported`, `unsupported`, `unknown`, and `notApplicable`. The shipped capability keys cover text generation, Chat Completions, Responses API, streaming, native tool calls, parallel tool calls, JSON-object output, strict JSON-schema output, reasoning hints, usage reporting, and system messages. Policy fields are `outputStrategyPolicy`, `parallelToolCallsPolicy`, `reasoningPolicy`, and `streamingPolicy`; newly created connections prefer strict schema output, serialize parallel tool calls, allow reasoning hints, allow streaming, and default `probeCacheTtlSeconds` to `900`.

`POST /api/model-connections/{connectionId}/connection-test` checks reachability only. `POST /api/model-connections/{connectionId}/capability-probe` checks selected or default capability keys, respects cached probe results unless refreshed, and updates capability timestamps without exposing provider internals. The Model Connections UI mirrors that split with separate test and probe actions.

Read payloads and errors must mask or omit raw secrets. Blank API-key edits preserve the stored key; non-empty edits rotate it. Packages store Model Connection keys as artifact references. Current readiness and execution resolve those keys against the live Model Connection store, so deleting or changing a connection affects subsequent preflight, launch, rerun, fork, or runtime checks without rewriting historical run snapshots.

## Tools

Tools are read-only server-declared metadata from `/api/tools`. Packages reference tool keys through local capability profiles; the platform does not expose global capability CRUD as a live route. The host is core, while the current finance/product/provider tool entries are provided by private `signaldeck.finance` registrars and appear only when that extension is enabled.

Current native tools cover market quote/history/OHLCV, indicators, fundamentals, news, social sentiment, insider data, positions, report lookup, and platform-core memory write/lookup. Finance-owned tools remain visible to smoke and demo Workflow Packages while `signaldeck.finance` is enabled by default; core memory tools stay visible even when it is disabled. Examples include `signaldeck.market_data.ohlcv_lookup`, `signaldeck.indicators.lookup`, `signaldeck.news.lookup`, `signaldeck.social_sentiment.lookup`, `signaldeck.reports.lookup`, `signaldeck.memory.write`, `signaldeck.memory.lookup`, and OpenAI function names such as `signaldeck_social_sentiment_lookup`, `signaldeck_reports_lookup`, and `signaldeck_memory_write`.

`signaldeck.news.lookup` remains the company/query/macro news contract. `signaldeck.social_sentiment.lookup` is separate and additive: it accepts `symbol`, optional `sources` (`reddit`, `stocktwits`), optional `startDate`, optional `endDate`, and optional `itemLimit` capped at `50`; output contains `sourceBlocks`, aggregate `metrics`, and structured `warnings`. Provider outage, timeout, rate-limit, empty-source, partial-result, and truncation paths return deterministic warnings rather than raw provider errors.

The canonical TradingAgents-style advisory package grants native data/news/social/report tools through package-local capability profiles, uses explicit analyst `sequence` topology, and remains advisory-only. It may propose a portfolio decision but does not execute trades, draft brokerage operations, or add LangGraph-specific checkpoint/runtime semantics.

## Runs

The browser launch surface is the dedicated `Launch Workflow Package` page at `/workflow-packages/:packageId/run` in phase 1. It is separate from the authoring editor and owns launch metadata, preflight gating, runtime parameters, saved inputs, and create-run state. The `/workflow-packages/:packageId/launch` browser rename is deferred follow-up only.

Package launch reads metadata from `GET /api/workflow-packages/{packageId}/launch`, then creates a durable queued run with `POST /api/workflow-packages/{packageId}/launches` using the selected workflow key and `parameters`. Launch captures the current package artifact and each resolved Model Connection's non-secret effective runtime profile into a run-owned executable snapshot before the explicit scheduler worker claims it.

Runs persist run status, inputs, final output, token/timing totals, optional Logfire trace ids, per-agent invocation span ids, per-operation invocation span ids, rerun metadata, fork metadata, scheduler metadata, dependency-only extension requirements, and snapshot-based package provenance. Current detail payloads include steps, agent invocations, operation invocations, read-only historical replay lineage when present, and the captured executable snapshot for review without requiring a separate tracing product or Logfire token. They expose invocation refs, not scalar internal `agent` or `output schema` ids. `packageProvenance.resolvedModelConnections` carries the sanitized runtime profile used for audit and replay decisions: protocol profile, model id, sanitized endpoint identity, capabilities, policies, probe cache TTL, timeout, and `hasApiKey`, but never raw keys or provider payloads. The `run_forks` artifact is persisted for forked descendants, but `RunRead` does not currently expose a top-level `fork` field. Reruns and forks execute the stored run snapshot and replay the run-owned runtime profile by default, not the current package state. Deleting a Workflow Package deletes its owned runs and their run-owned snapshots. `packageProvenance.workflowPackageStatus` is nullable historical snapshot data only; `packageProvenance.currentPackage` does not carry live package status.

Run progress is backend-owned. Run list and detail payloads include a `progress` object derived from persisted agent and operation invocation statuses, not from frontend status heuristics. The shipped shape uses `unit`, `terminalCount`, `totalCount`, and `percent`; terminal `succeeded` and `failed` runs report `percent: 100`, while count fields still come from invocation rows.

Queued-state explanations are backend-owned as a nullable `queue` read model on run list and detail payloads. Queue records explain whether a queued run is blocked behind an older or running run in the same serial package lane, or is awaiting worker capacity. `status` remains the lifecycle field and does not carry reason text.

The run scheduler is an explicit backend worker process. API launch, rerun, and fork requests stop after creating durable queued rows; local and E2E startup helpers start `python -m app.workers.run_scheduler` as a sibling process. Worker claims stamp lease owner/timestamps, heartbeat extends the lease, completion clears it, and expired running leases fail the abandoned run before the lane claims more work.

Rerun is the root-parameter flow. `GET /api/runs/{runId}/rerun-draft` returns root launch parameters, historical package provenance, and top-level current readiness for creating a descendant from the stored artifact plus the live environment. `POST /api/runs/{runId}/reruns` creates a new queued run with edited `parameters`.

Fork is the invocation-input flow. `GET /api/runs/{runId}/fork-draft?sourceInvocationId=...` returns the selected source agent invocation's persisted actual input, historical package provenance, and top-level current readiness. `POST /api/runs/{runId}/forks` creates a queued descendant run that preserves the source run input, copies upstream context, edits that one target invocation input, and resumes from `resumeStepIndex`. Phase 1 supports agent invocation targets only. Operation and tool invocation forks are rejected rather than treated as step-wide forks.

`resumeStepIndex` is an execution boundary, not the editable target. The editable target is `sourceInvocationId`, and the create payload uses `invocationInput` as a full replacement for that target invocation input. Browser URL state mirrors this separation with `fork=1&resumeStepIndex=<n>&invocationId=<id>`.

Historical step replay records remain readable through copied source links. They are audit history only and are not the live write path for new run descendants.

Run extension requirements appear as `extensionDependencies`. Each dependency record contains only `extensionKey`, `surfaces`, and `fields`. These records help explain launch-time requirements and are not public extension snapshots or a place to carry labels, enabled state, versioning, phase, categories, disabled reasons, or registrar metadata.

Run detail keeps operation invocation rows separate from agent rows. Each step has `invocations` for agents and `operationInvocations` for `kind: http` operations. Operation invocation detail includes `operationKey`, `operationKind`, `method`, `timeoutSeconds`, redacted `requestMetadata`, bounded `responseMetadata`, `output`, `outputOrigin`, status/error fields, replay source fields, and timestamps. HTTP-only steps have no agent invocations; mixed steps can show both families.

Run memory evidence is persisted as `memoryEvents[]`, a generic stream of retrieval, injection, write/reuse, review, supersession, and failure facts from `run_memory_events`. `memoryArtifacts[]` is only a compact human-auditable slice for memories written by the run. Artifacts expose opaque `memoryId`, `summary`, `status`, `createdAt`, provenance, graph metadata when available, and optional `auditLinks.report` only when an ordinary report-domain audit action exists.

## Immutable Workflow Artifact vs Late-Bound Execution Environment

SignalDeck does not promise bit-for-bit historical replay. The stable platform contract is **immutable workflow artifact + late-bound execution environment**. The stored run snapshot is the execution authority for workflow structure and run evidence; current platform state continues to supply credentials, bindings, feature availability, and runtime infrastructure.

### Terminology

- **Immutable workflow artifact**, the package-defined execution structure captured onto the run: workflow graph, package-local resources, package-authored MCP config, selected workflow, input schema, and launch parameters.
- **Run evidence**, the persisted history produced by execution: steps, invocation rows, operation rows, fork lineage, outputs, errors, trace ids, span ids, and memory evidence.
- **Late-bound execution environment**, current global/platform state resolved outside the run snapshot: model-connection settings and secrets, package secret binding values, extension enablement, tool/runtime availability, MCP runtime boundaries, provider bundles, and backend operational settings.

### Boundary Contract

| Surface | Must be frozen for an existing run | Allowed to change in global state | Current code paths |
|---|---|---|---|
| Workflow Package artifact | `packageDefinition`, `compiledPlan`, manifest/compiled hashes, selected workflow, package-local refs, capability-profile tool grants, package-authored private MCP config, input schema, launch parameters | The current package row may change for later launches only; rerun/fork still derive structure from the stored run snapshot | `backend/app/services/workflow_package_service.py`, `backend/app/services/run_service.py`, `backend/app/models/run.py` |
| Run evidence and lineage | `runs`, `run_steps`, `run_agent_invocations`, `run_operation_invocations`, `run_forks`, outputs, errors, trace/span ids, replay source metadata, `run_memory_events` | Historical rows are not rewritten; only new descendant runs add new evidence | `backend/app/services/run_service.py`, `backend/app/repositories/run*.py`, `backend/app/models/run.py` |
| Model Connections | The referenced key and launch-time effective runtime profile in `packageProvenance.resolvedModelConnections` remain part of run audit history and rerun/fork replay decisions | Live base URL, model id, protocol profile, capabilities, policies, probe cache, timeout, secret payload, and active/inactive status may change for later fresh launches without mutating the stored run snapshot; current readiness, launch, rerun, fork, and execute-time rules still validate current live secrets and availability | `backend/app/services/model_connection_service.py`, `backend/app/services/workflow_package_preflight.py`, `backend/app/services/run_rerun_fork.py`, `backend/app/services/agent_execution_service.py` |
| Package secret bindings | Secret binding keys referenced by HTTP nodes and redacted request/response evidence | Secret binding values may rotate or be deleted independently of package artifacts and run snapshots; exports and run detail never include raw values, and later readiness/runtime checks surface missing bindings | `backend/app/services/workflow_package_service.py`, `backend/app/repositories/workflow_package_secret_binding.py`, `backend/app/services/http_operation_execution_service.py` |
| Extensions and tool availability | Package-requested tool keys and dependency-only `extensionDependencies` captured on the run | Enabled/disabled extension state, tool catalog membership, runtime tool executors, provider bundles, and lifecycle hooks may change and affect later validation/runtime behavior | `backend/app/services/extension_service.py`, `backend/app/services/extension_dependency_service.py`, `backend/app/agents/tool_catalog/__init__.py`, `backend/app/agents/runtime_tools/registry.py` |
| MCP runtime | Package-authored private MCP config and any pinned saved MCP server identity recorded in package-owned descriptors | Live MCP server enabled/published status, runtime boundary enforcement, package-private tool ownership checks, and dispatcher availability may change | `backend/app/agents/mcp/runtime.py`, `backend/app/agents/mcp/boundaries.py`, `backend/app/agents/mcp/tool_adapter.py` |
| Platform runtime and providers | Stored outputs and evidence only | Backend settings, OpenAI client behavior, quote/social adapters, HTTP runtime limits, runtime tool implementations, and other server-owned execution infrastructure may change between runs | `backend/app/services/agent_execution_service.py`, `backend/app/services/execution_providers.py`, `backend/app/services/http_operation_execution_service.py`, `backend/app/core/config.py` |

### Allowed To Change vs Must Be Frozen

**Must be frozen for an existing run**

- workflow graph and selected workflow entrypoint
- package-local agents, schemas, capability profiles, and tool grants requested by the package
- package-authored private MCP config stored in the package artifact
- launch inputs, rerun/fork lineage, and persisted run evidence

**Allowed to change without mutating the stored run snapshot**

- credentials and live connection availability resolved by model-connection key
- non-secret connection settings for later fresh launches only
- package secret binding values for HTTP nodes
- enabled/disabled extension state and live tool/runtime availability
- provider/runtime implementations and backend operational settings

### Rerun, Fork, and Replay Semantics

- Rerun and fork derive execution structure and the default effective runtime profile from the stored run snapshot, not from the current mutable Workflow Package row.
- Rerun and fork drafts expose top-level `ready`, `blockingErrors`, and `warnings` for current create-readiness. Historical `packageProvenance.preflightSummary` remains provenance and does not decide whether the create action is enabled.
- Live dependencies are revalidated at launch, rerun, fork, or execute time. This validation affects whether a new run can start or continue, but it does not redefine what the package artifact or historical run snapshot contains.
- Audit payloads such as `resolvedModelConnections`, `preflightSummary`, `extensionDependencies`, and `currentPackage` explain what launch saw or what the current package looks like; they do not replace the stored run snapshot as the execution artifact.
- If stronger reproducibility is needed later, version the late-bound environment explicitly instead of broadening run snapshots to include raw secrets or mutable global state.

## UI Contract

`frontend/src/routes.ts` is the route source of truth. `frontend/src/components/layout.tsx` owns sidebar entries and breadcrumbs for Workflow Packages, Model Connections, and Runs.

List pages provide create/import actions, current-readiness badges, launch handoff actions, and archive/delete actions where supported. Editors use hooks and API modules rather than direct fetch calls from view code. Validation appears as inline alerts, field messages, toasts, and backend error-envelope messages.

Workflow Package and Template editor routes use the full-height layout region inside the normal shell. Workflow Package editing remains YAML-first and authoring-only for workflow graph changes; `kind: http` authoring lives in the manifest YAML, package secret binding editing lives in the Secret Bindings tab, launch runs on the separate `/workflow-packages/:packageId/run` console, Model Connections pages center protocol profile, capabilities, policies, reachability tests, and capability probes, and run detail renders operation invocation cards, agent invocation cards, and sanitized runtime-profile provenance separately.

## Backend Shape

```text
backend/app/api/platform_router.py
backend/app/api/{workflow_packages,model_connections,tools,runs}.py
backend/app/services/{workflow_package_service,workflow_package_preflight,workflow_package_export,run_service,model_connection_service,model_connection_probe_service,model_gateway*,http_operation_execution_service,memory_follow_up_service,social_sentiment_service}.py
backend/app/core/{config,telemetry}.py
backend/app/services/workflow_package_manifest_{parser,compiler,decompiler}.py
backend/app/schemas/{workflow_package,workflow_package_manifest,model_connection,run}.py
backend/app/models/{workflow_package,model_connection,run,run_fork,run_step,run_agent_invocation,run_operation_invocation}.py
backend/app/repositories/{workflow_package_secret_binding,run_fork,run_operation_invocation}.py
```

## Frontend Shape

```text
frontend/src/routes.ts
frontend/src/components/layout.tsx
frontend/src/pages/{workflow-packages,model-connections,runs}/
frontend/src/hooks/{use-workflow-packages,use-model-connections,use-runs}.ts
frontend/src/lib/api/{workflow-packages,model-connections,tools,runs}.ts
frontend/src/lib/types/{workflow-package,model-connection,tool,run}.ts
frontend/src/lib/platform-authoring/**
```

## Removed Surfaces

The removed global authoring routes `/api/agents`, `/api/capabilities`, `/api/mcp-servers`, `/api/output-schemas`, `/api/workflows`, `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, and `/workflows*` are absent from the mounted app and the live router. They are not compatibility aliases or redirects.

The old backend route modules are deleted. Current guardrails live in `backend/tests/test_legacy_backend_cutover.py`, `backend/tests/test_workflow_package_openapi.py`, `frontend/src/routes.test.tsx`, and `frontend/src/platform-clean-break.test.ts`.

## Validation

`docs/test-plan.md` owns the live validation matrix. For this platform surface, use targeted backend coverage around workflow package preflight/runtime/run contracts, model-connection protocol/capability/probe contracts, Model Gateway adapter behavior, scheduler queue behavior, HTTP operation execution, memory services, runtime tools, and runtime DB upgrades, plus frontend coverage for Model Connections, Workflow Package launch/secret-binding flows, capability blockers, and Runs list/detail runtime-profile rendering.
