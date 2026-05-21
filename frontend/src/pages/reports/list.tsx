import { useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Download,
  Eye,
  LayoutGrid,
  List,
  MoreHorizontal,
  Plus,
  Search,
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
import { GroupedListCard } from "@/components/shared/resource-row-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { GenerateReportDialog } from "@/components/forms/generate-report-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
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
  const [viewMode, setViewMode] = useState<"cards" | "table">("cards");
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

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploadFile(file);
      const nameWithoutExt = file.name.replace(/\.md$/i, "");
      const generatedSlug = nameWithoutExt
        .replace(/[^a-zA-Z0-9]/g, "_")
        .toLowerCase();
      setUploadSlug(generatedSlug);
    } else {
      setUploadFile(null);
    }
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
    <div className="space-y-4 p-4">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">Reports</h1>
          <p className="text-sm text-muted-foreground">
            Compiled template snapshots — point-in-time deliverables.
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
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
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative max-w-sm flex-1" role="search">
          <Label htmlFor="report-search" className="sr-only">
            Search reports
          </Label>
          <Search
            className="pointer-events-none absolute left-2.5 top-2 size-4 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            id="report-search"
            name="reportSearch"
            placeholder="Search reports..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 pl-8 text-xs"
          />
        </div>
        <div className="w-36">
          <Label htmlFor="report-group-by" className="sr-only">
            Group reports
          </Label>
          <Select
            value={groupBy}
            onValueChange={(v) => setGroupBy(v as GroupByOption)}
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
        <ToggleGroup
          type="single"
          value={viewMode}
          onValueChange={(v) => {
            if (!v) return;
            setViewMode(v as "cards" | "table");
            if (v === "cards") setSelectedSlugs(new Set());
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

      <div className="space-y-4">
        {reportsQuery.isPending ? (
          <Card>
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              Loading reports...
            </CardContent>
          </Card>
        ) : null}
        {reportsQuery.isError ? (
          <Card role="alert">
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              {reportsQuery.error instanceof Error
                ? reportsQuery.error.message
                : "Failed to load reports."}
            </CardContent>
          </Card>
        ) : null}
        {!reportsQuery.isPending &&
        !reportsQuery.isError &&
        reports.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              No reports yet. Generate one from a template or upload a markdown
              file.
            </CardContent>
          </Card>
        ) : null}
        {!reportsQuery.isPending &&
        !reportsQuery.isError &&
        reports.length > 0 &&
        filtered.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              No reports match your search.
            </CardContent>
          </Card>
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
              <CollapsibleContent
                className={viewMode === "cards" ? "space-y-2" : ""}
              >
                {viewMode === "cards" ? (
                  sortedReports.map((report) => {
                    const sourceLabel = getReportSourceLabel(report.source);

                    return (
                      <GroupedListCard
                        key={report.id}
                        testId={`reports-row-${report.slug}`}
                        title={report.name}
                        badges={<Badge variant="outline">{sourceLabel}</Badge>}
                        metadata={
                          <>Created {formatDateTime(report.createdAt)}</>
                        }
                        primaryAction={{
                          kind: "link",
                          label: `Open report ${report.name}`,
                          to: `/reports/${report.slug}`,
                        }}
                        actions={
                          <>
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
                          </>
                        }
                      />
                    );
                  })
                ) : (
                  <div className="rounded-md border">
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
                  </div>
                )}
              </CollapsibleContent>
            </Collapsible>
          );
        })}
      </div>

      {viewMode === "table" && selectedCount > 0 ? (
        <div
          data-testid="reports-bulk-actions"
          className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-muted/30 px-3 py-2"
        >
          <span className="text-xs text-muted-foreground">
            {selectedCount} of {filtered.length} reports selected
          </span>
          <div className="flex flex-wrap items-center gap-2">
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
          </div>
        </div>
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

      <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload Report</DialogTitle>
            <DialogDescription>
              Upload a markdown file to create a new report.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="file">Markdown File</Label>
              <Input
                id="file"
                type="file"
                accept=".md"
                onChange={handleFileChange}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="slug">Slug</Label>
              <Input
                id="slug"
                value={uploadSlug}
                onChange={(e) => setUploadSlug(e.target.value)}
                placeholder="my_report_slug"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="author">Author (optional)</Label>
              <Input
                id="author"
                value={uploadAuthor}
                onChange={(e) => setUploadAuthor(e.target.value)}
                placeholder="John Doe"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description (optional)</Label>
              <Textarea
                id="description"
                value={uploadDescription}
                onChange={(e) => setUploadDescription(e.target.value)}
                placeholder="Brief description of the report..."
                rows={3}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="tags">Tags (optional)</Label>
              <Input
                id="tags"
                value={uploadTags}
                onChange={(e) => setUploadTags(e.target.value)}
                placeholder="q1, finance, summary (comma-separated)"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setUploadOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleUpload}
              disabled={!uploadFile || !uploadSlug || uploadMutation.isPending}
            >
              {uploadMutation.isPending ? "Uploading…" : "Upload"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
