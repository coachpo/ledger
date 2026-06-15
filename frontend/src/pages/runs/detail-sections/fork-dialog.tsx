import { AlertCircle, Loader2, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";

import { useCreateRunFork, useRunForkDraft } from "@/hooks/use-runs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

import { DetailGrid } from "./shared";
import {
  DEFAULT_FORK_UNAVAILABLE_REASON,
  diagnosticsFromDraftReadiness,
  type ForkTargetContext,
  type RunDraftReadiness,
  type RunDraftReadinessDiagnostic,
  type RunForkAvailability,
} from "../detail-helpers";

const FORK_DIALOG_CLOSE_CLEANUP_DELAY_MS = 200;

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

function parseJsonValue(
  text: string,
  label: string,
): JsonValidationResult<unknown> {
  try {
    return { error: null, value: JSON.parse(text) as unknown };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Invalid JSON";
    return { error: `${label} must be valid JSON. ${message}`, value: null };
  }
}

function parseJsonRecord(
  text: string,
  label: string,
): JsonValidationResult<Record<string, unknown>> {
  const parsed = parseJsonValue(text, label);

  if (parsed.error) {
    return { error: parsed.error, value: null };
  }

  if (!isRecord(parsed.value)) {
    return { error: `${label} must be a JSON object.`, value: null };
  }

  return { error: null, value: parsed.value };
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
  rows = 8,
  value,
}: {
  disabled?: boolean;
  error: string | null;
  id: string;
  label: string;
  onChange: (value: string) => void;
  rows?: number;
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
        rows={rows}
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

function RunForkReadinessPanel({
  readiness,
}: {
  readiness: RunDraftReadiness;
}) {
  const diagnostics = diagnosticsFromDraftReadiness(readiness);
  const title = readiness.ready
    ? "Current fork readiness passed"
    : "Current fork readiness blocked";
  const description = readiness.ready
    ? "The backend reports this fork draft is ready to create from current package dependencies."
    : "The backend reports this fork draft is not ready to create from current package dependencies.";

  return (
    <Alert
      data-testid="run-fork-readiness"
      variant={readiness.ready ? "default" : "destructive"}
    >
      <AlertCircle />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="flex flex-col gap-3">
        <p>{description}</p>
        {diagnostics.length > 0 ? (
          <div className="flex flex-col gap-2">
            {diagnostics.map((diagnostic) => (
              <div
                className="grid min-w-0 gap-2 rounded-lg border border-border/70 bg-card/70 p-3 text-sm shadow-ui-xs md:grid-cols-[auto_minmax(0,10rem)_minmax(0,1fr)] md:items-center"
                key={`${diagnostic.severity}-${diagnostic.field}-${diagnostic.issue}`}
              >
                <div>{draftDiagnosticBadge(diagnostic)}</div>
                <code className="min-w-0 break-all rounded bg-ui-surface-grouped px-2 py-1 text-xs">
                  {diagnostic.field}
                </code>
                <span className="min-w-0 break-words">{diagnostic.issue}</span>
              </div>
            ))}
          </div>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}

export function RunForkDialog({
  forkAvailability,
  forkTarget,
  invocationId,
  onClose,
  open,
  resumeStepIndex,
  runId,
}: {
  forkAvailability: RunForkAvailability;
  forkTarget: ForkTargetContext | null;
  invocationId: number | undefined;
  onClose: () => void;
  open: boolean;
  resumeStepIndex: number | undefined;
  runId: string;
}) {
  const navigate = useNavigate();
  const createFork = useCreateRunFork();
  const [presentedForkState, setPresentedForkState] = useState(() => ({
    forkAvailability,
    forkTarget,
    invocationId,
    resumeStepIndex,
  }));
  const [draftTargetKey, setDraftTargetKey] = useState<string | null>(null);
  const [invocationInputText, setInvocationInputText] = useState("");
  const [apiError, setApiError] = useState<string | null>(null);
  const presentedAvailability = open
    ? forkAvailability
    : presentedForkState.forkAvailability;
  const presentedTarget = open ? forkTarget : presentedForkState.forkTarget;
  const presentedInvocationId = open
    ? invocationId
    : presentedForkState.invocationId;
  const presentedResumeStepIndex = open
    ? resumeStepIndex
    : presentedForkState.resumeStepIndex;
  const draftQuery = useRunForkDraft(runId, presentedInvocationId, {
    enabled: open && presentedAvailability.isAvailable,
  });

  const resetLocalState = useCallback(() => {
    setDraftTargetKey(null);
    setInvocationInputText("");
    setApiError(null);
  }, []);

  const closeDialog = () => {
    onClose();
  };

  useEffect(() => {
    if (open) {
      setPresentedForkState({
        forkAvailability: {
          isAvailable: forkAvailability.isAvailable,
          reason: forkAvailability.reason,
        },
        forkTarget,
        invocationId,
        resumeStepIndex,
      });
    }
  }, [
    forkAvailability.isAvailable,
    forkAvailability.reason,
    forkTarget,
    invocationId,
    open,
    resumeStepIndex,
  ]);

  useEffect(() => {
    if (open) {
      return undefined;
    }

    const cleanupTimer = window.setTimeout(
      resetLocalState,
      FORK_DIALOG_CLOSE_CLEANUP_DELAY_MS,
    );
    return () => window.clearTimeout(cleanupTimer);
  }, [open, resetLocalState]);

  useEffect(() => {
    if (!open || !draftQuery.data) {
      return;
    }

    const nextTargetKey = `${draftQuery.data.sourceRunId}:${draftQuery.data.sourceInvocationId}`;
    if (draftTargetKey === nextTargetKey) {
      return;
    }

    setDraftTargetKey(nextTargetKey);
    setInvocationInputText(
      formatJsonEditorValue(draftQuery.data.invocationInput),
    );
    setApiError(null);
  }, [draftQuery.data, draftTargetKey, open]);

  const invocationInputValidation = useMemo(
    () =>
      parseJsonRecord(
        invocationInputText || "{}",
        "Target invocation input JSON",
      ),
    [invocationInputText],
  );
  const forkPayload = useMemo(() => {
    if (
      !draftQuery.data ||
      invocationInputValidation.error ||
      !invocationInputValidation.value
    ) {
      return null;
    }

    return {
      invocationInput: invocationInputValidation.value,
      sourceInvocationId: draftQuery.data.sourceInvocationId,
    };
  }, [
    draftQuery.data,
    invocationInputValidation.error,
    invocationInputValidation.value,
  ]);
  const hasDraftEdits = Boolean(
    draftQuery.data &&
    !areJsonValuesEqual(
      invocationInputValidation.value,
      draftQuery.data.invocationInput,
    ),
  );
  const isSubmitDisabled =
    !forkPayload ||
    createFork.isPending ||
    draftQuery.isPending ||
    Boolean(invocationInputValidation.error) ||
    (draftQuery.data ? !draftQuery.data.ready : false);
  const targetLabel = presentedTarget
    ? `${presentedTarget.invocation.slot} invocation`
    : presentedInvocationId === undefined
      ? "selected invocation"
      : `invocation #${presentedInvocationId}`;

  const resetToDraft = () => {
    if (!draftQuery.data) {
      return;
    }

    setDraftTargetKey(
      `${draftQuery.data.sourceRunId}:${draftQuery.data.sourceInvocationId}`,
    );
    setInvocationInputText(
      formatJsonEditorValue(draftQuery.data.invocationInput),
    );
    setApiError(null);
  };

  const handleSubmit = async () => {
    if (!forkPayload) {
      return;
    }

    setApiError(null);

    try {
      const createdRun = await createFork.mutateAsync({
        runId,
        payload: forkPayload,
      });
      resetLocalState();
      navigate(`/runs/${createdRun.id}`);
    } catch (error) {
      setApiError(
        error instanceof Error ? error.message : "Failed to create the fork.",
      );
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !createFork.isPending) {
          closeDialog();
        }
      }}
    >
      <DialogContent
        className="max-h-dvh overflow-y-auto sm:max-w-3xl"
        onAnimationEnd={(event) => {
          if (event.currentTarget === event.target && !open) {
            resetLocalState();
          }
        }}
      >
        <DialogHeader>
          <div className="flex flex-wrap items-center gap-2 pr-6">
            <DialogTitle>Fork from {targetLabel}</DialogTitle>
            {presentedResumeStepIndex !== undefined ? (
              <Badge variant="outline">
                Resume at Step {presentedResumeStepIndex}
              </Badge>
            ) : null}
            {presentedInvocationId !== undefined ? (
              <Badge variant="outline">
                Invocation #{presentedInvocationId}
              </Badge>
            ) : null}
            {presentedTarget ? (
              <Badge variant="outline">
                {presentedTarget.invocation.agentKey} v
                {presentedTarget.invocation.agentVersion}
              </Badge>
            ) : null}
            {draftQuery.data ? (
              <Badge variant={hasDraftEdits ? "secondary" : "outline"}>
                {hasDraftEdits
                  ? "Invocation input edited"
                  : "Invocation input unchanged"}
              </Badge>
            ) : null}
          </div>
          <DialogDescription>
            Fork copies upstream context before the resume boundary, edits only
            the selected agent invocation input, and leaves the source run
            unchanged.
          </DialogDescription>
        </DialogHeader>

        {!presentedAvailability.isAvailable ? (
          <Alert variant="destructive" data-testid="run-fork-invalid-target">
            <AlertCircle />
            <AlertTitle>Fork unavailable</AlertTitle>
            <AlertDescription>
              {presentedAvailability.reason ?? DEFAULT_FORK_UNAVAILABLE_REASON}
            </AlertDescription>
          </Alert>
        ) : null}

        {presentedAvailability.isAvailable && draftQuery.isPending ? (
          <div
            className="flex items-center gap-2 rounded-lg border border-border/70 bg-card/70 p-4 text-sm text-muted-foreground shadow-ui-xs"
            data-testid="run-fork-loading"
          >
            <Loader2 className="size-4 animate-spin" />
            Loading target invocation input...
          </div>
        ) : null}

        {presentedAvailability.isAvailable && draftQuery.isError ? (
          <Alert variant="destructive" data-testid="run-fork-draft-error">
            <AlertCircle />
            <AlertTitle>Unable to load fork draft</AlertTitle>
            <AlertDescription>
              {draftQuery.error instanceof Error
                ? draftQuery.error.message
                : "The target invocation input could not be loaded."}
            </AlertDescription>
          </Alert>
        ) : null}

        {apiError ? (
          <Alert variant="destructive" data-testid="run-fork-api-error">
            <AlertCircle />
            <AlertTitle>Fork creation failed</AlertTitle>
            <AlertDescription>{apiError}</AlertDescription>
          </Alert>
        ) : null}

        {draftQuery.data ? (
          <RunForkReadinessPanel readiness={draftQuery.data} />
        ) : null}

        {draftQuery.data ? (
          <Card className="gap-3" data-testid="run-fork-dialog-body">
            <CardHeader>
              <CardTitle className="text-base">
                Target invocation input
              </CardTitle>
              <CardDescription>
                Edit the persisted input for {targetLabel}. Root run parameters
                stay unchanged; use rerun for root parameter edits.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <DetailGrid
                items={[
                  {
                    label: "Source run",
                    value: `Run #${draftQuery.data.sourceRunId}`,
                  },
                  {
                    label: "Source invocation",
                    value: `#${draftQuery.data.sourceInvocationId}`,
                  },
                  {
                    label: "Resume boundary",
                    value:
                      presentedResumeStepIndex === undefined
                        ? "Not recorded"
                        : `Step ${presentedResumeStepIndex}`,
                  },
                  {
                    label: "Target slot",
                    value: presentedTarget?.invocation.slot ?? "Not recorded",
                  },
                ]}
              />
              <JsonEditorField
                disabled={createFork.isPending}
                error={invocationInputValidation.error}
                id="run-fork-invocation-input-json"
                label="Target invocation input JSON"
                onChange={(value) => {
                  setApiError(null);
                  setInvocationInputText(value);
                }}
                rows={10}
                value={invocationInputText}
              />
            </CardContent>
          </Card>
        ) : null}

        <DialogFooter>
          <Button
            disabled={createFork.isPending}
            onClick={closeDialog}
            type="button"
            variant="ghost"
          >
            Cancel
          </Button>
          <Button
            disabled={!draftQuery.data || createFork.isPending}
            onClick={resetToDraft}
            type="button"
            variant="outline"
          >
            <RotateCcw data-icon="inline-start" />
            Reset target input
          </Button>
          <Button
            data-testid="run-fork-submit"
            disabled={isSubmitDisabled}
            onClick={() => void handleSubmit()}
            type="button"
          >
            {createFork.isPending ? (
              <Loader2 className="animate-spin" data-icon="inline-start" />
            ) : null}
            Create fork from invocation
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
