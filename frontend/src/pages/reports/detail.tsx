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

import { ConsoleSection } from "@/components/shared/console-section";
import {
  EvidenceCluster,
  type EvidenceClusterItem,
} from "@/components/shared/evidence-cluster";
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
  const reportEvidenceItems = [
    {
      label: "Source",
      value: `${report.source} snapshot`,
      tone: report.source === "uploaded" ? "verified" : "neutral",
    },
    {
      label: "Slug",
      value: report.slug,
      description: "Canonical route and download key",
    },
    {
      label: "Created",
      value: formatDateTime(report.createdAt),
    },
    {
      label: "Updated",
      value: formatDateTime(report.updatedAt),
      tone: "verified",
    },
  ] satisfies EvidenceClusterItem[];

  return (
    <div className="space-y-4 p-4">
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
          className="border-border/80 bg-card/95 shadow-none"
          description={
            <span
              className="text-xs font-medium uppercase tracking-wide text-muted-foreground"
              data-testid="report-detail-identity"
            >
              Immutable report snapshot
            </span>
          }
          meta={<EvidenceCluster items={reportEvidenceItems} layout="inline" />}
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

      <ConsoleSection
        description="Only markdown content is editable; report identity, source, and slug remain fixed."
        title={isEditing ? "Edit report content" : "Report content"}
      >
        {isEditing ? (
          <textarea
            aria-label="Report markdown content"
            className="min-h-[400px] w-full resize-y rounded-md border border-border bg-background px-4 py-3 font-mono text-sm leading-7 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            spellCheck={false}
          />
        ) : (
          <div
            className="prose prose-sm dark:prose-invert max-w-none rounded-md border border-border bg-muted/30 px-6 py-4"
            data-testid="report-content-pane"
          >
            <Markdown remarkPlugins={[remarkGfm]}>{report.content}</Markdown>
          </div>
        )}
      </ConsoleSection>
    </div>
  );
}
