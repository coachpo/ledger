import { AlertCircle, Loader2, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";

import { useCreateRunRerun, useRunRerunDraft } from "@/hooks/use-runs";
import { EntityDialogShell } from "@/components/shared/entity-dialog-shell";
import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import {
  diagnosticsFromDraftReadiness,
  type RunDraftReadiness,
  type RunDraftReadinessDiagnostic,
} from "./detail-helpers";

type JsonValidationResult<T> = {
  error: string | null;
  value: T | null;
};

function formatJsonEditorValue(value: unknown): string {
  return JSON.stringify(value, null, 2);
}
function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function parseJsonRecord(
  text: string,
  label: string,
): JsonValidationResult<Record<string, unknown>> {
  try {
    const parsed = JSON.parse(text) as unknown;

    if (!isRecord(parsed)) {
      return { error: `${label} must be a JSON object.`, value: null };
    }

    return { error: null, value: parsed };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Invalid JSON";
    return { error: `${label} must be valid JSON. ${message}`, value: null };
  }
}

function areJsonValuesEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}
function JsonEditorField({
  disabled,
  error,
  id,
  label,
  onChange,
  value,
}: {
  disabled?: boolean;
  error: string | null;
  id: string;
  label: string;
  onChange: (value: string) => void;
  value: string;
}) {
  return (
    <div className="flex flex-col gap-2">
      <Label className="text-sm" htmlFor={id}>
        {label}
      </Label>
      <Textarea
        aria-invalid={Boolean(error)}
        className="min-h-40 font-mono text-xs leading-relaxed"
        disabled={disabled}
        id={id}
        onChange={(event) => onChange(event.target.value)}
        rows={10}
        spellCheck={false}
        value={value}
      />
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  );
}

function draftDiagnosticBadge(diagnostic: RunDraftReadinessDiagnostic) {
  return diagnostic.severity === "error" ? (
    <Badge variant="destructive">Blocking</Badge>
  ) : (
    <Badge
      className="border-chart-3/30 bg-chart-3/10 text-chart-3"
      variant="outline"
    >
      Warning
    </Badge>
  );
}

function RunDraftReadinessPanel({
  readiness,
}: {
  readiness: RunDraftReadiness;
}) {
  const diagnostics = diagnosticsFromDraftReadiness(readiness);
  const title = readiness.ready
    ? "Current snapshot readiness passed"
    : "Current snapshot readiness blocked";
  const description = readiness.ready
    ? "The backend reports this rerun draft is ready to create from current package dependencies."
    : "The backend reports this rerun draft is not ready to create from current package dependencies.";

  return (
    <Alert
      data-testid="run-rerun-readiness"
      variant={readiness.ready ? "default" : "destructive"}
    >
      <AlertCircle />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="space-y-3">
        <p>{description}</p>
        {diagnostics.length > 0 ? (
          <div className="space-y-2">
            {diagnostics.map((diagnostic, diagnosticIndex) => (
              <div
                className="flex min-w-0 flex-wrap items-start gap-2 rounded-md border bg-background/60 p-3 text-sm"
                key={`${diagnostic.severity}-${diagnostic.field}-${diagnostic.issue}-${diagnosticIndex}`}
              >
                {draftDiagnosticBadge(diagnostic)}
                <span className="min-w-0 flex-1 basis-60 break-words">
                  <code className="break-all rounded bg-muted/40 px-2 py-1 text-xs">
                    {diagnostic.field}
                  </code>
                  {`: ${diagnostic.issue}`}
                </span>
              </div>
            ))}
          </div>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}

export function RunRerunDialog({
  onClose,
  open,
  runId,
}: {
  onClose: () => void;
  open: boolean;
  runId: string;
}) {
  const navigate = useNavigate();
  const draftQuery = useRunRerunDraft(runId, { enabled: open });
  const createRerun = useCreateRunRerun();
  const [draftSourceRunId, setDraftSourceRunId] = useState<number | null>(null);
  const [parametersText, setParametersText] = useState("");
  const [apiError, setApiError] = useState<string | null>(null);
  const resetLocalState = () => {
    setDraftSourceRunId(null);
    setParametersText("");
    setApiError(null);
  };

  const closeDialog = () => {
    resetLocalState();
    onClose();
  };

  useEffect(() => {
    if (!open || !draftQuery.data) {
      return;
    }

    if (draftSourceRunId === draftQuery.data.sourceRunId) {
      return;
    }

    setDraftSourceRunId(draftQuery.data.sourceRunId);
    setParametersText(formatJsonEditorValue(draftQuery.data.parameters));
    setApiError(null);
  }, [draftQuery.data, draftSourceRunId, open]);
  const parametersValidation = useMemo(
    () => parseJsonRecord(parametersText || "{}", "Root run parameters JSON"),
    [parametersText],
  );
  const rerunPayload = useMemo(() => {
    if (parametersValidation.error || !parametersValidation.value) {
      return null;
    }

    return { parameters: parametersValidation.value };
  }, [parametersValidation.error, parametersValidation.value]);
  const hasDraftEdits = Boolean(
    draftQuery.data &&
    !areJsonValuesEqual(parametersValidation.value, draftQuery.data.parameters),
  );
  const isSubmitDisabled =
    !rerunPayload ||
    createRerun.isPending ||
    draftQuery.isPending ||
    Boolean(parametersValidation.error) ||
    (draftQuery.data ? !draftQuery.data.ready : false);

  const resetToDraft = () => {
    if (!draftQuery.data) {
      return;
    }

    setDraftSourceRunId(draftQuery.data.sourceRunId);
    setParametersText(formatJsonEditorValue(draftQuery.data.parameters));
    setApiError(null);
  };
  const constraintItems = draftQuery.data
    ? [
        {
          label: "Source run",
          value: `#${draftQuery.data.sourceRunId}`,
        },
        {
          label: "Draft",
          value: hasDraftEdits ? "Edited" : "Captured snapshot",
        },
        {
          label: "Readiness",
          value: draftQuery.data.ready ? "Ready" : "Blocked",
        },
      ]
    : [
        {
          label: "Draft",
          value: draftQuery.isPending ? "Loading" : "Unavailable",
        },
      ];
  const handleSubmit = async () => {
    if (!rerunPayload) {
      return;
    }

    setApiError(null);

    try {
      const createdRun = await createRerun.mutateAsync({
        runId,
        payload: rerunPayload,
      });
      resetLocalState();
      navigate(`/runs/${createdRun.id}`);
    } catch (error) {
      setApiError(
        error instanceof Error ? error.message : "Failed to create rerun.",
      );
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !createRerun.isPending) {
          closeDialog();
        }
      }}
    >
      <EntityDialogShell
        className="sm:max-w-3xl"
        title="Run snapshot again"
        description="Create a new run from this captured snapshot."
        constraintStrip={<ResourceStatusStrip items={constraintItems} />}
        footer={
          <>
            <Button
              disabled={createRerun.isPending}
              onClick={closeDialog}
              type="button"
              variant="ghost"
            >
              Cancel
            </Button>
            <Button
              disabled={!draftQuery.data || createRerun.isPending}
              onClick={resetToDraft}
              type="button"
              variant="outline"
            >
              <RotateCcw data-icon="inline-start" />
              Reset draft
            </Button>
            <Button
              data-testid="run-rerun-submit"
              disabled={isSubmitDisabled}
              onClick={() => void handleSubmit()}
              type="button"
            >
              {createRerun.isPending ? (
                <Loader2 className="animate-spin" data-icon="inline-start" />
              ) : null}
              Run snapshot again
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          {draftQuery.isPending ? (
            <div
              className="flex items-center gap-2 rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground"
              data-testid="run-rerun-loading"
            >
              <Loader2 className="size-4 animate-spin" />
              Loading rerun draft...
            </div>
          ) : null}
          {draftQuery.isError ? (
            <Alert variant="destructive" data-testid="run-rerun-draft-error">
              <AlertCircle />
              <AlertTitle>Unable to load rerun draft</AlertTitle>
              <AlertDescription>
                {draftQuery.error instanceof Error
                  ? draftQuery.error.message
                  : "The rerun draft could not be loaded."}
              </AlertDescription>
            </Alert>
          ) : null}

          {apiError ? (
            <Alert variant="destructive" data-testid="run-rerun-api-error">
              <AlertCircle />
              <AlertTitle>Rerun creation failed</AlertTitle>
              <AlertDescription>{apiError}</AlertDescription>
            </Alert>
          ) : null}

          {draftQuery.data ? (
            <RunDraftReadinessPanel readiness={draftQuery.data} />
          ) : null}

          {draftQuery.data ? (
            <section
              className="flex flex-col gap-3 rounded-lg border bg-card p-4 text-card-foreground"
              data-testid="run-rerun-dialog-body"
            >
              <div className="flex flex-col gap-1">
                <h3 className="text-base font-medium leading-none">
                  Root run parameters
                </h3>
                <p className="text-sm text-muted-foreground">
                  Edit root parameters before creating the rerun.
                </p>
              </div>
              <JsonEditorField
                disabled={createRerun.isPending}
                error={parametersValidation.error}
                id="run-rerun-parameters-json"
                label="Root run parameters JSON"
                onChange={(value) => {
                  setApiError(null);
                  setParametersText(value);
                }}
                value={parametersText}
              />
            </section>
          ) : null}
        </div>
      </EntityDialogShell>
    </Dialog>
  );
}
