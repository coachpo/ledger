# FRONTEND PAGES GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This file covers routed page components in `src/pages/`.

## CHILD DOCS

- `extensions/AGENTS.md` — `/extensions` system-state route family
- `model-connections/AGENTS.md` — global model endpoint inventory/editor, write-only secrets, and connection-test route family
- `portfolios/AGENTS.md` — portfolio list/detail workspace route family
- `reports/AGENTS.md` — report inventory/detail, upload, generation, and markdown-edit route family
- `templates/AGENTS.md` — stored-template inventory/editor route family
- `workflow-packages/AGENTS.md` — Workflow Package list/editor/preflight/launch/import/export route family
- `runs/AGENTS.md` — runs list and detail route family
- `../../retired/global-authoring/src/pages/AGENTS.md` — archive-only global-authoring guide tree; do not treat as live route ownership

## OVERVIEW

`src/pages/` contains routed screen components that map directly to `src/routes.ts`. The shipped route families are the dashboard, bundled extension state page, extension-gated portfolio/template/report pages, and the package-first platform pages for Workflow Packages, Model Connections, and Runs.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are retired/archive context, not live acceptance paths.

This parent guide now delegates the contract-heavy Extensions, Model Connections, Portfolios, Reports, Templates, Workflow Packages, and Runs route families to child AGENTS files. Dashboard and shared route helpers stay here.

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

| Task                         | Location                                                                                | Notes                                                                                                       |
| ---------------------------- | --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Dashboard landing            | `dashboard.tsx`                                                                         | home route summary and retry state                                                                          |
| Extension state route        | `extensions/AGENTS.md`, `../extensions/AGENTS.md`, `../hooks/use-extensions.ts`         | bundled extension slim state and enable/disable toggle flow                                                 |
| Workflow Package pages       | `workflow-packages/AGENTS.md`                                                           | package authoring, validation, preflight, launch, import, and export                                        |
| Model connection pages       | `model-connections/AGENTS.md`, `../hooks/use-model-connections.ts`                      | saved connection inventory, write-only secrets, delete flow, and connection-test UI                         |
| Run pages                    | `runs/AGENTS.md`                                                                        | run list, detail, root-parameter rerun, invocation-input fork, trace views, and legacy replay lineage reads |
| Portfolio workspace          | `portfolios/AGENTS.md`, `../components/portfolios/AGENTS.md`                            | portfolio list/detail workspace                                                                             |
| Template list/editor         | `templates/AGENTS.md`, `../components/templates/AGENTS.md`, `../hooks/use-templates.ts` | stored-template CRUD, inline compile preview, placeholder browser, and saved-template report generation     |
| Report routes                | `reports/AGENTS.md`, `../hooks/use-reports.ts`, `../lib/report-grouping.ts`             | list/detail, upload/generate, markdown view/edit/download                                                   |
| Shared platform page helpers | `platform-resource-shared.tsx`                                                          | common badges, JSON helpers, and small route-level utilities                                                |
| Archive-only cutover context | `../../retired/global-authoring/src/pages/AGENTS.md`                                    | removed standalone authoring route families                                                                 |

## GLOBAL ROUTE GUARDRAILS

- `src/routes.ts` registers the live route tree, while `src/routes.metadata.ts` is the single contract for route archetype, breadcrumb title, nav label, sidebar test id, shell mode, ownership, and expected state variants. Add metadata before adding a live route.
- `Layout` consumes route metadata through `getRouteMetadataForPathname()`. Breadcrumbs, sidebar labels, `data-route-shell-mode`, and the routed `<main>` test id must not be rebuilt in page components.
- The app has exactly one page-level `<main>` for routed content. Full-height routes still render inside that shell main, not inside a nested page main.
- Unknown URLs must hit the product-owned catch-all route with `route-unknown` metadata. Thrown route errors must use `RouteErrorPage`; React Router's default developer error UI is not an accepted state.
- Link versus button semantics are required. Use links for navigation to real URLs, including row/card open actions. Use buttons for mutations, dialogs, menus, sorting, toggles, and transient UI state.
- Static tables stay static. Row, cell, sort, selection, and trailing actions must be explicit links, checkboxes, or buttons inside the table, never pointer-only row or cell widgets.
- Search, filter, and form controls need programmatic labels. Placeholder-only labeling is not enough for route-critical controls.
- Extension-owned routes render through runtime gates. Direct links to disabled Finance Workspace routes should show the deterministic disabled state, while platform/system routes and tools remain available according to extension-runtime filtering.
- Route shells must be mobile contained. Long keys, hashes, URLs, JSON, markdown, tables, and badges need `min-w-0`, wrapping, clipping, or internal scroll so the document does not gain horizontal overflow.
- Light and dark themes share the same route semantics. Theme checks should verify representative route chrome and content remain visible without adding route-local color-mode state.

## ROUTE ARCHETYPE RULES

- Dashboard routes may use summary bands and singleton landing sections, but must keep the same semantic header across loading, ready, and error states.
- Inventory routes use compact page stacks such as `space-y-4 p-4`. Header title and description stay left, primary actions stay right, and search/filter/view controls sit in a left-aligned toolbar below the header.
- Inventory search inputs use the compact pattern from Templates and Reports: `relative max-w-sm flex-1`, a search icon at `absolute left-2.5 top-2 size-4`, and an input with `h-8 pl-8 text-xs`.
- Inventory view switchers use `ToggleGroup type="single"`, `value={viewMode}`, guarded `onValueChange`, `ToggleGroupItem` controls sized `h-8 w-8 px-0`, and `LayoutGrid`/`List` icons sized `size-3.5`.
- Resource inventories render directly after toolbar and state cards. Platform pages prefer `PlatformResourceList` plus `PlatformResourceCard density="compactPlus"`; finance inventories can use `ResourceRowCard`, grouped list cards, or existing table primitives when the route owns that pattern.
- Detail routes keep route identity and back navigation explicit. Use `text-xl font-semibold tracking-tight` for the route title, keep secondary actions before destructive or primary save actions, and do not truncate the entity identity.
- Editor routes use metadata-owned `fullHeight` shell mode when they need split panes or persistent action bars. They must expose a labeled route shell, labeled inputs, save/cancel hierarchy, and mobile containment.
- Console routes such as package launch and run detail use metadata-owned `fullHeight` shell mode. Preserve evidence, preflight, trace, payload, and fork/rerun controls with internal scrolling for wide data.
- System-state routes stay narrow and contract-bound. `/extensions` renders only slim bundled extension state and must not grow marketplace, install, remove, or private scaffold details.
- Loading, error, empty, filtered-empty, disabled-extension, not-found, creating, editing, saving, importing, validating, launching, and polling states must match the route's `stateVariants` metadata and have targeted test coverage when they are visible user states.

## REGRESSION COVERAGE MATRIX

- `src/routes.test.tsx` guards metadata coverage for every registered route, route archetypes, state variants, shell mode ownership, product-owned 404/error routing, retired-route fallbacks, and extension contribution filtering.
- `src/components/layout.test.tsx` guards sidebar grouping, breadcrumb labels, extension nav hide/show/restore behavior, the single page `<main>`, and metadata-owned full-height wrapping.
- `e2e/navigation.spec.ts` covers primary nav, route shell metadata in the browser, retired nav absence, unknown-route 404 shell, link/button semantics, mobile overflow, and representative dark-mode chrome.
- `e2e/extensions.spec.ts` covers enabled, disabled, and re-enabled Finance Workspace states for nav, direct routes, and tool authoring discovery.
- `e2e/reports.spec.ts` covers seeded report flows plus representative empty and API-error list states for the finance inventory archetype.
- `e2e/workflow-packages.spec.ts` covers package-first authoring, import/export, launch, run provenance, and wide payload overflow in the run-detail console.

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
- Portfolio detail pages are routable but not exposed separately in the sidebar.
- The live router exposes dashboard, `/extensions`, extension-gated portfolio/template/report routes, Workflow Packages, Model Connections, and Runs.
