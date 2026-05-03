import { AlertCircle, GitFork, Loader2, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { useCreateRunFork, useRun, useRunForkDraft } from "@/hooks/use-runs";
import { formatDateTime } from "@/lib/format";
import type {
  RunAgentInvocationRead,
  RunForkCreateRequest,
  RunForkDraftRead,
  RunForkInvocationDraftRead,
  RunStatus,
  RunStepRead,
  RunStepStatus,
  RunTargetKind,
} from "@/lib/types/run";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";

import { stringifyJson } from "../platform-resource-shared";

type TraceSpanEntry = {
  invocationId: number;
  slot: string;
  spanId: string;
  stepIndex: number;
};

type DetailItem = {
  label: string;
  value: ReactNode;
};

type JsonValidationResult<T> = {
  error: string | null;
  value: T | null;
};

type ForkInvocationEditor = {
  key: string;
  stepIndex: number;
  slot: string;
  sourceInvocationId: number;
  agentKey: string;
  resolvedInputText: string;
  outputText: string;
};

type ForkAvailability = {
  isAvailable: boolean;
  reason: string | null;
};

const DEFAULT_FORK_UNAVAILABLE_REASON = "Choose a succeeded workflow step with a following step to create a fork.";

function isTerminalStatus(status: RunStepStatus): boolean {
  return status === "succeeded" || status === "failed" || status === "skipped";
}

function progressForInvocations(invocations: RunAgentInvocationRead[], fallbackStatus?: RunStepStatus | RunStatus): number {
  if (invocations.length === 0) {
    return fallbackStatus && fallbackStatus !== "running" && fallbackStatus !== "pending" ? 100 : 0;
  }

  const completed = invocations.filter((invocation) => isTerminalStatus(invocation.status)).length;
  return Math.round((completed / invocations.length) * 100);
}

function progressForRun(status: RunStatus, steps: RunStepRead[]): number {
  const invocations = steps.flatMap((step) => step.invocations);

  if (invocations.length === 0) {
    return status === "running" ? 0 : 100;
  }

  if (status !== "running") {
    return 100;
  }

  return progressForInvocations(invocations);
}

function formatTracePath(traceId: string | null, traceSpanEntries: TraceSpanEntry[]): string | null {
  const segments = traceSpanEntries.map(
    (entry) => `step ${entry.stepIndex}/${entry.slot}/${entry.spanId}`,
  );

  if (traceId && segments.length === 0) {
    return traceId;
  }

  if (!traceId && segments.length === 0) {
    return null;
  }

  return [traceId, ...segments].filter(Boolean).join(" -> ");
}

function formatTargetKindLabel(targetKind: RunTargetKind): string {
  return targetKind === "agent" ? "Agent" : "Workflow";
}

function describeRunTarget(targetKind: RunTargetKind): string {
  return targetKind === "agent"
    ? "Standalone agent execution with a single runnable target."
    : "Workflow execution with step-by-step agent orchestration.";
}

function formatOptional(value: ReactNode | null | undefined): ReactNode {
  if (value === null || value === undefined || value === "") {
    return "Not recorded";
  }

  return value;
}

function formatTimestamp(value: string | null): string {
  return value ? formatDateTime(value) : "Not recorded";
}

function formatDuration(durationMs: number | null): string {
  return durationMs === null ? "Not recorded" : `${durationMs} ms`;
}

function statusVariant(status: RunStatus | RunStepStatus): "secondary" | "destructive" | "outline" {
  if (status === "failed") {
    return "destructive";
  }

  if (status === "pending" || status === "skipped") {
    return "outline";
  }

  return "secondary";
}

function sortedInvocations(invocations: RunAgentInvocationRead[]): RunAgentInvocationRead[] {
  return [...invocations].sort((left, right) => left.position - right.position || left.slot.localeCompare(right.slot));
}

function finalExecutableStepIndex(steps: RunStepRead[]): number | null {
  if (steps.length === 0) {
    return null;
  }

  return Math.max(...steps.map((step) => step.index));
}

function getForkAvailability(
  targetKind: RunTargetKind,
  steps: RunStepRead[],
  forkStepIndex: number | undefined,
): ForkAvailability {
  if (targetKind !== "workflow") {
    return {
      isAvailable: false,
      reason: "Workflow-step forks are only available for workflow runs.",
    };
  }

  if (forkStepIndex === undefined) {
    return {
      isAvailable: false,
      reason: DEFAULT_FORK_UNAVAILABLE_REASON,
    };
  }

  const selectedStep = steps.find((step) => step.index === forkStepIndex);
  if (!selectedStep) {
    return {
      isAvailable: false,
      reason: `Step ${forkStepIndex} is not available on this run.`,
    };
  }

  if (selectedStep.status !== "succeeded") {
    return {
      isAvailable: false,
      reason: `Step ${forkStepIndex} is ${selectedStep.status}; only succeeded workflow steps can be forked.`,
    };
  }

  if (finalExecutableStepIndex(steps) === selectedStep.index) {
    return {
      isAvailable: false,
      reason: "Final workflow steps cannot be forked because there is no following step to resume.",
    };
  }

  return { isAvailable: true, reason: null };
}

function formatJsonEditorValue(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function parseJsonValue(text: string, label: string): JsonValidationResult<unknown> {
  try {
    return { error: null, value: JSON.parse(text) as unknown };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Invalid JSON";
    return { error: `${label} must be valid JSON. ${message}`, value: null };
  }
}

function parseJsonRecord(text: string, label: string): JsonValidationResult<Record<string, unknown>> {
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

function forkDraftTargetKey(draft: RunForkDraftRead): string {
  return `${draft.sourceRunId}:${draft.forkStepIndex}`;
}

function createInvocationEditor(invocation: RunForkInvocationDraftRead): ForkInvocationEditor {
  return {
    agentKey: invocation.agentKey,
    key: `${invocation.stepIndex}:${invocation.slot}:${invocation.sourceInvocationId}`,
    outputText: formatJsonEditorValue(invocation.output),
    resolvedInputText: formatJsonEditorValue(invocation.resolvedInput),
    slot: invocation.slot,
    sourceInvocationId: invocation.sourceInvocationId,
    stepIndex: invocation.stepIndex,
  };
}

function createInvocationEditors(draft: RunForkDraftRead): ForkInvocationEditor[] {
  return draft.steps.flatMap((step) =>
    step.invocations
      .map(createInvocationEditor)
      .sort((left, right) => left.stepIndex - right.stepIndex || left.slot.localeCompare(right.slot)),
  );
}

function DetailGrid({ items }: { items: DetailItem[] }) {
  return (
    <dl className="grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-3">
      {items.map((item) => (
        <div className="rounded-md border bg-muted/20 p-3" key={item.label}>
          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{item.label}</dt>
          <dd className="mt-1 break-words text-foreground">{formatOptional(item.value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function JsonBlock({ label, testId, value }: { label: string; testId?: string; value: unknown }) {
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">{label}</p>
      <pre className="overflow-x-auto rounded-md border bg-muted/30 p-3 text-xs" data-testid={testId}>
        {stringifyJson(value)}
      </pre>
    </div>
  );
}

function SourceRunLink({ children, runId }: { children: ReactNode; runId: number | null }) {
  if (!runId) {
    return <>{children}</>;
  }

  return (
    <Link className="text-primary underline-offset-4 hover:underline" to={`/runs/${runId}`}>
      {children}
    </Link>
  );
}

function SourceStepLink({ step }: { step: RunStepRead }) {
  if (!step.sourceRunId || step.sourceStepIndex === null) {
    return "Not recorded";
  }

  return (
    <Link className="text-primary underline-offset-4 hover:underline" to={`/runs/${step.sourceRunId}#step-${step.sourceStepIndex}`}>
      Run #{step.sourceRunId} step {step.sourceStepIndex}
    </Link>
  );
}

function SourceInvocationLink({ invocation, step }: { invocation: RunAgentInvocationRead; step: RunStepRead }) {
  if (invocation.sourceInvocationId === null) {
    return "Not recorded";
  }

  if (!step.sourceRunId) {
    return `Invocation #${invocation.sourceInvocationId}`;
  }

  return (
    <Link className="text-primary underline-offset-4 hover:underline" to={`/runs/${step.sourceRunId}#invocation-${invocation.sourceInvocationId}`}>
      Invocation #{invocation.sourceInvocationId}
    </Link>
  );
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
      <Label className="text-sm" htmlFor={id}>{label}</Label>
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

function RunForkDialog({
  forkAvailability,
  forkStepIndex,
  onClose,
  open,
  runId,
}: {
  forkAvailability: ForkAvailability;
  forkStepIndex: number | undefined;
  onClose: () => void;
  open: boolean;
  runId: string;
}) {
  const navigate = useNavigate();
  const draftQuery = useRunForkDraft(runId, forkStepIndex, { enabled: open && forkAvailability.isAvailable });
  const createRunFork = useCreateRunFork();
  const [draftTargetKey, setDraftTargetKey] = useState<string | null>(null);
  const [inputText, setInputText] = useState("");
  const [invocationEditors, setInvocationEditors] = useState<ForkInvocationEditor[]>([]);
  const [apiError, setApiError] = useState<string | null>(null);

  const resetLocalState = () => {
    setDraftTargetKey(null);
    setInputText("");
    setInvocationEditors([]);
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

    const nextTargetKey = forkDraftTargetKey(draftQuery.data);
    if (draftTargetKey === nextTargetKey) {
      return;
    }

    setDraftTargetKey(nextTargetKey);
    setInputText(formatJsonEditorValue(draftQuery.data.input));
    setInvocationEditors(createInvocationEditors(draftQuery.data));
    setApiError(null);
  }, [draftQuery.data, draftTargetKey, open]);

  const inputValidation = useMemo(
    () => parseJsonRecord(inputText || "{}", "Run input JSON"),
    [inputText],
  );
  const invocationValidations = useMemo(() => {
    const validations = new Map<string, {
      output: JsonValidationResult<unknown>;
      resolvedInput: JsonValidationResult<Record<string, unknown>>;
    }>();

    invocationEditors.forEach((editor) => {
      validations.set(editor.key, {
        output: parseJsonValue(editor.outputText, `Output JSON for step ${editor.stepIndex} ${editor.slot}`),
        resolvedInput: parseJsonRecord(editor.resolvedInputText, `Resolved input JSON for step ${editor.stepIndex} ${editor.slot}`),
      });
    });

    return validations;
  }, [invocationEditors]);
  const originalInvocationByKey = useMemo(() => {
    const originals = new Map<string, RunForkInvocationDraftRead>();

    draftQuery.data?.steps.forEach((step) => {
      step.invocations.forEach((invocation) => {
        originals.set(`${invocation.stepIndex}:${invocation.slot}:${invocation.sourceInvocationId}`, invocation);
      });
    });

    return originals;
  }, [draftQuery.data]);
  const hasValidationError = Boolean(
    inputValidation.error ||
      [...invocationValidations.values()].some((validation) => validation.resolvedInput.error || validation.output.error),
  );
  const forkPayload = useMemo<RunForkCreateRequest | null>(() => {
    if (!draftQuery.data || hasValidationError || !inputValidation.value) {
      return null;
    }

    const payload: RunForkCreateRequest = { forkStepIndex: draftQuery.data.forkStepIndex };
    if (!areJsonValuesEqual(inputValidation.value, draftQuery.data.input)) {
      payload.input = inputValidation.value;
    }

    const invocationEdits = invocationEditors.flatMap((editor) => {
      const original = originalInvocationByKey.get(editor.key);
      const validation = invocationValidations.get(editor.key);

      if (!original || !validation?.resolvedInput.value || validation.resolvedInput.error || validation.output.error) {
        return [];
      }

      const edit: NonNullable<RunForkCreateRequest["invocationEdits"]>[number] = {
        slot: editor.slot,
        stepIndex: editor.stepIndex,
      };
      let hasEdit = false;

      if (!areJsonValuesEqual(validation.resolvedInput.value, original.resolvedInput)) {
        edit.resolvedInput = validation.resolvedInput.value;
        hasEdit = true;
      }

      if (!areJsonValuesEqual(validation.output.value, original.output)) {
        edit.output = validation.output.value;
        hasEdit = true;
      }

      return hasEdit ? [edit] : [];
    });

    if (invocationEdits.length > 0) {
      payload.invocationEdits = invocationEdits;
    }

    return payload;
  }, [draftQuery.data, hasValidationError, inputValidation.value, invocationEditors, invocationValidations, originalInvocationByKey]);
  const hasDraftEdits = Boolean(forkPayload?.input || (forkPayload?.invocationEdits?.length ?? 0) > 0);
  const isSubmitDisabled = !forkPayload || createRunFork.isPending || draftQuery.isPending || hasValidationError;

  const updateInvocationEditor = (key: string, field: "outputText" | "resolvedInputText", value: string) => {
    setApiError(null);
    setInvocationEditors((editors) =>
      editors.map((editor) => (editor.key === key ? { ...editor, [field]: value } : editor)),
    );
  };

  const resetToDraft = () => {
    if (!draftQuery.data) {
      return;
    }

    setDraftTargetKey(forkDraftTargetKey(draftQuery.data));
    setInputText(formatJsonEditorValue(draftQuery.data.input));
    setInvocationEditors(createInvocationEditors(draftQuery.data));
    setApiError(null);
  };

  const handleSubmit = async () => {
    if (!forkPayload) {
      return;
    }

    setApiError(null);

    try {
      const createdRun = await createRunFork.mutateAsync({ runId, payload: forkPayload });
      resetLocalState();
      navigate(`/runs/${createdRun.id}`);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Failed to create forked run.");
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !createRunFork.isPending) {
          closeDialog();
        }
      }}
    >
      <DialogContent className="max-h-dvh overflow-y-auto sm:max-w-5xl">
        <DialogHeader>
          <div className="flex flex-wrap items-center gap-2 pr-6">
            <DialogTitle>Fork run draft</DialogTitle>
            {forkStepIndex !== undefined ? <Badge variant="outline">Step {forkStepIndex}</Badge> : null}
            {draftQuery.data ? <Badge variant={hasDraftEdits ? "secondary" : "outline"}>{hasDraftEdits ? "Edited draft" : "Source snapshot"}</Badge> : null}
          </div>
          <DialogDescription>
            Create a new run from copied step payloads. Edits apply only to the fork draft; the source run remains immutable.
          </DialogDescription>
        </DialogHeader>

        {!forkAvailability.isAvailable ? (
          <Alert variant="destructive" data-testid="run-fork-invalid-step">
            <AlertCircle />
            <AlertTitle>Fork step unavailable</AlertTitle>
            <AlertDescription>{forkAvailability.reason ?? DEFAULT_FORK_UNAVAILABLE_REASON}</AlertDescription>
          </Alert>
        ) : null}

        {forkAvailability.isAvailable && draftQuery.isPending ? (
          <div className="flex items-center gap-2 rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground" data-testid="run-fork-loading">
            <Loader2 className="size-4 animate-spin" />
            Loading fork draft...
          </div>
        ) : null}

        {forkAvailability.isAvailable && draftQuery.isError ? (
          <Alert variant="destructive" data-testid="run-fork-draft-error">
            <AlertCircle />
            <AlertTitle>Unable to load fork draft</AlertTitle>
            <AlertDescription>{draftQuery.error instanceof Error ? draftQuery.error.message : "The fork draft could not be loaded."}</AlertDescription>
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
          <div className="grid gap-4" data-testid="run-fork-dialog-body">
            <Card className="gap-3">
              <CardHeader>
                <CardTitle className="text-base">Run input draft</CardTitle>
                <CardDescription>Edit the input JSON that the new forked run will receive.</CardDescription>
              </CardHeader>
              <CardContent>
                <JsonEditorField
                  disabled={createRunFork.isPending}
                  error={inputValidation.error}
                  id="run-fork-input-json"
                  label="Fork draft run input JSON"
                  onChange={(value) => {
                    setApiError(null);
                    setInputText(value);
                  }}
                  rows={10}
                  value={inputText}
                />
              </CardContent>
            </Card>

            <div className="grid gap-3">
              {invocationEditors.length === 0 ? (
                <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground">No copied invocation payloads are available for this fork step.</div>
              ) : null}
              {invocationEditors.map((editor) => {
                const validation = invocationValidations.get(editor.key);

                return (
                  <Card className="gap-3" data-testid={`run-fork-invocation-${editor.stepIndex}-${editor.slot}`} key={editor.key}>
                    <CardHeader>
                      <CardTitle className="text-base">Step {editor.stepIndex} · {editor.slot}</CardTitle>
                      <CardDescription>
                        Copied from invocation #{editor.sourceInvocationId} · {editor.agentKey}
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="grid gap-3 lg:grid-cols-2">
                      <JsonEditorField
                        disabled={createRunFork.isPending}
                        error={validation?.resolvedInput.error ?? null}
                        id={`run-fork-resolved-input-${editor.key}`}
                        label="Fork draft resolved input JSON"
                        onChange={(value) => updateInvocationEditor(editor.key, "resolvedInputText", value)}
                        value={editor.resolvedInputText}
                      />
                      <JsonEditorField
                        disabled={createRunFork.isPending}
                        error={validation?.output.error ?? null}
                        id={`run-fork-output-${editor.key}`}
                        label="Fork draft output JSON"
                        onChange={(value) => updateInvocationEditor(editor.key, "outputText", value)}
                        value={editor.outputText}
                      />
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </div>
        ) : null}

        <DialogFooter>
          <Button disabled={createRunFork.isPending} onClick={closeDialog} type="button" variant="ghost">
            Cancel
          </Button>
          <Button disabled={!draftQuery.data || createRunFork.isPending} onClick={resetToDraft} type="button" variant="outline">
            <RotateCcw data-icon="inline-start" />
            Reset draft
          </Button>
          <Button data-testid="run-fork-submit" disabled={isSubmitDisabled} onClick={() => void handleSubmit()} type="button">
            {createRunFork.isPending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <GitFork data-icon="inline-start" />}
            Create fork
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function InvocationCard({ invocation, step }: { invocation: RunAgentInvocationRead; step: RunStepRead }) {
  const hasError = Boolean(invocation.errorCode || invocation.errorMessage || invocation.errorDetails.length > 0);

  return (
    <Card id={`invocation-${invocation.id}`} data-testid={`runs-step-${step.index}-slot-${invocation.slot}`}>
      <CardHeader>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex flex-col gap-1">
            <CardTitle className="text-base">{invocation.slot}</CardTitle>
            <CardDescription>
              Position {invocation.position} · {invocation.agentKey}@{invocation.agentVersion}
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={statusVariant(invocation.status)}>{invocation.status}</Badge>
            <Badge variant="outline">{invocation.inputMode}</Badge>
            <Badge variant="outline">input {invocation.resolvedInputOrigin}</Badge>
            <Badge variant="outline">output {invocation.outputOrigin ?? "pending"}</Badge>
            <Badge variant="outline">{invocation.optional ? "optional" : "required"}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {hasError ? (
          <Alert variant="destructive">
            <AlertCircle />
            <AlertTitle>{invocation.errorCode ?? "Invocation failed"}</AlertTitle>
            <AlertDescription className="space-y-2">
              <p>{invocation.errorMessage ?? "No error message recorded."}</p>
              {invocation.errorDetails.length > 0 ? (
                <pre className="overflow-x-auto rounded-md border border-destructive/30 bg-muted/30 p-3 text-xs">
                  {stringifyJson(invocation.errorDetails)}
                </pre>
              ) : null}
            </AlertDescription>
          </Alert>
        ) : null}

        <DetailGrid
          items={[
            { label: "Invocation id", value: `#${invocation.id}` },
            { label: "Agent", value: `${invocation.agentKey}@${invocation.agentVersion}` },
            { label: "Agent id", value: `#${invocation.agentId}` },
            { label: "Output schema", value: `#${invocation.outputSchemaId}@${invocation.outputSchemaVersion}` },
            { label: "Source invocation", value: <SourceInvocationLink invocation={invocation} step={step} /> },
            { label: "Tokens", value: invocation.tokens },
            { label: "Cost", value: invocation.costUsd },
            { label: "Duration", value: formatDuration(invocation.durationMs) },
            {
              label: "Trace span",
              value: invocation.traceSpanId ? (
                <Button asChild size="sm" variant="outline">
                  <Link to="#run-trace-linkage">Trace link · {invocation.traceSpanId}</Link>
                </Button>
              ) : (
                "Not recorded"
              ),
            },
            { label: "Started", value: formatTimestamp(invocation.startedAt) },
            { label: "Finished", value: formatTimestamp(invocation.finishedAt) },
            { label: "Persisted", value: formatTimestamp(invocation.persistedAt) },
          ]}
        />

        <div className="grid gap-4 xl:grid-cols-3">
          <JsonBlock label="Wiring" value={invocation.wiring} />
          <JsonBlock label="Resolved input" value={invocation.resolvedInput} />
          <JsonBlock label="Output" value={invocation.output} />
        </div>
      </CardContent>
    </Card>
  );
}

function StepCard({ canFork, onOpenFork, step }: { canFork: boolean; onOpenFork: (stepIndex: number) => void; step: RunStepRead }) {
  const invocations = sortedInvocations(step.invocations);
  const progress = progressForInvocations(invocations, step.status);

  return (
    <Card id={`step-${step.index}`} data-testid={`runs-step-${step.index}`}>
      <AccordionItem className="border-b-0" value={`step-${step.index}`}>
        <CardHeader>
          <AccordionTrigger className="py-0 hover:no-underline">
            <div className="flex w-full flex-col gap-3 pr-2 text-left">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="flex flex-col gap-1">
                  <CardTitle className="text-base">Step {step.index}</CardTitle>
                  <CardDescription>
                    {step.origin} origin · {invocations.length} invocation(s) · {progress}% terminal
                  </CardDescription>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge variant={statusVariant(step.status)}>{step.status}</Badge>
                  <Badge variant="outline">{step.origin}</Badge>
                  <Badge variant="secondary">{progress}%</Badge>
                </div>
              </div>
              <Progress value={progress} />
            </div>
          </AccordionTrigger>
        </CardHeader>
        <AccordionContent className="px-6 pb-6">
          <div className="flex flex-col gap-4">
            {step.error ? (
              <Alert variant="destructive">
                <AlertCircle />
                <AlertTitle>Step failed</AlertTitle>
                <AlertDescription>{step.error}</AlertDescription>
              </Alert>
            ) : null}

            {canFork ? (
              <div className="flex flex-col gap-3 rounded-md border bg-muted/20 p-4 sm:flex-row sm:items-center sm:justify-between" data-testid={`runs-step-${step.index}-fork-entry`}>
                <div className="flex flex-col gap-1">
                  <p className="text-sm font-medium">Fork from this succeeded step</p>
                  <p className="text-sm text-muted-foreground">Copy steps through step {step.index}, edit fork draft payloads, then resume in a new run.</p>
                </div>
                <Button onClick={() => onOpenFork(step.index)} size="sm" type="button" variant="outline">
                  <GitFork data-icon="inline-start" />
                  Fork step
                </Button>
              </div>
            ) : null}

            <DetailGrid
              items={[
                { label: "Step row", value: `#${step.id}` },
                { label: "Source step", value: <SourceStepLink step={step} /> },
                { label: "Started", value: formatTimestamp(step.startedAt) },
                { label: "Finished", value: formatTimestamp(step.finishedAt) },
                { label: "Persisted", value: formatTimestamp(step.persistedAt) },
                { label: "Updated", value: formatDateTime(step.updatedAt) },
              ]}
            />

            {invocations.length === 0 ? (
              <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground">
                No invocations have been planned or persisted for this step yet.
              </div>
            ) : (
              <div className="grid gap-3">
                {invocations.map((invocation) => (
                  <InvocationCard invocation={invocation} key={invocation.id} step={step} />
                ))}
              </div>
            )}
          </div>
        </AccordionContent>
      </AccordionItem>
    </Card>
  );
}

export function RunsDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const runQuery = useRun(runId, { refetchInterval: 2_000 });

  const steps = useMemo(
    () => [...(runQuery.data?.steps ?? [])].sort((left, right) => left.index - right.index),
    [runQuery.data?.steps],
  );
  const allInvocations = useMemo(() => steps.flatMap((step) => sortedInvocations(step.invocations)), [steps]);
  const traceSpanEntries = useMemo(
    () =>
      steps.flatMap((step) =>
        sortedInvocations(step.invocations)
          .filter((invocation) => invocation.traceSpanId)
          .map((invocation) => ({
            invocationId: invocation.id,
            slot: invocation.slot,
            spanId: invocation.traceSpanId as string,
            stepIndex: step.index,
          })),
      ),
    [steps],
  );
  const forkDialogOpen = searchParams.get("fork") === "1";
  const forkStepIndexParam = searchParams.get("forkStepIndex");
  const forkStepIndex = useMemo(() => {
    if (forkStepIndexParam === null || forkStepIndexParam.trim() === "") {
      return undefined;
    }

    const parsed = Number(forkStepIndexParam);
    return Number.isInteger(parsed) && parsed >= 0 ? parsed : undefined;
  }, [forkStepIndexParam]);

  const openForkDialog = (stepIndex: number) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("fork", "1");
      next.set("forkStepIndex", String(stepIndex));
      return next;
    });
  };

  const closeForkDialog = () => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.delete("fork");
      next.delete("forkStepIndex");
      return next;
    });
  };

  if (!runId) {
    return <div className="p-4 text-sm text-muted-foreground">Run route is missing an id.</div>;
  }

  if (runQuery.isPending) {
    return <div className="p-4 text-sm text-muted-foreground">Loading run details...</div>;
  }

  if (runQuery.isError || !runQuery.data) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        {runQuery.error instanceof Error ? runQuery.error.message : "Run not found."}
      </div>
    );
  }

  const run = runQuery.data;
  const copiedSteps = steps.filter((step) => step.origin === "copied").length;
  const plannedSteps = steps.filter((step) => step.origin === "planned").length;
  const copiedInvocations = allInvocations.filter((invocation) => invocation.outputOrigin === "copied" || invocation.resolvedInputOrigin === "copied").length;
  const plannedInvocations = allInvocations.length - copiedInvocations;
  const runProgress = progressForRun(run.status, steps);
  const tracePath = formatTracePath(run.traceId, traceSpanEntries);
  const traceIdLabel = run.traceId ?? (traceSpanEntries.length > 0 ? "Captured through invocation spans" : "No trace id recorded");
  const targetKindLabel = formatTargetKindLabel(run.targetKind);
  const forkAvailability = getForkAvailability(run.targetKind, steps, forkStepIndex);

  return (
    <div className="flex flex-col gap-4 p-4" data-testid="runs-detail-page">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight">Run #{run.id}</h1>
            <Badge data-testid="runs-detail-status" variant={statusVariant(run.status)}>
              {run.status}
            </Badge>
            <Badge data-testid="runs-detail-target-kind" variant="outline">
              {targetKindLabel}
            </Badge>
            <Badge data-testid="runs-detail-target-identity" variant="outline">
              {run.targetKey}@{run.targetVersion}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {describeRunTarget(run.targetKind)} · Started {formatDateTime(run.startedAt)}
            {run.finishedAt ? ` · Finished ${formatDateTime(run.finishedAt)}` : " · Still running"}
          </p>
        </div>
        <Button asChild size="sm" variant="outline">
          <Link to="/runs">Back to runs</Link>
        </Button>
      </div>

      {run.error ? (
        <Alert variant="destructive">
          <AlertCircle />
          <AlertTitle>Run failed</AlertTitle>
          <AlertDescription>{run.error}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Progress</CardTitle>
            <CardDescription>Terminal invocation completion.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>Run progress</span>
              <span>{runProgress}%</span>
            </div>
            <Progress value={runProgress} />
            <p className="text-sm text-muted-foreground">
              {allInvocations.filter((invocation) => isTerminalStatus(invocation.status)).length} of {allInvocations.length} invocation(s) terminal.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Target</CardTitle>
            <CardDescription>Runnable identity for this execution.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>Target kind: {targetKindLabel}</p>
            <p>Target key: {run.targetKey}</p>
            <p>Target version: {run.targetVersion}</p>
            <p>Target id: {run.targetId}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Usage</CardTitle>
            <CardDescription>Copied, executed, and total usage.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>Total tokens: {run.totalTokens}</p>
            <p>Total cost: {run.totalCostUsd}</p>
            <p>Inherited tokens: {run.inheritedTokens}</p>
            <p>Inherited cost: {run.inheritedCostUsd}</p>
            <p>Executed tokens: {run.executedTokens}</p>
            <p>Executed cost: {run.executedCostUsd}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Trace</CardTitle>
            <CardDescription>Run-level trace plus invocation spans.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>Run trace id: {traceIdLabel}</p>
            <p data-testid="runs-trace-path">
              {tracePath ? `Linkage path: ${tracePath}` : `Span links: ${traceSpanEntries.length}`}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card data-testid="runs-lineage-summary">
        <CardHeader>
          <CardTitle className="text-base">Lineage</CardTitle>
          <CardDescription>Fork and resume metadata for copied and planned execution origins.</CardDescription>
        </CardHeader>
        <CardContent>
          <DetailGrid
            items={[
              {
                label: "Source run",
                value: run.sourceRunId ? <SourceRunLink runId={run.sourceRunId}>Run #{run.sourceRunId}</SourceRunLink> : "Original run",
              },
              { label: "Lineage root", value: run.lineageRootRunId ? `Run #${run.lineageRootRunId}` : `Run #${run.id}` },
              { label: "Forked from step", value: run.forkedFromStepIndex === null ? "Not forked" : `Step ${run.forkedFromStepIndex}` },
              { label: "Resume step", value: `Step ${run.resumeStepIndex}` },
              { label: "Step origins", value: `${copiedSteps} copied · ${plannedSteps} planned` },
              { label: "Invocation origins", value: `${copiedInvocations} copied · ${plannedInvocations} planned/executed` },
            ]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Final output</CardTitle>
          <CardDescription>Run input and resolved final payload.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <JsonBlock label="Input" value={run.input} />
          <JsonBlock label="Final output" testId="runs-detail-final-output" value={run.finalOutput} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader id="run-trace-linkage">
          <CardTitle className="text-base">Trace linkage</CardTitle>
          <CardDescription>Run trace id plus per-invocation span references.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground" data-testid="runs-trace-linkage">
          <p>Run trace id: {traceIdLabel}</p>
          {tracePath ? <p>Trace path: {tracePath}</p> : null}
          {traceSpanEntries.length === 0 ? <p>No invocation trace spans captured.</p> : null}
          {traceSpanEntries.map((entry) => (
            <div className="rounded-md border bg-muted/20 p-3" key={`${entry.stepIndex}-${entry.slot}-${entry.spanId}`}>
              <p>
                {run.traceId ? `Path ${run.traceId} / step ${entry.stepIndex} / ${entry.slot}` : `Path step ${entry.stepIndex} / ${entry.slot}`}
              </p>
              <p>Invocation #{entry.invocationId}</p>
              <p>Span id: {entry.spanId}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Step timeline</CardTitle>
          <CardDescription>Normalized steps with nested invocation state, origins, metrics, and payloads.</CardDescription>
        </CardHeader>
        <CardContent>
          {steps.length === 0 ? (
            <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground" data-testid="runs-empty-steps">
              No steps have been planned for this run yet.
            </div>
          ) : (
            <Accordion className="flex w-full flex-col gap-3" defaultValue={steps.map((step) => `step-${step.index}`)} type="multiple">
              {steps.map((step) => (
                <StepCard
                  canFork={getForkAvailability(run.targetKind, steps, step.index).isAvailable}
                  key={step.id}
                  onOpenFork={openForkDialog}
                  step={step}
                />
              ))}
            </Accordion>
          )}
        </CardContent>
      </Card>

      <RunForkDialog
        forkAvailability={forkAvailability}
        forkStepIndex={forkStepIndex}
        onClose={closeForkDialog}
        open={forkDialogOpen}
        runId={runId}
      />
    </div>
  );
}
