import {
  CalendarClock,
  FileUp,
  PackagePlus,
  PlayCircle,
  SquarePen,
  Trash2,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";

import {
  useDeleteWorkflowPackage,
  useDeleteWorkflowPackages,
  useWorkflowPackages,
} from "@/hooks/use-workflow-packages";
import { useResourceSelectionState } from "@/hooks/use-resource-selection-state";
import { formatDateTime } from "@/lib/format";
import type { WorkflowPackageRead } from "@/lib/types/workflow-package";
import { ConfirmDeleteDialog } from "@/components/shared/confirm-delete-dialog";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { ResourceBulkActionsBar } from "@/components/shared/resource-bulk-actions-bar";
import { ResourceSelectionCheckbox } from "@/components/shared/resource-selection-checkbox";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import { ResourceTableFrame } from "@/components/shared/resource-table-frame";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

function formatNullableHash(value: string | null): string {
  return value ? value.slice(0, 12) : "Not recorded";
}

function hasRecordedHash(value: string | null): boolean {
  return Boolean(value?.trim());
}

function getWorkflowPackageId(workflowPackage: WorkflowPackageRead) {
  return workflowPackage.id;
}

function getPackageReadiness(workflowPackage: WorkflowPackageRead) {
  const hasManifest = hasRecordedHash(workflowPackage.manifestHash);
  const hasCompiledPlan = hasRecordedHash(workflowPackage.compiledHash);

  if (hasManifest && hasCompiledPlan) {
    return {
      label: "Ready for preflight",
      tone: "success" as const,
    };
  }

  return {
    description: "Missing manifest or compiled artifact evidence",
    label: "Needs validation",
    tone: "warning" as const,
  };
}

function sortPackages(items: readonly WorkflowPackageRead[]) {
  return [...items].sort((left, right) => {
    const byUpdated = right.updatedAt.localeCompare(left.updatedAt);
    return byUpdated !== 0 ? byUpdated : left.key.localeCompare(right.key);
  });
}

function filterPackages(items: readonly WorkflowPackageRead[], search: string) {
  const query = search.trim().toLowerCase();
  if (!query) {
    return items;
  }

  return items.filter((item) =>
    [
      item.name,
      item.key,
      item.description,
      item.manifestHash ?? "",
      item.compiledHash ?? "",
      formatNullableHash(item.manifestHash),
      formatNullableHash(item.compiledHash),
      getPackageReadiness(item).label,
    ]
      .join(" ")
      .toLowerCase()
      .includes(query),
  );
}

function LoadingTable() {
  return (
    <ResourceTableFrame>
      <div className="flex flex-col gap-3 p-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton className="h-12 w-full" key={index} />
        ))}
      </div>
    </ResourceTableFrame>
  );
}

function EmptyState({ search }: { search: string }) {
  const hasSearch = Boolean(search.trim());

  return (
    <InventoryStatePanel
      className="bg-card/70"
      description={
        hasSearch
          ? "Refine the search by package name, key, manifest hash, or readiness cue."
          : "Create or import a package manifest to author private agents, schemas, capabilities, MCP bindings, and launch flows."
      }
      testId={
        hasSearch
          ? "workflow-packages-filtered-empty-state"
          : "workflow-packages-empty-state"
      }
      title={
        hasSearch ? "No packages match this search." : "No workflow packages yet."
      }
    />
  );
}

type PackageSelectionHandlers = {
  onDelete: (workflowPackage: WorkflowPackageRead) => void;
  onSelect: (
    packagesToUpdate: readonly WorkflowPackageRead[],
    selected: boolean,
  ) => void;
};

function WorkflowPackagesPageActions() {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <Button asChild size="sm" variant="outline">
        <Link
          aria-label="Import workflow package manifest"
          data-testid="workflow-packages-import"
          to="/workflow-packages/import"
        >
          <FileUp data-icon="inline-start" />
          Import Package
        </Link>
      </Button>
      <Button asChild size="sm" variant="outline">
        <Link
          aria-label="Create scheduled task"
          data-testid="workflow-packages-scheduled-tasks-new"
          to="/scheduled-tasks/new"
        >
          <CalendarClock data-icon="inline-start" />
          Schedule Task
        </Link>
      </Button>
      <Button asChild size="sm">
        <Link
          aria-label="Create new workflow package"
          data-testid="workflow-packages-new"
          to="/workflow-packages/new"
        >
          <PackagePlus data-icon="inline-start" />
          New Package
        </Link>
      </Button>
    </div>
  );
}

function WorkflowPackagesStateCards({
  error,
  filteredCount,
  isError,
  isPending,
  search,
}: {
  error: unknown;
  filteredCount: number;
  isError: boolean;
  isPending: boolean;
  search: string;
}) {
  if (isPending) {
    return <LoadingTable />;
  }

  if (isError) {
    const message =
      error instanceof Error
        ? error.message
        : "Failed to load workflow packages.";

    return (
      <InventoryStatePanel
        testId="workflow-packages-error-state"
        title={message}
        tone="danger"
      />
    );
  }

  return filteredCount === 0 ? <EmptyState search={search} /> : null;
}

function WorkflowPackagesTable({
  allFilteredSelected,
  deletePending,
  packages,
  selectedPackageIds,
  someFilteredSelected,
  onDelete,
  onSelect,
}: {
  allFilteredSelected: boolean;
  deletePending: boolean;
  packages: readonly WorkflowPackageRead[];
  selectedPackageIds: ReadonlySet<WorkflowPackageRead["id"]>;
  someFilteredSelected: boolean;
} & PackageSelectionHandlers) {
  return (
    <ResourceTableFrame>
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead className="w-9">
              <ResourceSelectionCheckbox
                ariaLabel="Select all shown workflow packages"
                indeterminate={someFilteredSelected}
                selected={allFilteredSelected}
                onSelectedChange={(selected) =>
                  onSelect(packages, selected)
                }
              />
            </TableHead>
            <TableHead>Name</TableHead>
            <TableHead>Key</TableHead>
            <TableHead>Readiness</TableHead>
            <TableHead>Manifest hash</TableHead>
            <TableHead>Compiled hash</TableHead>
            <TableHead>Updated</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {packages.map((workflowPackage) => {
            const isSelected = selectedPackageIds.has(workflowPackage.id);
            const readiness = getPackageReadiness(workflowPackage);

            return (
              <TableRow
                key={workflowPackage.id}
                data-state={isSelected ? "selected" : undefined}
                data-testid={`workflow-packages-row-${workflowPackage.key}`}
              >
                <TableCell>
                  <ResourceSelectionCheckbox
                    ariaLabel={`Select workflow package ${workflowPackage.name}`}
                    selected={isSelected}
                    onSelectedChange={(selected) =>
                      onSelect([workflowPackage], selected)
                    }
                  />
                </TableCell>
                <TableCell className="min-w-56 whitespace-normal">
                  <div className="flex flex-col gap-1">
                    <p className="font-medium text-foreground">
                      {workflowPackage.name}
                    </p>
                    <p className="line-clamp-2 text-xs text-muted-foreground">
                      {workflowPackage.description || "No description provided."}
                    </p>
                  </div>
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">
                  {workflowPackage.key}
                </TableCell>
                <TableCell className="min-w-56 whitespace-normal">
                  <div className="flex flex-col gap-1.5 text-xs text-muted-foreground">
                    <ResourceStatusBadge
                      label={readiness.label}
                      tone={readiness.tone}
                    />
                    <span>{readiness.description}</span>
                  </div>
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">
                  {formatNullableHash(workflowPackage.manifestHash)}
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">
                  {formatNullableHash(workflowPackage.compiledHash)}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {formatDateTime(workflowPackage.updatedAt)}
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-2">
                    <Button asChild size="sm" variant="outline">
                      <Link
                        aria-label={`Open package ${workflowPackage.name}`}
                        to={`/workflow-packages/${workflowPackage.id}`}
                      >
                        <SquarePen data-icon="inline-start" />
                        Open
                      </Link>
                    </Button>
                    <Button asChild size="sm" variant="outline">
                      <Link
                        aria-label={`Launch package ${workflowPackage.name}`}
                        to={`/workflow-packages/${workflowPackage.id}/run`}
                      >
                        <PlayCircle data-icon="inline-start" />
                        Launch
                      </Link>
                    </Button>
                    <Button
                      aria-label={`Delete package ${workflowPackage.name}`}
                      className="cursor-pointer"
                      disabled={deletePending}
                      size="sm"
                      variant="destructive"
                      type="button"
                      onClick={() => onDelete(workflowPackage)}
                    >
                      <Trash2 data-icon="inline-start" />
                      Delete
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </ResourceTableFrame>
  );
}

export function WorkflowPackagesListPage() {
  const deletePackage = useDeleteWorkflowPackage();
  const deletePackages = useDeleteWorkflowPackages();
  const packagesQuery = useWorkflowPackages();
  const packages = useMemo(
    () => sortPackages(packagesQuery.data?.items ?? []),
    [packagesQuery.data?.items],
  );
  const [deleting, setDeleting] = useState<WorkflowPackageRead | null>(null);
  const [isBulkDeleting, setIsBulkDeleting] = useState(false);
  const [search, setSearch] = useState("");
  const filteredPackages = useMemo(
    () => filterPackages(packages, search),
    [packages, search],
  );
  const packageSelection = useResourceSelectionState({
    getId: getWorkflowPackageId,
    items: filteredPackages,
  });
  const selectedPackages = packageSelection.selectedItems;
  const selectedCount = packageSelection.selectedCount;
  const allFilteredSelected = packageSelection.allSelected;
  const someFilteredSelected = packageSelection.someSelected;

  const deletePending = deletePackage.isPending || deletePackages.isPending;
  const showTable =
    !packagesQuery.isPending &&
    !packagesQuery.isError &&
    filteredPackages.length > 0;

  const deleteSelectedPackage = async () => {
    if (!deleting) {
      return;
    }

    try {
      await deletePackage.mutateAsync(deleting.id);
      toast.success("Workflow package permanently deleted");
      packageSelection.setIdsSelected([deleting.id], false);
      setDeleting(null);
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Failed to delete workflow package.",
      );
    }
  };

  const confirmDeleteSelectedPackages = () => {
    if (selectedPackages.length === 0) {
      return;
    }

    const packageIds = selectedPackages.map(
      (workflowPackage) => workflowPackage.id,
    );
    const count = selectedPackages.length;
    deletePackages.mutate(packageIds, {
      onError: (error) =>
        toast.error(
          error instanceof Error
            ? error.message
            : "Failed to delete workflow packages.",
        ),
      onSuccess: () => {
        toast.success(
          `${count} ${count === 1 ? "workflow package" : "workflow packages"} deleted`,
        );
        packageSelection.clearSelection();
        setIsBulkDeleting(false);
      },
    });
  };

  return (
    <InventoryPageShell
      pageContext={{
        actions: <WorkflowPackagesPageActions />,
        description: "Author and launch packages.",
        title: "Workflow Packages",
      }}
      testId="workflow-packages-list-page"
      toolbar={{
        resultSummary: `${filteredPackages.length} of ${packages.length} packages shown`,
        search: {
          id: "workflow-package-search",
          label: "Search workflow packages",
          name: "workflowPackageSearch",
          placeholder: "Search packages by name, key, hash, or readiness...",
          value: search,
          onChange: setSearch,
        },
      }}
    >
      <WorkflowPackagesStateCards
        error={packagesQuery.error}
        filteredCount={filteredPackages.length}
        isError={packagesQuery.isError}
        isPending={packagesQuery.isPending}
        search={search}
      />
      {showTable ? (
        <WorkflowPackagesTable
          allFilteredSelected={allFilteredSelected}
          deletePending={deletePending}
          packages={filteredPackages}
          selectedPackageIds={packageSelection.selectedIds}
          someFilteredSelected={someFilteredSelected}
          onDelete={setDeleting}
          onSelect={packageSelection.setItemsSelected}
        />
      ) : null}
      <ResourceBulkActionsBar
        deletePending={deletePackages.isPending}
        resourceLabel="workflow packages"
        selectedCount={selectedCount}
        testId="workflow-packages-bulk-actions"
        totalCount={filteredPackages.length}
        onClear={packageSelection.clearSelection}
        onDeleteSelected={() => setIsBulkDeleting(true)}
      />
      <ConfirmDeleteDialog
        open={isBulkDeleting}
        title="Delete selected workflow packages"
        description={`Permanently delete ${selectedCount} selected ${selectedCount === 1 ? "workflow package" : "workflow packages"}? This deletes ${selectedCount === 1 ? "the package" : "the selected packages"}, related package resources, and ${selectedCount === 1 ? "its" : "their"} owned runs. This cannot be undone.`}
        confirmLabel="Delete selected"
        isPending={deletePackages.isPending}
        onOpenChange={setIsBulkDeleting}
        onConfirm={confirmDeleteSelectedPackages}
      />
      <ConfirmDeleteDialog
        open={deleting !== null}
        title="Delete workflow package"
        description={`Permanently delete ${deleting?.name ?? "this workflow package"}? This deletes the package, related package resources, and its owned runs. This cannot be undone.`}
        confirmLabel="Delete package"
        isPending={deletePackage.isPending}
        onOpenChange={(open) => {
          if (!open) {
            setDeleting(null);
          }
        }}
        onConfirm={deleteSelectedPackage}
      />
    </InventoryPageShell>
  );
}
