import { AlertCircle, ArrowLeft, CheckCircle2, FileUp, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useBeforeUnload, useBlocker, useNavigate } from "react-router";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { useImportWorkflowPackage } from "@/hooks/use-workflow-packages";
import { ApiRequestError } from "@/lib/api-client";
import type { ApiErrorDetail } from "@/lib/types/common";

type ImportFailure = {
  details: ApiErrorDetail[];
  message: string;
};

function importFailureFromError(error: unknown): ImportFailure {
  if (error instanceof ApiRequestError) {
    return {
      details: error.details,
      message: error.message,
    };
  }

  if (error instanceof Error) {
    return {
      details: [],
      message: error.message,
    };
  }

  return {
    details: [],
    message: "Failed to import workflow package.",
  };
}

function ImportFailureAlert({ failure }: { failure: ImportFailure | null }) {
  if (!failure) {
    return null;
  }

  return (
    <Alert variant="destructive" role="alert" data-testid="workflow-package-import-error">
      <AlertCircle />
      <AlertTitle>Import failed</AlertTitle>
      <AlertDescription className="space-y-2">
        <p>{failure.message}</p>
        {failure.details.length > 0 ? (
          <ul className="list-disc pl-5">
            {failure.details.map((detail, index) => (
              <li key={`${detail.field}-${detail.issue}-${index}`}>
                {detail.field}: {detail.issue}
              </li>
            ))}
          </ul>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}

const DIRTY_IMPORT_CONFIRMATION_MESSAGE =
  "You have pasted workflow package YAML. Discard it and leave this page?";
const PENDING_IMPORT_CONFIRMATION_MESSAGE =
  "An import is still in progress. Leave this page and stop following its result?";

export function WorkflowPackageImportPage() {
  const navigate = useNavigate();
  const importPackage = useImportWorkflowPackage();
  const [manifestSource, setManifestSource] = useState("");
  const [failure, setFailure] = useState<ImportFailure | null>(null);
  const hasUnsavedManifest = manifestSource.trim().length > 0;
  const canSubmit = hasUnsavedManifest && !importPackage.isPending;
  const isMountedRef = useRef(true);
  const skipNavigationBlockRef = useRef(false);
  const shouldBlockNavigation = hasUnsavedManifest || importPackage.isPending;
  const navigationConfirmationMessage = importPackage.isPending
    ? PENDING_IMPORT_CONFIRMATION_MESSAGE
    : DIRTY_IMPORT_CONFIRMATION_MESSAGE;
  const blocker = useBlocker(() =>
    shouldBlockNavigation && !skipNavigationBlockRef.current,
  );

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useBeforeUnload((event) => {
    if (!shouldBlockNavigation) {
      return;
    }
    event.preventDefault();
    event.returnValue = "";
  });

  useEffect(() => {
    if (blocker.state !== "blocked") {
      return;
    }

    if (window.confirm(navigationConfirmationMessage)) {
      skipNavigationBlockRef.current = true;
      blocker.proceed();
      return;
    }

    blocker.reset();
  }, [blocker, navigationConfirmationMessage]);

  const leaveImportWorkspace = () => {
    if (importPackage.isPending) {
      return;
    }

    if (hasUnsavedManifest && !window.confirm(DIRTY_IMPORT_CONFIRMATION_MESSAGE)) {
      return;
    }

    skipNavigationBlockRef.current = true;
    navigate("/workflow-packages");
  };

  const submitImport = async () => {
    if (!hasUnsavedManifest) {
      toast.error("Workflow package YAML is required");
      return;
    }

    setFailure(null);

    try {
      const imported = await importPackage.mutateAsync({ manifestSource });
      if (!isMountedRef.current) {
        return;
      }
      skipNavigationBlockRef.current = true;
      toast.success("Imported workflow package");
      navigate(`/workflow-packages/${imported.id}`);
    } catch (error) {
      if (!isMountedRef.current) {
        return;
      }
      const nextFailure = importFailureFromError(error);
      setFailure(nextFailure);
      toast.error(nextFailure.message);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-background font-['Fira_Sans',ui-sans-serif,system-ui,sans-serif]" data-testid="workflow-package-import-page">
      <div className="border-b border-border bg-card px-4 py-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex min-w-0 items-center gap-2">
            <Button
              aria-label="Cancel import"
              className="h-8 w-8 shrink-0"
              disabled={importPackage.isPending}
              onClick={leaveImportWorkspace}
              size="icon"
              type="button"
              variant="ghost"
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <Separator orientation="vertical" className="hidden h-5 sm:block" />
            <div className="min-w-0 space-y-1">
              <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                <FileUp className="h-3 w-3" />
                <span>Workflow Packages</span>
              </div>
              <div>
                <h1 className="text-xl font-semibold tracking-tight">Import workflow package YAML</h1>
                <p className="max-w-3xl text-sm text-muted-foreground">
                  Paste a complete package manifest for a full-height review before it enters the package-first authoring surface.
                </p>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 border-t border-border/60 pt-3 sm:justify-end xl:border-t-0 xl:pt-0">
            <Button
              disabled={importPackage.isPending}
              type="button"
              variant="ghost"
              size="sm"
              onClick={leaveImportWorkspace}
            >
              Cancel
            </Button>
            <Button disabled={!canSubmit} size="sm" type="button" onClick={() => void submitImport()}>
              {importPackage.isPending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <FileUp data-icon="inline-start" />}
              Import package
            </Button>
          </div>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <section className="flex min-h-0 min-w-0 flex-col xl:border-r xl:border-border" aria-labelledby="workflow-package-import-editor-title">
          <div className="flex items-center gap-2 border-b border-border bg-muted/50 px-4 py-2">
            <FileUp className="h-3 w-3 text-muted-foreground" />
            <span id="workflow-package-import-editor-title" className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Import package YAML
            </span>
            <span className="ml-auto text-[10px] text-muted-foreground">
              signaldeck.workflowPackage/v1
            </span>
          </div>
          <div className="relative min-h-0 flex-1">
            <textarea
              aria-label="Import package YAML"
              className="h-full w-full resize-none border-none bg-background px-4 py-3 font-['Fira_Code',ui-monospace,monospace] text-sm leading-7 text-foreground placeholder:text-muted-foreground focus:outline-none"
              placeholder="apiVersion: signaldeck.workflowPackage/v1\nkind: WorkflowPackage\nmetadata:\n  key: imported_package\n  name: Imported Package\nspec:\n  agents: []"
              spellCheck={false}
              value={manifestSource}
              onChange={(event) => setManifestSource(event.target.value)}
            />
          </div>
        </section>

        <aside className="min-h-0 bg-muted/20" aria-label="Import guidance">
          <ScrollArea className="h-full">
            <div className="space-y-4 p-4">
              <ImportFailureAlert failure={failure} />
              <Card className="border-border/70 bg-card/80 shadow-sm backdrop-blur">
                <CardHeader>
                  <CardTitle>Before importing</CardTitle>
                  <CardDescription>
                    The YAML is sent unchanged to the existing Workflow Package import API.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-sm text-muted-foreground">
                  <div className="flex gap-2">
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-positive" />
                    <p>Package-private MCP env, headers, and query values stay inline exactly as pasted.</p>
                  </div>
                  <div className="flex gap-2">
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-positive" />
                    <p>Imports create a new package only when the manifest key is unused. Existing active keys are rejected.</p>
                  </div>
                  <div className="flex gap-2">
                    <AlertCircle className="mt-0.5 size-4 shrink-0 text-chart-3" />
                    <p>Review long manifests here before import; validation details remain visible if the backend rejects the YAML.</p>
                  </div>
                </CardContent>
              </Card>
              <Card className="border-border/70 bg-card/80 shadow-sm backdrop-blur">
                <CardHeader>
                  <CardTitle>Navigation</CardTitle>
                  <CardDescription>
                    Cancel returns to the Workflow Packages list. If pasted YAML is present, leaving asks for confirmation. A successful import opens the imported package editor.
                  </CardDescription>
                </CardHeader>
              </Card>
            </div>
          </ScrollArea>
        </aside>
      </div>
    </div>
  );
}
