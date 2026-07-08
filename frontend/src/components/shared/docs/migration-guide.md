# UI migration guide

Use this guide when cleaning older route-local UI. The goal is not a visual rewrite. The goal is to move repeated page chrome and state patterns into the current shared library while preserving route behavior.

## What to replace

Replace route-local inventory wrappers with `InventoryPageShell` when the page has a title, description, actions, toolbar, filters, and list or table content.

Replace hand-built search rows with `ResourceToolbar.search`. It gives compact sizing, a hidden label, search role, icon placement, and consistent summary placement.

Replace local active filter chip rows with `ResourceFilterBar`.

Replace selected-count delete/clear bars with `ResourceBulkActionsBar`.

Replace repeated row overflow dropdown trigger/content wrappers with `ResourceActionsMenu`.

Replace resource table select-all and row selection checkbox wiring with `ResourceSelectionCheckbox`.

Replace repeated card rows with `ResourceRowCard` when the card represents a resource and needs title link, badges, metadata, status, evidence, or actions.

Replace raw status spans with `ResourceStatusBadge` or `ResourceStatusStrip`.

Replace ad-hoc bordered table wrappers with `ResourceTableFrame`, or replace small custom sortable tables with `DataTable`.
Replace local empty, warning, and error card markup with `InventoryStatePanel`, `EmptyStatePanel`, or `InlineStatePanel`.

Replace create or edit dialog content scaffolding with `EntityDialogShell` when the flow has a form body and footer actions.

Replace destructive confirmation dialogs with `ConfirmDeleteDialog`.

Leave route-local inspector scaffolds alone unless a second route needs the same markup.

## What to leave route-owned

Leave data fetching in `src/hooks` and API modules. Shared UI should not call `fetch`, use query keys, or know backend endpoints.

Leave route params, navigation, links, redirects, toasts, and mutation sequencing in pages or route-family helpers.

Leave feature-specific copy, column definitions, validation messages, and form submit handlers with the owning route.

Leave route metadata in `src/routes.metadata.ts` and shell rendering in `layout.tsx`.
Leave feature-only widgets in their feature folder until they have a second real use case.

## Replacement map

| Older local pattern | Replace with | Notes |
| --- | --- | --- |
| Page-local title, summary, toolbar, and list stack | `InventoryPageShell` | Pass `pageContext`, `toolbar`, and `filterBar` props from the route. |
| Search input with copied icon and sizing | `ResourceToolbar.search` | Keep search state route-owned. |
| Filter summary card or badge row | `ResourceFilterBar` | Use item `onClear` callbacks to update route state. |
| Selected-count delete/clear bar | `ResourceBulkActionsBar` | Keep selection state, mutation calls, and toasts route-owned. |
| Row action dropdown trigger/content wrapper | `ResourceActionsMenu` | Keep `DropdownMenuItem` children, links, callbacks, and destructive variants route-owned. |
| Resource row or select-all checkbox checked-state mapping | `ResourceSelectionCheckbox` | Keep selected ids, selected items, and mutation behavior route-owned. |
| Clickable resource card wrapper | `ResourceRowCard` plus `primaryAction` | Use real links and buttons. |
| Status text with custom colors | `ResourceStatusBadge` or `ResourceStatusStrip` | Use supported tones only. |
| Dashed empty or error cards | `InventoryStatePanel`, `EmptyStatePanel`, or `InlineStatePanel` | Match the scope of the state; shared state panels now use solid grouped/elevated surfaces. |
| `rounded-md border bg-muted/20` route panels | Shared shell, `Card`, `ResourceTableFrame`, or a route-owned section component using `bg-card/70` or `bg-ui-surface-grouped` plus `shadow-ui-*` | Keep route copy and behavior in place while replacing only the visual wrapper. |
| `shadow-sm`, `shadow-md`, or `shadow-lg` page chrome | `shadow-ui-xs`, `shadow-ui-md`, or primitive defaults | Keep one elevation scale across light and dark themes. |
| New `space-y-*` stacks in shared UI | `flex flex-col gap-*` or `grid gap-*` | Keeps spacing explicit and easier to combine with responsive layouts. |
| Local dialog content frame | `EntityDialogShell` | Parent still controls `Dialog` open state. |
| Local destructive confirmation | `ConfirmDeleteDialog` | Parent still owns mutation state and post-delete cleanup. |
| Local split pane with resize or inspector | Route-owned panel or dialog | Add shared layout only after repeated use. |
## Incremental migration order

1. Confirm the route is live in `src/routes.ts` and has correct metadata in `src/routes.metadata.ts`.
2. Identify repeated chrome: page context, search, filters, state panels, rows, status, table frame, dialog frame, or inspector.
3. Replace one layer at a time. Start with page shell and toolbar, then state panels, then rows or tables, then dialogs.
4. Keep the route's hook calls, derived data, mutations, toasts, and navigation unchanged during the visual extraction.
5. Run focused tests for the route or component after each layer moves.
6. Remove dead local helper components only after the shared replacement is wired and verified.

## Guardrails

Don't add `/src/ui` or a second library structure.

Don't move a one-off route widget into `components/shared` before there is real reuse.

Don't document removed route families as active migration targets.
Don't put report-only, template-only, package-only, run-only, or extension-only request logic into shared components.

Don't change API field names, query keys, route paths, or backend-owned tool contracts as part of a UI-only migration.

Don't hide accessibility regressions behind visual parity. Search, filters, dialogs, tables, cards, and inspector panes still need labels, keyboard access, and visible focus.

## UI PR checklist

- The change stays frontend-only unless the task explicitly asks for backend work.
- New shared UI lives in `components/shared`; primitive wrappers stay in `components/ui`.
- Route metadata and `Layout` still own page shell behavior.
- Search, filters, status, empty states, dialogs, and tables use the shared patterns where they fit.
- Links navigate. Buttons mutate, sort, toggle, or open transient UI.
- Long ids, JSON, markdown, tables, and badges are mobile contained.
- Light and dark themes remain readable.
- No new route-local muted slabs, dashed empty containers, or one-off shadow utilities were introduced outside intentional chart/data-visualization affordances.
- Component and route tests are updated when visible states or shared contracts change.
