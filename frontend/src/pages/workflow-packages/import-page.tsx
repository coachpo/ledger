import { AlertCircle, ArrowLeft, FileUp, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useBeforeUnload, useBlocker, useNavigate } from "react-router";
import { toast } from "sonner";

import { ConstraintInspector } from "@/components/shared/constraint-inspector";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
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
    <Alert
      variant="destructive"
      role="alert"
      data-testid="workflow-package-import-error"
    >
      <AlertCircle />
      <AlertTitle>Import failed</AlertTitle>
      <AlertDescription className="flex flex-col gap-2">
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
const IMPORT_MANIFEST_PLACEHOLDER = `apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: imported_package
  name: Imported Package
spec:
  agents: []`;
const IMPORT_REQUIREMENTS = [
  "apiVersion must be signaldeck.workflowPackage/v1.",
  "kind must be WorkflowPackage.",
  "metadata.key must be stable and unused by active packages.",
  "Package-local agents, workflows, capabilities, schemas, and private MCP config stay inside this manifest.",
] as const;
const IMPORT_WARNINGS = [
  "The pasted YAML is submitted unchanged to the existing import API.",
  "Duplicate active package keys and invalid package-local references are rejected by the backend.",
  "Private MCP env, headers, and query values remain inline in the imported manifest.",
] as const;

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
  const blocker = useBlocker(
    () => shouldBlockNavigation && !skipNavigationBlockRef.current,
  );
  const importBlockingConstraints = hasUnsavedManifest
    ? []
    : ["Paste a Workflow Package manifest before importing."];
  const importWarningConstraints = [
    ...IMPORT_WARNINGS,
    failure
      ? "Backend rejection details are shown in this route and remain visible until the next import attempt."
      : "Backend rejection details will render in this route if validation fails.",
  ];
  const importStatusItems = [
    {
      label: "Input",
      tone: hasUnsavedManifest ? ("warning" as const) : ("muted" as const),
      value: hasUnsavedManifest ? "Pasted YAML" : "Required",
    },
    {
      label: "Validation",
      tone: failure ? ("danger" as const) : ("neutral" as const),
      value: failure ? "Rejected" : "Backend-owned",
    },
    {
      label: "Guards",
      tone: shouldBlockNavigation ? ("warning" as const) : ("success" as const),
      value: shouldBlockNavigation ? "Active" : "Clear",
    },
  ];

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

    if (
      hasUnsavedManifest &&
      !window.confirm(DIRTY_IMPORT_CONFIRMATION_MESSAGE)
    ) {
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
    <WorkspacePageShell
      bodyAriaLabel="Workflow package import workspace"
      bodyClassName="overflow-hidden"
      contentClassName="gap-0 p-0"
      contextBar={
        <PageContextBar
          actions={
            <div className="flex flex-wrap items-center gap-2 sm:justify-end">
              <Button
                aria-label="Cancel import"
                className="size-8 shrink-0"
                disabled={importPackage.isPending}
                onClick={leaveImportWorkspace}
                size="icon"
                type="button"
                variant="ghost"
              >
                <ArrowLeft data-icon="inline-start" />
              </Button>
              <Button
                disabled={importPackage.isPending}
                type="button"
                variant="ghost"
                size="sm"
                onClick={leaveImportWorkspace}
              >
                Cancel
              </Button>
              <Button
                disabled={!canSubmit}
                size="sm"
                type="button"
                onClick={() => void submitImport()}
              >
                {importPackage.isPending ? (
                  <Loader2 className="animate-spin" data-icon="inline-start" />
                ) : (
                  <FileUp data-icon="inline-start" />
                )}
                Import package
              </Button>
            </div>
          }
          description="Paste a workflow package manifest."
          meta={
            <div className="flex min-w-0 items-center gap-1.5">
              <FileUp data-icon="inline-start" />
              <span>Workflow Packages</span>
            </div>
          }
          status={<ResourceStatusStrip items={importStatusItems} />}
          title={
            <span id="workflow-package-import-title">
              Import workflow package YAML
            </span>
          }
        />
      }
      testId="workflow-package-import-page"
    >
      <div
        aria-labelledby="workflow-package-import-title"
        className="grid min-h-0 flex-1 grid-cols-1 xl:grid-cols-[minmax(0,1fr)_22rem]"
      >
        <section
          className="flex min-h-0 min-w-0 flex-col xl:border-r xl:border-border"
          aria-labelledby="workflow-package-import-editor-title"
        >
          <div className="flex items-center gap-2 border-b border-border bg-muted/50 px-4 py-2">
            <FileUp data-icon="inline-start" />
            <Label
              htmlFor="workflow-package-import-yaml"
              id="workflow-package-import-editor-title"
              className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground"
            >
              Import package YAML
            </Label>
            <span className="ml-auto text-[10px] text-muted-foreground">
              signaldeck.workflowPackage/v1
            </span>
          </div>
          <div className="relative min-h-0 flex-1">
            <textarea
              id="workflow-package-import-yaml"
              className="h-full w-full resize-none border-none bg-background px-4 py-3 font-mono text-sm leading-7 text-foreground placeholder:text-muted-foreground focus:outline-none"
              placeholder={IMPORT_MANIFEST_PLACEHOLDER}
              spellCheck={false}
              value={manifestSource}
              onChange={(event) => setManifestSource(event.target.value)}
            />
          </div>
        </section>

        <aside
          className="min-h-0 bg-ui-surface-grouped/50"
          aria-label="Import constraint inspector"
        >
          <ScrollArea className="h-full">
            <div
              className="flex min-w-0 flex-col gap-4 p-4"
              data-testid="workflow-package-import-inspector"
            >
              <ImportFailureAlert failure={failure} />
              <ConstraintInspector
                blocking={importBlockingConstraints}
                requirements={IMPORT_REQUIREMENTS}
                summary="Import keeps pasted YAML route-owned and sends it unchanged to the Workflow Package import API."
                title="Import constraints"
                warnings={importWarningConstraints}
              />
            </div>
          </ScrollArea>
        </aside>
      </div>
    </WorkspacePageShell>
  );
}
