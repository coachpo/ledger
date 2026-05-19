import {
  Box,
  LayoutGrid,
  List,
  PackagePlus,
  PlayCircle,
  Search,
  SquarePen,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import {
  useDeleteWorkflowPackage,
  useImportWorkflowPackage,
  useWorkflowPackages,
} from "@/hooks/use-workflow-packages";
import { formatDateTime } from "@/lib/format";
import type {
  WorkflowPackageImportRequest,
  WorkflowPackageRead,
} from "@/lib/types/workflow-package";
import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { WorkflowPackageImportDialog } from "./workflow-package-import-dialog";

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
              ? "No packages match this command."
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

export function WorkflowPackagesListPage() {
  const navigate = useNavigate();
  const deletePackage = useDeleteWorkflowPackage();
  const importPackage = useImportWorkflowPackage();
  const packagesQuery = useWorkflowPackages();
  const packages = useMemo(
    () => sortPackages(packagesQuery.data?.items ?? []),
    [packagesQuery.data?.items],
  );
  const [deleting, setDeleting] = useState<WorkflowPackageRead | null>(null);
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState<"cards" | "table">("cards");
  const filteredPackages = useMemo(
    () => filterPackages(packages, search),
    [packages, search],
  );

  const importManifest = async (payload: WorkflowPackageImportRequest) => {
    try {
      const imported = await importPackage.mutateAsync(payload);
      toast.success("Imported workflow package");
      navigate(`/workflow-packages/${imported.id}`);
      return imported;
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Failed to import package.",
      );
      return null;
    }
  };

  const deleteSelectedPackage = async () => {
    if (!deleting) {
      return;
    }

    try {
      await deletePackage.mutateAsync(deleting.id);
      toast.success("Workflow package permanently deleted");
      setDeleting(null);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Failed to delete workflow package.",
      );
    }
  };

  return (
    <div className="space-y-4 p-4" data-testid="workflow-packages-list-page">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">
            Workflow Packages
          </h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Package-first authoring for private agents, output schemas,
            capability profiles, MCP bindings, artifact updates, and controlled
            launches.
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <WorkflowPackageImportDialog
            buttonTestId="workflow-packages-import"
            isPending={importPackage.isPending}
            onImport={importManifest}
          />
          <Button
            aria-label="Create new workflow package"
            className="cursor-pointer"
            data-testid="workflow-packages-new"
            size="sm"
            type="button"
            onClick={() => navigate("/workflow-packages/new")}
          >
            <PackagePlus data-icon="inline-start" />
            New Package
          </Button>
        </div>
      </div>

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
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <ToggleGroup
          type="single"
          value={viewMode}
          onValueChange={(value) =>
            value && setViewMode(value as "cards" | "table")
          }
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

      {packagesQuery.isPending ? <LoadingTable /> : null}
      {packagesQuery.isError ? (
        <div
          className="flex items-start gap-3 p-6 text-sm text-muted-foreground"
          role="alert"
        >
          <TriangleAlert
            className="mt-0.5 size-4 shrink-0 text-destructive"
            aria-hidden="true"
          />
          <span>
            {packagesQuery.error instanceof Error
              ? packagesQuery.error.message
              : "Failed to load workflow packages."}
          </span>
        </div>
      ) : null}
      {!packagesQuery.isPending &&
      !packagesQuery.isError &&
      filteredPackages.length === 0 ? (
        <EmptyState search={search} />
      ) : null}
      {!packagesQuery.isPending &&
      !packagesQuery.isError &&
      filteredPackages.length > 0 &&
      viewMode === "cards" ? (
        <PlatformResourceList>
          {filteredPackages.map((workflowPackage) => {
            const packagePath = `/workflow-packages/${workflowPackage.id}`;
            const launchPath = `/workflow-packages/${workflowPackage.id}/run`;

            return (
              <PlatformResourceCard
                key={workflowPackage.id}
                density="compactPlus"
                testId={`workflow-packages-row-${workflowPackage.key}`}
                title={workflowPackage.name}
                subtitle={
                  <span className="font-['Fira_Code',ui-monospace,monospace] text-xs">
                    {workflowPackage.key}
                  </span>
                }
                description={
                  workflowPackage.description || "No description provided."
                }
                primaryAction={{
                  kind: "button",
                  label: `Open package details for ${workflowPackage.name}`,
                  onClick: () => navigate(packagePath),
                }}
                metadata={
                  <div className="grid min-w-0 gap-x-5 gap-y-2 sm:grid-cols-2">
                    <div className="min-w-0">
                      <span className="font-medium text-foreground">
                        Manifest Hash:
                      </span>{" "}
                      <span className="font-['Fira_Code',ui-monospace,monospace]">
                        {formatNullableHash(workflowPackage.manifestHash)}
                      </span>
                    </div>
                    <div className="min-w-0">
                      <span className="font-medium text-foreground">
                        Updated:
                      </span>{" "}
                      <span>{formatDateTime(workflowPackage.updatedAt)}</span>
                    </div>
                  </div>
                }
                actions={
                  <>
                    <Button
                      aria-label={`Open package ${workflowPackage.name}`}
                      className="cursor-pointer"
                      size="sm"
                      variant="outline"
                      type="button"
                      onClick={() => navigate(packagePath)}
                    >
                      <SquarePen data-icon="inline-start" />
                      Open
                    </Button>
                    <Button
                      aria-label={`Launch package ${workflowPackage.name}`}
                      className="cursor-pointer"
                      size="sm"
                      variant="outline"
                      type="button"
                      onClick={() => navigate(launchPath)}
                    >
                      <PlayCircle data-icon="inline-start" />
                      Launch
                    </Button>
                    <Button
                      aria-label={`Delete package ${workflowPackage.name}`}
                      className="cursor-pointer"
                      disabled={deletePackage.isPending}
                      size="sm"
                      variant="destructive"
                      type="button"
                      onClick={() => setDeleting(workflowPackage)}
                    >
                      <Trash2 data-icon="inline-start" />
                      Delete
                    </Button>
                  </>
                }
              />
            );
          })}
        </PlatformResourceList>
      ) : null}
      {!packagesQuery.isPending &&
      !packagesQuery.isError &&
      filteredPackages.length > 0 &&
      viewMode === "table" ? (
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/30 hover:bg-muted/30">
              <TableHead>Name</TableHead>
              <TableHead>Key</TableHead>
              <TableHead>Manifest Hash</TableHead>
              <TableHead>Updated</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredPackages.map((workflowPackage) => (
                <TableRow
                  key={workflowPackage.id}
                  data-testid={`workflow-packages-row-${workflowPackage.key}`}
                >
                  <TableCell className="min-w-56 whitespace-normal">
                    <div className="space-y-1">
                      <p className="font-medium text-foreground">
                        {workflowPackage.name}
                      </p>
                      <p className="line-clamp-2 text-xs text-muted-foreground">
                        {workflowPackage.description ||
                          "No description provided."}
                      </p>
                    </div>
                  </TableCell>
                  <TableCell className="font-['Fira_Code',ui-monospace,monospace] text-xs text-muted-foreground">
                    {workflowPackage.key}
                  </TableCell>
                  <TableCell className="font-['Fira_Code',ui-monospace,monospace] text-xs">
                    {formatNullableHash(workflowPackage.manifestHash)}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatDateTime(workflowPackage.updatedAt)}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-2">
                      <Button
                        aria-label={`Open package ${workflowPackage.name}`}
                        className="cursor-pointer"
                        size="sm"
                        variant="outline"
                        type="button"
                        onClick={() =>
                          navigate(`/workflow-packages/${workflowPackage.id}`)
                        }
                      >
                        <SquarePen data-icon="inline-start" />
                        Open
                      </Button>
                      <Button
                        aria-label={`Launch package ${workflowPackage.name}`}
                        className="cursor-pointer"
                        size="sm"
                        variant="outline"
                        type="button"
                        onClick={() =>
                          navigate(
                            `/workflow-packages/${workflowPackage.id}/run`,
                          )
                        }
                      >
                        <PlayCircle data-icon="inline-start" />
                        Launch
                      </Button>
                      <Button
                        aria-label={`Delete package ${workflowPackage.name}`}
                        className="cursor-pointer"
                        disabled={deletePackage.isPending}
                        size="sm"
                        variant="destructive"
                        type="button"
                        onClick={() => setDeleting(workflowPackage)}
                      >
                        <Trash2 data-icon="inline-start" />
                        Delete
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : null}
      <ConfirmDeleteDialog
        open={deleting !== null}
        title="Delete workflow package"
        description={`Permanently delete ${deleting?.name ?? "this workflow package"}? This removes the current package and related package resources. Historical run snapshots are preserved. This cannot be undone.`}
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
