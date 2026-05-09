import { FileUp, Loader2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import type {
  WorkflowPackageImportMode,
  WorkflowPackageImportRequest,
  WorkflowPackageRead,
} from "@/lib/types/workflow-package";

export function sanitizePreviewText(text: string): string {
  return text
    .replace(/sk-[A-Za-z0-9_-]+/g, "[redacted]")
    .replace(/(apiKey|secretPayload|encrypted|password):[^\n]*/gi, "$1: [redacted]");
}

type WorkflowPackageImportDialogProps = {
  buttonAriaLabel?: string;
  buttonTestId?: string;
  isPending: boolean;
  onImport: (payload: WorkflowPackageImportRequest) => Promise<WorkflowPackageRead | null>;
};

export function WorkflowPackageImportDialog(props: WorkflowPackageImportDialogProps) {
  const {
    buttonAriaLabel = "Import workflow package manifest",
    buttonTestId,
    isPending,
    onImport,
  } = props;
  const [open, setOpen] = useState(false);
  const [importMode, setImportMode] = useState<WorkflowPackageImportMode>("create");
  const [importSource, setImportSource] = useState("");

  const submitImport = async () => {
    const imported = await onImport({ manifestSource: importSource, mode: importMode });
    if (!imported) {
      return;
    }
    setOpen(false);
    setImportMode("create");
    setImportSource("");
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button
        aria-label={buttonAriaLabel}
        className="cursor-pointer"
        data-testid={buttonTestId}
        size="sm"
        type="button"
        variant="outline"
        onClick={() => setOpen(true)}
      >
        <FileUp data-icon="inline-start" />
        Import Package
      </Button>
      <DialogContent className="max-h-dvh overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Import workflow package YAML</DialogTitle>
          <DialogDescription>
            Paste a package manifest. Secret-like values are redacted from preview text and should not be included.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <RadioGroup value={importMode} onValueChange={(value) => setImportMode(value as WorkflowPackageImportMode)}>
            <label className="flex items-center gap-2 text-sm"><RadioGroupItem value="create" />Create new package</label>
            <label className="flex items-center gap-2 text-sm"><RadioGroupItem value="createVersion" />Create version for matching package key</label>
          </RadioGroup>
          <div className="space-y-2">
            <Label htmlFor="import-yaml">Import package YAML</Label>
            <Textarea
              id="import-yaml"
              aria-label="Import package YAML"
              className="min-h-64 font-mono text-xs"
              value={importSource}
              onChange={(event) => setImportSource(sanitizePreviewText(event.target.value))}
            />
          </div>
        </div>
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          <Button disabled={isPending || !importSource.trim()} type="button" onClick={() => void submitImport()}>
            {isPending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : null}
            Import package
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
