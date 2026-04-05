import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router";
import { ArrowLeft, Download, Loader2, Pencil, Save } from "lucide-react";
import { toast } from "sonner";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { useReport, useUpdateReport } from "@/hooks/use-reports";
import { formatDateTime } from "@/lib/format";
import { downloadReportUrl } from "@/lib/api/reports";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
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
      <div className="p-4 text-center text-sm text-muted-foreground">Report not found.</div>
    );
  }

  const sourceLabel =
    report.source === "uploaded"
      ? "Uploaded"
      : report.source === "external"
        ? "External"
        : "Compiled";
  const sourceBadgeVariant = report.source === "uploaded" ? "secondary" : "outline";

  return (
    <div className="max-w-5xl space-y-4 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0"
          onClick={() => navigate("/reports")}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <Separator orientation="vertical" className="h-5" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-lg font-semibold tracking-tight">{report.name}</h1>
            <Badge variant={sourceBadgeVariant} className="text-[10px]">
              {sourceLabel}
            </Badge>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Created {formatDateTime(report.createdAt)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" className="h-8 text-sm" asChild>
            <a href={downloadReportUrl(report.slug)} download>
              <Download className="mr-1 h-3 w-3" />
              Download
            </a>
          </Button>
          {isEditing ? (
            <>
              <Button variant="ghost" size="sm" className="h-8 text-sm" onClick={handleCancelEdit}>
                Cancel
              </Button>
              <Button
                size="sm"
                className="h-8 gap-1.5 text-sm"
                onClick={handleSave}
                disabled={updateMutation.isPending}
              >
                {updateMutation.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Save className="h-3 w-3" />
                )}
                Save
              </Button>
            </>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              className="h-8 text-sm"
              onClick={() => setIsEditing(true)}
            >
              <Pencil className="mr-1 h-3 w-3" />
              Edit
            </Button>
          )}
        </div>
      </div>

      {isEditing ? (
        <textarea
          className="min-h-[400px] w-full resize-y rounded-md border border-border bg-background px-4 py-3 font-mono text-sm leading-7 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          value={editContent}
          onChange={(e) => setEditContent(e.target.value)}
          spellCheck={false}
        />
      ) : (
        <div className="prose prose-sm dark:prose-invert max-w-none rounded-md border border-border bg-muted/30 px-6 py-4">
          <Markdown remarkPlugins={[remarkGfm]}>{report.content}</Markdown>
        </div>
      )}
    </div>
  );
}
