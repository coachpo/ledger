# UI and UX standard

This is the project-owned frontend UI standard for SignalDeck. It reflects the current React and Vite app, the shared component set in `src/components/shared`, shadcn primitives in `src/components/ui`, route metadata in `src/routes.metadata.ts`, layout ownership in `src/components/layout.tsx`, and theme tokens in `src/styles/theme.css`.

## Assumptions

SignalDeck is a workflow and finance workspace app with dense data, long identifiers, markdown, JSON, run evidence, tables, and editor panes. The app ships a flat route tree under one layout shell. Workflow Packages, Scheduled Tasks, Model Connections, Runs, and static finance routes are live surfaces. Removed route families are not active UI targets.

The frontend has no user migration burden yet, so new work should prefer the shared library and current route contracts over compatibility wrappers.

## Design principles

Use one route shell. `Layout` owns page framing, sidebar navigation, breadcrumbs, full-height treatment, and route metadata consumption.

Keep pages thin. Pages choose data, route params, actions, and feature text. Shared components own repeatable chrome, spacing, table frames, status display, and shell structure.

Prefer compact density. This app is an operator workspace, not a marketing page. Lists, filters, and status panels should be readable at high information density.

Use the renovated Apple-inspired surface model. Screens should read as a calm management workspace: neutral canvas, grouped surfaces, crisp separators, soft elevation, precise alignment, and compact system typography. Avoid decorative gradients, oversized marketing sections, and card-heavy bento layouts for ordinary management workflows.

Use semantic tokens. Colors come from `theme.css` and Tailwind semantic classes such as `bg-ui-canvas`, `bg-card/95`, `bg-ui-surface-grouped`, `bg-ui-surface-inset`, `text-foreground`, `text-muted-foreground`, `border-border/70`, `text-destructive`, `text-positive`, and `text-negative`.

Make state explicit. Loading, empty, filtered-empty, unavailable, error, saving, validating, launching, and polling states should map to route metadata and visible UI states.

Keep route ownership visible. Feature labels, route-specific copy, query hooks, mutation behavior, toasts, and navigation stay route-owned.

## Layout and spacing

Inventory routes use `InventoryPageShell` when the route has a page header, toolbar, optional filter bar, and list or table content. Keep the default stack of `flex flex-col gap-4 p-4` unless the route has a documented reason to tune spacing.

Workspace and console routes use `WorkspacePageShell` when content needs full-height layout, a sticky context bar, optional left rail, and an internally scrolling body.

Inspector flows stay route-owned; use dialogs or simple panels before adding shared split-pane scaffolding.
Use `gap-*` for spacing. Don't use `space-x-*` or `space-y-*` in new shared UI. Prefer `min-w-0`, `overflow-auto`, `break-words`, and table wrappers for dense content.

Use the project `--ui-*` tokens when component CSS needs custom values for surfaces, spacing, shadows, z-index, motion, breakpoints, or control sizes. Don't create a parallel token file.

## Typography

Page titles use `PageContextBar`, which renders the route title as a responsive `h1` with `text-2xl` and `sm:text-3xl`.

Detail titles use compact heading styles such as `text-xl font-semibold tracking-tight`. Inventory card titles use the shared row card title treatment.

Body copy uses `text-sm` or `text-xs` depending on density. Supporting text uses `text-muted-foreground`. Avoid washed-out copy that fails in light mode.

Keep long ids, hashes, package keys, and URLs readable with wrapping, clipping, or internal scroll. Don't hide entity identity behind aggressive truncation.
## Color and theme

Use theme classes and shadcn variants before custom colors. `ResourceStatusBadge` owns status badge tone mapping for neutral, success, warning, danger, and muted states.

Use `text-positive` and `text-negative` for financial deltas only when the value meaning is clear. Pair color with labels or icons when color indicates status.

Don't add route-local theme state. `theme-provider.tsx` owns theme persistence and system sync.

Check light and dark themes for every new shared pattern. Borders, grouped panels, inset surfaces, elevated cards, and focus shadows must remain visible in both themes.

Do not add new route-local `bg-muted/20`, `bg-muted/30`, `rounded-md border bg-muted/*`, `border-dashed`, or `shadow-sm`/`shadow-md` page chrome. Use shared state/table/dialog components or the `bg-ui-*` and `shadow-ui-*` tokens. Dashed strokes are reserved for data-visualization affordances such as chart markers.

## Icons

Use `lucide-react`, matching the current project. Icons should be decorative unless they carry unique meaning, then provide labels through the surrounding control.

Buttons with icons need readable text or an `aria-label`. Icon-only toggle items need `aria-label`, as in `ResourceToolbar` view controls.

Use `size-*` utilities for square icon boxes and controls. Keep icon sizing consistent with current shared components, usually `size-4` for inline icons and compact controls.
## Buttons and actions

Use `Button` from `components/ui/button`. Use links for navigation to real URLs and buttons for mutations, dialogs, sorting, toggles, and transient UI.

Primary actions sit in `PageContextBar.actions` or `ResourceToolbar.actions`. Secondary actions come before destructive or save actions in detail/editor flows.

Use disabled state for in-flight mutations. Pair mutation feedback with Sonner toasts where the route already uses toast feedback.

Don't make whole table rows or static cells clickable. Put a real link or button inside the row.

## Forms

Use shadcn form primitives and existing cross-route helpers. Shared dialogs such as `EntityDialogShell` provide the content frame, title, description, optional constraint strip, scrollable body, and footer.

Labels are required. Placeholder-only labels are not enough for route-critical search, filter, or form controls.

Route forms own submit handlers, API calls, validation wiring, toasts, navigation, and dirty-state decisions. Shared form components receive values, callbacks, and validation messages.
Use `ResourceToolbar.search` for compact inventory search. It supplies a hidden label, `role="search"`, the search icon, `h-8` input height, and compact text.

## Tables, lists, and resource rows

Use `DataTable` for small generic sortable tables. Use `ResourceTableFrame` for route-owned table markup that only needs the shared border and containment frame.

Use `ResourceRowCard` for compact inventory cards that need title links, badges, metadata, status strips, evidence chips, provenance, or trailing actions.

Use `ResourceStatusStrip` for grouped status facts and `ResourceStatusBadge` for single status pills.

Lists and tables must be mobile contained. Use `min-w-0`, internal horizontal scroll where needed, and wrapping for long user or run data.

## Modals, dialogs, drawers, and inspectors

Use shadcn `Dialog`, `Sheet`, and related primitives. Every dialog or sheet needs a title, visible or screen-reader-only.
Use `EntityDialogShell` for entity create or edit dialogs with a form body and footer actions.

Keep inspector dialogs and panels labeled. Promote a shared inspector layout only after repeated route-owned markup proves it needs one.

Dialogs should not fetch data directly. The parent route or hook supplies data and callbacks.

## Navigation

`src/routes.ts` registers live routes. `src/routes.metadata.ts` defines route archetype, breadcrumb title, nav label, sidebar test id, shell mode, ownership, and state variants.

`Layout` renders sidebar, breadcrumbs, shell mode, width mode, and the single page-level `main`. Leaf pages don't rebuild those structures.

Routes are static frontend entries. Platform/system routes stay available according to the platform contracts, and package tool pickers read backend-owned `/api/tools` metadata.

## State patterns

Use `InventoryStatePanel` for route-level inventory empty, filtered-empty, disabled, or error states inside inventory pages.
Use `EmptyStatePanel` for card-like empty states that may include an icon and action.

Use `InlineStatePanel` for inline notices inside existing panels, forms, payload sections, or split panes.

Use tone `neutral` for normal empty states, `warning` for recoverable attention, and `danger` for destructive or failed states. Use `success` only where a component supports it, such as status badges.

Loading states should reserve enough structure to avoid layout jumps. Route-level loading, error, and empty states should match route metadata and tests when user-visible.

## Responsive behavior

Design for 375px, 768px, 1024px, and 1440px. Inventory controls wrap, not overflow. Full-height workspaces keep internal scrolling instead of document-wide overflow.

Use route-owned responsive branching when inspector content would be cramped on small screens.

Floating or sticky chrome needs enough clearance from viewport edges and fixed shell regions.
## Accessibility requirements

Use semantic regions: one page `main` from `Layout`, `section` and `aside` labels for workspaces and inspectors, `role="search"` for search controls, and `role="list"` where status strips render list-like facts.

Every input, select, search field, and icon-only action needs a programmatic label. Link text and button labels must describe the action.

Focus states must remain visible. Don't remove shadcn focus rings. Dialogs and sheets must keep focus trapped through their primitives.

Use status text and labels, not color alone. Badge tone can support the message, but it cannot be the only cue.

## Naming conventions

Shared component names describe UI shape and scope: `InventoryPageShell`, `WorkspacePageShell`, `ResourceToolbar`, `ResourceRowCard`, `InlineStatePanel`.

Use `Resource*` for reusable inventory chrome, `*Shell` for structural wrappers, `*Panel` for empty, inline, or state containers, and `*Layout` for multi-region arrangements.
Props should name semantic regions, not implementation details. Prefer `pageContext`, `toolbar`, `filterBar`, `leftPane`, `rightPane`, `emptyInspector`, `actions`, and `status`.

Test ids should be route or component specific and stable. Shared shells already expose region attributes such as `data-inventory-shell-region` and `data-workspace-shell-region`.

## Do and don't

Do use `components/shared` for cross-feature shells and repeated resource chrome.

Do use `components/ui` primitives instead of raw styled HTML for buttons, cards, badges, dialogs, sheets, tables, alerts, inputs, toggles, and selects.

Do use `routes.metadata.ts` and `layout.tsx` for route shell decisions.

Don't create `/src/ui`, a second component library, or route-local clones of shared inventory controls.

Don't document removed route families as active UI targets.

Don't move feature business rules, query hooks, route params, or API calls into shared presentational components.
