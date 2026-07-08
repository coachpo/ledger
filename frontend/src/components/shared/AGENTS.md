# FRONTEND SHARED COMPONENTS GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/components/AGENTS.md`.

## OVERVIEW
`src/components/shared/` holds reusable route-shell components, inventory/workspace/inspection layouts, evidence and status chrome, management-list actions/selection helpers, destructive confirmation dialogs, and helper schemas used across multiple feature areas. This folder is where cross-feature UI belongs once it has real reuse beyond a single route.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Error containment | `error-boundary.tsx`, `error-boundary-fallback.tsx` | route-safe fallback UI |
| Route-safe shells | `inventory-page-shell.tsx`, `workspace-page-shell.tsx`, `entity-dialog-shell.tsx` | shared inventory/workspace framing and dialog shell composition |
| Resource chrome | `resource-toolbar.tsx`, `resource-filter-bar.tsx`, `resource-status-strip.tsx`, `page-context-bar.tsx`, `provenance-badge.tsx` | reusable filter, summary, and status chrome for finance and platform pages |
| Management-list actions | `resource-actions-menu.tsx`, `resource-bulk-actions-bar.tsx`, `resource-selection-checkbox.tsx`, `confirm-delete-dialog.tsx` | row overflow menus, selected-count action bars, accessible select-all/row checkboxes, and destructive confirmations |
| Evidence / state helpers | `console-section.tsx`, `evidence-cluster.tsx`, `constraint-inspector.tsx`, `empty-state-panel.tsx`, `inventory-state-panel.tsx`, `inline-state-panel.tsx` | wide payload, evidence, and empty/error/loading presentation |
| Generic tables | `data-table.tsx`, `data-table-column-header.tsx`, `resource-table-frame.tsx` | lightweight sortable tables and route-owned table framing |
| Summary metrics | `metric-card.tsx` | consistent KPI card layout |
| Shared field logic | `form-schemas.ts` | reusable Zod validation snippets for current shared forms |
| Search/select UI | `searchable-select.tsx` | command-style picker used by feature forms |
| Row-card inventory UI | `resource-row-card.tsx` | compact resource cards used by platform inventories when a card surface is still warranted |
| Design-system source | `../../../DESIGN.md` | source of truth for page layout, shared shells, tokens, and management UI patterns |
| UI/UX standards and examples | `docs/README.md` | shared UI standards, component specs, page blueprints, and migration guide |

## CONVENTIONS
- Keep components generic enough to serve multiple features; pass feature-specific labels, callbacks, and columns from callers.
- `frontend/DESIGN.md` is the source of truth for shared shell composition, tokens, route states, status chrome, management-list actions, selection, and destructive confirmation patterns.
- Route-shell components stay presentational; pages and hooks own data loading, URL state, navigation, and mutations.
- Inventory/workspace shells preserve consistent region order, inspector behavior, and mobile containment; do not fork context/toolbar/filter/action/selection/inspector scaffolding per route.
- Shared status components (`ResourceStatusBadge` and `ResourceStatusStrip`) own reusable status presentation; do not recreate route-local colored badge spans in routed pages.
- Shared action, bulk-action, selection, and confirmation components stay presentational. Routes still own selected ids, mutation sequencing, toasts, navigation, and domain-specific labels.
- Shared validation snippets belong in `form-schemas.ts` when they are reused across preserved product forms or dialogs.
- Error-boundary components stay UI-focused; logging or recovery policy belongs in higher-level app code.
- Keep shared helpers presentational; request logic and route ownership stay in pages, hooks, or feature folders.

## ANTI-PATTERNS
- Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.
- Do not embed template-only, report-only, or agent-platform request logic in this folder.
- Do not hard-code route metadata, URL params, or fetch logic inside reusable shells.
- Do not turn a one-off route widget into a shared component before a second real use case exists.
- Do not hard-code API types or query keys inside reusable table/search/action/selection wrappers.
- Do not duplicate form validation that already exists in `form-schemas.ts`.

## NOTES
- Shared schemas here are the canonical place for cross-route validation rules that are still reused after the cutover.
- The inventory/workspace/split-inspector shells plus management-list helpers are the current shared page chrome for finance template/report inventories, platform workspace/console pages, and shared UI migrations.
- This folder no longer owns retired orchestration, Studio, Tryout, or runtime-v2 helper surfaces.
