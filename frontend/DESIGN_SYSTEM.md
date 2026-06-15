# SignalDeck Design System

## Purpose

SignalDeck is a dense management UI for workflow packages, scheduled runs, model connections, memory, reports, templates, portfolios, and finance workspace surfaces. The design system keeps those screens consistent without changing product behavior.

## System Layers

- `src/styles/theme.css` is the token source of truth. Use semantic Tailwind classes and the `--ui-*` tokens for custom spacing, layout, shadows, motion, z-index, control sizing, and state values.
- `src/components/ui` contains shadcn/Radix primitives. Keep these presentational and free of route or API logic.
- `src/components/shared` contains reusable SignalDeck UI: page shells, toolbars, state panels, status chrome, data-table frames, dialogs, row cards, and management-list helpers.
- Feature folders and pages own domain copy, route params, hooks, mutations, toasts, navigation, and validation behavior.

## Tokens

Use the existing semantic tokens for product color: `background`, `foreground`, `card`, `muted`, `accent`, `primary`, `destructive`, `border`, `positive`, `negative`, charts, and sidebar colors. Use `text-positive` and `text-negative` only for clear financial deltas.

Use `--ui-space-*`, `--ui-shadow-*`, `--ui-z-*`, `--ui-motion-*`, `--ui-breakpoint-*`, `--ui-layout-*`, and `--ui-size-*` when a component needs a value that Tailwind semantic utilities do not already cover. Do not create another token file.

## Layout Rules

- `Layout` owns the app shell, sidebar, breadcrumb, scroll mode, full-height mode, and route width.
- Inventory routes use `InventoryPageShell` with `PageContextBar`, `ResourceToolbar`, optional `ResourceFilterBar`, and route-owned content.
- Full-height editors and consoles use `WorkspacePageShell`.
- Inspectable source/detail flows use `SplitInspectorLayout` or `SheetInspectorLayout`.
- Avoid nested page shells and route-local top-level layout wrappers.

## Component Rules

- Buttons use `Button`; icon buttons need accessible labels.
- Icons inside buttons use `data-icon` where practical.
- Destructive confirmations use `ConfirmDeleteDialog`.
- Selected-count delete/clear bars use `ResourceBulkActionsBar`.
- Row overflow menus use `ResourceActionsMenu`; callers still own menu items, callbacks, navigation, and destructive variants.
- Selectable management tables use `ResourceSelectionCheckbox` for select-all and row checkboxes.
- Ordinary selectable resource lists use `useResourceSelectionState` for selected ids, selected items, selected count, all/some selection, and clear selection.
- Inventory search uses `ResourceToolbar.search`.
- Active filters use `ResourceFilterBar`.
- Route-level empty/error/loading states use `InventoryStatePanel`; inline notices use `InlineStatePanel`; card-like empty states use `EmptyStatePanel`.
- Tables use `DataTable` when generic sorting/pagination fits, or `ResourceTableFrame` around route-owned table markup.
- Status uses `ResourceStatusBadge` and `ResourceStatusStrip`, not route-local colored spans.

## Forms And Dialogs

Forms keep submit handlers, mutations, navigation, and toasts in the page or owning feature component. Shared form shells receive values, callbacks, labels, descriptions, and validation messages.

Use `EntityDialogShell` for create/edit dialogs with a form body and footer. Confirmation-only destructive flows use `ConfirmDeleteDialog`.

## Styling Rules

- Prefer semantic classes: `bg-background`, `bg-card`, `text-foreground`, `text-muted-foreground`, `border-border`, `bg-muted/30`, `text-destructive`.
- Prefer `flex` or `grid` with `gap-*`; do not add new `space-x-*` or `space-y-*` patterns.
- Prefer `size-*` for square controls.
- Do not introduce new UI libraries, styling frameworks, route-local themes, or decorative variants.
- Keep management screens compact, readable, and stable at 375px, 768px, 1024px, and 1440px.

## Migration Checklist

- Keep route behavior and data flow unchanged.
- Replace copied page chrome with shared shells first.
- Replace copied search/filter/bulk/state/table/dialog patterns next.
- Move only presentational behavior into shared components.
- Remove obsolete local helpers after all imports are migrated.
- Run focused tests, then lint, typecheck, unit tests, and build.
