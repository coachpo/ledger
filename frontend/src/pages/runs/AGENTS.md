# FRONTEND RUNS PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW

`src/pages/runs/` contains the routed run inventory and run detail views. The list page acts as a polling monitor, and the detail route has grown into the execution evidence surface: progress, usage, lineage diagrams, root-parameter rerun, invocation-specific fork actions, trace linkage, inspection panes, memory event groups, memory artifacts, and per-agent/per-operation drilldowns.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative old paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or non-goal surfaces, not live acceptance paths.

## WHERE TO LOOK

| Task               | Location                                                              | Notes                                                                                                                                                                     |
| ------------------ | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Run inventory      | `list.tsx`                                                            | filters, polling monitor, progress, token usage, and timing summary                                                                                                       |
| Run detail         | `detail.tsx`, `detail-sections/AGENTS.md`                             | progress cards, lineage diagrams, inspection panes, rerun dialog, invocation-specific fork dialog, trace linkage, final output, memory evidence, and per-agent accordions |
| Fork/rerun helpers | `rerun-dialog.tsx`, `inspection-state.ts`, `detail-tabs.ts`            | root-parameter rerun modal plus URL-backed inspection-pane and tab state                                                                                                  |
| Run hooks          | `../../hooks/use-runs.ts`                                             | list/detail queries, rerun draft/create hooks, fork draft/create hooks, and refetch intervals                                                                             |
| Shared formatting  | `../../lib/format.ts`, `../platform-resource-shared.tsx`              | timestamps, badges, and JSON helpers                                                                                                                                      |
| Route coverage     | `list.test.tsx`, `detail.test.tsx`, `detail-tabs.test.ts`, `detail-http-operations.test.tsx`, `detail-sections.exports.test.ts` | list polling, detail rendering, URL tab resolution, fork/rerun behavior, HTTP operation coverage, and detail-section export contract |

## CONVENTIONS

- `list.tsx` keeps target-kind, target-key, and status filters local to the page and refetches on a timer while any run is queued or running.
- Run list and detail render backend `run.progress` and nullable `run.queue`; do not recreate status-to-percent or queued-reason heuristics in the page layer. Keep trace linkage visible even when the top-level trace id is missing.
- Run detail renders `memoryEvents` as the canonical run-scoped evidence stream and `memoryArtifacts` as the compact artifact slice. Artifact `memoryId` values are opaque. Report open/download actions are optional audit actions sourced from `artifact.auditLinks.report.url` and `artifact.auditLinks.report.downloadUrl`, never derived from `memoryId`.
- Memory event presentation is grouped into retrieved context, memory writes/reuse, review/follow-up, and audit-trail panes; keep those groupings route-owned instead of flattening everything into one raw event list.
- Per-agent and per-operation details stay inside accordions/inspection panes so the page can expose the full run without flattening the layout.
- Run detail expects ref-based invocation payloads such as `agentRef` and `outputSchemaRef`, not scalar internal ids.
- Rerun is the only root-parameter editor. It opens from `rerun=1` and uses rerun draft/create hooks.
- Fork actions are invocation-specific. Open them from agent invocation rows, use URL state `fork=1&resumeStepIndex=<n>&invocationId=<id>`, fetch drafts by `sourceInvocationId`, and submit full replacement `invocationInput`.
- Treat `resumeStepIndex` as the execution boundary only. Do not use it as the editable target when an invocation id is required.
- Operation and tool invocation forks are unsupported in phase 1. Show that limitation on operation rows instead of exposing ambiguous step-wide fork actions.
- Historical replay data is read-only lineage. Label it as historical when rendered, and do not wire `stepReplay`, `stepIndex`, `step-replay-draft`, or `step-replays` as live run creation paths.
- Hooks own polling and request behavior; the page owns presentation, filters, URL state, inspection panes, fork availability messaging, and trace summaries.
- Route metadata intentionally treats `/runs` as an `inventory` polling monitor with scroll shell and `/runs/:runId` as a `console` with full-height shell. Preserve that split instead of turning run detail into a generic detail page.
- Wide evidence, trace ids, JSON payloads, operation URLs, badges, and lineage nodes must use internal scrolling or wrapping so mobile viewports do not gain document-level horizontal overflow.

## ANTI-PATTERNS

- Do not move polling controls out of the list page.
- Do not hide trace linkage behind a single summary string when span references exist.
- Do not bypass the hook layer for run reads, reruns, or forks.
- Do not collapse per-agent detail or evidence panes into one monolithic block.
- Do not derive report links or editable fork targets from opaque `memoryId` or `resumeStepIndex` values alone.

## VALIDATION

```bash
cd frontend
pnpm test:run src/pages/runs/list.test.tsx src/pages/runs/detail.test.tsx src/pages/runs/detail-tabs.test.ts src/pages/runs/detail-http-operations.test.tsx
```

## NOTES

- The detail page uses URL-backed route state for rerun, fork, selected tabs, and inspection-pane views so deep links can reopen the same context.
- Fork edits one selected agent invocation input only; rerun edits root launch parameters only.
