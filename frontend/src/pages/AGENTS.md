# FRONTEND PAGES GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This file covers routed page components in `src/pages/`.

## CHILD DOCS
- `extensions/AGENTS.md` — bundled extension state/toggle system route
- `workflow-packages/AGENTS.md` — Workflow Package list/editor/preflight/launch/import/export route family
- `model-connections/AGENTS.md` — saved model connection list/editor route family
- `runs/AGENTS.md` — runs list and detail route family
- `portfolios/AGENTS.md` — portfolio list/detail workspace routes
- `templates/AGENTS.md` — template list/editor routes and preview rules
- `reports/AGENTS.md` — report list/detail routes and markdown workflows
- `../../retired/global-authoring/src/pages/*/AGENTS.md` — archive-only global-authoring guide tree; do not treat as live route ownership

## OVERVIEW
`src/pages/` contains routed screen components that map directly to `src/routes.ts`. The shipped route families are the dashboard, bundled extension state page, extension-gated portfolio/template/report pages, and the package-first platform pages for Workflow Packages, Model Connections, and Runs.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

## STRUCTURE
```text
src/pages/
├── dashboard.tsx                # home route summary
├── extensions/                  # bundled extension state/toggle route
├── workflow-packages/           # package list and editor routes
├── model-connections/           # saved model connection list and editor routes
├── runs/                        # run list and detail routes
├── portfolios/                  # portfolio workspace routes
├── templates/                   # stored-template list/editor routes
├── reports/                     # report inventory and detail routes
└── platform-resource-shared.tsx # shared route helper utilities for platform pages
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Dashboard landing | `dashboard.tsx` | home route summary and retry state |
| Extension state route | `extensions/AGENTS.md` | bundled extension slim state and enable/disable toggle flow |
| Agent-platform pages | `workflow-packages/AGENTS.md`, `model-connections/AGENTS.md`, `runs/AGENTS.md` | package authoring, saved connections, and run inspection |
| Portfolio workspace | `portfolios/AGENTS.md` | portfolio list and detail workspace |
| Template list/editor | `templates/AGENTS.md` | stored-template CRUD, inline compile preview, placeholder browser |
| Report routes | `reports/AGENTS.md` | list/detail, upload/generate, markdown view/edit/download |
| Shared platform page helpers | `platform-resource-shared.tsx` | common badges, JSON helpers, and small route-level utilities |

## CONVENTIONS
- `src/routes.ts` is the route source of truth, and routed screens in this folder back the registered paths, even when one editor component handles both create and edit URLs.
- `src/components/layout.tsx` owns the shell, breadcrumbs, and sidebar labels assembled from `src/extensions/runtime.tsx` plus static platform/system routes.
- Pages compose hooks from `src/hooks/`, shared components from `src/components/shared/`, and route-specific helpers from nearby files.
- Pages handle top-level data fetching, mutation feedback, and route-level error states, but business rules stay in hooks or shared helpers.
- List pages use the shared frontend page UI standard below before adding route-specific layout.
- The template editor page uses `useDebounce()`, `useCompileInline()`, and `usePlaceholders()` to keep preview and placeholder browsing responsive without moving that logic into the component library.
- Portfolio detail pages compose portfolio, balance, position, trade, and market-data hooks together; quote enrichment and allocation math stay in shared analytics helpers instead of the page body.
- Workflow package pages keep package-private resources inside package editor tabs and use global Model Connections, extension-filtered read-only Tools, and global Runs through dedicated hooks.
- The `/extensions` page is a system state surface only; it should not grow marketplace/install/remove behavior in phase 1.

## FRONTEND PAGE UI STANDARD
- Page shells use a simple content stack such as `space-y-4 p-4`; legacy inventory wrappers and dashboard-style summary-card bands are not the default for resource lists.
- Header rows put the page title and short muted description on the left, with primary page actions on the right. Use `text-xl font-semibold tracking-tight` for page titles and compact `size="sm"` buttons for header actions.
- Search, filter, and view controls sit in a left-aligned toolbar directly below the header. Search inputs use the compact pattern from Templates and Reports: `relative max-w-sm flex-1`, a search icon at `absolute left-2.5 top-2 size-4`, and an input with `h-8 pl-8 text-xs`.
- Cards/table view switchers use `ToggleGroup type="single"`, `value={viewMode}`, guarded `onValueChange`, `ToggleGroupItem` controls sized `h-8 w-8 px-0`, and `LayoutGrid`/`List` icons sized `size-3.5`.
- Resource inventories render directly after their toolbar and state cards. Platform pages prefer `PlatformResourceList` plus `PlatformResourceCard density="compactPlus"`; non-platform pages can use `ResourceRowCard` or the shared table primitives when that route already owns the pattern.
- Loading, error, empty, and filtered-empty states use compact `Card` + `CardContent` blocks in the page stack, not nested inside a labeled inventory shell unless a route genuinely needs a separate panel boundary.
- Preserve stable row/card `data-testid` values and accessible labels for primary actions, search fields, and view controls so tests and Playwright QA can target the same surface.

## ANTI-PATTERNS
- Do not put business rules or complex state management directly in page components.
- Do not duplicate feature-specific logic here when a feature folder or hook already owns it.
- Do not call `fetch` directly; use hooks from `src/hooks/` instead.
- Do not create ad-hoc query keys in pages; use canonical keys from `src/lib/query-keys.ts`.
- Do not bypass the layout shell, error boundary, or template-editor full-height layout rules when adding a new page.
- Do not add nested `Package Inventory`/`Resource Inventory` card shells, route-local summary-card bands, or oversized search/view controls to new list pages unless the product requirement explicitly calls for that hierarchy.
- Do not duplicate report request logic in page components when `use-reports.ts` and the template editor already own the server-side workflow.
- Do not add dead routes or stale route docs that are not wired into `src/routes.ts`.
- Do not bypass extension route gates or duplicate Finance Workspace visibility rules in page components.

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
- Portfolio detail pages are routable but not exposed separately in the sidebar.
- The live router exposes dashboard, `/extensions`, extension-gated portfolio/template/report routes, Workflow Packages, Model Connections, and Runs.
