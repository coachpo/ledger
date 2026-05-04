import { AlertCircle, Loader2, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";

import { useCreateRunRerun, useRunRerunDraft } from "@/hooks/use-runs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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

function parseJsonRecord(text: string, label: string): JsonValidationResult<Record<string, unknown>> {
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
      <Label className="text-sm" htmlFor={id}>{label}</Label>
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
    () => parseJsonRecord(parametersText || "{}", "Rerun parameters JSON"),
    [parametersText],
  );
  const rerunPayload = useMemo(() => {
    if (parametersValidation.error || !parametersValidation.value) {
      return null;
    }

    return { parameters: parametersValidation.value };
  }, [parametersValidation.error, parametersValidation.value]);
  const hasDraftEdits = Boolean(draftQuery.data && !areJsonValuesEqual(parametersValidation.value, draftQuery.data.parameters));
  const isSubmitDisabled = !rerunPayload || createRerun.isPending || draftQuery.isPending || Boolean(parametersValidation.error);

  const resetToDraft = () => {
    if (!draftQuery.data) {
      return;
    }

    setDraftSourceRunId(draftQuery.data.sourceRunId);
    setParametersText(formatJsonEditorValue(draftQuery.data.parameters));
    setApiError(null);
  };
  const handleSubmit = async () => {
    if (!rerunPayload) {
      return;
    }

    setApiError(null);

    try {
      const createdRun = await createRerun.mutateAsync({ runId, payload: rerunPayload });
      resetLocalState();
      navigate(`/runs/${createdRun.id}`);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Failed to create rerun.");
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
      <DialogContent className="max-h-dvh overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <div className="flex flex-wrap items-center gap-2 pr-6">
            <DialogTitle>Rerun draft</DialogTitle>
            {draftQuery.data ? <Badge variant="outline">Source run #{draftQuery.data.sourceRunId}</Badge> : null}
            {draftQuery.data ? <Badge variant={hasDraftEdits ? "secondary" : "outline"}>{hasDraftEdits ? "Edited draft" : "Source parameters"}</Badge> : null}
          </div>
          <DialogDescription>
            Create a new run from the same workflow version and parameters. Edit the JSON if this rerun needs different inputs.
          </DialogDescription>
        </DialogHeader>

        {draftQuery.isPending ? (
          <div className="flex items-center gap-2 rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground" data-testid="run-rerun-loading">
            <Loader2 className="size-4 animate-spin" />
            Loading rerun draft...
          </div>
        ) : null}
        {draftQuery.isError ? (
          <Alert variant="destructive" data-testid="run-rerun-draft-error">
            <AlertCircle />
            <AlertTitle>Unable to load rerun draft</AlertTitle>
            <AlertDescription>{draftQuery.error instanceof Error ? draftQuery.error.message : "The rerun draft could not be loaded."}</AlertDescription>
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
          <Card className="gap-3" data-testid="run-rerun-dialog-body">
            <CardHeader>
              <CardTitle className="text-base">Rerun parameters</CardTitle>
              <CardDescription>Submit unchanged source parameters or edit the JSON before creating a new run.</CardDescription>
            </CardHeader>
            <CardContent>
              <JsonEditorField
                disabled={createRerun.isPending}
                error={parametersValidation.error}
                id="run-rerun-parameters-json"
                label="Rerun parameters JSON"
                onChange={(value) => {
                  setApiError(null);
                  setParametersText(value);
                }}
                value={parametersText}
              />
            </CardContent>
          </Card>
        ) : null}

        <DialogFooter>
          <Button disabled={createRerun.isPending} onClick={closeDialog} type="button" variant="ghost">
            Cancel
          </Button>
          <Button disabled={!draftQuery.data || createRerun.isPending} onClick={resetToDraft} type="button" variant="outline">
            <RotateCcw data-icon="inline-start" />
            Reset draft
          </Button>
          <Button data-testid="run-rerun-submit" disabled={isSubmitDisabled} onClick={() => void handleSubmit()} type="button">
            {createRerun.isPending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : null}
            Create rerun
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
