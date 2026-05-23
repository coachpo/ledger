# SignalDeck Memory Layer Design Note

> Status: Core memory infrastructure phase-1 contract for branch `main` at `f9ae90d`.

## Scope

SignalDeck memory is platform-core infrastructure for Workflow Package runs. The phase-1 contract is neutral: callers write and look up memory by `kind`, `summary`, `content`, `subjectRefs`, `attributes`, scope, status, revision, and provenance. Finance-specific concepts can appear only as extension-owned attributes or subject references; they are not required core fields.

This note covers the phase-1 contract now represented in `backend/app/schemas/memory.py`:

1. Memory IDs and revision IDs are opaque.
2. Writes create immutable revisions or reuse an exact duplicate active revision.
3. Lookup is bounded and scoped, with a safe current-context fallback.
4. Runtime tool names are `signaldeck.memory.write` and `signaldeck.memory.lookup`.
5. Exact-id `signaldeck.memory.get` is deferred to phase 1b.

There is still no public browser `/api/memory` CRUD surface in this phase. The implementation path is package-first runtime memory, not standalone global agents or retired authoring surfaces.

## Live Contract Files

| Area | Live files |
| --- | --- |
| Core memory schemas | `backend/app/schemas/memory.py` |
| Schema contract tests | `backend/tests/test_memory_domain_schemas.py` |
| Tool contract guardrails | `backend/tests/test_tool_catalog_api.py` |
| Persistence owner | `backend/app/db/`, `backend/app/models/`, `backend/app/repositories/` |
| Runtime-tool owner | `backend/app/agents/` |
| Run evidence owner | `backend/app/schemas/run.py`, `backend/app/services/run_service.py` |

## Core DTO Contract

Memory DTOs use SignalDeck's camelCase API convention externally and snake_case internally. All schemas inherit `CamelModel`, so extra request fields remain forbidden.

The required core write fields are:

| Field | Purpose |
| --- | --- |
| `kind` | Neutral memory category such as `observation`, `research.note`, or extension-defined values. |
| `summary` | Short model-safe summary for cards, snippets, and run evidence. |
| `content` | Canonical memory text used for deterministic lexical lookup before pgvector lands. |
| `subjectRefs` | Optional neutral references to subjects such as packages, portfolios, documents, users, or instruments. |
| `attributes` | Optional JSON metadata; extension-specific fields live here instead of top-level core fields. |
| `scope` | Required write scope with `scopeType` and `scopeKey`. |
| `provenance` | Trusted server context for run, agent, workflow, step, slot, and trace. |

The core contract does not require `ticker`, `action`, `benchmarkSymbol`, `rawReturn`, `alpha`, report slugs, report URLs, download URLs, or `auditLinks`.

## Revision Semantics

Every content-changing write creates a new immutable revision. The write request carries an explicit revision policy:

```text
mode = "immutable-revision-per-content-change"
duplicateContent = "reuse-existing-active-revision"
```

If an exact duplicate active revision already exists, the write returns that revision with `revisionAction="reused"`. A new content revision returns `revisionAction="created"`. Superseding a prior revision is explicit through `supersedesRevisionId` and returns `revisionAction="superseded"`.

Shared-scope revision mutations acquire the memory entry row before reading latest revision state. Concurrent broader-scope mutations have one canonical winner; lock contention returns a retryable `409` with `code="memory_revision_conflict"`, so callers can re-read the latest revision and retry.

`MemoryWriteResult` returns `memoryId`, `revisionId`, status, `revisionAction`, created time, provenance, revision metadata, idempotency semantics, and warnings. It does not expose the old generic `action` field.

## Idempotency

Writers may provide `idempotencyKey`. If they omit it, phase 1 uses this deterministic fallback identity:

```text
(scope_type, scope_key, kind, content_hash, source_run_id, source_agent_key, source_step_id, source_slot)
```

`content_hash` is the SHA-256 hash of the canonical `content` string. The fallback intentionally includes trusted provenance so two agents can write the same text in different run slots without accidental collision, while exact repeat calls from the same slot reuse the existing active revision.

## Lookup Scope and Budgets

`signaldeck.memory.lookup` is never an unscoped global search. A request can provide explicit selectors through `scope`, `subjectRefs`, or `kind`. Runtime broader scopes are canonicalized by server context: `package` resolves to the current package key, while `workflow` and `agent` resolve to package-qualified `package:local` keys. Raw provenance still records the run, workflow, agent, step, and slot that produced the memory.

When selectors are omitted, the server binds lookup to the current run/package/agent context only, represented in schema outputs as:

```text
scopeMode = "current-context-fallback"
fallbackScope = "current-run-package-agent"
```

Explicitly scoped lookups serialize as `scopeMode="explicit-selectors"`.

Phase-1 lookup budgets are fixed in the schema contract:

| Budget | Default | Hard cap |
| --- | ---: | ---: |
| `limit` | 5 | 20 |
| `maxCharacters` | 4000 | 8000 |

Requests above those caps fail validation. Phase-1 ranking is deterministic: scope specificity first, lexical PostgreSQL ranking over `content`, revision creation time descending, then `memoryId` ascending as the final tie-breaker. pgvector can accelerate retrieval later, but canonical memory remains in Postgres entries and revisions.

## Runtime Tools

The phase-1 core memory tool keys are:

| Stable surface | Value |
| --- | --- |
| Core memory write tool key | `signaldeck.memory.write` |
| Core memory lookup tool key | `signaldeck.memory.lookup` |
| Exact-id get tool | Deferred to phase 1b (`signaldeck.memory.get`) |

These tools are platform-core, not finance-extension tools. They must remain available when `signaldeck.finance` is disabled. `signaldeck.reports.write` is not the canonical memory write surface for the core contract.

## Model-Safe Projection

Model-visible memory outputs can include `memoryId`, `revisionId`, `status`, `kind`, `summary`, `content`, `subjectRefs`, `attributes`, `scope`, provenance, and warnings. They must not include report ids, report slugs, report names, report routes, download URLs, raw markdown, or `auditLinks`.

`MemoryPromptSnippet` is safe prompt context. It frames old memory as historical context, not a system or developer instruction.

`RunMemoryEventRead` is the full run-detail evidence stream for retrieval, injection, write/reuse, supersede, review, and failure facts persisted in `run_memory_events`. `MemoryArtifactRead` is only the compact run-detail write slice assembled from canonical memory events and rows.

## What Stays Stable

1. Workflow Packages remain the only live executable workflow entry point.
2. There is no public `/api/memory` CRUD route in phase 1.
3. `memoryId` and `revisionId` are opaque outside the memory store.
4. Reports remain ordinary report-domain artifacts; they are not the memory substrate.
5. Core memory must operate with the Finance Workspace extension disabled.
6. pgvector, embeddings, and chunk tables are phase-2 accelerators, not the source of truth.

## Guardrails

1. Do not add finance-only fields as required top-level core memory fields.
2. Do not allow unscoped global lookup.
3. Do not let package-local workflow or agent scope keys collide across packages.
4. Do not treat shared-memory mutation conflicts as generic server errors; callers should retry after reading the latest revision.
5. Do not use reports as the canonical memory persistence substrate.
6. Do not expose report identity or raw markdown in model-visible memory outputs.
7. Do not register core memory tools through finance-owned registrars.
8. Do not ship exact-id `get` until a concrete phase-1b flow proves the need.

## Verification Targets

Use focused backend and frontend contract tests when this layer changes:

```bash
(cd backend && uv run pytest tests/test_memory_domain_schemas.py tests/test_tool_catalog_api.py tests/test_memory_service.py tests/test_runtime_tools.py tests/test_workflow_package_run_contracts.py -k "memory or run_detail_exposes_persisted_memory_event_evidence")
(cd frontend && pnpm test:run src/pages/runs/detail.test.tsx)
```

The stale-claim guard should confirm live docs and targeted tests no longer describe reports as the canonical memory substrate.
