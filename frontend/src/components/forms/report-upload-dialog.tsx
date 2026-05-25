import type { ChangeEvent } from "react";

import { EntityDialogShell } from "@/components/shared/entity-dialog-shell";
import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export type ReportUploadDialogProps = {
  author: string;
  description: string;
  isPending: boolean;
  open: boolean;
  slug: string;
  tags: string;
  uploadFile: File | null;
  onAuthorChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onFileChange: (file: File | null) => void;
  onOpenChange: (open: boolean) => void;
  onSlugChange: (value: string) => void;
  onTagsChange: (value: string) => void;
  onUpload: () => void;
};

export function ReportUploadDialog({
  author,
  description,
  isPending,
  open,
  slug,
  tags,
  uploadFile,
  onAuthorChange,
  onDescriptionChange,
  onFileChange,
  onOpenChange,
  onSlugChange,
  onTagsChange,
  onUpload,
}: ReportUploadDialogProps) {
  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    onFileChange(event.target.files?.[0] ?? null);
  };

  const handleSubmit = (event: { preventDefault: () => void }) => {
    event.preventDefault();

    if (!uploadFile || !slug || isPending) {
      return;
    }

    onUpload();
  };

  const formId = "report-upload-form";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <EntityDialogShell
        title="Upload Report"
        description="Upload a markdown file to create a new report."
        constraintStrip={
          <ResourceStatusStrip
            items={[
              {
                label: "File",
                value: uploadFile?.name ?? "Required markdown",
              },
              {
                label: "Slug",
                value: slug || "Required",
              },
              {
                label: "Metadata",
                value: "Optional",
              },
            ]}
          />
        }
        footer={
          <form id={formId} className="contents" onSubmit={handleSubmit}>
            <Button
              disabled={isPending}
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button disabled={!uploadFile || !slug || isPending} type="submit">
              {isPending ? "Uploading…" : "Upload"}
            </Button>
          </form>
        }
      >
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="report-upload-file">Markdown File</Label>
            <Input
              accept=".md"
              disabled={isPending}
              form={formId}
              id="report-upload-file"
              name="file"
              type="file"
              onChange={handleFileChange}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="report-upload-slug">Slug</Label>
            <Input
              autoCapitalize="off"
              autoCorrect="off"
              disabled={isPending}
              form={formId}
              id="report-upload-slug"
              name="slug"
              placeholder="my_report_slug"
              value={slug}
              onChange={(event) => onSlugChange(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="report-upload-author">Author (optional)</Label>
            <Input
              disabled={isPending}
              form={formId}
              id="report-upload-author"
              name="author"
              placeholder="John Doe"
              value={author}
              onChange={(event) => onAuthorChange(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="report-upload-description">
              Description (optional)
            </Label>
            <Textarea
              disabled={isPending}
              form={formId}
              id="report-upload-description"
              name="description"
              placeholder="Brief description of the report..."
              rows={3}
              value={description}
              onChange={(event) => onDescriptionChange(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="report-upload-tags">Tags (optional)</Label>
            <Input
              disabled={isPending}
              form={formId}
              id="report-upload-tags"
              name="tags"
              placeholder="q1, finance, summary (comma-separated)"
              value={tags}
              onChange={(event) => onTagsChange(event.target.value)}
            />
          </div>
        </div>
      </EntityDialogShell>
    </Dialog>
  );
}
