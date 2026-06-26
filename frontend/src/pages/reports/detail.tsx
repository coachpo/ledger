import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router";
import { ArrowLeft, Download, Loader2, Pencil, Save } from "lucide-react";
import { toast } from "sonner";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { useReport, useUpdateReport } from "@/hooks/use-reports";
import { formatDateTime } from "@/lib/format";
import { downloadReportUrl } from "@/lib/api/reports";
import { getReportSourceLabel } from "@/lib/report-grouping";

import { PageContextBar } from "@/components/shared/page-context-bar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export function ReportDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();

  const { data: report, isLoading } = useReport(slug);
  const updateMutation = useUpdateReport();

  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState("");

  useEffect(() => {
    if (report) {
      setEditContent(report.content);
    }
  }, [report]);

  const handleSave = async () => {
    if (!slug || !report) return;

    try {
      await updateMutation.mutateAsync({
        slug,
        data: { content: editContent },
      });
      toast.success("Report updated");
      setIsEditing(false);
    } catch {
      toast.error("Failed to update report");
    }
  };

  const handleCancelEdit = () => {
    if (report) setEditContent(report.content);
    setIsEditing(false);
  };

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="p-4 text-center text-sm text-muted-foreground">
        Report not found.
      </div>
    );
  }

  const sourceLabel = getReportSourceLabel(report.source);
  const sourceBadgeVariant =
    report.source === "uploaded" ? "secondary" : "outline";
  const reportMetadataItems = [
    {
      label: "Source",
      value: `${report.source} snapshot`,
    },
    {
      label: "Slug",
      value: report.slug,
    },
    {
      label: "Created",
      value: formatDateTime(report.createdAt),
    },
    {
      label: "Updated",
      value: formatDateTime(report.updatedAt),
    },
  ];

  return (
    <div className="flex min-w-0 flex-col gap-4 p-4">
      <div
        aria-labelledby="report-detail-title"
        data-testid="report-detail-header"
      >
        <PageContextBar
          actions={
            <div
              className="flex w-full flex-wrap gap-2 sm:w-auto sm:justify-end"
              data-testid="report-detail-actions"
            >
              <Button
                variant="ghost"
                size="sm"
                className="h-8 px-2 text-xs text-muted-foreground hover:text-foreground"
                onClick={() => navigate("/reports")}
              >
                <ArrowLeft className="mr-1 size-3.5" /> Reports
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs"
                asChild
              >
                <a href={downloadReportUrl(report.slug)} download>
                  <Download className="mr-1 size-3" />
                  Download
                </a>
              </Button>
              {isEditing ? (
                <>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 text-xs"
                    onClick={handleCancelEdit}
                  >
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    className="h-8 gap-1.5 text-xs"
                    onClick={handleSave}
                    disabled={updateMutation.isPending}
                  >
                    {updateMutation.isPending ? (
                      <Loader2 className="size-3 animate-spin" />
                    ) : (
                      <Save className="size-3" />
                    )}
                    Save
                  </Button>
                </>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs"
                  onClick={() => setIsEditing(true)}
                >
                  <Pencil className="mr-1 size-3" />
                  Edit
                </Button>
              )}
            </div>
          }
          className="border-b border-border pb-3"
          description={
            <span
              className="block min-w-0 break-words text-sm text-muted-foreground"
              data-testid="report-detail-identity"
            >
              Immutable report snapshot
            </span>
          }
          meta={
            <div
              className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs"
              role="list"
              aria-label="Report metadata"
            >
              {reportMetadataItems.map((item) => (
                <span
                  className="flex min-w-0 items-baseline gap-1.5 border-r border-border pr-3 last:border-r-0 last:pr-0"
                  key={item.label}
                  role="listitem"
                >
                  <span className="shrink-0 text-muted-foreground">
                    {item.label}
                  </span>
                  <span className="min-w-0 break-words font-medium text-foreground">
                    {item.value}
                  </span>
                </span>
              ))}
            </div>
          }
          title={
            <span className="flex min-w-0 flex-wrap items-center gap-2">
              <span
                id="report-detail-title"
                className="break-words text-xl font-semibold tracking-tight"
              >
                {report.name}
              </span>
              <Badge variant={sourceBadgeVariant} className="text-[10px]">
                {sourceLabel}
              </Badge>
            </span>
          }
        />
      </div>

      {isEditing ? (
        <textarea
          aria-label="Report markdown content"
          className="min-h-[400px] w-full resize-y rounded-xl border border-border/70 bg-ui-surface-inset px-4 py-3 font-mono text-sm leading-7 text-foreground shadow-inner shadow-black/[0.02] outline-none placeholder:text-muted-foreground focus:border-ring focus:[box-shadow:var(--ui-focus-shadow)] dark:shadow-black/20"
          value={editContent}
          onChange={(e) => setEditContent(e.target.value)}
          spellCheck={false}
        />
      ) : (
        <div
          className="report-markdown min-w-0 max-w-none rounded-xl border border-border/70 bg-card/95 px-6 py-5 text-foreground shadow-ui-xs"
          data-testid="report-content-pane"
        >
          <Markdown remarkPlugins={[remarkGfm]}>{report.content}</Markdown>
        </div>
      )}
    </div>
  );
}
