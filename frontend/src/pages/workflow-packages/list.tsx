import {
  Box,
  FileUp,
  LayoutGrid,
  List,
  MoreHorizontal,
  PackagePlus,
  PlayCircle,
  Search,
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
import { formatDateTime } from "@/lib/format";
import type { WorkflowPackageRead } from "@/lib/types/workflow-package";
import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

import {
  PlatformResourceCard,
  PlatformResourceList,
} from "../platform-resource-shared";

function formatNullableHash(value: string | null): string {
  return value ? value.slice(0, 12) : "Not recorded";
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
    ]
      .join(" ")
      .toLowerCase()
      .includes(query),
  );
}

function LoadingTable() {
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton className="h-12 w-full" key={index} />
        ))}
      </CardContent>
    </Card>
  );
}

function EmptyState({ search }: { search: string }) {
  return (
    <Card className="border-dashed bg-card/70">
      <CardContent className="flex flex-col items-center gap-3 px-4 py-12 text-center">
        <div className="flex size-11 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-primary">
          <Box className="size-5" aria-hidden="true" />
        </div>
        <div className="space-y-1">
          <p className="text-sm font-medium text-foreground">
            {search.trim()
              ? "No packages match this search."
              : "No workflow packages yet."}
          </p>
          <p className="max-w-md text-sm text-muted-foreground">
            {search.trim()
              ? "Refine the search by package name, key, or manifest hash."
              : "Create or import a package manifest to author private agents, schemas, capabilities, MCP bindings, and launch flows."}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

type ViewMode = "cards" | "table";

type PackageSelectionHandlers = {
  onDelete: (workflowPackage: WorkflowPackageRead) => void;
  onSelect: (
    packagesToUpdate: readonly WorkflowPackageRead[],
    selected: boolean,
  ) => void;
};

function WorkflowPackagesHeader() {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">
          Workflow Packages
        </h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Package-first authoring for private agents, output schemas, capability
          profiles, MCP bindings, artifact updates, and controlled launches.
        </p>
      </div>
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
    </div>
  );
}

function WorkflowPackagesToolbar({
  search,
  viewMode,
  onSearchChange,
  onViewModeChange,
}: {
  search: string;
  viewMode: ViewMode;
  onSearchChange: (value: string) => void;
  onViewModeChange: (value: ViewMode) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <div className="relative max-w-sm flex-1" role="search">
        <Search
          className="pointer-events-none absolute left-2.5 top-2 size-4 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          aria-label="Search workflow packages"
          className="h-8 pl-8 text-xs"
          placeholder="Search packages by name, key, or hash..."
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
        />
      </div>
      <ToggleGroup
        type="single"
        value={viewMode}
        onValueChange={(value) => {
          if (value) {
            onViewModeChange(value as ViewMode);
          }
        }}
      >
        <ToggleGroupItem
          value="cards"
          aria-label="Cards view"
          className="h-8 w-8 px-0"
        >
          <LayoutGrid className="size-3.5" />
        </ToggleGroupItem>
        <ToggleGroupItem
          value="table"
          aria-label="Table view"
          className="h-8 w-8 px-0"
        >
          <List className="size-3.5" />
        </ToggleGroupItem>
      </ToggleGroup>
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

function WorkflowPackageMetadata({
  workflowPackage,
}: {
  workflowPackage: WorkflowPackageRead;
}) {
  return (
    <div className="grid min-w-0 gap-x-5 gap-y-1.5 text-xs text-muted-foreground sm:grid-cols-2">
      <div className="min-w-0">
        <span className="font-medium text-foreground">Manifest Hash:</span>{" "}
        <span className="font-mono">
          {formatNullableHash(workflowPackage.manifestHash)}
        </span>
      </div>
      <div className="min-w-0">
        <span className="font-medium text-foreground">Updated:</span>{" "}
        <span>{formatDateTime(workflowPackage.updatedAt)}</span>
      </div>
    </div>
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
          density="compactPlus"
          testId={`workflow-packages-row-${workflowPackage.key}`}
          title={workflowPackage.name}
          subtitle={<span className="font-mono">{workflowPackage.key}</span>}
          description={
            workflowPackage.description || "No description provided."
          }
          metadata={
            <WorkflowPackageMetadata workflowPackage={workflowPackage} />
          }
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
          <TableHead>Manifest Hash</TableHead>
          <TableHead>Updated</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {packages.map((workflowPackage) => {
          const isSelected = selectedPackageIds.has(workflowPackage.id);

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
                <div className="space-y-1">
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
              <TableCell className="font-mono text-xs">
                {formatNullableHash(workflowPackage.manifestHash)}
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
  const [viewMode, setViewMode] = useState<ViewMode>("cards");
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

  const handleViewModeChange = (value: ViewMode) => {
    setViewMode(value);
    if (value === "cards") {
      setSelectedPackageIds(new Set());
    }
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
    <div className="space-y-4 p-4" data-testid="workflow-packages-list-page">
      <WorkflowPackagesHeader />
      <WorkflowPackagesToolbar
        search={search}
        viewMode={viewMode}
        onSearchChange={setSearch}
        onViewModeChange={handleViewModeChange}
      />
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
    </div>
  );
}
