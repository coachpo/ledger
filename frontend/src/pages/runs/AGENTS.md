# FRONTEND RUNS PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW

`src/pages/runs/` contains the routed run inventory and run detail views. The list page acts as a polling monitor, and the detail route has grown into the execution evidence surface: progress, usage, source-run rerun provenance, root-parameter rerun, trace linkage, inspection panes, and per-agent/per-operation drilldowns.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative old paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or non-goal surfaces, not live acceptance paths.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK

| Task               | Location                                                              | Notes                                                                                                                                                                     |
| ------------------ | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Run inventory      | `list.tsx`                                                            | filters, polling monitor, progress, token usage, and timing summary                                                                                                       |
| Run detail         | `detail.tsx`, `detail-sections/AGENTS.md`                             | progress cards, source-run rerun provenance, inspection panes, rerun dialog, trace linkage, final output, and per-agent accordions |
| Rerun helpers      | `rerun-dialog.tsx`, `inspection-state.ts`, `detail-tabs.ts`            | root-parameter rerun modal plus URL-backed inspection-pane and tab state                                                                                                  |
| Run hooks          | `../../hooks/use-runs.ts`                                             | list/detail queries, rerun draft/create hooks, and refetch intervals                                                                             |
| Shared formatting  | `../../lib/format.ts`                                                 | timestamps and JSON helpers                                                                                                                                               |
| Route coverage     | `list.test.tsx`, `detail-tabs.test.ts`, `detail-http-operations.test.tsx`, `detail-sections.exports.test.ts`, `frontend/e2e/runs.spec.ts` | list polling, URL tab resolution, rerun behavior, HTTP operation coverage, detail-section export contract, and routed detail coverage |

## CONVENTIONS

- `frontend/DESIGN.md` is the source of truth for this route family's page layout, shared shells, tokens, and management UI patterns.
- Because `/runs` is metadata `inventory`, `list.tsx` must use the `DESIGN.md` inventory-page pattern: `InventoryPageShell`, `PageContextBar`, `ResourceToolbar`, optional `ResourceFilterBar`, shared state panels, `ResourceTableFrame` or approved shared list/card primitives, action helpers where present, and `ResourceStatusBadge`/`ResourceStatusStrip` for statuses.
- The `/runs/:runId` metadata `console` route is full-height and must use the `DESIGN.md` `WorkspacePageShell` guidance, not inventory shell chrome.
- Inventory chrome must not be replaced with `WorkspacePageShell`, route-local page wrappers, custom toolbar/filter cards, dashed empty states, or one-off `rounded-md border bg-muted/*` / `shadow-sm` page chrome.
- `list.tsx` keeps target-kind, target-key, and status filters local to the page and refetches on a timer while any run is queued or running.
- Run list and detail render backend `run.progress` and nullable `run.queue`; do not recreate status-to-percent or queued-reason heuristics in the page layer. Keep trace linkage visible even when the top-level trace id is missing.
- Per-agent and per-operation details stay inside accordions/inspection panes so the page can expose the full run without flattening the layout.
- Run detail expects ref-based invocation payloads such as `agentRef` and `outputSchemaRef`, not scalar internal ids.
- Rerun is the only root-parameter editor. It opens from `rerun=1` and uses rerun draft/create hooks.
- Rerun source-run metadata is read-only provenance. Keep rerun creation on the current `rerun` URL state.
- Hooks own polling and request behavior; the page owns presentation, filters, URL state, inspection panes, and trace summaries.
- Route metadata intentionally treats `/runs` as an `inventory` polling monitor with scroll shell and `/runs/:runId` as a `console` with full-height shell. Preserve that split instead of turning run detail into a generic detail page.
- Wide evidence, trace ids, JSON payloads, operation URLs, and badges must use internal scrolling or wrapping so mobile viewports do not gain document-level horizontal overflow.

## ANTI-PATTERNS

- Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.
- Do not move polling controls out of the list page.
- Do not hide trace linkage behind a single summary string when span references exist.
- Do not bypass the hook layer for run reads or reruns.
- Do not collapse per-agent detail or evidence panes into one monolithic block.

## VALIDATION

```bash
cd frontend
pnpm test:run src/pages/runs/list.test.tsx src/pages/runs/detail-tabs.test.ts src/pages/runs/detail-http-operations.test.tsx
pnpm test:e2e -- runs.spec.ts
```

## NOTES

- The detail page uses URL-backed route state for rerun, selected tabs, and inspection-pane views so deep links can reopen the same context.
- Rerun edits root launch parameters only.
