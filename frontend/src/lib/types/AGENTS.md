# FRONTEND SHARED TYPES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/lib/AGENTS.md`.

## OVERVIEW
`src/lib/types/` mirrors the backend wire contracts for portfolios, balances, positions, market data, templates, reports, CSV import, trading operations, Extensions, Workflow Packages, Tools, Model Connections, and Runs. Treat these files as the shared schema boundary between frontend UI and backend API.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Portfolio, balance, and position types | `portfolio.ts`, `balance.ts`, `position.ts` | preserved product CRUD payloads plus read models |
| Trading payload unions | `trading.ts` | BUY, SELL, DIVIDEND, and SPLIT request shapes |
| Market data types | `market-data.ts` | quote, history, and warning payloads |
| Template contract | `text-template.ts` | template CRUD, compile payloads, runtime-input maps, and placeholder tree |
| Report contract | `report.ts` | slug-based report reads, metadata, and update input |
| Shared helpers | `common.ts`, `csv.ts` | common ids, timestamps, and CSV preview shapes |
| Extension state contract | `extension.ts` | bundled extension `key`, `label`, `enabled`, and toggle payloads |
| Workflow Package contracts | `workflow-package.ts` | package manifests, versions, diagnostics, preflight, launch, import, and export payloads |
| Platform catalog and binding contracts | `tool.ts`, `model-connection.ts` | read-only tool metadata and saved model connection payloads |
| Platform execution contracts | `run.ts` | run list/detail, monitor payloads, and package provenance |

## CONVENTIONS
- Keep frontend field names aligned with backend camelCase aliases; do not reintroduce snake_case here.
- Money, quantities, market values, and similar numeric payloads stay as strings on the wire; conversion belongs in shared formatting and analytics helpers, not in the type layer.
- Model enum-like values as exact string unions so invalid report sources, trading sides, and platform status values fail at compile time.
- Use these files for API shapes only; derive view models separately when the UI needs extra formatting or enrichment.
- Unknown report metadata keys are allowed by the backend; preserve extensibility in `report.ts` instead of narrowing metadata too aggressively.
- Keep route forms, hook inputs, extension-state consumers, and shared type names aligned with the current backend contract.
- Extension state types must stay slim. Do not add plugin-manifest fields, scaffold data, reason text, categories, version policy, or state counters to `extension.ts`.
- Run memory evidence is phase-1 core memory shaped: `memoryEvents` carries the full event stream, `memoryArtifacts` is the compact artifact slice, and `memoryId` is an opaque string. Optional report actions live only under `auditLinks.report`; frontend types must not derive report slugs, report downloads, or route paths from `memoryId`.
- Frontend phase 1 has run memory evidence types only; there is no vector search, embeddings, chunk table, or public browser `/api/memory` shape.

## ANTI-PATTERNS
- Do not declare ad-hoc wire types inside hooks or page components.
- Do not collapse backend distinctions such as slug-based report lookup vs numeric portfolio ids or versioned platform references.
- Do not convert decimal strings to numbers at the type layer.
- Do not change template, report, extension, or agent-platform payload shapes without coordinating backend schemas, hooks, and tests.

## NOTES
- These files cover the preserved product routes plus the current agent-platform routes; retired orchestration, Studio, Tryout, and runtime-v2 types do not ship here.
- Keep route forms, hook inputs, extension-state consumers, and shared type names in sync when preserved product or platform fields change.
