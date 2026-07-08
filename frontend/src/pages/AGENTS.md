# FRONTEND PAGES GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This file covers routed page components in `src/pages/`.

## CHILD DOCS

- `extensions/AGENTS.md` — stale `/extensions` route family scheduled for Task 5.3 removal
- `model-connections/AGENTS.md` — global model endpoint inventory/editor, write-only secrets, and connection-test route family
- `reports/AGENTS.md` — report inventory/detail, upload, generation, and markdown-edit route family
- `templates/AGENTS.md` — stored-template inventory/editor route family
- `workflow-packages/AGENTS.md` — Workflow Package list/editor/preflight/launch/import/export route family
- `scheduled-tasks/AGENTS.md` — Scheduled Task list/create/detail/preview/fire-history route family
- `runs/AGENTS.md` — runs list and detail route family

## OVERVIEW

`src/pages/` contains routed screen components that map directly to `src/routes.ts`. The shipped route families are the dashboard, template/report pages, and the package-first platform pages for Workflow Packages, Scheduled Tasks, Model Connections, and Runs. Digital Oracle is visible only as backend tool metadata, not as a route or nav surface.

Extension model: backend extensions are statically installed; remaining frontend extension-gated route code is transitional Task 5.3 cleanup scope.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative old paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or non-goal surfaces, not live acceptance paths.

This parent guide delegates Model Connections, Scheduled Tasks, Reports, Templates, Workflow Packages, and Runs route families to child AGENTS files. The stale Extensions child doc exists only until Task 5.3 removes that route family. Dashboard and shared route helpers stay here.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## STRUCTURE

```text
src/pages/
├── dashboard.tsx                # home route summary
├── extensions/                  # stale extension state/toggle route removed in Task 5.3
├── workflow-packages/           # package list and editor/launch routes
├── scheduled-tasks/             # scheduled package-run list, create, and detail routes
├── model-connections/           # saved model connection list and editor routes
├── runs/                        # run list and detail routes
├── templates/                   # stored-template list/editor routes
├── reports/                     # report inventory and detail routes
```

## WHERE TO LOOK

| Task                         | Location                                                                                | Notes                                                                                                       |
| ---------------------------- | --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Dashboard landing            | `dashboard.tsx`                                                                         | home route summary and retry state                                                                          |
| Transitional extension route | `extensions/AGENTS.md`, `../extensions/AGENTS.md`, `../hooks/use-extensions.ts`         | stale frontend extension route and hooks removed in Task 5.3                                                           |
| Workflow Package pages       | `workflow-packages/AGENTS.md`                                                           | package authoring, validation, preflight, launch, import, and export                                        |
| Scheduled Task pages         | `scheduled-tasks/AGENTS.md`, `../hooks/use-scheduled-tasks.ts`                          | scheduled package-run inventory, create/detail editors, preview, fire history, delete, and run-now          |
| Model connection pages       | `model-connections/AGENTS.md`, `../hooks/use-model-connections.ts`                      | saved connection inventory, write-only secrets, delete flow, and connection-test UI                         |
| Run pages                    | `runs/AGENTS.md`                                                                        | run list, detail, root-parameter rerun, trace views, and execution evidence reads |
| Template list/editor         | `templates/AGENTS.md`, `../components/templates/AGENTS.md`, `../hooks/use-templates.ts` | stored-template CRUD, inline compile preview, placeholder browser, and saved-template report generation     |
| Report routes                | `reports/AGENTS.md`, `../hooks/use-reports.ts`, `../lib/report-grouping.ts`             | list/detail, upload/generate, markdown view/edit/download                                                   |
| UI/UX standards and page blueprints | `../../DESIGN.md`, `../components/shared/docs/README.md`                         | design-system source of truth, reusable component specs, examples, and migration guidance                   |

## GLOBAL ROUTE GUARDRAILS

- `src/routes.ts` registers the live route tree, while `src/routes.metadata.ts` is the single contract for route archetype, breadcrumb title, nav label, sidebar test id, shell mode, ownership, and expected state variants. Add metadata before adding a live route.
- `frontend/DESIGN.md` is the source of truth for page layout, shared shells, tokens, and management UI patterns. Route metadata, page implementation, and the owning AGENTS guide must agree.
- `Layout` consumes route metadata through `getRouteMetadataForPathname()`. Breadcrumbs, sidebar labels, `data-route-shell-mode`, and the routed `<main>` test id must not be rebuilt in page components.
- The app has exactly one page-level `<main>` for routed content. Full-height routes still render inside that shell main, not inside a nested page main.
- Unknown URLs must hit the product-owned catch-all route with `route-unknown` metadata. Thrown route errors must use `RouteErrorPage`; React Router's default developer error UI is not an accepted state.
- Link versus button semantics are required. Use links for navigation to real URLs, including row/card open actions. Use buttons for mutations, dialogs, menus, sorting, toggles, and transient UI state.
- Static tables stay static. Row, cell, sort, selection, and trailing actions must be explicit links, checkboxes, or buttons inside the table, never pointer-only row or cell widgets.
- Search, filter, and form controls need programmatic labels. Placeholder-only labeling is not enough for route-critical controls.
- Extension-owned route gates are stale cleanup scope. After Task 5.3, template/report routes are static, platform/system routes remain available, and Digital Oracle contributes backend tools only.
- Route shells must be mobile contained. Long keys, hashes, URLs, JSON, markdown, tables, and badges need `min-w-0`, wrapping, clipping, or internal scroll so the document does not gain horizontal overflow.
- Light and dark themes share the same route semantics. Theme checks should verify representative route chrome and content remain visible without adding route-local color-mode state.

## ROUTE ARCHETYPE RULES

- Dashboard routes may use summary bands and singleton landing sections, but must keep the same semantic header across loading, ready, and error states.
- Inventory routes, identified by route metadata archetype `inventory`, must use the `DESIGN.md` inventory-page pattern: `InventoryPageShell`, `PageContextBar`, `ResourceToolbar` for search/result summary/actions, optional `ResourceFilterBar`, `InventoryStatePanel`/`EmptyStatePanel`/`InlineStatePanel`, `ResourceTableFrame` or approved shared resource-list/card primitives, `ResourceSelectionCheckbox`/`ResourceBulkActionsBar`/`ConfirmDeleteDialog`/`ResourceActionsMenu` where selection/delete/actions exist, and `ResourceStatusBadge`/`ResourceStatusStrip` for statuses.
- Inventory routes must not use `WorkspacePageShell`, route-local page wrappers, custom toolbar cards, custom filter cards, dashed empty states, or one-off `rounded-md border bg-muted/*` / `shadow-sm` page chrome.
- Non-inventory routes follow their `DESIGN.md` route shell: full-height editors/consoles use `WorkspacePageShell`, inspectable flows keep route-owned panels/dialogs, and system-state routes remain narrow and contract-bound.
- Detail routes keep route identity and back navigation explicit. Use `text-xl font-semibold tracking-tight` for the route title, keep secondary actions before destructive or primary save actions, and do not truncate the entity identity.
- Editor routes use metadata-owned `fullHeight` shell mode when they need split panes or persistent action bars. They must expose a labeled route shell, labeled inputs, save/cancel hierarchy, and mobile containment.
- Console routes such as package launch, Scheduled Task detail, and run detail use metadata-owned `fullHeight` shell mode. Preserve evidence, preflight, backend progress/queue/readiness payloads, scheduled input previews, trace, payload, and rerun controls with internal scrolling for wide data.
- System-state routes stay narrow and contract-bound. `/extensions` is no longer backed by a live backend contract and is removed in Task 5.3.
- Loading, error, empty, filtered-empty, not-found, creating, editing, saving, importing, validating, launching, and polling states must match the route's `stateVariants` metadata and have targeted test coverage when they are visible user states.

## REGRESSION COVERAGE MATRIX

- `src/routes.test.tsx` guards metadata coverage for every registered route, route archetypes, state variants, shell mode ownership, and product-owned 404/error routing.
- `src/components/layout.test.tsx` guards sidebar grouping, breadcrumb labels, the single page `<main>`, and metadata-owned full-height wrapping.
- `e2e/navigation.spec.ts` covers primary nav, route shell metadata in the browser, unknown-route 404 shell, link/button semantics, mobile overflow, and representative dark-mode chrome.
- `e2e/extensions.spec.ts` is stale coverage removed in Task 5.3 with the frontend plugin host.
- `e2e/reports.spec.ts` covers seeded report flows plus representative empty and API-error list states for the finance inventory archetype.
- `e2e/workflow-packages.spec.ts` covers package-first authoring, import/export, launch, run provenance, and wide payload overflow in the run-detail console.
- `e2e/scheduled-tasks.spec.ts` covers scheduled package-run automation, fire history, delete confirmation and post-delete absence states, and run-now links into run detail.
- `e2e/model-connections.spec.ts` and `e2e/runs.spec.ts` cover model-connection secret-safe flows and run inspection/rerun paths.
- `e2e/shell-regression.spec.ts`, `e2e/smoke.spec.ts`, and `e2e/workflow-package-tradingagents-smoke.spec.ts` cover route-shell regressions, smoke navigation, and TradingAgents package smoke behavior.

## ANTI-PATTERNS

- Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.
- Do not put business rules or complex state management directly in page components.
- Do not duplicate feature-specific logic here when a feature folder or hook already owns it.
- Do not call `fetch` directly; use hooks from `src/hooks/` instead.
- Do not create ad-hoc query keys in pages; use canonical keys from `src/lib/query-keys.ts`.
- Do not bypass the layout shell, error boundary, or template-editor full-height layout rules when adding a new page.
- Do not add nested `Package Inventory`/`Resource Inventory` card shells, route-local summary-card bands, or oversized search/filter controls to new list pages unless the product requirement explicitly calls for that hierarchy.
- Do not duplicate report request logic in page components when `use-reports.ts` and the template editor already own the server-side workflow.
- Do not add dead routes or stale route docs that are not wired into `src/routes.ts`.
- Do not bypass extension route gates or duplicate Finance Workspace visibility rules in page components.
- Do not create additional child route-family AGENTS files beyond the current set unless a folder grows an independent contract surface that the parent can no longer cover cleanly.

## VALIDATION

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm build
pnpm test:run
pnpm test:e2e
```

## NOTES

- Pages are thin route-layer components; the real complexity lives in hooks, shared components, and nearby page helpers.
- The live router exposes dashboard, `/extensions`, extension-gated template/report routes, Workflow Packages, Scheduled Tasks, Model Connections, and Runs.
