# Page blueprints

Use these examples when building new frontend pages. Keep route data, hooks, navigation, and mutations in the page or route family. Use shared components for shell and repeatable UI.

## New inventory page

Use this for a list route with search, view mode, active filters, and cards or a table.

```tsx
import { useMemo, useState } from "react";
import { Link } from "react-router";

import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { ResourceRowCard } from "@/components/shared/resource-row-card";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import { Button } from "@/components/ui/button";

type Resource = {
  id: string;
  name: string;
  status: "ready" | "blocked";
};
```
```tsx
export function ExampleInventoryPage({ resources }: { resources: Resource[] }) {
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState("cards");

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return resources;
    return resources.filter((resource) =>
      resource.name.toLowerCase().includes(query),
    );
  }, [resources, search]);

  return (
    <InventoryPageShell
      pageContext={{
        title: "Resources",
        description: "Manage package-owned resources.",
        actions: <Button type="button">Create resource</Button>,
      }}
```
```tsx
      toolbar={{
        search: {
          id: "resource-search",
          label: "Search resources",
          placeholder: "Search resources",
          value: search,
          onChange: setSearch,
        },
        viewMode,
        onViewModeChange: setViewMode,
        resultSummary: `${filtered.length} of ${resources.length} resources`,
      }}
      filterBar={search ? {
        summary: "Filtered view",
        items: [{
          id: "search",
          label: "Search",
          value: search,
          active: true,
          onClear: () => setSearch(""),
        }],
        onClearAll: () => setSearch(""),
      } : null}
    >
```
```tsx
      {filtered.length === 0 ? (
        <InventoryStatePanel
          title="No resources found"
          description="Clear search or create the first resource."
          action={<Button variant="outline" onClick={() => setSearch("")}>Clear search</Button>}
        />
      ) : (
        <div className="grid gap-3">
          {filtered.map((resource) => (
            <ResourceRowCard
              key={resource.id}
              density="compactPlus"
              title={resource.name}
              subtitle={resource.id}
              primaryAction={{
                kind: "link",
                label: `Open ${resource.name}`,
                to: `/resources/${resource.id}`,
              }}
              badges={<ResourceStatusBadge label={resource.status} tone={resource.status === "ready" ? "success" : "warning"} />}
              actions={<Button asChild variant="outline"><Link to={`/resources/${resource.id}`}>Open</Link></Button>}
            />
          ))}
        </div>
      )}
    </InventoryPageShell>
  );
}
```
## Detail or editor shell

Use `WorkspacePageShell` for full-height detail, editor, or console pages. The route metadata should own full-height shell mode before this layout is used.

```tsx
import { PageContextBar } from "@/components/shared/page-context-bar";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { InlineStatePanel } from "@/components/shared/inline-state-panel";
import { Button } from "@/components/ui/button";

export function ExampleEditorPage() {
  return (
    <WorkspacePageShell
      contextBar={
        <PageContextBar
          layout="toolbar"
          title="Edit workflow package"
          description="Author package-local resources and validate the manifest."
          status={<span className="text-xs text-muted-foreground">Draft</span>}
          actions={<Button type="submit" form="package-editor">Save</Button>}
        />
      }
      bodyAriaLabel="Workflow package editor"
    >
```
```tsx
      <form id="package-editor" className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4">
        <InlineStatePanel
          title="Validation runs before launch"
          description="Save changes, then use the launch page for runtime parameters."
        />
        <section aria-label="Package manifest" className="min-h-0 flex-1 rounded-xl border border-border/70 bg-card/95 p-4 shadow-ui-xs">
          <PackageManifestEditor />
        </section>
      </form>
    </WorkspacePageShell>
  );
}
```

Keep editor forms route-owned. The shared shell should not know query keys, route params, API modules, or toast messages.

## Split inspector page

Use this for inventory plus selected detail, run evidence panes, or package resource browsers.

```tsx
import { SplitInspectorLayout } from "@/components/shared/split-inspector-layout";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
```
```tsx
export function ExampleInspectorPage({ selectedId }: { selectedId?: string }) {
  const selected = selectedId ? getResource(selectedId) : null;

  return (
    <SplitInspectorLayout
      leftPane={<ResourceList selectedId={selectedId} />}
      leftPaneAriaLabel="Resources"
      inspectorAriaLabel="Resource inspector"
      inspectorTitle={selected?.name ?? "No resource selected"}
      inspectorOpen={Boolean(selected)}
      emptyInspector={
        <InventoryStatePanel
          title="Select a resource"
          description="Choose a row to inspect details and activity."
        />
      }
      tabs={selected ? [
        { value: "summary", label: "Summary", content: <ResourceSummary resource={selected} /> },
        { value: "events", label: "Events", content: <ResourceEvents id={selected.id} /> },
      ] : undefined}
    />
  );
}
```
## Dialog and form flow

Use `EntityDialogShell` inside shadcn `Dialog` for create or edit flows. Keep dialog open state and submit behavior in the route or owning component.

```tsx
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EntityDialogShell } from "@/components/shared/entity-dialog-shell";

export function CreateResourceDialog({ open, onOpenChange, onSubmit }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <EntityDialogShell
        title="Create resource"
        description="Create a package-owned resource for this workflow."
        footer={
          <>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" form="create-resource-form">Create</Button>
          </>
        }
      >
```
```tsx
        <form id="create-resource-form" className="flex flex-col gap-4" onSubmit={onSubmit}>
          <div className="flex flex-col gap-2">
            <Label htmlFor="resource-name">Name</Label>
            <Input id="resource-name" name="name" required />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="resource-key">Key</Label>
            <Input id="resource-key" name="key" required />
          </div>
        </form>
      </EntityDialogShell>
    </Dialog>
  );
}
```

## Before shipping a new page

1. Add or update `src/routes.metadata.ts` when the page is a live route.
2. Use `InventoryPageShell`, `WorkspacePageShell`, or the route-owned page pattern that matches the route archetype.
3. Use shared state panels for visible loading, empty, filtered-empty, disabled, and error states.
4. Keep query hooks, route params, mutation code, and navigation out of shared components.
5. Check mobile containment, keyboard labels, light theme, and dark theme.
