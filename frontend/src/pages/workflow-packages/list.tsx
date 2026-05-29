import {
  Box,
  FileUp,
  MoreHorizontal,
  PackagePlus,
  PlayCircle,
  SquarePen,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";

import {
  useDeleteWorkflowPackage,
  useDeleteWorkflowPackages,
  useWorkflowPackages,
} from "@/hooks/use-workflow-packages";
import { useInventoryViewState } from "@/hooks/use-inventory-view-state";
import { formatDateTime } from "@/lib/format";
import type { WorkflowPackageRead } from "@/lib/types/workflow-package";
import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";
import { EmptyStatePanel } from "@/components/shared/empty-state-panel";
import { EvidenceCluster } from "@/components/shared/evidence-cluster";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { ProvenanceBadge } from "@/components/shared/provenance-badge";
import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  PlatformResourceCard,
  PlatformResourceList,
} from "../platform-resource-shared";

function formatNullableHash(value: string | null): string {
  return value ? value.slice(0, 12) : "Not recorded";
}

function hasRecordedHash(value: string | null): boolean {
  return Boolean(value?.trim());
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
    <Card>
      <CardContent className="flex flex-col gap-3 p-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton className="h-12 w-full" key={index} />
        ))}
      </CardContent>
    </Card>
  );
}

function EmptyState({ search }: { search: string }) {
  const hasSearch = Boolean(search.trim());

  return (
    <EmptyStatePanel
      className="bg-card/70"
      description={
        hasSearch
          ? "Refine the search by package name, key, manifest hash, or readiness cue."
          : "Create or import a package manifest to author private agents, schemas, capabilities, MCP bindings, and launch flows."
      }
      icon={
        <div className="flex size-9 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-primary">
          <Box aria-hidden="true" />
        </div>
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
    return (
      <Card role="alert" aria-live="polite">
        <CardContent className="flex items-start gap-3 p-4 text-sm text-muted-foreground">
          <TriangleAlert
            className="mt-0.5 size-4 shrink-0 text-destructive"
            aria-hidden="true"
          />
          <span>
            {error instanceof Error
              ? error.message
              : "Failed to load workflow packages."}
          </span>
        </CardContent>
      </Card>
    );
  }

  return filteredCount === 0 ? <EmptyState search={search} /> : null;
}

function WorkflowPackageStatusStrip({
  workflowPackage,
}: {
  workflowPackage: WorkflowPackageRead;
}) {
  const readiness = getPackageReadiness(workflowPackage);
  const hasManifest = hasRecordedHash(workflowPackage.manifestHash);
  const hasCompiledPlan = hasRecordedHash(workflowPackage.compiledHash);

  return (
    <ResourceStatusStrip
      density="compact"
      items={[
        {
          description: readiness.description,
          label: "Readiness",
          tone: readiness.tone,
          value: readiness.label,
        },
        {
          label: "Manifest",
          tone: hasManifest ? "success" : "warning",
          value: hasManifest ? "Recorded" : "Missing",
        },
        {
          label: "Compiled",
          tone: hasCompiledPlan ? "success" : "warning",
          value: hasCompiledPlan ? "Recorded" : "Missing",
        },
      ]}
    />
  );
}

function WorkflowPackageProvenance({
  workflowPackage,
}: {
  workflowPackage: WorkflowPackageRead;
}) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
      <ProvenanceBadge
        detail={formatNullableHash(workflowPackage.manifestHash)}
        label="Manifest"
        tone={hasRecordedHash(workflowPackage.manifestHash) ? "verified" : "warning"}
      />
      <ProvenanceBadge
        detail={formatNullableHash(workflowPackage.compiledHash)}
        label="Compiled"
        tone={hasRecordedHash(workflowPackage.compiledHash) ? "verified" : "warning"}
      />
      <ProvenanceBadge
        detail={formatDateTime(workflowPackage.updatedAt)}
        label="Updated"
      />
    </div>
  );
}

function WorkflowPackageEvidence({
  workflowPackage,
}: {
  workflowPackage: WorkflowPackageRead;
}) {
  return (
    <EvidenceCluster
      layout="inline"
      items={[
        {
          label: "Package key",
          tone: "neutral",
          value: <span className="font-mono">{workflowPackage.key}</span>,
        },
        {
          label: "Created",
          tone: "neutral",
          value: formatDateTime(workflowPackage.createdAt),
        },
      ]}
    />
  );
}

function WorkflowPackageActions({
  deletePending,
  workflowPackage,
  onDelete,
}: {
  deletePending: boolean;
  workflowPackage: WorkflowPackageRead;
  onDelete: (workflowPackage: WorkflowPackageRead) => void;
}) {
  const packagePath = `/workflow-packages/${workflowPackage.id}`;
  const launchPath = `/workflow-packages/${workflowPackage.id}/run`;

  return (
    <>
      <Button asChild size="sm" variant="outline">
        <Link
          aria-label={`Open package ${workflowPackage.name}`}
          to={packagePath}
        >
          <SquarePen data-icon="inline-start" />
          Open
        </Link>
      </Button>
      <Button asChild size="sm">
        <Link
          aria-label={`Launch package ${workflowPackage.name}`}
          to={launchPath}
        >
          <PlayCircle data-icon="inline-start" />
          Launch
        </Link>
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            aria-label={`Open actions for package ${workflowPackage.name}`}
            className="cursor-pointer"
            size="icon"
            type="button"
            variant="ghost"
          >
            <MoreHorizontal className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            disabled={deletePending}
            onSelect={() => onDelete(workflowPackage)}
            variant="destructive"
          >
            <Trash2 className="size-3.5" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );
}

function WorkflowPackageCards({
  deletePending,
  packages,
  onDelete,
}: {
  deletePending: boolean;
  packages: readonly WorkflowPackageRead[];
  onDelete: (workflowPackage: WorkflowPackageRead) => void;
}) {
  return (
    <PlatformResourceList>
      {packages.map((workflowPackage) => (
        <PlatformResourceCard
          key={workflowPackage.id}
          density="compact"
          testId={`workflow-packages-row-${workflowPackage.key}`}
          title={workflowPackage.name}
          subtitle={<span className="font-mono">{workflowPackage.key}</span>}
          description={
            workflowPackage.description || "No description provided."
          }
          statusStrip={
            <WorkflowPackageStatusStrip workflowPackage={workflowPackage} />
          }
          provenance={
            <WorkflowPackageProvenance workflowPackage={workflowPackage} />
          }
          evidence={<WorkflowPackageEvidence workflowPackage={workflowPackage} />}
          actions={
            <WorkflowPackageActions
              deletePending={deletePending}
              workflowPackage={workflowPackage}
              onDelete={onDelete}
            />
          }
        />
      ))}
    </PlatformResourceList>
  );
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
    <Table>
      <TableHeader>
        <TableRow className="bg-muted/30 hover:bg-muted/30">
          <TableHead className="w-9">
            <Checkbox
              aria-label="Select all shown workflow packages"
              checked={
                allFilteredSelected
                  ? true
                  : someFilteredSelected
                    ? "indeterminate"
                    : false
              }
              onCheckedChange={(checked) =>
                onSelect(packages, checked === true)
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
                <Checkbox
                  aria-label={`Select workflow package ${workflowPackage.name}`}
                  checked={isSelected}
                  onCheckedChange={(checked) =>
                    onSelect([workflowPackage], checked === true)
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
                  <Badge
                    data-tone={readiness.tone}
                    variant={readiness.tone === "success" ? "secondary" : "outline"}
                  >
                    {readiness.label}
                  </Badge>
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
  );
}

function WorkflowPackagesBulkActions({
  filteredCount,
  selectedCount,
  isPending,
  onClear,
  onDeleteSelected,
}: {
  filteredCount: number;
  selectedCount: number;
  isPending: boolean;
  onClear: () => void;
  onDeleteSelected: () => void;
}) {
  if (selectedCount === 0) {
    return null;
  }

  return (
    <div
      data-testid="workflow-packages-bulk-actions"
      className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-muted/30 px-3 py-2"
    >
      <span className="text-xs text-muted-foreground">
        {selectedCount} of {filteredCount} workflow packages selected
      </span>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="destructive"
          disabled={isPending}
          onClick={onDeleteSelected}
        >
          <Trash2 className="size-3.5" /> Delete selected
        </Button>
        <Button size="sm" variant="ghost" onClick={onClear}>
          Clear
        </Button>
      </div>
    </div>
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
  const [selectedPackageIds, setSelectedPackageIds] = useState<
    Set<WorkflowPackageRead["id"]>
  >(new Set());
  const { viewMode, onViewModeChange } = useInventoryViewState({
    initialViewMode: "table",
    onCardsMode: () => setSelectedPackageIds(new Set()),
  });
  const filteredPackages = useMemo(
    () => filterPackages(packages, search),
    [packages, search],
  );
  const selectedPackages = useMemo(
    () =>
      filteredPackages.filter((workflowPackage) =>
        selectedPackageIds.has(workflowPackage.id),
      ),
    [filteredPackages, selectedPackageIds],
  );
  const selectedCount = selectedPackages.length;
  const allFilteredSelected =
    filteredPackages.length > 0 &&
    filteredPackages.every((workflowPackage) =>
      selectedPackageIds.has(workflowPackage.id),
    );
  const someFilteredSelected = filteredPackages.some((workflowPackage) =>
    selectedPackageIds.has(workflowPackage.id),
  );

  const deletePending = deletePackage.isPending || deletePackages.isPending;
  const showCards =
    !packagesQuery.isPending &&
    !packagesQuery.isError &&
    filteredPackages.length > 0 &&
    viewMode === "cards";
  const showTable =
    !packagesQuery.isPending &&
    !packagesQuery.isError &&
    filteredPackages.length > 0 &&
    viewMode === "table";

  const setPackagesSelected = (
    packagesToUpdate: readonly WorkflowPackageRead[],
    selected: boolean,
  ) => {
    setSelectedPackageIds((previous) => {
      const next = new Set(previous);
      packagesToUpdate.forEach((workflowPackage) => {
        if (selected) {
          next.add(workflowPackage.id);
        } else {
          next.delete(workflowPackage.id);
        }
      });
      return next;
    });
  };

  const deleteSelectedPackage = async () => {
    if (!deleting) {
      return;
    }

    try {
      await deletePackage.mutateAsync(deleting.id);
      toast.success("Workflow package permanently deleted");
      setSelectedPackageIds((previous) => {
        const next = new Set(previous);
        next.delete(deleting.id);
        return next;
      });
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
        setSelectedPackageIds(new Set());
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
        viewMode,
        onViewModeChange,
      }}
    >
      <WorkflowPackagesStateCards
        error={packagesQuery.error}
        filteredCount={filteredPackages.length}
        isError={packagesQuery.isError}
        isPending={packagesQuery.isPending}
        search={search}
      />
      {showCards ? (
        <WorkflowPackageCards
          deletePending={deletePending}
          packages={filteredPackages}
          onDelete={setDeleting}
        />
      ) : null}
      {showTable ? (
        <WorkflowPackagesTable
          allFilteredSelected={allFilteredSelected}
          deletePending={deletePending}
          packages={filteredPackages}
          selectedPackageIds={selectedPackageIds}
          someFilteredSelected={someFilteredSelected}
          onDelete={setDeleting}
          onSelect={setPackagesSelected}
        />
      ) : null}
      {viewMode === "table" ? (
        <WorkflowPackagesBulkActions
          filteredCount={filteredPackages.length}
          selectedCount={selectedCount}
          isPending={deletePackages.isPending}
          onClear={() => setSelectedPackageIds(new Set())}
          onDeleteSelected={() => setIsBulkDeleting(true)}
        />
      ) : null}
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
