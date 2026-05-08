# Ledger Memory Layer Technical Design

> Status: Phase 1 implementation notes for the memory domain layer over the current report backed persistence path as of 2026-05-08.

## Overview

Ledger's current agent memory is durable because it is stored as reports. That stays true in phase 1. Reports remain the current durable backing store, while agents, workflow packages, runtime tools, and run detail clients depend on memory concepts through a memory domain layer.

The core design choice is to place a memory boundary above report persistence. The system should expose memory entries, prompts, lifecycle state, provenance, and audit links to agent code. It should not expose report ids, report slugs, report names, or markdown report bodies as the primary memory model.

This solves the persistence caveat directly. Swapping persistence is only easy if report details do not leak upward. If tools, prompts, run artifacts, and UI contracts keep treating memory as report shaped data, any future move to a dedicated memory table or another store would be a breaking product change. If those surfaces depend on a MemoryStore contract, ReportBackedMemoryStore can be replaced later with a different adapter while the agent layer keeps the same memory concepts.

## Goals

1. Keep report backed durability for phase 1.
2. Add a memory domain layer that hides report implementation details from agent and run surfaces.
3. Preserve current stable runtime tool keys and OpenAI function names.
4. Keep existing report routes, report download behavior, report filters, and template placeholders unchanged.
5. Make memory prompts safer by sending quoted historical context with provenance and outcomes, not raw markdown or instruction like report content.
6. Give future implementers clear DTOs, service boundaries, store methods, lifecycle rules, phases, and tests.

## Non Goals

1. Do not replace reports with a new memory table in phase 1.
2. Do not add vector search in phase 1.
3. Do not break `/api/v1/reports`, report slugs, report sources, report downloads, report filters, or `reports.*` template placeholders.
4. Do not rename existing runtime tool keys or OpenAI function names in phase 1.
5. Do not add embeddings in phase 1.
6. Do not add broad unrelated agent platform refactors.

## Phase 1 Implementation Boundaries

Phase 1 preserves `ledger.reports.lookup` and `ledger.reports.write` as the stable runtime tool keys. The OpenAI function names stay `ledger_reports_lookup` and `ledger_reports_write`. These names are compatibility anchors for package manifests, catalog metadata, and runtime grants, not legacy debt to remove in this phase.

Only `ReportBackedMemoryStore` may parse or format the phase 1 `memoryId` value, currently `mem_<report_id>`. Every other layer treats `memoryId` as opaque, including `MemoryService`, prompt rendering, runtime tools, run artifacts, API schemas, and frontend pages.

There is no vector search, no embeddings, and no memory table in phase 1. Query behavior is metadata-filter based over report-backed rows.

The practical projection matrix is simple: model-visible prompts and tool outputs stay report-free; API/UI responses may include nested audit links; report routes stay report-shaped. Prompts and model-visible tool outputs must not expose report ids, slugs, names, raw markdown, URLs, downloads, or audit links. Frontend run detail can show report open/download actions only from optional `auditLinks.report`, never from `memoryId`.

## Current State

Ledger stores agent memory as reports with `source="agent"`. The agent memory identity is carried in `metadata.analysis.reviewType="agent_memory"` and `metadata.analysis.versionGroup="agent_memory/v1"`. The report markdown content is generated from the same metadata and acts as a human readable audit artifact.

The relevant current backend path is:

```text
runtime tool or post run memory policy
  -> MemoryService
  -> MemoryStore Protocol
  -> ReportBackedMemoryStore
  -> ReportRepository
  -> reports table
```

Current post-run memory creation is workflow-only in `RunService`. Workflow package runs rely on granted runtime memory tools in phase 1 unless a package post-run memory policy is added later. If that policy is added, it routes through the same `MemoryService` boundary.

The current prompt context path is:

```text
MemoryContextService
  -> MemoryService.query_memory
  -> ReportBackedMemoryStore.query_prompt_snippets
  -> formatted prompt snippets
```

The current run detail path is:

```text
RunService.get_run
  -> MemoryService.list_run_artifacts
  -> RunMemoryArtifactRead
  -> frontend run detail memory artifacts card
```

These paths are workable because report concepts now stop at the persistence adapter and audit-link projections.

## Phase 1 Boundary Checks

The following boundaries describe the phase 1 contract that prevents report details from leaking above the persistence layer.

| Boundary | Phase 1 contract |
| --- | --- |
| Runtime memory write | Returns memory-shaped results under stable `ledger.reports.write` and `ledger_reports_write` names. |
| Prompt context | Labels snippets as historical memory with source run, agent, decision, outcome, and reflection context, without report identity or raw markdown. |
| Run memory artifacts | Use `memoryId`, status, provenance, summary, and optional `auditLinks.report`. |
| Frontend run detail | Presents memory artifacts first, with report open and download as optional audit actions from `auditLinks.report`. |
| Memory identity | Treats `memoryId` as opaque outside `ReportBackedMemoryStore`. |

These are not data loss concerns. They are boundary rules. The phase 1 implementation keeps the data in reports while moving all callers above the persistence adapter to memory domain DTOs.

## Target Layering

The target dependency path is:

```text
agent/workflow package
  -> runtime tools
  -> MemoryService/MemoryContextService
  -> MemoryStore Protocol
  -> ReportBackedMemoryStore
  -> ReportRepository/reports table
```

Layer responsibilities:

| Layer | Owns | Does not own |
| --- | --- | --- |
| Agent and workflow package | Tool selection, package local grants, model prompts, memory write intent | Report lookup details, report slugs, markdown audit rendering |
| Runtime tools | Stable tool definitions, argument parsing, trusted runtime context injection, result DTO serialization | Report repository calls or report shaped results |
| `MemoryService` | Memory writes, outcome resolution, reflection append, memory entry reads, audit link shaping | Prompt ranking and prompt text assembly |
| `MemoryContextService` | Query normalization, snippet ranking, prompt safe rendering, character budget handling | Durable persistence mechanics |
| `MemoryStore Protocol` | Abstract create, update, query, and artifact projection methods | Business rules tied to one persistence engine |
| `ReportBackedMemoryStore` | Maps memory DTOs to report rows and report metadata, including `mem_<report_id>` parsing and formatting | Public report API behavior |
| `ReportRepository` and reports table | Current durable report persistence | Agent memory semantics above JSONB filters |

`MemoryService` is the runtime command boundary for memory writes, resolution, reflection append, reads, and run artifact projection. `ReportBackedMemoryStore` owns the report adapter details behind the `MemoryStore` Protocol.

## Phase 1 Implementation Files

The phase 1 file ownership is explicit.

| Area | Files or updates |
| --- | --- |
| Domain schemas | `backend/app/schemas/memory.py` defines memory DTOs and projection helpers; `memory_report.py` stays report-backed metadata support. |
| Store protocol | `backend/app/services/memory_store.py` defines the `MemoryStore` Protocol and shared store DTO inputs. |
| Report adapter | `backend/app/services/report_backed_memory_store.py` translates memory DTOs to `ReportRepository` and report rows. |
| Command service | `backend/app/services/memory_service.py` owns write, resolve, reflection, read, and run artifact commands. |
| Prompt service | `backend/app/services/memory_context_service.py` renders safe historical-memory snippets without report identity. |
| Runtime tools | `backend/app/agents/runtime_tools/reports.py` and `runtime_tools/types.py` return memory-shaped write results while preserving stable report tool names. |
| Run API | `backend/app/schemas/run.py` and `backend/app/services/run_service.py` expose memory-shaped `memoryArtifacts`. |
| Frontend contract | `frontend/src/lib/types/run.ts`, `frontend/src/pages/runs/detail.tsx`, and run detail tests use `memoryId` plus optional audit report links. |
| Tests | Store/service, runtime, memory, run artifact, workflow package, catalog, and frontend run detail tests cover the phase 1 contract. |

## Domain Concepts

Memory is a domain object, not a report subtype at the caller boundary.

A memory entry represents one remembered agent decision and its lifecycle. It can begin as pending, later resolve to an outcome, gain one or more reflections, appear in prompt context, and show up as a run artifact. The report row is one possible audit and persistence representation.

Phase 1 memory entries use these stable concepts:

1. Identity, exposed as `memoryId`.
2. Lifecycle status, exposed as `pending`, `resolved`, or `expired`.
3. Decision text, including action, rationale, risk summary, and execution plan.
4. Provenance, including run, agent, workflow, graph node, slot, trace, and creation time.
5. Outcome, including resolved time, raw return, benchmark return, and alpha when known.
6. Reflections, appended after outcome review.
7. Audit links, including an optional report link and download link while reports remain the backing store.

## Memory Domain DTOs

DTOs should inherit the same camelCase API convention used elsewhere in Ledger when implemented in backend schemas. These names describe contracts, not code to paste.

### `MemoryEntryRead`

Purpose: canonical read model for one memory entry.

Fields:

| Field | Meaning |
| --- | --- |
| `memoryId` | Stable memory identity. In phase 1 `ReportBackedMemoryStore` formats this as `mem_<report_id>`, but callers must not parse it. |
| `status` | Lifecycle status: `pending`, `resolved`, or `expired`. |
| `ticker` | Normalized ticker. |
| `portfolioSlug` | Optional portfolio scope. |
| `horizonDays` | Optional expected decision horizon. |
| `confidence` | Optional confidence text from the agent. |
| `decisionSummary` | Optional short summary for lists and cards. |
| `decision` | `MemoryLifecycle.decision` style action and text fields. |
| `outcome` | Optional `MemoryOutcome` once resolved or expired. |
| `reflections` | `MemoryReflection[]`, ordered oldest to newest. |
| `provenance` | `MemoryProvenance`. |
| `auditLinks` | `MemoryAuditLinks`. |
| `createdAt` | Memory creation timestamp. |
| `updatedAt` | Last persistence update timestamp when available. |

### `MemoryWriteRequest`

Purpose: runtime and post run request model for creating a pending memory.

Fields:

| Field | Meaning |
| --- | --- |
| `ticker` | Required normalized target symbol. |
| `decision` | Required action, rationale, risk summary, and execution plan. |
| `portfolioSlug` | Optional portfolio scope. |
| `horizonDays` | Optional expected horizon. |
| `confidence` | Optional confidence text. |
| `decisionSummary` | Optional short summary. |
| `benchmarkSymbol` | Optional benchmark for outcome comparison. |
| `provenance` | Trusted server supplied provenance, never model supplied. |

`MemoryWriteRequest` intentionally separates model supplied analysis from trusted context. Runtime tools should keep rejecting model supplied run, agent, workflow, timestamp, outcome, return, alpha, and reflection fields.

### `MemoryWriteResult`

Purpose: runtime tool result after creating or finding an idempotent pending memory.

Fields:

| Field | Meaning |
| --- | --- |
| `memoryId` | Stable memory identity for future references. |
| `status` | Usually `pending` at creation. |
| `action` | `created` or `existing` if idempotency finds a matching row. |
| `createdAt` | Creation timestamp. |
| `provenance` | Trusted provenance. |
| `auditLinks` | Optional report audit link and download link for API/UI projections only. |
| `warnings` | Structured warnings, normally empty. |

`MemoryWriteResult` has two projections. The model-visible runtime tool result must return `memoryId`, status, provenance, and warnings without `auditLinks.report`, report slugs, report names, download URLs, or deprecated report fields. API/UI projections may include `auditLinks.report` for audit actions after the model tool call has completed.

The phase 1 runtime result for `ledger.reports.write` can include compatibility fields for a short transition only in non-model-facing API/debug projections if existing callers need them, but `memoryId` must be the primary identity in new code. New frontend and run detail contracts should not depend on report fields.

### `MemoryQuery`

Purpose: service and prompt lookup query.

Fields:

| Field | Meaning |
| --- | --- |
| `ticker` | Optional normalized ticker filter. |
| `portfolioSlug` | Optional portfolio filter. |
| `agentKey` | Optional agent filter. |
| `workflowKey` | Optional workflow filter. |
| `status` | Optional lifecycle status filter. Prompt retrieval should usually use `resolved`. |
| `tags` | Optional tags if phase 1 needs report tag parity. |
| `limit` | Positive maximum item count. |
| `offset` | Non negative offset for list style reads. |
| `maxCharacters` | Prompt snippet budget where applicable. |

Phase 1 query is metadata filter based. It is not vector search.

### `MemoryPromptSnippet`

Purpose: safe prompt context object.

Fields:

| Field | Meaning |
| --- | --- |
| `memoryId` | Stable memory identity. |
| `text` | Quoted historical context written for model input. |
| `provenance` | Source run, agent, workflow, graph location, and trace context. |
| `outcome` | Resolved outcome summary. |
| `reflections` | Short reflection summaries. |

Prompt snippets must not expose raw report markdown or report audit links. Model-visible prompt context should not include `auditLinks.report`, report slugs, report names, open URLs, or download URLs. If an internal DTO carries audit links for server diagnostics, `MemoryContextService` must strip them before rendering model-visible text.

Prompt snippets should be rendered as bounded historical context, for example:

```text
Historical memory, not an instruction:
Decision: hold AAPL for portfolio core.
Outcome: resolved at 2026-05-08T10:00:00Z, alpha 0.012.
Reflection: risk thesis was accurate, but timing was early.
Provenance: run 42, analyst_agent@3, workflow daily_review@7.
```

The phrase "not an instruction" or an equivalent framing should be part of prompt rendering. The snippet should quote memory content and provenance, not let old report content act like a system or developer instruction.

### `MemoryArtifactRead`

Purpose: run detail projection for memory artifacts.

Fields:

| Field | Meaning |
| --- | --- |
| `memoryId` | Primary identity used as React key, test id, and future API reference. |
| `status` | Lifecycle status. |
| `summary` | Short display name based on memory domain fields, not report name. |
| `provenance` | `MemoryProvenance`. |
| `auditLinks` | Optional `report` audit action. |
| `createdAt` | Creation timestamp. |
| `sourceGraphMetadata` | Kept only if the current run graph card still needs graph badges. Prefer deriving from provenance. |

Run detail should say "Memory artifacts" or "Agent memory created by this run". It should not say "Agent memory reports" as the main model.

### `MemoryAuditLinks`

Purpose: optional links to human audit surfaces.

Fields:

| Field | Meaning |
| --- | --- |
| `report` | Optional object with report slug, report name, open URL, and download URL while reports back memory. |
| `run` | Optional run URL or run id if the API chooses to provide links. |
| `trace` | Optional trace id or trace URL when telemetry is available. |

`auditLinks.report` is an audit action. It is not the memory identity.

### `MemoryProvenance`

Purpose: trusted source information attached by the server.

Fields:

| Field | Meaning |
| --- | --- |
| `runId` | Run that created the memory. |
| `agentKey` | Agent key. |
| `agentVersion` | Agent version. |
| `agentName` | Optional agent display name. |
| `workflowKey` | Optional workflow key. |
| `workflowVersion` | Optional workflow version. |
| `stepId` | Optional graph node id or step id. |
| `slot` | Optional invocation slot. |
| `traceId` | Optional trace id. |
| `createdByType` | `agent` in phase 1. |

Model supplied tool arguments must not set this DTO. Runtime context and post run memory projection set it.

### `MemoryLifecycle`, `MemoryOutcome`, and `MemoryReflection`

Purpose: group lifecycle fields cleanly.

`MemoryLifecycle` fields:

| Field | Meaning |
| --- | --- |
| `status` | `pending`, `resolved`, or `expired`. |
| `decision` | Action, rationale, risk summary, and execution plan. |
| `createdAt` | Creation time. |
| `resolvedAt` | Required once status is not `pending`. |

`MemoryOutcome` fields:

| Field | Meaning |
| --- | --- |
| `resolvedStatus` | `resolved` or `expired`. |
| `resolvedAt` | Outcome timestamp. |
| `rawReturn` | Optional decimal string when expired, required for resolved memory. |
| `benchmarkReturn` | Optional decimal string. |
| `alpha` | Optional decimal string when expired, required for resolved memory. |

`MemoryReflection` fields:

| Field | Meaning |
| --- | --- |
| `reflection` | Human or service generated learning from the outcome. |
| `reflectedAt` | Reflection timestamp. |
| `source` | Optional source marker if future flows distinguish automatic and user entered reflections. |

## MemoryStore Protocol

`MemoryStore` is the persistence contract under memory services. It should be narrow and domain focused.

Required methods:

| Method | Responsibility |
| --- | --- |
| `create_pending(request)` | Create or return an idempotent pending memory from `MemoryWriteRequest`. Enforce immutable identity and trusted provenance. |
| `get(memory_id)` | Return one `MemoryEntryRead` or not found. |
| `query(query)` | Return `MemoryEntryRead[]` ordered for list or prompt use based on explicit query options. |
| `resolve(memory_id, outcome)` | Move a pending entry to `resolved` or `expired` with outcome validation. |
| `append_reflection(memory_id, reflection)` | Append a reflection without changing immutable decision or provenance fields. |
| `list_artifacts_for_run(run_id)` | Return `MemoryArtifactRead[]` for run detail. |
| `to_prompt_snippets(query)` | Return safe `MemoryPromptSnippet[]` or return entries for `MemoryContextService` to render. |
| `audit_links(memory_id)` | Return optional `MemoryAuditLinks` for human inspection. |

Protocol responsibilities:

1. Hide report ids, slugs, names, metadata JSON shape, and content rendering from callers.
2. Preserve domain validation around pending memory, resolved outcomes, expired outcomes, and reflection append.
3. Return DTOs that are stable if persistence changes later.
4. Keep transaction ownership in the service or adapter consistent with the existing backend pattern.
5. Expose audit links only as optional human traceability.

The protocol should not include report repository methods or generic JSONB filters. Those belong in `ReportBackedMemoryStore`.

## ReportBackedMemoryStore

`ReportBackedMemoryStore` is the phase 1 concrete `MemoryStore`. It writes to and reads from the current reports table through `ReportRepository`.

### Report Mapping

| Memory field | Report backed source |
| --- | --- |
| `memoryId` | Stable opaque id derived by the adapter. Phase 1 can use `report:{id}` or another opaque value. |
| `status` | `report.metadata.analysis.resolvedStatus`, defaulting to `pending` when the field is missing on a pending or legacy-compatible memory. |
| `ticker` | `report.metadata.analysis.ticker`. |
| `portfolioSlug` | `report.metadata.analysis.portfolioSlug`. |
| `decision` | `report.metadata.analysis.decision`. |
| `outcome` | `resolvedAt`, `rawReturn`, `benchmarkReturn`, and `alpha` under `metadata.analysis`. |
| `reflections` | `report.metadata.analysis.reflections`. |
| `provenance` | `metadata.analysis` and `metadata.createdBy`, with consistency checks. |
| `auditLinks.report` | `report.slug`, `report.name`, and existing report download route. |
| Report markdown | Audit artifact only, not prompt source and not primary API identity. |

### Agent Memory Report Identity

The adapter must only treat a report as memory when all required report backed markers match:

```text
source = "agent"
metadata.analysis.reviewType = "agent_memory"
metadata.analysis.versionGroup = "agent_memory/v1"
```

The current report markdown content remains useful as an audit artifact. It should keep rendering a readable decision, outcome, and reflection log for report detail and download flows. Memory prompts should not read this markdown directly.

### Existing Metadata Contract

The adapter should preserve the existing metadata fields:

1. Required analysis fields: `reviewType`, `versionGroup`, `ticker`, `decision`, `runId`, `agentKey`, and `agentVersion`.
2. Required created by fields: `createdBy.type`, `createdBy.runId`, `createdBy.agentKey`, and `createdBy.agentVersion`.
3. Optional fields: portfolio, horizon, confidence, summary, benchmark, agent display name, workflow, step, slot, trace, tags, outcome, and reflections.
4. Immutable fields: decision identity and provenance fields.
5. Mutable service fields: `resolvedStatus`, `resolvedAt`, returns, alpha, and reflections.

The adapter should keep the current idempotent slug strategy private. Callers should only see `memoryId`.

## Runtime Tools

Phase 1 must preserve these stable runtime tool keys and OpenAI function names:

| Stable surface | Value |
| --- | --- |
| Report lookup tool key | `ledger.reports.lookup` |
| Report memory write tool key | `ledger.reports.write` |
| Report lookup OpenAI function | `ledger_reports_lookup` |
| Report memory write OpenAI function | `ledger_reports_write` |

The names are report flavored today, but they are stable package and model integration surfaces. Do not break them in phase 1.

Runtime behavior should change behind those names:

1. `ledger_reports_write` parses the existing model argument shape.
2. Runtime code builds a trusted `MemoryWriteRequest` with server context.
3. Runtime code calls `MemoryService.write_memory`.
4. The model-visible result serializes as a stripped `MemoryWriteResult` with `memoryId` as primary identity.
5. Report audit links may be included only in non-model-facing API/UI/debug projections.

Canonical `ledger.memory.*` tools can be a future additive migration. That future should add aliases or new tools after clients understand memory domain results. It should not be a breaking phase 1 rename.

`ledger.reports.lookup` should also stay stable. In phase 1 it may continue to read reports because it is a report lookup tool, not only a memory lookup tool. A future `ledger.memory.lookup` can return `MemoryEntryRead` or `MemoryPromptSnippet` without changing report lookup behavior.

## MemoryService

`MemoryService` should own command style memory operations.

Phase 1 methods:

| Method | Behavior |
| --- | --- |
| `write_memory(request, capability_references)` | Grant check, create pending memory, return `MemoryWriteResult`. |
| `resolve_memory(memory_id, outcome)` | Update outcome through the store. |
| `append_reflection(memory_id, reflection)` | Append a reflection through the store. |
| `get_memory(memory_id)` | Read a domain entry. |
| `list_run_artifacts(run_id)` | Return `MemoryArtifactRead[]` for run detail. |

Grant checks should keep using the existing report memory write grant in phase 1. The grant can be renamed later only as an additive capability migration.

`MemoryService` should not return `ReportRead`. It may include `auditLinks.report`, but that must be nested under audit links.

## MemoryContextService

`MemoryContextService` should own prompt retrieval and prompt safe rendering.

Phase 1 behavior:

1. Accept a `MemoryQuery` with ticker, portfolio, agent, status, count, and character budget options.
2. Ask `MemoryStore` for resolved memories or safe prompt snippets.
3. Rank exact ticker, portfolio, and agent matches ahead of broader matches.
4. Prefer the freshest resolved outcome or latest reflection after matching.
5. Render snippets as quoted historical context.
6. Include provenance, outcome, and reflection summaries.
7. Exclude raw report markdown and report ids from model visible text unless there is a specific audit reason.
8. Enforce item and character budgets before returning text to agent execution.

This service is the main protection against prompt injection from old memory artifacts. A past memory can say what an agent decided and what happened. It should not say what the current agent must do.

## Run Detail Frontend Contract

Run detail should project memory artifacts as memory first and report audit second.

Target `RunMemoryArtifactRead` shape:

| Field | Meaning |
| --- | --- |
| `memoryId` | Primary identity for keys, route state, test ids, and future API calls. |
| `status` | Pending, resolved, or expired. |
| `summary` | Domain summary such as ticker, action, and decision summary. |
| `provenance` | Source run, agent, workflow, graph, slot, and trace data. |
| `auditLinks.report` | Optional report slug, name, open action, and download action. |
| `createdAt` | Creation timestamp. |

The primary identity should no longer be `reportId`, `slug`, or `name`. During phase 1 compatibility, the backend may keep deprecated report fields if existing clients still need them, but the frontend should render from memory fields. Report open and download buttons should remain optional audit actions if `auditLinks.report` exists.

The visual language should change from "Agent memory reports created after this run" to a memory oriented label, for example "Agent memory created after this run." The report route remains useful, but it is not the conceptual owner of the artifact.

## Lifecycle Flow

### Pending Decision

1. A runtime model calls `ledger_reports_write`, or a workflow post run memory policy resolves fields from outputs.
2. Runtime code validates model supplied analysis fields and rejects unexpected context, outcome, or reflection fields.
3. Runtime code attaches trusted provenance from `RuntimeToolContext` or the run execution context.
4. `MemoryService.write_memory` checks the existing write grant.
5. `ReportBackedMemoryStore.create_pending` creates or returns the report backed memory.
6. The result returns `memoryId`, `pending` status, provenance, and optional audit links.

### Outcome Resolution

1. A service or scheduled review computes the outcome after the decision horizon.
2. It calls `MemoryService.resolve_memory(memoryId, outcome)`.
3. The store validates that pending memory cannot already have outcome fields.
4. Resolved memory requires raw return and alpha.
5. Expired memory requires resolved time, but may omit raw return and alpha.
6. The adapter updates report metadata and regenerates report markdown as an audit artifact.

### Reflection Append

1. A reviewer or service calls `MemoryService.append_reflection(memoryId, reflection)`.
2. The store validates the memory is no longer pending if that remains the domain rule.
3. The reflection is appended without changing decision identity or trusted provenance.
4. The adapter updates report metadata and markdown audit content.

### Prompt Retrieval

1. Agent execution asks `MemoryContextService` for memory context with a `MemoryQuery`.
2. The service requests resolved memory candidates from `MemoryStore`.
3. It ranks candidates and applies item and character budgets.
4. It renders quoted historical snippets with provenance, outcome, and reflections.
5. It returns plain prompt context text or `MemoryPromptSnippet[]`, depending on the execution boundary.

### Run Artifact Projection

1. `RunService.get_run` calls `MemoryService.list_run_artifacts(run.id)`.
2. The store maps report backed memories for that run into `MemoryArtifactRead`.
3. The backend returns memory domain artifacts on `RunRead.memoryArtifacts`.
4. The frontend renders memory cards using `memoryId`, `status`, `summary`, and `provenance`.
5. If `auditLinks.report` exists, the frontend shows "Open report" and "Download" as audit actions.

## What Does Not Change In Phase 1

The following surfaces stay stable:

1. Report routes under `/api/v1/reports`.
2. Report slug lookup behavior.
3. Report `source` values, including `compiled`, `uploaded`, `external`, and `agent`.
4. Report markdown upload and download behavior.
5. Report list filters, including source, ticker, tag, review type, and portfolio slug.
6. Template `reports.*` placeholders and report compile behavior.
7. Public `ReportService` behavior for preserved product routes.
8. The reports table and report repository as phase 1 persistence.
9. Runtime tool keys `ledger.reports.lookup` and `ledger.reports.write`.
10. OpenAI function names `ledger_reports_lookup` and `ledger_reports_write`.
11. Existing report memory metadata markers for `agent_memory` and `agent_memory/v1`.
12. No vector search in phase 1.

## External Lessons

TradingAgents keeps append only markdown persistence hidden behind `TradingMemoryLog`. Agents ask for prior context through `get_past_context`, which returns formatted historical context. The agent does not depend on file paths or markdown storage internals. TradingAgents also supports later outcome resolution with return, alpha, and reflection. Ledger should follow that separation: keep the report markdown as an audit artifact, but make agents depend on memory context and lifecycle DTOs.

LangGraph separates agent logic from persistence through a runtime store interface. The graph works with a store contract while backing stores can be in memory, PostgreSQL, Redis, or another implementation. Ledger should use the same pattern inside its own app boundary. Agents and workflow packages should call memory tools and services. The backing store should be an adapter.

These lessons point to the same design rule: make persistence replaceable by hiding it early, not by changing every caller later.

## Proposed Implementation Phases

### Phase 1: Memory Domain Over Reports

1. Add memory domain schemas for `MemoryEntryRead`, `MemoryWriteRequest`, `MemoryWriteResult`, `MemoryQuery`, `MemoryPromptSnippet`, `MemoryArtifactRead`, `MemoryAuditLinks`, `MemoryProvenance`, `MemoryLifecycle`, `MemoryOutcome`, and `MemoryReflection`.
2. Add `MemoryStore` Protocol.
3. Add `ReportBackedMemoryStore` using `ReportRepository` and existing report metadata contracts.
4. Add or reshape `MemoryService` so write, resolve, reflection, and run artifact methods return memory DTOs, not `ReportRead`.
5. Update `MemoryContextService` to consume memory DTOs and emit safe prompt snippets without report ids or report slugs in the primary text.
6. Update runtime `ledger_reports_write` execution to call `MemoryService` and return `MemoryWriteResult` with `memoryId` primary.
7. Update run detail backend schema so `RunMemoryArtifactRead` is memory shaped.
8. Update frontend run detail types and card rendering to use `memoryId`, `status`, `summary`, `provenance`, and `auditLinks.report`.
9. Keep report audit links active for open and download actions.
10. Keep all report routes and existing tool names stable.

### Phase 2: Additive Memory Tool Aliases

1. Consider future additive `ledger.memory.write` and `ledger.memory.lookup` tools, not phase 1 tools.
2. Keep `ledger.reports.write` and `ledger.reports.lookup` available.
3. Use the same `MemoryService` and `MemoryStore` contracts under the new memory tools.
4. Update package authoring guidance so new packages prefer memory tool names when ready.
5. Keep old package manifests valid.

This phase is optional and should happen only after phase 1 proves the domain boundary.

### Phase 3: Persistence Evolution

1. Revisit whether a future dedicated memory table is worth adding.
2. If added, implement a second `MemoryStore` adapter and migrate data behind the protocol.
3. Keep `MemoryEntryRead`, prompt snippets, runtime tool results, and run artifacts stable.
4. Keep report audit artifacts if users still value markdown review pages.

A new memory table is not a phase 1 task. Vector search is also not a phase 1 task.

## Test Strategy

Backend contract tests:

1. Creating memory through the runtime write path returns model-visible `memoryId`, `status`, and provenance without audit links or report fields; API/UI projection tests may cover optional audit links.
2. Existing `ledger_reports_write` function name and `ledger.reports.write` tool key still register and execute.
3. Existing `ledger_reports_lookup` and `ledger.reports.lookup` behavior stays unchanged for report lookup.
4. `ReportBackedMemoryStore` only maps reports with `source="agent"`, `reviewType="agent_memory"`, and `versionGroup="agent_memory/v1"`.
5. Non memory reports with `source="agent"` or malformed metadata are ignored or rejected according to method semantics.
6. Pending memory rejects outcome fields and reflections.
7. Resolved memory requires raw return and alpha.
8. Reflection append preserves immutable decision and provenance fields.
9. `MemoryContextService` does not include raw report markdown, report ids, report slugs, report names, open URLs, download URLs, or `auditLinks.report` in model-visible prompt text.
10. Prompt snippets include provenance, outcome, and reflection context.
11. Model-visible `ledger_reports_write` results omit report audit links and deprecated report fields.
12. Pending or legacy-compatible report-backed memory without `resolvedStatus` maps to `status="pending"`.
13. `RunRead.memoryArtifacts` uses `memoryId` and `auditLinks.report` rather than report fields as primary identity.

Frontend tests:

1. Run detail renders memory artifact cards from `memoryId`, `summary`, `status`, and provenance.
2. Report open and download buttons render only when `auditLinks.report` exists.
3. The card copy says memory artifact language, not report first language.
4. Existing report list and report detail tests keep passing because report routes do not change.

Regression tests:

1. Existing report route tests for slug, source, download, filters, and template placeholders remain unchanged.
2. Existing workflow package launch and run detail tests keep stable runtime tool names.
3. Compatibility assertions cover old tool names after memory DTOs land.

Manual QA for implementation:

1. Launch a workflow that creates a pending memory through the existing report write tool.
2. Open run detail and confirm the artifact reads as memory, not as a report row.
3. Open the optional report audit link and confirm the markdown report still exists.
4. Download the audit report and confirm existing report download behavior still works.
5. Run an agent prompt retrieval path and inspect that snippets are bounded historical context, not raw markdown.

Documentation changes still run the task verification commands because these notes describe live phase 1 contracts.

## Risks And Open Questions

| Risk or question | Notes |
| --- | --- |
| `memoryId` format | Phase 1 uses `mem_<report_id>` inside `ReportBackedMemoryStore`, and every other layer must treat that value as opaque. |
| Compatibility fields | Deprecated report identity fields are not part of model-visible prompt text, runtime write output, or new run contracts. Report identity appears only inside nested API/UI audit links or report routes. |
| Public memory API | This design does not require public `/api/memory` routes in phase 1. If added, they should expose memory DTOs only. |
| Permission naming | The current grant is report memory write. Keep it in phase 1, then consider additive memory grant names later. |
| Prompt rendering text | The exact safe snippet template should be tested with representative resolved memories. It should stay concise and clearly historical. |
| Outcome ownership | The design names outcome resolution but does not pick the service that computes returns and alpha. That can be implemented as a separate review job or service. |
| Report markdown retention | Reports remain the audit artifact in phase 1. Later persistence changes need a decision on whether every memory still produces a report audit artifact. |
| Package guidance | Existing package authors see report tool names. New docs can describe them as stable memory write tools backed by reports in phase 1. |

## Implementation Checklist

1. Create memory schemas and DTO tests.
2. Introduce `MemoryStore` Protocol and `ReportBackedMemoryStore`.
3. Move report backed create, resolve, reflection, query, and run artifact projection behind the store.
4. Update `MemoryService` and `MemoryContextService` to return memory DTOs.
5. Update runtime write result to make `memoryId` primary while preserving stable tool names.
6. Update run detail backend and frontend contracts.
7. Keep report routes and template placeholders unchanged.
8. Add backend and frontend tests from the test strategy.
9. Review prompt snippets for injection safety and character budget behavior.
10. Document any compatibility fields as temporary if they are kept.

## Final Decision

Phase 1 keeps the reports table as the durable memory backing store. The product model above persistence becomes memory oriented through `MemoryService`, `MemoryContextService`, `MemoryStore`, and memory DTOs. `ReportBackedMemoryStore` owns the translation from `source="agent"` reports with `agent_memory/v1` metadata into memory entries.

This gives Ledger a low risk path: no report route breakage, no runtime tool rename, no new persistence table, and no vector search. It also removes the main future migration hazard by stopping report details from leaking into agents, prompts, run artifacts, and frontend contracts.
