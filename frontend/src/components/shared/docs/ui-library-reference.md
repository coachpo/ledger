# UI library reference

This reference documents project-owned shared UI in `src/components/shared`. It is for developers building frontend routes. It does not replace shadcn docs for primitives in `src/components/ui`.

## InventoryPageShell

Purpose: standard page stack for inventory routes with a header, optional toolbar, optional filter bar, and content region.

Use when a route lists resources and needs consistent page context, search or filters, and card or table content.

Don't use for full-height editors, run consoles, or split-pane workspaces. Use `WorkspacePageShell` or route metadata full-height mode instead.

API: `children`, `pageContext`, optional `toolbar`, optional `filterBar`, optional `className`, `contentClassName`, and `testId`.

Accessibility: the shell preserves region order. The supplied `PageContextBar`, toolbar controls, and content must carry labels.

Example:
```tsx
<InventoryPageShell
  pageContext={{
    title: "Reports",
    description: "Browse generated report snapshots.",
    actions: <Button type="button">Upload report</Button>,
  }}
  toolbar={{
    search: {
      id: "report-search",
      label: "Search reports",
      value: search,
      onChange: setSearch,
    },
    resultSummary: `${filteredReports.length} reports`,
  }}
>
  <ReportList reports={filteredReports} />
</InventoryPageShell>
```

Common mistakes: nesting another page shell inside it, putting data fetching inside shared shell props, or hiding the route title in local markup.
## WorkspacePageShell

Purpose: full-height workspace frame with sticky context bar, optional left rail, and internally scrolling body.

Use for editors, consoles, and detail pages where the route metadata uses full-height shell behavior.

Don't use for simple lists that can scroll with the document.

API: `contextBar`, `children`, optional `leftRail`, `bodyAriaLabel`, `leftRailAriaLabel`, `className`, `contentClassName`, `contextBarClassName`, `leftRailClassName`, `bodyClassName`, and `testId`.

Accessibility: set specific aria labels when the default labels are not enough.

Example:

```tsx
<WorkspacePageShell
  contextBar={<PageContextBar title="Run detail" status={<RunStatus />} />}
  bodyAriaLabel="Run evidence"
  leftRail={<RunStepList />}
  leftRailAriaLabel="Run steps"
>
  <RunEvidencePanels />
</WorkspacePageShell>
```
Common mistakes: adding a nested `main`, allowing body content to escape internal scroll, or rebuilding breadcrumbs in the context bar.

## SplitInspectorLayout and SheetInspectorLayout

Purpose: two-region source and inspector layout with optional tabs, inspector actions, and empty inspector content.

Use `SplitInspectorLayout` for desktop split panes. Use `SheetInspectorLayout` when the inspector should be controlled as a sheet.

Don't use for basic dialogs or route lists without an inspectable selected item.

API: `leftPane`, `emptyInspector`, optional `rightPane`, `tabs`, `activeTab`, `onActiveTabChange`, `inspectorTitle`, `inspectorActions`, `inspectorOpen`, aria labels, panel size props, and `testId`. Sheet mode adds `onInspectorOpenChange` and `sheetDescription`.

Variants: direction `horizontal` or `vertical`; panel sizes through `defaultSize`, `minSize`, and `maxSize`.

Accessibility: source and inspector regions are `section` and `aside`. Use specific labels when showing entities, runs, or payloads.
```tsx
<SplitInspectorLayout
  leftPane={<PackageList />}
  leftPaneAriaLabel="Workflow packages"
  inspectorAriaLabel="Selected package details"
  inspectorTitle={selectedPackage?.name ?? "No package selected"}
  inspectorOpen={Boolean(selectedPackage)}
  emptyInspector={<InventoryStatePanel title="Select a package" />}
  tabs={selectedPackage ? [
    { value: "summary", label: "Summary", content: <PackageSummary /> },
    { value: "manifest", label: "Manifest", content: <ManifestPreview /> },
  ] : undefined}
/>
```

Common mistakes: using the split layout on routes without full-height metadata, leaving tabs uncontrolled when route state owns the active tab, or omitting useful inspector labels.
## PageContextBar

Purpose: consistent route title, description, metadata, status, and action row.

Use inside `InventoryPageShell`, `WorkspacePageShell.contextBar`, or route-owned compact headers.

Don't use for card titles or nested section headings.

API: `title`, optional `description`, `meta`, `status`, `actions`, `density`, `layout`, `toolbarMetaPlacement`, and `className`.

Variants: density `compact` or `comfortable`; layout `stacked` or `toolbar`; toolbar metadata placement `below` or `middle`.

Accessibility: renders the page title as `h1`. Keep one logical route title per page.

Common mistakes: duplicating `h1` elsewhere, passing long descriptions that should be body copy, or using actions for navigation that should be links.

## ResourceToolbar

Purpose: compact inventory search, filters, view toggle, actions, result summary, and selection summary.
Use for inventory pages that need search or view controls.

Don't use as a page header or form action footer.

API: optional `search`, `filters`, `viewMode`, `viewModes`, `onViewModeChange`, `actions`, `resultSummary`, `selectionSummary`, `children`, and `className`.

Search API: `id`, `label`, `value`, `onChange`, optional `placeholder`, `name`, `disabled`, and `testId`.

Variants: default view options are cards and table. Custom view options accept `value`, `label`, optional `icon`, `disabled`, and `testId`.

Accessibility: search has `role="search"`, a hidden label, and an input aria label. Icon-only view toggles use aria labels.

Common mistakes: using placeholder-only search labels, allowing empty `onValueChange` to clear a single toggle, or creating route-local search wrappers.

## ResourceFilterBar

Purpose: active filter summary with badge chips, clear buttons, custom children, and clear-all action.
Use when filters are active, or when a route needs a compact summary below the toolbar.

Don't render an empty local filter container. This component returns `null` when it has no content.

API: `items`, optional `summary`, `actions`, `children`, `clearAllLabel`, `onClearAll`, `className`, and `testId`.

Item API: `id`, `label`, optional `value`, `active`, `clearLabel`, and `onClear`.

Accessibility: clear buttons need meaningful labels. The default is based on the item label, but route-owned labels are better for non-string labels.

Common mistakes: duplicating active filter chips in the toolbar and filter bar, or rendering clear controls that don't update route state.

## ResourceBulkActionsBar

Purpose: standard selected-count bar for inventory bulk actions.

Use when a management list has selected rows and needs the common destructive delete plus clear-selection controls.

Don't use for row-level actions or non-destructive filter summaries. Use `ResourceFilterBar` for active filters.

API: `selectedCount`, `totalCount`, `resourceLabel`, `onDeleteSelected`, `onClear`, optional `deletePending`, `deleteLabel`, `clearLabel`, `summary`, and `testId`.

Accessibility: routes still own the action meaning. Use clear resource labels such as `reports`, `templates`, or `scheduled tasks`.

Common mistakes: moving mutation logic into the component, or using it when a route needs a different bulk workflow than delete/clear.

## ResourceSelectionCheckbox

Purpose: standard checkbox for selectable management rows and select-all table headers.

Use when a resource list already owns selection state and needs consistent accessible checkbox wiring for row or visible-list selection.

Don't use for forms, feature toggles, boolean settings, or editor checkboxes.

API: `ariaLabel`, `selected`, `onSelectedChange`, optional `indeterminate`, `disabled`, `className`, and `testId`.

Accessibility: labels should describe the selection target, such as `Select all shown templates` or `Select report Quarterly review`.

Example:

```tsx
<ResourceSelectionCheckbox
  ariaLabel="Select all shown reports"
  indeterminate={someReportsSelected}
  selected={allReportsSelected}
  onSelectedChange={(selected) =>
    reportSelection.setItemsSelected(visibleReports, selected)
  }
/>
```

Common mistakes: using it for non-resource form fields, passing generic labels, or moving selected-id state into the component.

## ResourceActionsMenu

Purpose: standard row or compact header overflow menu trigger and dropdown frame.

Use when a resource row, table action cell, or compact header needs the common "more actions" icon button with consistent sizing, labels, alignment, and menu content framing.

Don't use for bulk actions, primary row navigation, or menus that need custom trigger content.

API: `ariaLabel`, `children`, optional `align`, `disabled`, `testId`, `triggerClassName`, `triggerVariant`, `contentClassName`, and `className`.

Accessibility: every caller must pass a specific `ariaLabel`, such as `Open actions for Quarterly report`. Menu items remain route-owned links or buttons through shadcn `DropdownMenuItem`.

Example:

```tsx
<ResourceActionsMenu ariaLabel={`Open actions for ${report.name}`}>
  <DropdownMenuItem asChild>
    <a href={downloadReportUrl(report.slug)} download>
      <Download data-icon="inline-start" />
      Download
    </a>
  </DropdownMenuItem>
  <DropdownMenuItem
    variant="destructive"
    onSelect={() => setDeleting(report)}
  >
    <Trash2 data-icon="inline-start" />
    Delete
  </DropdownMenuItem>
</ResourceActionsMenu>
```

Common mistakes: moving route callbacks into the component, using generic labels like `Actions`, or wrapping a visible primary action that should be a normal button or link.

## ResourceRowCard

Purpose: compact resource card for inventory lists with title link, metadata, badges, evidence, status, provenance, footer, and trailing actions.

Use for portfolio, template, report, run, or platform resource lists where cards are clearer than a table.
Don't use for static metric summaries or deeply nested editor panes.

API: `title`, optional `subtitle`, `description`, `metadata`, `badges`, `leading`, `actions`, `primaryAction`, `bodyAction`, `selected`, `statusStrip`, `provenance`, `factsGrid`, `evidenceChips`, `evidence`, `footer`, `density`, `className`, and `testId`.

Variants: density `compact` or `compactPlus`.

Accessibility: title links use React Router `Link` and need clear labels. Actions must be buttons or links, not pointer-only wrappers.

Example:

```tsx
<ResourceRowCard
  density="compactPlus"
  title={report.name}
  subtitle={report.slug}
  metadata={`Updated ${formatDate(report.updatedAt)}`}
  primaryAction={{ kind: "link", label: `Open ${report.name}`, to: `/reports/${report.slug}` }}
  badges={<ResourceStatusBadge label={report.source} tone="muted" />}
/>
```
Common mistakes: wrapping the whole card in a click handler, putting feature-specific fetch logic in card props, or using badges without text.

## ResourceStatusStrip and ResourceStatusBadge

Purpose: standard status display for resource facts and compact state badges.

Use badges for a single state. Use strips for several facts such as readiness, queue state, source, or validation result.

Don't use raw colored spans for shared status UI.

Badge API: `label`, optional `tone`, `className`, and `testId`.

Strip API: `items`, optional `density`, `emptyLabel`, and `className`.

Variants: tones `neutral`, `success`, `warning`, `danger`, and `muted`; strip density `compact`, `comfortable`, and `toolbar`.

Accessibility: strips render `role="list"` and each item as `role="listitem"`. Keep label and value text meaningful.
Common mistakes: relying on tone color alone, passing empty item arrays when a route-specific empty state would be clearer, or adding new tone names without updating the component.

## ResourceTableFrame

Purpose: minimal rounded bordered table container with width containment.

Use when route-owned table markup already exists and only needs the shared frame.

Don't use when you need TanStack sorting and pagination. Use `DataTable` instead.

API: `children`, optional `className`, and `testId`.

Accessibility: the table inside still needs its own labels, headers, and actions.

Common mistakes: expecting this component to add horizontal scroll or pagination. The child table owns those details.

## EmptyStatePanel, InventoryStatePanel, and InlineStatePanel

Purpose: standard empty, warning, and error state surfaces.

Use `InventoryStatePanel` for inventory route states. Use `EmptyStatePanel` for card-like empty states with optional icon and action. Use `InlineStatePanel` for notices inside another panel or form section.
Don't create custom dashed alerts for each route.

Shared API: `title`, optional `description`, `action`, `className`, `testId`, and `tone` where supported. `EmptyStatePanel` and `InlineStatePanel` also accept `icon`; `InlineStatePanel` accepts `children`.

Variants: tones `neutral`, `warning`, and `danger`.

Accessibility: panels use shadcn `Alert`, `AlertTitle`, and `AlertDescription`. Icons are decorative unless the surrounding copy doesn't explain the state.

Example:

```tsx
<InventoryStatePanel
  tone="warning"
  title="No matching schedules"
  description="Clear filters to see all scheduled package runs."
  action={<Button variant="outline" onClick={clearFilters}>Clear filters</Button>}
/>
```

Common mistakes: using a danger tone for normal empty states, omitting action labels, or using inline notices as page-level errors.
## EntityDialogShell

Purpose: shared dialog content frame for entity forms.

Use inside a shadcn `Dialog` when a create or edit flow needs title, description, optional constraint strip, scrollable body, and footer actions.

Don't use for confirmation-only dialogs or sheet inspectors.

API: `title`, `footer`, `children`, optional `description`, `constraintStrip`, and `className`.

Accessibility: `DialogTitle` is always rendered. Keep the parent `Dialog` state controlled by the route or owning component.

Example:

```tsx
<Dialog open={open} onOpenChange={setOpen}>
  <EntityDialogShell
    title="Create model connection"
    description="Save provider metadata. Secrets stay write-only."
    footer={<Button type="submit" form="connection-form">Save</Button>}
  >
    <ConnectionForm id="connection-form" />
  </EntityDialogShell>
</Dialog>
```
Common mistakes: placing `DialogContent` around `EntityDialogShell`, omitting footer actions, or letting the dialog component call route APIs directly.

## ConfirmDeleteDialog

Purpose: controlled destructive confirmation dialog for cross-route delete flows.

Use for confirmation-only destructive actions. Parent pages keep mutation state, toasts, navigation, and selection cleanup.

Don't use for create/edit form dialogs. Use `EntityDialogShell` inside a normal `Dialog` for those.

API: `open`, `title`, `description`, `onOpenChange`, `onConfirm`, optional `confirmLabel`, and optional `isPending`.

Accessibility: renders shadcn `AlertDialogTitle` and `AlertDialogDescription`; keep descriptions explicit about irreversible effects.

## MetricCard

Purpose: compact KPI card with title, value, note, optional icon, status, provenance, footer, and optional link behavior.

Use for dashboard and summary metrics.

Don't use for inventory rows or editable fields.

API: `title`, `value`, optional `density`, `tone`, `note`, `icon`, `iconClassName`, `status`, `provenance`, `footer`, `to`, and `valueClassName`.

Variants: density `default` or `compact`; tone `default` or `muted`.

Accessibility: when `to` is provided, the card renders as a link. The title and value must make the destination clear enough in context.

Common mistakes: using metric cards for action panels, hiding key status in icon color only, or putting long prose in `note`.
## DataTable and DataTableColumnHeader

Purpose: generic TanStack table wrapper with sorting, pagination, density options, empty message, and row test id support.

Use for data that benefits from tabular scan, sortable columns, and pagination.

Don't use for simple cards, route-owned custom tables that already handle paging, or wide payload consoles.

DataTable API: `columns`, `data`, `emptyMessage`, optional `density`, `initialSorting`, `initialPageSize`, `pageSizeOptions`, `tableLabel`, `getRowTestId`, and `className`.

Column header API: `column`, `title`, optional `density`, and `className`.

Variants: table density `comfortable` or `compact`; header density `comfortable` or `compact`.

Accessibility: pass `tableLabel` when the surrounding heading is not enough. Sortable headers use buttons with aria labels and title text.

Common mistakes: putting navigation on a row instead of a cell link, using table state as route state without syncing intentionally, or forgetting `emptyMessage`.
