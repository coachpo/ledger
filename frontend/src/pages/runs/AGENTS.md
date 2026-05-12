# FRONTEND RUNS PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/runs/` contains the routed run inventory and run detail views. The list page acts as a polling monitor, and the detail page exposes progress, usage, rerun/step-replay flows, trace linkage, and per-agent accordion drilldowns.

The application is under active development and has no users at the moment; future upgrade, migration, and compatibility design must account for that and should not preserve speculative legacy paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Run inventory | `list.tsx` | filters, polling monitor, progress, token usage, and timing summary |
| Run detail | `detail.tsx` | progress cards, rerun/step-replay actions, trace linkage, final output, and per-agent accordion |
| Run hooks | `../../hooks/use-runs.ts` | list/detail queries and refetch intervals |
| Shared formatting | `../../lib/format.ts`, `../platform-resource-shared.tsx` | timestamps and JSON helpers |
| Run types | `../../lib/types/run.ts` | run status, step-agent reads, and trace fields |

## CONVENTIONS
- `list.tsx` keeps workflow-key and status filters local to the page and refetches on a timer.
- `detail.tsx` computes progress from step outputs and keeps trace linkage visible even when the top-level trace id is missing.
- Run detail renders memory artifacts by opaque `memoryId`. Report open/download actions are optional audit actions sourced from `artifact.auditLinks.report.url` and `artifact.auditLinks.report.downloadUrl`, never derived from `memoryId`.
- Per-agent details stay inside the accordion so the page can expose the full run without flattening the layout.
- Hooks own the polling query behavior, while the page owns presentation, filters, and trace summaries.

## ANTI-PATTERNS
- Do not move polling controls out of the list page.
- Do not hide trace linkage behind a single summary string when span references exist.
- Do not bypass the hook layer for run reads.
- Do not collapse per-agent detail into a single monolithic block.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```
