# FRONTEND SHARED TYPES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/lib/AGENTS.md`.

## OVERVIEW
`src/lib/types/` mirrors the backend wire contracts for portfolios, balances, positions, market data, templates, reports, CSV import, trading operations, orchestration, runtime, Studio, and Tryout. Treat these files as the shared schema boundary between frontend UI and backend API.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Portfolio/balance/position types | `portfolio.ts`, `balance.ts`, `position.ts` | CRUD payloads plus read models |
| Trading payload unions | `trading.ts` | BUY/SELL/DIVIDEND/SPLIT request shapes |
| Orchestration contracts | `orchestration.ts` | role/character read models, create/update inputs, mention catalog items |
| Runtime contracts | `runtime.ts` | runtime runs, artifacts, approvals, trace events, caller filters |
| Studio contracts | `studio.ts` | workflow/agent/persona/capability list/detail reads plus lifecycle inputs |
| Tryout contracts | `tryout.ts` | execute/read/persist payloads tied to runtime run ids |
| Market data types | `market-data.ts` | quote/history payloads and warnings |
| Template contract | `text-template.ts` | template CRUD, compile, runtime-input maps, placeholder tree |
| Report contract | `report.ts` | slug-based report reads, metadata, update input |
| Shared helpers | `common.ts`, `csv.ts` | common ids/timestamps and CSV preview shapes |

## CONVENTIONS
- Keep frontend field names aligned with backend camelCase aliases; do not reintroduce snake_case here.
- Money, quantities, market values, and similar numeric payloads stay as strings on the wire; conversion belongs in shared formatting/analytics helpers, not in the type layer.
- Model enum-like values as exact string unions so invalid report sources, trading sides, orchestration mention kinds, runtime approval statuses, or Studio lifecycle states fail at compile time.
- Use these files for API shapes only; derive view models separately when the UI needs extra formatting or enrichment.
- Unknown report metadata keys are allowed by the backend; preserve extensibility in `report.ts` instead of narrowing metadata too aggressively.
- Runtime wire contracts must mirror the current backend contract exactly, including approval actions, trace events, and artifact reads.
- Studio wire contracts intentionally separate managed drafts and lifecycle transitions from read-only seeded or imported catalog entries.
- Orchestration types should mirror backend role/character schemas exactly, including mention catalog items and role linkage.
- Tryout types should stay tied to runtime run ids, execute payloads, and persist results rather than inventing page-local shapes.

## ANTI-PATTERNS
- Do not declare ad-hoc wire types inside hooks or page components.
- Do not collapse backend distinctions such as slug-based report lookup vs numeric portfolio ids or numeric runtime run ids.
- Do not collapse Studio lifecycle states into generic strings; list/editor flows depend on the exact unions.
- Do not convert decimal strings to numbers at the type layer.
- Do not change template/report placeholder tree shapes without coordinating backend schemas, hooks, and tests.
- Do not loosen orchestration identifiers, runtime approval payloads, or Tryout target shapes just to make forms easier.

## NOTES
- The orchestration schema is separate from runtime and Tryout; it supports reusable role/character configuration, not run-state inspection.
- Runtime and Studio types intentionally overlap on run, artifact, approval, and trace payloads because the product exposes those views in multiple route families.
- Keep route forms, hook inputs, and shared type names in sync when orchestration, runtime, Studio, or Tryout fields change.
