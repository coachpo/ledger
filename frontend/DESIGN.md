# SignalDeck Design System

## Purpose

SignalDeck is a dense management UI for workflow packages, scheduled runs, model connections, reports, templates, and finance workspace surfaces. The design system keeps those screens consistent without changing product behavior. The current visual language is Apple-inspired management UI: neutral canvases, grouped surfaces, soft elevation, precise spacing, compact typography, and visible focus.

## System Layers

- `src/styles/theme.css` is the token source of truth. Use semantic Tailwind classes and the `--ui-*` tokens for custom surfaces, spacing, layout, shadows, motion, z-index, control sizing, and state values.
- `src/components/ui` contains shadcn/Radix primitives. Keep these presentational and free of route or API logic.
- `src/components/shared` contains reusable SignalDeck UI: page shells, toolbars, state panels, status chrome, table frames, dialogs, and management-list helpers.
- Feature folders and pages own domain copy, route params, hooks, mutations, toasts, navigation, and validation behavior.

## Tokens

Use the existing semantic tokens for product color: `background`, `foreground`, `card`, `muted`, `accent`, `primary`, `destructive`, `border`, `positive`, `negative`, charts, and sidebar colors. Use `text-positive` and `text-negative` only for clear financial deltas.

Use `bg-ui-canvas`, `bg-ui-surface`, `bg-ui-surface-elevated`, `bg-ui-surface-grouped`, `bg-ui-surface-inset`, `bg-ui-surface-chrome`, `border-ui-separator`, `text-ui-text-secondary`, `text-ui-text-tertiary`, `bg-ui-accent-soft`, and `shadow-ui-*` for the renovated surface model. These map to `--ui-*` tokens and keep light/dark behavior aligned.

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
- Route-level empty/error/loading states use `InventoryStatePanel`; inline notices use `InlineStatePanel`; card-like empty states use `EmptyStatePanel`. These are solid grouped/elevated surfaces, not dashed containers.
- Tables use `ResourceTableFrame` around route-owned table markup; routes own columns, sorting, and pagination behavior.
- Status uses `ResourceStatusBadge` and `ResourceStatusStrip`, not route-local colored spans.

## Forms And Dialogs

Forms keep submit handlers, mutations, navigation, and toasts in the page or owning feature component. Shared form shells receive values, callbacks, labels, descriptions, and validation messages.

Use `EntityDialogShell` for create/edit dialogs with a form body and footer. Confirmation-only destructive flows use `ConfirmDeleteDialog`.

## Styling Rules

- Prefer semantic classes and renovated surface tokens: `bg-ui-canvas`, `bg-card/95`, `bg-ui-surface-grouped`, `bg-ui-surface-inset`, `text-foreground`, `text-muted-foreground`, `border-border/70`, `shadow-ui-xs`, `shadow-ui-md`, and `text-destructive`.
- Prefer `flex` or `grid` with `gap-*`; do not add new `space-x-*` or `space-y-*` patterns.
- Prefer `size-*` for square controls.
- Do not introduce new UI libraries, styling frameworks, route-local themes, or decorative variants.
- Keep management screens compact, readable, and stable at 375px, 768px, 1024px, and 1440px.
- Do not add new route-local `rounded-md border bg-muted/20`, `bg-muted/30`, dashed empty containers, or one-off `shadow-sm`/`shadow-md` page chrome. Use shared components or `shadow-ui-*` tokens. Dashed strokes are reserved for data visualization affordances such as chart markers.

## Migration Checklist

- Keep route behavior and data flow unchanged.
- Replace copied page chrome with shared shells first.
- Replace copied search/filter/bulk/state/table/dialog patterns next.
- Move only presentational behavior into shared components.
- Remove obsolete local helpers after all imports are migrated.
- Run focused tests, then lint, typecheck, unit tests, and build.
