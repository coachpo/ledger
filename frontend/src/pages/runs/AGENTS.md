# FRONTEND RUNS PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/runs/` contains the routed run inventory and run detail views. The list page acts as a polling monitor, and the detail page exposes progress, usage, root-parameter rerun, invocation-specific fork actions, trace linkage, and per-agent accordion drilldowns.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are retired/archive context, not live acceptance paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Run inventory | `list.tsx` | filters, polling monitor, progress, token usage, and timing summary |
| Run detail | `detail.tsx` | progress cards, rerun dialog, invocation-specific fork dialog, legacy replay lineage labels, trace linkage, final output, and per-agent accordion |
| Run hooks | `../../hooks/use-runs.ts` | list/detail queries, rerun draft/create hooks, fork draft/create hooks, and refetch intervals |
| Shared formatting | `../../lib/format.ts`, `../platform-resource-shared.tsx` | timestamps and JSON helpers |
| Run types | `../../lib/types/run.ts` | run status, step-agent reads, fork read/write contracts, legacy replay lineage, and trace fields |

## CONVENTIONS
- `list.tsx` keeps workflow-key and status filters local to the page and refetches on a timer.
- `detail.tsx` computes progress from step outputs and keeps trace linkage visible even when the top-level trace id is missing.
- Run detail renders `memoryEvents` as the canonical run-scoped evidence stream and `memoryArtifacts` as the compact artifact slice. Artifact `memoryId` values are opaque. Report open/download actions are optional audit actions sourced from `artifact.auditLinks.report.url` and `artifact.auditLinks.report.downloadUrl`, never derived from `memoryId`.
- Per-agent details stay inside the accordion so the page can expose the full run without flattening the layout.
- Rerun is the only root-parameter editor. It opens from `rerun=1` and uses rerun draft/create hooks.
- Fork actions are invocation-specific. Open them from agent invocation rows, use URL state `fork=1&resumeStepIndex=<n>&invocationId=<id>`, fetch drafts by `sourceInvocationId`, and submit full replacement `invocationInput`.
- Treat `resumeStepIndex` as the execution boundary only. Do not use it as the editable target when an invocation id is required.
- Operation and tool invocation forks are unsupported in phase 1. Show that limitation on operation rows instead of exposing ambiguous step-wide fork actions.
- Legacy replay data is read-only lineage. Label it as legacy when rendered, and do not wire `stepReplay`, `stepIndex`, `step-replay-draft`, or `step-replays` as live run creation paths.
- Hooks own the polling query behavior, while the page owns presentation, filters, fork URL state, and trace summaries.

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
