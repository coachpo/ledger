import { Box, LayoutGrid, List, PackagePlus, PlayCircle, Search, SquarePen, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import {
  useImportWorkflowPackage,
  useWorkflowPackages,
  useWorkflowPackageVersionSummaries,
  type WorkflowPackageVersionSummary,
} from "@/hooks/use-workflow-packages";
import { formatDateTime } from "@/lib/format";
import type { WorkflowPackageImportRequest, WorkflowPackageRead, WorkflowPackageStatus } from "@/lib/types/workflow-package";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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

import { PlatformResourceCard, PlatformResourceList } from "../platform-resource-shared";
import { WorkflowPackageImportDialog } from "./workflow-package-import-dialog";

const statusLabel: Record<WorkflowPackageStatus, string> = {
  active: "Active",
  archived: "Archived",
  draft: "Draft",
};

function formatNullableDateTime(value: string | null): string {
  return value ? formatDateTime(value) : "Not recorded";
}

function formatLatestVersion(value: number | null): string {
  return value === null ? "None" : `v${value}`;
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
    [item.name, item.key, item.description, item.status, String(item.latestVersion ?? "")]
      .join(" ")
      .toLowerCase()
      .includes(query),
  );
}

function statusBadge(packageStatus: WorkflowPackageStatus) {
  const className =
    packageStatus === "active"
      ? "border-positive/30 bg-positive/10 text-positive"
      : packageStatus === "draft"
        ? "border-chart-3/30 bg-chart-3/10 text-chart-3"
        : "border-muted bg-muted text-muted-foreground";

  return (
    <Badge className={className} variant="outline">
      {statusLabel[packageStatus]}
    </Badge>
  );
}

function preflightBadge(summary: WorkflowPackageVersionSummary | undefined, latestVersion: number | null) {
  if (latestVersion === null) {
    return <Badge variant="outline">Not versioned</Badge>;
  }

  if (!summary || summary.isPending) {
    return <Badge variant="outline">Checking</Badge>;
  }

  if (summary.isError) {
    return <Badge variant="outline">Unavailable</Badge>;
  }

  if (summary.warningCount > 0) {
    return (
      <Badge className="border-chart-3/30 bg-chart-3/10 text-chart-3" variant="outline">
        {summary.warningCount} warning{summary.warningCount === 1 ? "" : "s"}
      </Badge>
    );
  }

  return <Badge className="border-positive/30 bg-positive/10 text-positive" variant="outline">Passed</Badge>;
}

function lastRunLabel(summary: WorkflowPackageVersionSummary | undefined) {
  if (!summary || summary.isPending) {
    return "Checking";
  }

  if (summary.isError) {
    return summary.errorMessage ?? "Unavailable";
  }

  return formatNullableDateTime(summary.latestLaunchedAt);
}

type SummaryCardProps = {
  label: string;
  tone?: "default" | "warning";
  value: string;
};

function SummaryCard({ label, tone = "default", value }: SummaryCardProps) {
  return (
    <Card className="border-border/70 bg-card/80 shadow-sm backdrop-blur">
      <CardContent className="flex items-center justify-between gap-3 p-4">
        <div className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
          <p className="font-['Fira_Code',ui-monospace,monospace] text-2xl font-semibold tracking-tight text-foreground">
            {value}
          </p>
        </div>
        <div
          className={
            tone === "warning"
              ? "flex size-10 items-center justify-center rounded-xl border border-chart-3/30 bg-chart-3/10 text-chart-3"
              : "flex size-10 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-primary"
          }
        >
          <Box className="size-5" aria-hidden="true" />
        </div>
      </CardContent>
    </Card>
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
            {search.trim() ? "No packages match this command." : "No workflow packages yet."}
          </p>
          <p className="max-w-md text-sm text-muted-foreground">
            {search.trim()
              ? "Refine the search by package name, key, status, or version."
              : "Create or import a package manifest to author private agents, schemas, capabilities, MCP bindings, and launch flows."}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

export function WorkflowPackagesListPage() {
  const navigate = useNavigate();
  const importPackage = useImportWorkflowPackage();
  const packagesQuery = useWorkflowPackages({ includeArchived: true });
  const packages = useMemo(() => sortPackages(packagesQuery.data?.items ?? []), [packagesQuery.data?.items]);
  const versionSummaries = useWorkflowPackageVersionSummaries(
    packages.map((item) => item.id),
    !packagesQuery.isPending && !packagesQuery.isError,
  );
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState<"cards" | "table">("cards");
  const filteredPackages = useMemo(() => filterPackages(packages, search), [packages, search]);
  const activeCount = packages.filter((item) => item.status === "active").length;
  const warningCount = packages.reduce((sum, item) => sum + item.warnings.length, 0);
  const versionCount = packages.filter((item) => item.latestVersion !== null).length;

  const importManifest = async (payload: WorkflowPackageImportRequest) => {
    try {
      const imported = await importPackage.mutateAsync(payload);
      toast.success("Imported workflow package");
      navigate(`/workflow-packages/${imported.id}`);
      return imported;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to import package.");
      return null;
    }
  };

  return (
    <div
      className="flex h-full flex-col gap-4 overflow-y-auto p-4 font-['Fira_Sans',ui-sans-serif,system-ui,sans-serif]"
      data-testid="workflow-packages-list-page"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">Workflow Packages</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Package-first authoring for private agents, output schemas, capability profiles, MCP bindings, preflight checks, and controlled launches.
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

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard label="Total Packages" value={String(packages.length)} />
        <SummaryCard label="Active" value={String(activeCount)} />
        <SummaryCard label="Versioned" value={String(versionCount)} />
        <SummaryCard label="Validation Warnings" tone="warning" value={String(warningCount)} />
      </div>

      <Card className="border-border/70 bg-card/80 backdrop-blur">
        <CardHeader className="gap-3 border-b pb-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="space-y-1">
              <CardTitle className="text-base">Package Inventory</CardTitle>
              <p className="text-sm text-muted-foreground">Command-search manifests by package identity, state, and version.</p>
            </div>
            <div className="flex w-full items-center gap-2 lg:max-w-lg">
              <div className="relative min-w-0 flex-1" role="search">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
                <Input
                  aria-label="Search workflow packages"
                  className="h-10 bg-background/70 pl-9"
                  placeholder="Search packages by name, key, status, or version..."
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </div>
              <ToggleGroup type="single" value={viewMode} onValueChange={(value) => value && setViewMode(value as "cards" | "table")}>
                <ToggleGroupItem value="cards" aria-label="Cards view" className="h-10 w-10 px-0">
                  <LayoutGrid className="size-4" />
                </ToggleGroupItem>
                <ToggleGroupItem value="table" aria-label="Table view" className="h-10 w-10 px-0">
                  <List className="size-4" />
                </ToggleGroupItem>
              </ToggleGroup>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {packagesQuery.isPending ? <LoadingTable /> : null}
          {packagesQuery.isError ? (
            <div className="flex items-start gap-3 p-6 text-sm text-muted-foreground" role="alert">
              <TriangleAlert className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
              <span>{packagesQuery.error instanceof Error ? packagesQuery.error.message : "Failed to load workflow packages."}</span>
            </div>
          ) : null}
          {!packagesQuery.isPending && !packagesQuery.isError && filteredPackages.length === 0 ? <EmptyState search={search} /> : null}
          {!packagesQuery.isPending && !packagesQuery.isError && filteredPackages.length > 0 && viewMode === "cards" ? (
            <div className="p-3 sm:p-4">
              <PlatformResourceList>
                {filteredPackages.map((workflowPackage) => {
                  const summary = versionSummaries.get(String(workflowPackage.id));
                  const packagePath = `/workflow-packages/${workflowPackage.id}`;
                  const launchPath = `/workflow-packages/${workflowPackage.id}/run`;

                  return (
                    <PlatformResourceCard
                      key={workflowPackage.id}
                      density="compactPlus"
                      testId={`workflow-packages-row-${workflowPackage.key}`}
                      title={workflowPackage.name}
                      subtitle={(
                        <span className="font-['Fira_Code',ui-monospace,monospace] text-xs">
                          {workflowPackage.key}
                        </span>
                      )}
                      description={workflowPackage.description || "No description provided."}
                      primaryAction={{
                        kind: "button",
                        label: `Open package details for ${workflowPackage.name}`,
                        onClick: () => navigate(packagePath),
                      }}
                      badges={(
                        <>
                          {statusBadge(workflowPackage.status)}
                          {preflightBadge(summary, workflowPackage.latestVersion)}
                        </>
                      )}
                      metadata={(
                        <div className="grid min-w-0 gap-x-5 gap-y-2 sm:grid-cols-2 xl:grid-cols-4">
                          <div className="min-w-0">
                            <span className="font-medium text-foreground">Latest Version:</span>{" "}
                            <span className="font-['Fira_Code',ui-monospace,monospace]">
                              {formatLatestVersion(workflowPackage.latestVersion)}
                            </span>
                          </div>
                          <div className="min-w-0">
                            <span className="font-medium text-foreground">Last Preflight:</span>{" "}
                            {preflightBadge(summary, workflowPackage.latestVersion)}
                          </div>
                          <div className="min-w-0">
                            <span className="font-medium text-foreground">Last Run:</span>{" "}
                            <span>{lastRunLabel(summary)}</span>
                          </div>
                          <div className="min-w-0">
                            <span className="font-medium text-foreground">Updated:</span>{" "}
                            <span>{formatDateTime(workflowPackage.updatedAt)}</span>
                          </div>
                        </div>
                      )}
                      actions={(
                        <>
                          <Button aria-label={`Open package ${workflowPackage.name}`} className="cursor-pointer" size="sm" variant="outline" type="button" onClick={() => navigate(packagePath)}>
                            <SquarePen data-icon="inline-start" />
                            Open
                          </Button>
                          <Button aria-label={`Launch package ${workflowPackage.name}`} className="cursor-pointer" size="sm" variant="outline" type="button" onClick={() => navigate(launchPath)}>
                            <PlayCircle data-icon="inline-start" />
                            Launch
                          </Button>
                        </>
                      )}
                    />
                  );
                })}
              </PlatformResourceList>
            </div>
          ) : null}
          {!packagesQuery.isPending && !packagesQuery.isError && filteredPackages.length > 0 && viewMode === "table" ? (
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/30 hover:bg-muted/30">
                  <TableHead>Name</TableHead>
                  <TableHead>Key</TableHead>
                  <TableHead>Latest Version</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last Preflight</TableHead>
                  <TableHead>Last Run</TableHead>
                  <TableHead>Updated</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredPackages.map((workflowPackage) => {
                  const summary = versionSummaries.get(String(workflowPackage.id));
                  return (
                    <TableRow key={workflowPackage.id} data-testid={`workflow-packages-row-${workflowPackage.key}`}>
                      <TableCell className="min-w-56 whitespace-normal">
                        <div className="space-y-1">
                          <p className="font-medium text-foreground">{workflowPackage.name}</p>
                          <p className="line-clamp-2 text-xs text-muted-foreground">{workflowPackage.description || "No description provided."}</p>
                        </div>
                      </TableCell>
                      <TableCell className="font-['Fira_Code',ui-monospace,monospace] text-xs text-muted-foreground">{workflowPackage.key}</TableCell>
                      <TableCell className="font-['Fira_Code',ui-monospace,monospace] text-xs">{formatLatestVersion(workflowPackage.latestVersion)}</TableCell>
                      <TableCell>{statusBadge(workflowPackage.status)}</TableCell>
                      <TableCell>{preflightBadge(summary, workflowPackage.latestVersion)}</TableCell>
                      <TableCell className="max-w-44 whitespace-normal text-xs text-muted-foreground">{lastRunLabel(summary)}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{formatDateTime(workflowPackage.updatedAt)}</TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-2">
                          <Button aria-label={`Open package ${workflowPackage.name}`} className="cursor-pointer" size="sm" variant="outline" type="button" onClick={() => navigate(`/workflow-packages/${workflowPackage.id}`)}>
                            <SquarePen data-icon="inline-start" />
                            Open
                          </Button>
                          <Button aria-label={`Launch package ${workflowPackage.name}`} className="cursor-pointer" size="sm" variant="outline" type="button" onClick={() => navigate(`/workflow-packages/${workflowPackage.id}/run`)}>
                            <PlayCircle data-icon="inline-start" />
                            Launch
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
