import { useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Download,
  Eye,
  MoreHorizontal,
  Plus,
  Trash2,
  Upload,
} from "lucide-react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";

import {
  useCompileReport,
  useDeleteReport,
  useDeleteReports,
  useReports,
  useUploadReport,
} from "@/hooks/use-reports";
import { useTemplates } from "@/hooks/use-templates";
import { formatDateTime } from "@/lib/format";
import { downloadReportUrl } from "@/lib/api/reports";
import type { ReportRead } from "@/lib/types/report";
import type { TextTemplateRead } from "@/lib/types/text-template";
import { ReportUploadDialog } from "@/components/forms/report-upload-dialog";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { ResourceFilterBar } from "@/components/shared/resource-filter-bar";
import { ResourceTableFrame } from "@/components/shared/resource-table-frame";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { GenerateReportDialog } from "@/components/forms/generate-report-dialog";
import { Label } from "@/components/ui/label";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  type GroupByOption,
  GROUP_BY_LABELS,
  filterReports,
  getReportSourceLabel,
  groupReports,
  type SortField,
  type SortDirection,
  sortReports,
} from "@/lib/report-grouping";

import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";

type TemplateListData = TextTemplateRead[] | { items?: TextTemplateRead[] };

function getTemplateItems(
  data: TemplateListData | undefined,
): TextTemplateRead[] {
  if (Array.isArray(data)) {
    return data;
  }

  return data?.items ?? [];
}

export function ReportListPage() {
  const navigate = useNavigate();
  const reportsQuery = useReports();
  const templatesQuery = useTemplates();
  const compileMutation = useCompileReport();
  const deleteMutation = useDeleteReport();
  const deleteReportsMutation = useDeleteReports();
  const uploadMutation = useUploadReport();

  const [deleting, setDeleting] = useState<ReportRead | null>(null);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadSlug, setUploadSlug] = useState("");
  const [uploadAuthor, setUploadAuthor] = useState("");
  const [uploadDescription, setUploadDescription] = useState("");
  const [uploadTags, setUploadTags] = useState("");

  const [search, setSearch] = useState("");
  const [groupBy, setGroupBy] = useState<GroupByOption>("tags");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    new Set(),
  );
  const [selectedSlugs, setSelectedSlugs] = useState<Set<string>>(new Set());
  const [sortField, setSortField] = useState<SortField>("createdAt");
  const [sortDir, setSortDir] = useState<SortDirection>("desc");

  const reports = useMemo(() => reportsQuery.data ?? [], [reportsQuery.data]);
  const templates = getTemplateItems(templatesQuery.data);

  const filtered = useMemo(
    () => filterReports(reports, search),
    [reports, search],
  );
  const grouped = useMemo(
    () => groupReports(filtered, groupBy),
    [filtered, groupBy],
  );
  const selectedReports = useMemo(
    () => filtered.filter((report) => selectedSlugs.has(report.slug)),
    [filtered, selectedSlugs],
  );
  const selectedCount = selectedReports.length;
  const toggleGroup = (label: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  const getSortDirection = (
    field: SortField,
  ): "ascending" | "descending" | undefined => {
    if (sortField !== field) {
      return undefined;
    }

    return sortDir === "asc" ? "ascending" : "descending";
  };

  const renderSortButton = (field: SortField, label: string) => {
    const direction = getSortDirection(field);

    return (
      <Button
        aria-label={
          direction
            ? `Sort reports by ${label} (${direction})`
            : `Sort reports by ${label}`
        }
        className="-ml-2 h-8 px-2 text-xs font-medium"
        onClick={() => handleSort(field)}
        size="sm"
        type="button"
        variant="ghost"
      >
        <span>{label}</span>
        {direction ? (
          <span aria-hidden="true" className="ml-1">
            {sortDir === "asc" ? "↑" : "↓"}
          </span>
        ) : null}
      </Button>
    );
  };

  const setReportsSelected = (
    reportsToUpdate: ReportRead[],
    selected: boolean,
  ) => {
    setSelectedSlugs((prev) => {
      const next = new Set(prev);
      reportsToUpdate.forEach((report) => {
        if (selected) next.add(report.slug);
        else next.delete(report.slug);
      });
      return next;
    });
  };

  const handleDeleteSelected = () => {
    if (selectedReports.length === 0) return;

    const slugs = selectedReports.map((report) => report.slug);
    const count = selectedReports.length;
    deleteReportsMutation.mutate(slugs, {
      onError: (error) =>
        toast.error(
          error instanceof Error ? error.message : "Failed to delete reports",
        ),
      onSuccess: () => {
        toast.success(`${count} ${count === 1 ? "report" : "reports"} deleted`);
        setSelectedSlugs(new Set());
      },
    });
  };

  const handleGenerate = ({
    inputs,
    templateId,
  }: {
    inputs: Record<string, string>;
    templateId: string;
  }) => {
    compileMutation.mutate(
      {
        templateId,
        input: { inputs },
      },
      {
        onError: (error) =>
          toast.error(
            error instanceof Error
              ? error.message
              : "Failed to generate report",
          ),
        onSuccess: (report) => {
          toast.success(`Report "${report.name}" generated`);
          setGenerateOpen(false);
          navigate(`/reports/${report.slug}`);
        },
      },
    );
  };

  const handleFileChange = (file: File | null) => {
    if (!file) {
      setUploadFile(null);
      return;
    }

    setUploadFile(file);
    const nameWithoutExt = file.name.replace(/\.md$/i, "");
    const generatedSlug = nameWithoutExt
      .replace(/[^a-zA-Z0-9]/g, "_")
      .toLowerCase();
    setUploadSlug(generatedSlug);
  };

  const handleUpload = () => {
    if (!uploadFile || !uploadSlug) return;

    const formData = new FormData();
    formData.append("file", uploadFile);
    formData.append("slug", uploadSlug);
    if (uploadAuthor) formData.append("author", uploadAuthor);
    if (uploadDescription) formData.append("description", uploadDescription);
    if (uploadTags) formData.append("tags", uploadTags);

    uploadMutation.mutate(formData, {
      onError: (error) => {
        const status = (error as { status?: number }).status;
        if (status === 409) {
          toast.error("A report with this slug already exists");
        } else {
          toast.error(
            error instanceof Error ? error.message : "Failed to upload report",
          );
        }
      },
      onSuccess: (report) => {
        toast.success(`Report "${report.name}" uploaded`);
        setUploadOpen(false);
        setUploadFile(null);
        setUploadSlug("");
        setUploadAuthor("");
        setUploadDescription("");
        setUploadTags("");
        navigate(`/reports/${report.slug}`);
      },
    });
  };

  return (
    <InventoryPageShell
      pageContext={{
        actions: (
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" onClick={() => setGenerateOpen(true)}>
              <Plus data-icon="inline-start" /> Generate Report
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setUploadOpen(true)}
            >
              <Upload data-icon="inline-start" /> Upload Report
            </Button>
          </div>
        ),
        description: "Generate and review reports.",
        layout: "toolbar",
        title: "Reports",
      }}
      testId="reports-list-page"
      toolbar={{
        resultSummary:
          reportsQuery.isPending || reportsQuery.isError
            ? undefined
            : `Showing ${filtered.length} of ${reports.length} reports`,
        search: {
          id: "report-search",
          label: "Search reports",
          name: "reportSearch",
          placeholder: "Search reports...",
          value: search,
          onChange: setSearch,
        },
        filters: (
          <div className="w-36">
            <Label htmlFor="report-group-by" className="sr-only">
              Group reports
            </Label>
            <Select
              value={groupBy}
              onValueChange={(value) => setGroupBy(value as GroupByOption)}
            >
              <SelectTrigger id="report-group-by" className="h-8 text-xs">
                <SelectValue placeholder="Group by" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(GROUP_BY_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value} className="text-xs">
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ),
        selectionSummary:
          selectedCount > 0 ? `${selectedCount} selected` : undefined,
      }}
    >
      <div className="space-y-4">
        {reportsQuery.isPending ? (
          <InventoryStatePanel
            description="Fetching report inventory."
            testId="reports-loading-state"
            title="Loading reports..."
          />
        ) : null}
        {reportsQuery.isError ? (
          <InventoryStatePanel
            description={
              reportsQuery.error instanceof Error
                ? reportsQuery.error.message
                : "Failed to load reports."
            }
            testId="reports-error-state"
            title="Reports could not be loaded"
            tone="danger"
          />
        ) : null}
        {!reportsQuery.isPending &&
        !reportsQuery.isError &&
        reports.length === 0 ? (
          <InventoryStatePanel
            description="Generate one from a template or upload a markdown file."
            testId="reports-empty-state"
            title="No reports yet."
          />
        ) : null}
        {!reportsQuery.isPending &&
        !reportsQuery.isError &&
        reports.length > 0 &&
        filtered.length === 0 ? (
          <InventoryStatePanel
            testId="reports-filtered-empty-state"
            title="No reports match your search."
          />
        ) : null}

        {Array.from(grouped.entries()).map(([groupLabel, groupReports]) => {
          const isCollapsed = collapsedGroups.has(groupLabel);
          const showHeader = groupBy !== "none" || grouped.size > 1;
          const sortedReports = sortReports(groupReports, sortField, sortDir);
          const allGroupSelected =
            sortedReports.length > 0 &&
            sortedReports.every((report) => selectedSlugs.has(report.slug));
          const someGroupSelected = sortedReports.some((report) =>
            selectedSlugs.has(report.slug),
          );

          return (
            <Collapsible
              key={groupLabel}
              open={!isCollapsed}
              onOpenChange={() => toggleGroup(groupLabel)}
              className="space-y-2"
            >
              {showHeader && (
                <CollapsibleTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="flex w-full items-center justify-start gap-2 p-0 hover:bg-transparent"
                  >
                    {isCollapsed ? (
                      <ChevronRight className="size-4" />
                    ) : (
                      <ChevronDown className="size-4" />
                    )}
                    <span className="text-xs font-medium text-muted-foreground">
                      {groupLabel}
                    </span>
                    <Badge variant="outline">{groupReports.length}</Badge>
                  </Button>
                </CollapsibleTrigger>
              )}
              <CollapsibleContent>
                <ResourceTableFrame>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-9">
                            <Checkbox
                              aria-label={`Select reports in ${groupLabel}`}
                              checked={
                                allGroupSelected
                                  ? true
                                  : someGroupSelected
                                    ? "indeterminate"
                                    : false
                              }
                              onCheckedChange={(checked) =>
                                setReportsSelected(
                                  sortedReports,
                                  checked === true,
                                )
                              }
                            />
                          </TableHead>
                          <TableHead aria-sort={getSortDirection("name")}>
                            {renderSortButton("name", "Name")}
                          </TableHead>
                          <TableHead aria-sort={getSortDirection("source")}>
                            {renderSortButton("source", "Source")}
                          </TableHead>
                          <TableHead>Tags</TableHead>
                          <TableHead aria-sort={getSortDirection("createdAt")}>
                            {renderSortButton("createdAt", "Created")}
                          </TableHead>
                          <TableHead className="w-[132px] text-right">
                            Actions
                          </TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {sortedReports.map((report) => {
                          const sourceLabel = getReportSourceLabel(
                            report.source,
                          );
                          const isSelected = selectedSlugs.has(report.slug);

                          return (
                            <TableRow
                              key={report.id}
                              data-state={isSelected ? "selected" : undefined}
                            >
                              <TableCell>
                                <Checkbox
                                  aria-label={`Select report ${report.name}`}
                                  checked={isSelected}
                                  onCheckedChange={(checked) =>
                                    setReportsSelected(
                                      [report],
                                      checked === true,
                                    )
                                  }
                                />
                              </TableCell>
                              <TableCell className="font-medium">
                                {report.name}
                              </TableCell>
                              <TableCell>
                                <Badge variant="outline">{sourceLabel}</Badge>
                              </TableCell>
                              <TableCell className="text-xs text-muted-foreground">
                                {report.metadata?.tags?.join(", ") || "—"}
                              </TableCell>
                              <TableCell className="text-xs text-muted-foreground">
                                {formatDateTime(report.createdAt)}
                              </TableCell>
                              <TableCell>
                                <div className="flex justify-end gap-1.5">
                                  <Button asChild size="sm">
                                    <Link
                                      aria-label={`View report ${report.name}`}
                                      to={`/reports/${report.slug}`}
                                    >
                                      <Eye data-icon="inline-start" />
                                      View
                                    </Link>
                                  </Button>
                                  <DropdownMenu>
                                    <DropdownMenuTrigger asChild>
                                      <Button
                                        aria-label={`Open actions for ${report.name}`}
                                        size="icon"
                                        type="button"
                                        variant="ghost"
                                      >
                                        <MoreHorizontal className="size-4" />
                                      </Button>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent align="end">
                                      <DropdownMenuItem asChild>
                                        <a
                                          href={downloadReportUrl(report.slug)}
                                          download
                                        >
                                          <Download className="size-3.5" />
                                          Download
                                        </a>
                                      </DropdownMenuItem>
                                      <DropdownMenuItem
                                        onSelect={() => setDeleting(report)}
                                        variant="destructive"
                                      >
                                        <Trash2 className="size-3.5" />
                                        Delete
                                      </DropdownMenuItem>
                                    </DropdownMenuContent>
                                  </DropdownMenu>
                                </div>
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                </ResourceTableFrame>
              </CollapsibleContent>
            </Collapsible>
          );
        })}
      </div>

      {selectedCount > 0 ? (
        <ResourceFilterBar
          actions={
            <>
              <Button
                size="sm"
                variant="destructive"
                disabled={deleteReportsMutation.isPending}
                onClick={handleDeleteSelected}
              >
                <Trash2 className="size-3.5" /> Delete selected
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setSelectedSlugs(new Set())}
              >
                Clear
              </Button>
            </>
          }
          summary={`${selectedCount} of ${filtered.length} reports selected`}
          testId="reports-bulk-actions"
        />
      ) : null}

      <ConfirmDeleteDialog
        open={Boolean(deleting)}
        title="Delete report"
        description={`Delete "${deleting?.name ?? "this report"}"? This cannot be undone.`}
        isPending={deleteMutation.isPending}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        onConfirm={() => {
          if (!deleting) return;
          const slug = deleting.slug;
          deleteMutation.mutate(slug, {
            onError: (error) =>
              toast.error(
                error instanceof Error
                  ? error.message
                  : "Failed to delete report",
              ),
            onSuccess: () => {
              toast.success("Report deleted");
              setDeleting(null);
              setSelectedSlugs((prev) => {
                const next = new Set(prev);
                next.delete(slug);
                return next;
              });
            },
          });
        }}
      />

      <GenerateReportDialog
        open={generateOpen}
        onOpenChange={setGenerateOpen}
        templateOptions={templates.map((template) => ({
          id: String(template.id),
          name: template.name,
        }))}
        isPending={compileMutation.isPending}
        onGenerate={handleGenerate}
      />

      <ReportUploadDialog
        author={uploadAuthor}
        description={uploadDescription}
        isPending={uploadMutation.isPending}
        open={uploadOpen}
        slug={uploadSlug}
        tags={uploadTags}
        uploadFile={uploadFile}
        onAuthorChange={setUploadAuthor}
        onDescriptionChange={setUploadDescription}
        onFileChange={handleFileChange}
        onOpenChange={setUploadOpen}
        onSlugChange={setUploadSlug}
        onTagsChange={setUploadTags}
        onUpload={handleUpload}
      />
    </InventoryPageShell>
  );
}
