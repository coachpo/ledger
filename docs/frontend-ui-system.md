# Frontend UI System Inventory and Consolidation Plan

## Scope and Sources

This document inventories the current `frontend/` UI system and proposes a consolidation plan. It is analysis only; it does not define a product change or authorize implementation.

Primary code sources inspected:

- `frontend/AGENTS.md`
- `frontend/src/pages/AGENTS.md`
- `frontend/src/components/AGENTS.md`
- `frontend/src/components/shared/AGENTS.md`
- `frontend/src/components/ui/AGENTS.md`
- `frontend/src/extensions/AGENTS.md`
- `frontend/src/routes.ts`
- `frontend/src/routes.metadata.ts`
- `frontend/src/components/layout.tsx`
- `frontend/src/styles/theme.css`
- `frontend/src/styles/tailwind.css`
- `frontend/src/components/shared/docs/README.md`
- `frontend/src/components/shared/docs/ui-ux-standard.md`
- `frontend/src/components/shared/docs/ui-library-reference.md`
- `frontend/src/components/shared/docs/page-blueprints.md`
- `frontend/src/components/shared/docs/migration-guide.md`

Existing shared UI docs already define the strongest baseline for future work. This document should be treated as a repository-wide inventory and planning layer on top of those docs, not as a competing design system.

## Current UI System Inventory

### Application Shell and Routing

The frontend uses a single flat React Router tree under `Layout`.

- `frontend/src/routes.ts` registers live routes under `Layout`, assembles Finance Workspace routes from `assembleFinanceWorkspaceRoutes()`, and asserts metadata coverage with `assertRouteMetadataCoverage()`.
- `frontend/src/routes.metadata.ts` is the route UI contract. It owns route archetype, breadcrumb, sidebar navigation group, icon, ownership, shell mode, width mode, state variants, and route test ids.
- `frontend/src/components/layout.tsx` renders the only page-level `main`, the sidebar, grouped navigation, sticky header, breadcrumbs, theme toggle, route shell mode, and route width wrapper.
- `frontend/src/App.tsx` owns app-level providers: theme, TanStack Query, router, error boundary, and toaster.
- `frontend/src/pages/route-error.tsx`, `frontend/src/pages/not-found.tsx`, `frontend/src/components/shared/error-boundary.tsx`, and `frontend/src/components/shared/error-boundary-fallback.tsx` own route and React fallback states.

The live route archetypes are `dashboard`, `inventory`, `detail`, `editor`, `console`, `systemState`, and `unknown` in `frontend/src/routes.metadata.ts`. Shell modes are `scroll` and `fullHeight`; width modes are `wide`, `full`, `compact`, and `readable`.

### Route Families

Platform and system routes:

- Dashboard: `frontend/src/pages/dashboard.tsx`
- Extensions: `frontend/src/pages/extensions/list.tsx`
- Workflow Packages: `frontend/src/pages/workflow-packages/list.tsx`, `frontend/src/pages/workflow-packages/import-page.tsx`, `frontend/src/pages/workflow-packages/editor.tsx`, `frontend/src/pages/workflow-packages/launch.tsx`
- Model Connections: `frontend/src/pages/model-connections/list.tsx`, `frontend/src/pages/model-connections/editor.tsx`, `frontend/src/pages/model-connections/model-connection-ui.ts`
- Memory: `frontend/src/pages/memory/list.tsx`
- Scheduled Tasks: `frontend/src/pages/scheduled-tasks/list.tsx`, `frontend/src/pages/scheduled-tasks/editor.tsx`, `frontend/src/pages/scheduled-tasks/detail.tsx`, `frontend/src/pages/scheduled-tasks/pickers.tsx`, `frontend/src/pages/scheduled-tasks/time-zones.ts`
- Runs: `frontend/src/pages/runs/list.tsx`, `frontend/src/pages/runs/detail.tsx`, `frontend/src/pages/runs/detail-helpers.ts`, `frontend/src/pages/runs/detail-tabs.ts`, `frontend/src/pages/runs/inspection-state.ts`, `frontend/src/pages/runs/detail-sections/*`
- Shared platform route helpers: `frontend/src/pages/platform-resource-shared.tsx`, `frontend/src/pages/platform-resource-helpers.ts`

Extension-owned Finance Workspace routes are registered through `frontend/src/extensions/signaldeck-finance/scaffold.ts` and mounted through runtime helpers, not by hard-coded route logic in `routes.ts` or `layout.tsx`. Their route components live under:

- `frontend/src/pages/portfolios/list.tsx`
- `frontend/src/pages/portfolios/detail.tsx`
- `frontend/src/pages/templates/list.tsx`
- `frontend/src/pages/templates/editor.tsx`
- `frontend/src/pages/reports/list.tsx`
- `frontend/src/pages/reports/detail.tsx`

Digital Oracle is intentionally tool-only. Its frontend scaffold is `frontend/src/extensions/signaldeck-digital-oracle/scaffold.ts`; it contributes no route or navigation surface.

### Layouts and Route Shells

The mature layout system is already present in `frontend/src/components/shared`.

- `inventory-page-shell.tsx` defines the standard inventory stack: context bar, optional toolbar, optional filter bar, and content region.
- `workspace-page-shell.tsx` defines full-height editor/detail/console framing with sticky context bar, optional left rail, and internally scrolling body.
- `split-inspector-layout.tsx` defines selected-item source plus inspector layouts, including sheet-style inspector support.
- `entity-dialog-shell.tsx` defines reusable dialog content structure for entity forms.
- `page-context-bar.tsx` defines route title, description, metadata, status, and action placement.
- `resource-toolbar.tsx` defines compact search, filters, actions, result summary, and selection summary placement.
- `resource-filter-bar.tsx` defines active filter chip summaries and clear controls.

Route guidance in `frontend/src/pages/AGENTS.md` confirms these are the default page chrome patterns and explicitly warns against route-local forks of cards, tables, filters, selection, and inspector scaffolding.

### Shared Components and UI Primitives

Reusable application components:

- State and notice surfaces: `empty-state-panel.tsx`, `inventory-state-panel.tsx`, `inline-state-panel.tsx`
- Resource displays: `resource-row-card.tsx`, `resource-status-strip.tsx`, `resource-table-frame.tsx`, `data-table.tsx`, `data-table-column-header.tsx`
- Evidence and console UI: `console-section.tsx`, `evidence-cluster.tsx`, `constraint-inspector.tsx`, `provenance-badge.tsx`
- Metrics and summaries: `metric-card.tsx`
- Shared input helpers: `searchable-select.tsx`, `form-schemas.ts`, `saved-runtime-input-registry-panel.tsx`

Cross-route form and feature helpers:

- `frontend/src/components/forms/portfolio-form-dialog.tsx`
- `frontend/src/components/forms/report-upload-dialog.tsx`
- `frontend/src/components/forms/generate-report-dialog.tsx`
- `frontend/src/components/forms/secret-input.tsx`
- `frontend/src/components/templates/template-placeholder-reference.tsx`
- `frontend/src/components/templates/template-runtime-inputs-section.tsx`
- `frontend/src/components/templates/placeholder-group.tsx`

The primitive layer is `frontend/src/components/ui`. It contains shadcn/Radix-style wrappers such as `button.tsx`, `card.tsx`, `dialog.tsx`, `sheet.tsx`, `table.tsx`, `tabs.tsx`, `input.tsx`, `textarea.tsx`, `select.tsx`, `checkbox.tsx`, `switch.tsx`, `badge.tsx`, `alert.tsx`, `sidebar.tsx`, and `scroll-area.tsx`.

### Hooks and UI State

Server state is route-owned through TanStack Query hooks in `frontend/src/hooks`, backed by API helpers and query keys in `frontend/src/lib`.

Major resource hooks include:

- `use-extensions.ts`
- `use-workflow-packages.ts`
- `use-scheduled-tasks.ts`
- `use-model-connections.ts`
- `use-memory.ts`
- `use-runs.ts`
- `use-portfolios.ts`
- `use-templates.ts`
- `use-reports.ts`
- `use-balances.ts`
- `use-positions.ts`
- `use-trading-operations.ts`
- `use-market-data.ts`

Reusable UI-state hooks include:

- `use-inventory-view-state.ts`
- `use-resource-filter-state.ts`
- `use-resource-selection-state.ts`
- `use-split-inspector-state.ts`
- `use-debounce.ts`

The frontend guidance in `frontend/AGENTS.md` and `frontend/src/hooks/AGENTS.md` requires pages to use hooks and shared query keys rather than direct `fetch` calls or route-local query-key construction.

### Theme, Color, Typography, Spacing, and Assets

The global styling system is token-first.

- `frontend/src/styles/theme.css` defines light/dark semantic colors, chart colors, positive/negative financial colors, radius, sidebar tokens, typography defaults, and project `--ui-*` tokens for spacing, shadows, z-index, motion, breakpoints, and control/icon sizes.
- `frontend/src/styles/tailwind.css` imports Tailwind, `tw-animate-css`, the typography plugin, and the source scan pattern.
- `frontend/src/styles/fonts.css` exists but is currently noted in `frontend/AGENTS.md` as empty or unreferenced.
- Theme state lives in `frontend/src/components/theme-provider.tsx`, with UI control in `frontend/src/components/theme-toggle.tsx` and types in `frontend/src/components/theme.ts`.
- The visible brand asset used by the shell is `frontend/public/favicon.svg`, referenced by `frontend/src/components/layout.tsx`.

The current palette is neutral/cool with blue-violet primary accents through OKLCH semantic variables. Typography uses the project font variables through Tailwind's `font-sans` and `font-mono`, with base heading styles in `theme.css` and route-level headings in shared components such as `PageContextBar`.

### Platform-Core Versus Extension-Owned Boundaries

Platform-core UI includes dashboard, extensions state, Workflow Packages, Scheduled Tasks, Model Connections, Memory, Runs, the app shell, shared components, hooks, theme, route metadata, and error/fallback states.

Extension-owned UI includes Finance Workspace route/nav/tool contributions and finance route families for portfolios, templates, and reports. Those routes are enabled through `frontend/src/extensions/runtime.tsx`, `frontend/src/extensions/runtime-helpers.ts`, `frontend/src/extensions/registry.ts`, and `frontend/src/extensions/signaldeck-finance/scaffold.ts`.

Digital Oracle is a statically resident bundled extension but is tool-only in the frontend. Keep it out of route and navigation standards unless that product boundary changes explicitly.

## Duplication and Consolidation Report

### Strong Existing Consolidation Anchors

The project already has the correct consolidation direction documented in `frontend/src/components/shared/docs/*`:
- `ui-ux-standard.md` defines layout, typography, color, controls, states, responsive behavior, accessibility, and naming.
- `ui-library-reference.md` defines developer-facing component specs for shared UI.
- `page-blueprints.md` gives route archetype examples for inventory, workspace/editor, split inspector, and dialog flows.
- `migration-guide.md` maps older route-local patterns to shared replacements.

Future implementation work should consolidate around these files and the components they cite instead of inventing a second standard.

### Duplicate or Near-Duplicate Patterns

Inventory state panels are nearly duplicated. `frontend/src/components/shared/empty-state-panel.tsx` and `frontend/src/components/shared/inventory-state-panel.tsx` share the same dashed card, alert variant, tone mapping, title, description, and action structure. `EmptyStatePanel` adds an icon option; `InventoryStatePanel` adds `testId` and has inventory-specific naming. Reuse opportunity: keep both public names if callers need semantic clarity, but factor any future behavior changes through one shared internal state-card primitive before adding new state panel variants.

Inventory search and view controls exist as both route guidance and shared implementation. `frontend/src/components/shared/resource-toolbar.tsx` implements the compact search pattern called out in `frontend/src/pages/AGENTS.md`, while route files such as `frontend/src/pages/memory/list.tsx` still include direct compact search markup. Reuse opportunity: migrate route-local search rows to `ResourceToolbar.search` when the route fits the inventory archetype and the route can keep state ownership.

Filter, selection, and view state are partly centralized through `frontend/src/hooks/use-resource-filter-state.ts`, `frontend/src/hooks/use-resource-selection-state.ts`, `frontend/src/hooks/use-inventory-view-state.ts`, and `frontend/src/hooks/use-split-inspector-state.ts`. Some pages still own local state directly because their domain is more complex. Reuse opportunity: use shared hooks for generic inventories first; leave route-owned state where the shape is package-, memory-, run-, or schedule-specific.

Page shell duplication remains the largest risk. `InventoryPageShell`, `WorkspacePageShell`, and `SplitInspectorLayout` are mature, but route families with complex editors and consoles can still create local wrappers for context bars, sticky headers, internal scroll, or inspector panes. Reuse opportunity: require each live route to choose one shell archetype from `routes.metadata.ts` and compose from the corresponding shared shell before adding local layout containers.

Status displays and badges should consolidate around `frontend/src/components/shared/resource-status-strip.tsx`. The migration guide explicitly replaces raw colored spans with `ResourceStatusBadge` or `ResourceStatusStrip`. Reuse opportunity: avoid new route-local color mappings unless the status vocabulary is feature-owned and cannot be expressed through existing tones.

Dialog content structure should consolidate around `frontend/src/components/shared/entity-dialog-shell.tsx` for create/edit flows. Existing dialogs in `frontend/src/components/forms` and `frontend/src/components/portfolios` should remain route- or feature-owned for data and submit logic, but any repeated title/body/footer scaffolding should move toward `EntityDialogShell`.

Table and card containers should consolidate around `DataTable`, `ResourceTableFrame`, and `ResourceRowCard`. Route-owned table markup is acceptable when columns and actions are feature-specific, but borders, containment, row-card density, title links, badges, metadata, and actions should use shared components where possible.

### One-Off Styling Risks

The project correctly keeps global styles small. The risk is not a missing global stylesheet; the risk is repeated Tailwind class bundles inside route pages for headers, search rows, dashed state cards, split panes, and sticky bars. The current standard should be: if a class bundle describes route chrome or a reusable resource pattern, prefer `components/shared`; if it describes feature-only content, keep it local.

Avoid growing `frontend/src/styles` beyond theme and global Tailwind entrypoints. `frontend/AGENTS.md` explicitly says one-off layout and feature styling should stay in components instead of global CSS.

### Uncertainties

This analysis inspected the major route, shell, standard, style, and guidance files plus broad pattern search results. Some deep implementation details should be rechecked before a code migration phase:

- `frontend/src/pages/workflow-packages/editor-sections*`
- `frontend/src/pages/runs/detail-sections/*`
- `frontend/src/pages/scheduled-tasks/pickers.tsx`
- `frontend/src/pages/model-connections/model-connection-ui.ts`
- `frontend/src/components/platform-authoring/**`
- `frontend/src/components/portfolios/**`

The consolidation direction is clear, but exact per-file refactors should be validated immediately before implementation.

## Proposed Universal UI Standard

### Layout

Use one app shell. `frontend/src/components/layout.tsx` owns the single `main`, sidebar, breadcrumbs, header, route width, full-height wrapping, and scroll behavior. Leaf pages must not rebuild those structures.

Every route should map to one route archetype in `frontend/src/routes.metadata.ts` and then use the matching shell pattern:

- Inventory: `InventoryPageShell`
- Editor/detail/console with full-height needs: `WorkspacePageShell`
- Selected-item inspection: `SplitInspectorLayout` or `SheetInspectorLayout`
- Entity create/edit modal: `EntityDialogShell`

### Typography

Use `PageContextBar` for route titles and action rows. Use compact detail headings such as `text-xl font-semibold tracking-tight` only for detail identity inside a route body. Body copy should use `text-sm` or `text-xs` with `text-muted-foreground` for supporting text.

Long ids, hashes, URLs, package keys, JSON, and markdown must remain readable through wrapping, clipping, or internal scroll. Do not hide entity identity behind aggressive truncation.

### Color and Theme

Use semantic Tailwind classes backed by `frontend/src/styles/theme.css`: `bg-background`, `text-foreground`, `bg-card`, `border-border`, `text-muted-foreground`, `text-destructive`, `text-positive`, and `text-negative`. Use `text-positive` and `text-negative` for financial deltas only when the sign is meaningful.

Do not create route-local theme state. `frontend/src/components/theme-provider.tsx` owns persistence and system sync.

### Spacing and Density

The default density is compact operator-workspace density, not marketing-page spacing. Inventory routes should start with `InventoryPageShell` default spacing, currently `flex flex-col gap-4 p-4`. New shared UI should prefer `gap-*`, `min-w-0`, `overflow-auto`, and internal scroll over document-wide overflow.
Use `--ui-*` tokens from `theme.css` when custom CSS needs stable values for spacing, shadows, z-index, motion, breakpoints, or control sizes. Do not add a second token file.

### States

Visible route states should match each route's `stateVariants` in `frontend/src/routes.metadata.ts`. Use:

- `InventoryStatePanel` for inventory loading, empty, filtered-empty, disabled, warning, and error states.
- `EmptyStatePanel` for card-like empty states that may include icons and actions.
- `InlineStatePanel` for notices inside forms, panes, inspectors, and payload sections.
- `ResourceStatusBadge` and `ResourceStatusStrip` for status vocabulary and fact groups.

Use tone `neutral` for normal empty states, `warning` for recoverable attention, and `danger` for failures or destructive states. Do not rely on color alone.

### Components and Interactions

Navigation uses links. Mutations, toggles, sorting, dialogs, and transient UI use buttons. Tables and cards should expose explicit links or buttons, not whole-row pointer behavior.

Search controls need labels. Prefer `ResourceToolbar.search`, which supplies `role="search"`, hidden label, icon placement, compact input sizing, and test id support.

Dialogs and sheets must use shadcn/Radix primitives and expose titles. Entity form dialogs should compose `EntityDialogShell` and keep data fetching, navigation, toasts, and mutation sequencing in route owners.

### Accessibility and Responsive Behavior

Keep one page-level `main` from `Layout`. Workspaces and inspectors need labeled regions. Icon-only controls need `aria-label`. Search, filters, forms, and selects need programmatic labels, not placeholder-only labels.

Design for 375px, 768px, 1024px, and 1440px. Dense lists, tables, badges, JSON, markdown, and editor panes must be mobile contained with `min-w-0`, wrapping, clipping, or internal scrolling.

## Recommended Component System Architecture

Keep the current layered architecture.

1. Route contracts: `frontend/src/routes.ts` and `frontend/src/routes.metadata.ts`
2. App shell: `frontend/src/components/layout.tsx`
3. Extension runtime: `frontend/src/extensions/runtime.tsx`, `frontend/src/extensions/runtime-helpers.ts`, `frontend/src/extensions/*/scaffold.ts`
4. Shared app UI: `frontend/src/components/shared/*`
5. Primitive UI: `frontend/src/components/ui/*`
6. Cross-route form helpers: `frontend/src/components/forms/*`
7. Feature-owned components: `frontend/src/components/portfolios/*`, `frontend/src/components/templates/*`, `frontend/src/components/platform-authoring/*`, and route-family helpers under `frontend/src/pages/*`
8. Data and state: `frontend/src/hooks/*`, `frontend/src/lib/api/*`, `frontend/src/lib/types/*`, `frontend/src/lib/query-keys.ts`
9. Theme and global styling: `frontend/src/styles/theme.css`, `frontend/src/styles/tailwind.css`, `frontend/src/styles/fonts.css`

Do not add a new `src/ui`, `src/design-system`, or global stylesheet layer. Build on `components/shared`, `components/ui`, route metadata, and theme tokens.

Shared components should remain presentational. Pages and hooks own route params, query hooks, API modules, query keys, derived domain state, navigation, toasts, and mutations.

Feature-only widgets should stay with their owning feature until a second real use case exists. `components/shared` should receive only proven cross-feature UI.

## Prioritized Implementation Roadmap

### Phase 1: Document and Enforce the Baseline

Safest first step: align documentation and review checklists, not code.

- Treat `frontend/src/components/shared/docs/ui-ux-standard.md` as the canonical UI standard.
- Treat `frontend/src/components/shared/docs/ui-library-reference.md` as the component API reference.
- Treat `frontend/src/components/shared/docs/page-blueprints.md` as the new-route blueprint source.
- Use this document as the inventory and consolidation tracker.

Exit criteria: no route behavior changes, no source changes, and all future UI work has a clear reference path.

### Phase 2: Consolidate Inventory Chrome

Start with low-risk list pages that already use `InventoryPageShell` or closely match it.

- Replace route-local search rows with `ResourceToolbar.search` where behavior is generic.
- Replace route-local active filter rows with `ResourceFilterBar` where filters are visible route state.
- Replace local empty/error cards with `InventoryStatePanel` or `EmptyStatePanel` based on state scope.
- Replace raw status spans with `ResourceStatusBadge` or `ResourceStatusStrip`.

Good candidate families: `frontend/src/pages/model-connections/list.tsx`, `frontend/src/pages/portfolios/list.tsx`, `frontend/src/pages/reports/list.tsx`, `frontend/src/pages/templates/list.tsx`, `frontend/src/pages/runs/list.tsx`, and `frontend/src/pages/scheduled-tasks/list.tsx`.

### Phase 3: Normalize Full-Height Workspaces and Inspectors

Migrate only one route family at a time.

- Confirm `shellMode: "fullHeight"` in `frontend/src/routes.metadata.ts` before adopting `WorkspacePageShell` or split inspectors.
- Use `WorkspacePageShell` for sticky context plus internal body scroll.
- Use `SplitInspectorLayout` or `SheetInspectorLayout` for selected-item detail panes.
- Keep route-owned forms, query hooks, route params, toasts, and navigation unchanged during visual extraction.

Good candidate families: `frontend/src/pages/memory/list.tsx`, `frontend/src/pages/runs/detail.tsx`, `frontend/src/pages/scheduled-tasks/detail.tsx`, `frontend/src/pages/model-connections/editor.tsx`, and `frontend/src/pages/workflow-packages/editor.tsx`.

### Phase 4: Consolidate Dialogs, Forms, and Tables

Move repeated scaffolding, not domain rules.

- Use `EntityDialogShell` for repeated create/edit dialog frames.
- Keep confirmation-only dialogs feature-owned unless a repeated confirmation pattern emerges.
- Use `ResourceTableFrame` for route-owned tables needing only containment.
- Use `DataTable` when sorting and pagination are generic enough to share.
- Use `form-schemas.ts` only for validation snippets that are already reused across routes.

Good candidate folders: `frontend/src/components/forms`, `frontend/src/components/portfolios`, `frontend/src/pages/model-connections`, and `frontend/src/pages/scheduled-tasks`.

### Phase 5: Audit Deep Feature Widgets

This phase should happen after the shared shell and inventory consolidation is stable.

- Review `frontend/src/components/platform-authoring/**` for repeated tabs, inspectors, generated forms, and structured previews.
- Review `frontend/src/pages/workflow-packages/editor-sections*` for repeated editor pane and validation UI.
- Review `frontend/src/pages/runs/detail-sections/*` for repeated evidence panels and payload wrappers.
- Review `frontend/src/components/portfolios/**` for finance-owned components that should stay extension-owned versus components mature enough for shared UI.

Exit criteria: no feature-specific business rules move into `components/shared`, and no Finance Workspace assumptions leak into platform-core contracts.

## Non-Goals

- Do not implement any code changes from this document without a separate implementation request.
- Do not introduce a new component library or route shell.
- Do not change API contracts, query keys, route paths, or extension gates as part of UI consolidation.
- Do not document removed route families as live surfaces.
- Do not move feature-owned logic into shared presentational components.
