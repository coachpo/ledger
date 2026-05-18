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
import { Textarea } from "@/components/ui/textarea";
import type {
  WorkflowPackageImportRequest,
  WorkflowPackageRead,
} from "@/lib/types/workflow-package";

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
  const [importSource, setImportSource] = useState("");

  const submitImport = async () => {
    const imported = await onImport({ manifestSource: importSource });
    if (!imported) {
      return;
    }
    setOpen(false);
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
            Paste a package manifest. Package-private MCP inline values are imported exactly as shown.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="import-yaml">Import package YAML</Label>
            <Textarea
              id="import-yaml"
              aria-label="Import package YAML"
              className="min-h-64 font-mono text-xs"
              value={importSource}
              onChange={(event) => setImportSource(event.target.value)}
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
