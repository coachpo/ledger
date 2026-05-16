# SignalDeck Memory Layer Design Note

> Status: Phase 1 memory layer notes for branch `main` at `987686e`.

## Scope

SignalDeck's live agent memory layer stores durable memory as reports, but callers work with memory-domain services and DTOs. Reports remain the backing store and audit surface for phase 1. The product model above persistence is memory-first.

This note covers the shipped phase 1 boundary:

1. Memory writes and reads go through `MemoryService`.
2. Persistence goes through the `MemoryStore` Protocol.
3. The concrete adapter is `ReportBackedMemoryStore`.
4. Prompt context goes through `MemoryContextService`.
5. Run detail exposes memory artifacts, with report links only as audit actions.

There is no public `/api/memory` route, no memory table, no vector search, and no embeddings in phase 1.

## Live Implementation

| Area | Live files |
| --- | --- |
| Domain schemas | `backend/app/schemas/memory.py`, `backend/app/schemas/memory_report.py` |
| Service boundary | `backend/app/services/memory_service.py` |
| Store contract | `backend/app/services/memory_store.py` |
| Report-backed adapter | `backend/app/services/report_backed_memory_store.py` |
| Prompt context | `backend/app/services/memory_context_service.py` |
| Runtime tools | `backend/app/agents/runtime_tools/reports.py`, `backend/app/agents/runtime_tools/types.py` |
| Run API | `backend/app/schemas/run.py`, `backend/app/services/run_service.py` |
| Frontend run detail | `frontend/src/lib/types/run.ts`, `frontend/src/pages/runs/detail.tsx` |
| Contract tests | `backend/tests/test_memory_domain_schemas.py`, `backend/tests/test_memory_service.py`, `backend/tests/test_report_backed_memory_store.py`, `backend/tests/test_runtime_tools.py`, `backend/tests/test_memory_layer_static_contracts.py`, `frontend/src/pages/runs/detail.test.tsx` |

## Data Model

Phase 1 memory is a domain object backed by a report row.

A memory report is identified by these persisted markers:

```text
source = "agent"
metadata.analysis.reviewType = "agent_memory"
metadata.analysis.versionGroup = "agent_memory/v1"
metadata.createdBy.type = "agent"
```

`ReportBackedMemoryStore` owns the conversion between report rows and memory DTOs. It is also the only place that parses or formats the current `memoryId` value, `mem_<report_id>`. Every other layer treats `memoryId` as opaque.

Report markdown remains a human audit artifact for report detail and download flows. It isn't the prompt source, the API identity, or the frontend card model.

## Service Boundaries

`MemoryService` is the command boundary for memory work. It checks memory write grants, creates pending memories, reads one memory entry, resolves outcomes, appends reflections, queries prompt snippets, and lists run artifacts.

`MemoryStore` defines the persistence contract:

| Method | Responsibility |
| --- | --- |
| `create_pending` | Create or return an idempotent pending memory. |
| `get` | Return one `MemoryEntryRead` by opaque memory id. |
| `query` | Return bounded `MemoryPromptSnippet` values. |
| `resolve` | Move a memory to resolved or expired with outcome data. |
| `append_reflection` | Add a reflection without changing the original decision or provenance. |
| `list_artifacts_for_run` | Return memory artifacts for run detail. |
| `audit_links` | Return optional report links for human review. |

`ReportBackedMemoryStore` implements that contract using `ReportRepository` and the reports table. It hides report ids, slugs, names, markdown rendering, and metadata JSON details from callers above the adapter.

## DTO Contract

Memory DTOs use SignalDeck's camelCase API convention.

`MemoryEntryRead` is the full memory read model. It includes `memoryId`, `status`, ticker and portfolio scope, decision text, optional outcome, reflections, provenance, audit links, and timestamps.

`MemoryWriteRequest` is the trusted write input built from runtime tool arguments plus server context. Model-supplied arguments provide the decision analysis. Trusted provenance, run ids, agent keys, workflow keys, graph node ids, trace ids, outcome fields, and reflections come from the server.

`MemoryWriteResult` is the runtime write result. Model-visible output includes `memoryId`, `status`, action, created time, provenance, and warnings. It omits report ids, slugs, names, URLs, downloads, and `auditLinks`.
`MemoryPromptSnippet` is safe prompt context. It carries bounded historical memory text, provenance, outcome context, and reflections. It must not include raw report markdown, report identity, report routes, download URLs, or audit links.

`MemoryArtifactRead` is the run detail projection. It includes `memoryId`, `summary`, `status`, `createdAt`, provenance, optional graph metadata, and optional `auditLinks.report`.

`MemoryAuditLinks` holds optional human audit links. In phase 1 the useful link is the backing report open/download pair.

## Runtime Tools

The stable runtime tool keys and OpenAI function names stay unchanged:

| Stable surface | Value |
| --- | --- |
| Report lookup tool key | `signaldeck.reports.lookup` |
| Report memory write tool key | `signaldeck.reports.write` |
| Report lookup OpenAI function | `signaldeck_reports_lookup` |
| Report memory write OpenAI function | `signaldeck_reports_write` |

The names are report flavored because existing package manifests and tool grants depend on them. The write path now returns memory-shaped results through `MemoryService`. Future `signaldeck.memory.*` tools would be additive, not a phase 1 rename.

`signaldeck.reports.lookup` remains a report lookup tool. Memory prompt context is handled by `MemoryContextService`, not by sending raw report markdown into model prompts.

## Prompt Context

`MemoryContextService` owns model-safe prompt rendering. It accepts `MemoryQuery`, asks the store for memory snippets, applies item and character budgets, and renders historical context with provenance, outcome, and reflection details.

Prompt snippets should frame old memory as history, not instructions. A past decision can say what an agent chose and what happened. It cannot direct the current agent as system or developer content.

The model-visible context excludes report ids, report slugs, report names, report URLs, download URLs, `auditLinks.report`, and raw markdown.

## Run Detail Artifacts

`RunService.get_run` calls `MemoryService.list_run_artifacts` and returns memory artifacts on `RunRead.memoryArtifacts`. The frontend run detail card renders `memoryId`, `summary`, `status`, `createdAt`, provenance, and graph context.

If `auditLinks.report` exists, the frontend shows report open and download actions. Those are audit actions only. The primary identity is still `memoryId`.

Frontend run types expose memory artifacts with `memoryId`, `summary`, `status`, provenance, optional `sourceGraphMetadata`, and optional report audit links.

## What Stays Stable

1. Report routes stay under `/api/v1/reports`.
2. Report slug lookup, filters, upload, download, and markdown behavior stay unchanged.
3. Report `source` values remain `compiled`, `uploaded`, `external`, and `agent`.
4. Template `reports.*` placeholders and compile behavior stay unchanged.
5. Runtime tool keys stay `signaldeck.reports.lookup` and `signaldeck.reports.write`.
6. OpenAI function names stay `signaldeck_reports_lookup` and `signaldeck_reports_write`.
7. Memory reports keep `agent_memory` and `agent_memory/v1` metadata markers.

## Guardrails

1. Keep `memoryId` opaque outside `ReportBackedMemoryStore`.
2. Don't expose report identity in model-visible memory outputs.
3. Don't use report markdown as prompt memory content.
4. Don't add a public memory API until it can expose memory DTOs only.
5. Don't rename stable report tool keys during phase 1.
6. Don't add vector search or embeddings to the phase 1 contract.

## Verification Targets

Use the memory and run contract tests when code changes touch this layer:

```bash
(cd backend && uv run pytest tests/test_memory_domain_schemas.py tests/test_memory_service.py tests/test_report_backed_memory_store.py tests/test_runtime_tools.py tests/test_memory_layer_static_contracts.py)
(cd frontend && pnpm test:run src/pages/runs/detail.test.tsx)
```

Manual product checks for memory changes are run detail first: launch a workflow that writes memory, open the run detail page, confirm memory cards render from memory fields, open the optional audit report, and download the report from the audit action.
