import { AlertCircle, Download, FileText, Loader2, PlayCircle, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { useCreateRunStepReplay, useRun, useRunStepReplayDraft } from "@/hooks/use-runs";
import { downloadReportUrl } from "@/lib/api/reports";
import { formatDateTime } from "@/lib/format";
import type {
  RunAgentInvocationRead,
  RunGraphMetadata,
  RunMemoryArtifactRead,
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
import { RunRerunDialog } from "./rerun-dialog";

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

type StepReplayAvailability = {
  isAvailable: boolean;
  reason: string | null;
};

const DEFAULT_STEP_REPLAY_UNAVAILABLE_REASON = "Choose a succeeded workflow step to replay from.";

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
  if (status === "queued") {
    return 0;
  }

  const invocations = steps.flatMap((step) => step.invocations);

  if (invocations.length === 0) {
    return status === "running" ? 0 : 100;
  }

  if (status !== "running") {
    return 100;
  }

  return progressForInvocations(invocations);
}

function formatUnfinishedRunStatus(status: RunStatus): string {
  return status === "queued" ? " · Awaiting execution" : " · Still running";
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

function getStepReplayAvailability(
  targetKind: RunTargetKind,
  steps: RunStepRead[],
  replayStepIndex: number | undefined,
): StepReplayAvailability {
  if (targetKind !== "workflow") {
    return {
      isAvailable: false,
      reason: "Step replay is only available for workflow runs.",
    };
  }

  if (replayStepIndex === undefined) {
    return {
      isAvailable: false,
      reason: DEFAULT_STEP_REPLAY_UNAVAILABLE_REASON,
    };
  }

  const selectedStep = steps.find((step) => step.index === replayStepIndex);
  if (!selectedStep) {
    return {
      isAvailable: false,
      reason: `Step ${replayStepIndex} is not available on this run.`,
    };
  }

  if (selectedStep.status !== "succeeded") {
    return {
      isAvailable: false,
      reason: `Step ${replayStepIndex} is ${selectedStep.status}; only succeeded workflow steps can be replayed.`,
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

function graphMetadataLabel(metadata: RunGraphMetadata | null): string {
  if (!metadata) {
    return "Not recorded";
  }

  return [
    metadata.nodeKind,
    metadata.nodeId,
    metadata.fanoutId ? `fanout ${metadata.fanoutId}` : null,
    metadata.branchId ? `branch ${metadata.branchId}` : null,
    metadata.loopId ? `loop ${metadata.loopId}` : null,
    metadata.loopIteration ? `iteration ${metadata.loopIteration}` : null,
  ].filter(Boolean).join(" · ");
}

function GraphMetadataBadges({ metadata }: { metadata: RunGraphMetadata | null }) {
  if (!metadata) {
    return null;
  }

  return (
    <>
      {metadata.nodeKind ? <Badge variant="outline">{metadata.nodeKind}</Badge> : null}
      {metadata.nodeId ? <Badge variant="outline">node {metadata.nodeId}</Badge> : null}
      {metadata.fanoutId ? <Badge variant="outline">fanout {metadata.fanoutId}</Badge> : null}
      {metadata.branchId ? <Badge variant="outline">branch {metadata.branchId}</Badge> : null}
      {metadata.loopId ? <Badge variant="outline">loop {metadata.loopId}</Badge> : null}
      {metadata.loopIteration ? <Badge variant="outline">iteration {metadata.loopIteration}</Badge> : null}
    </>
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

type RunGraphGroup = {
  branchIds: string[];
  invocations: RunAgentInvocationRead[];
  key: string;
  label: string;
  loopId: string | null;
  loopIteration: number | null;
  nodeKind: string;
  steps: RunStepRead[];
};

function groupRunGraphSteps(steps: RunStepRead[]): RunGraphGroup[] {
  const groups = new Map<string, RunGraphGroup>();
  const ensureGroup = (key: string, label: string, nodeKind: string, loopId: string | null, loopIteration: number | null) => {
    let group = groups.get(key);
    if (!group) {
      group = { branchIds: [], invocations: [], key, label, loopId, loopIteration, nodeKind, steps: [] };
      groups.set(key, group);
    }
    return group;
  };

  steps.forEach((step) => {
    const metadata = step.graphMetadata;
    const firstInvocationMetadata = step.invocations.find((invocation) => invocation.graphMetadata)?.graphMetadata ?? null;
    const groupingMetadata = metadata ?? firstInvocationMetadata;
    if (!groupingMetadata) {
      return;
    }
    const loopKey = groupingMetadata.loopId
      ? `:loop:${groupingMetadata.loopId}:iteration:${groupingMetadata.loopIteration ?? "all"}`
      : "";
    const key = groupingMetadata.fanoutId
      ? `fanout:${groupingMetadata.fanoutId}${loopKey}`
      : groupingMetadata.loopId
        ? `loop:${groupingMetadata.loopId}:iteration:${groupingMetadata.loopIteration ?? "all"}`
        : groupingMetadata.nodeId
          ? `node:${groupingMetadata.nodeId}`
          : `step:${step.index}`;
    const loopContext = groupingMetadata.loopId
      ? ` · loop ${groupingMetadata.loopId}${groupingMetadata.loopIteration ? ` iteration ${groupingMetadata.loopIteration}` : ""}`
      : "";
    const label = groupingMetadata.fanoutId
      ? `Fanout ${groupingMetadata.fanoutId}${loopContext}`
      : groupingMetadata.loopId
        ? `Loop ${groupingMetadata.loopId}${groupingMetadata.loopIteration ? ` iteration ${groupingMetadata.loopIteration}` : ""}`
        : groupingMetadata.nodeId
          ? `Node ${groupingMetadata.nodeId}`
          : `Step ${step.index}`;
    const group = ensureGroup(
      key,
      label,
      groupingMetadata.nodeKind ?? metadata?.nodeKind ?? "step",
      groupingMetadata.loopId ?? null,
      groupingMetadata.loopIteration ?? null,
    );
    group.steps.push(step);
    group.invocations.push(...step.invocations);
    for (const invocation of step.invocations) {
      const branchId = invocation.graphMetadata?.branchId;
      if (branchId && !group.branchIds.includes(branchId)) {
        group.branchIds.push(branchId);
      }
    }
  });

  return [...groups.values()].sort((left, right) => {
    const leftIndex = Math.min(...left.steps.map((step) => step.index));
    const rightIndex = Math.min(...right.steps.map((step) => step.index));
    return leftIndex - rightIndex || left.key.localeCompare(right.key);
  });
}

function RunGraphSummary({ groups }: { groups: RunGraphGroup[] }) {
  if (groups.length === 0) {
    return null;
  }

  return (
    <Card data-testid="runs-graph-summary">
      <CardHeader>
        <CardTitle className="text-base">Graph execution summary</CardTitle>
        <CardDescription>Sequence, fanout, and loop grouping derived from runtime graph metadata.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {groups.map((group, index) => (
          <div className="rounded-md border bg-muted/20 p-3 text-sm" data-testid={`runs-graph-group-${index + 1}`} key={group.key}>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary">{group.nodeKind}</Badge>
              {group.loopId ? <Badge variant="outline">loop {group.loopId}</Badge> : null}
              {group.loopIteration ? <Badge variant="outline">iteration {group.loopIteration}</Badge> : null}
              {group.branchIds.map((branchId) => <Badge key={branchId} variant="outline">branch {branchId}</Badge>)}
            </div>
            <p className="mt-2 font-medium">{group.label}</p>
            <p className="mt-1 text-muted-foreground">
              Steps {group.steps.map((step) => step.index).join(", ")} · {group.invocations.length} invocation(s)
            </p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function MemoryArtifacts({ artifacts }: { artifacts: RunMemoryArtifactRead[] }) {
  if (artifacts.length === 0) {
    return null;
  }

  return (
    <Card data-testid="runs-memory-artifacts">
      <CardHeader>
        <CardTitle className="text-base">Memory artifacts</CardTitle>
        <CardDescription>Agent memory reports created after this run.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {artifacts.map((artifact) => (
          <div className="rounded-md border bg-muted/20 p-3 text-sm" data-testid={`runs-memory-artifact-${artifact.slug}`} key={artifact.slug}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate font-medium">{artifact.name}</p>
                <p className="text-xs text-muted-foreground">{artifact.status} · {formatDateTime(artifact.createdAt)}</p>
              </div>
              <FileText className="size-4 shrink-0 text-muted-foreground" />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{graphMetadataLabel(artifact.sourceGraphMetadata)}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button asChild size="sm" variant="outline">
                <Link to={`/reports/${artifact.slug}`}>Open report</Link>
              </Button>
              <Button asChild size="sm" variant="ghost">
                <a href={downloadReportUrl(artifact.slug)} download>
                  <Download data-icon="inline-start" />
                  Download
                </a>
              </Button>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
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

function RunStepReplayDialog({
  onClose,
  open,
  replayAvailability,
  replayStepIndex,
  runId,
}: {
  onClose: () => void;
  open: boolean;
  replayAvailability: StepReplayAvailability;
  replayStepIndex: number | undefined;
  runId: string;
}) {
  const navigate = useNavigate();
  const draftQuery = useRunStepReplayDraft(runId, replayStepIndex, { enabled: open && replayAvailability.isAvailable });
  const createStepReplay = useCreateRunStepReplay();
  const [draftTargetKey, setDraftTargetKey] = useState<string | null>(null);
  const [parametersText, setParametersText] = useState("");
  const [apiError, setApiError] = useState<string | null>(null);

  const resetLocalState = () => {
    setDraftTargetKey(null);
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

    const nextTargetKey = `${draftQuery.data.sourceRunId}:${draftQuery.data.replayStepIndex}`;
    if (draftTargetKey === nextTargetKey) {
      return;
    }

    setDraftTargetKey(nextTargetKey);
    setParametersText(formatJsonEditorValue(draftQuery.data.parameters));
    setApiError(null);
  }, [draftQuery.data, draftTargetKey, open]);

  const parametersValidation = useMemo(
    () => parseJsonRecord(parametersText || "{}", "Replay parameters JSON"),
    [parametersText],
  );
  const replayPayload = useMemo(() => {
    if (!draftQuery.data || parametersValidation.error || !parametersValidation.value) {
      return null;
    }

    return {
      parameters: parametersValidation.value,
      replayStepIndex: draftQuery.data.replayStepIndex,
    };
  }, [draftQuery.data, parametersValidation.error, parametersValidation.value]);
  const hasDraftEdits = Boolean(draftQuery.data && !areJsonValuesEqual(parametersValidation.value, draftQuery.data.parameters));
  const isSubmitDisabled = !replayPayload || createStepReplay.isPending || draftQuery.isPending || Boolean(parametersValidation.error);

  const resetToDraft = () => {
    if (!draftQuery.data) {
      return;
    }

    setDraftTargetKey(`${draftQuery.data.sourceRunId}:${draftQuery.data.replayStepIndex}`);
    setParametersText(formatJsonEditorValue(draftQuery.data.parameters));
    setApiError(null);
  };

  const handleSubmit = async () => {
    if (!replayPayload) {
      return;
    }

    setApiError(null);

    try {
      const createdRun = await createStepReplay.mutateAsync({ runId, payload: replayPayload });
      resetLocalState();
      navigate(`/runs/${createdRun.id}`);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Failed to create step replay.");
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !createStepReplay.isPending) {
          closeDialog();
        }
      }}
    >
      <DialogContent className="max-h-dvh overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <div className="flex flex-wrap items-center gap-2 pr-6">
            <DialogTitle>Step replay draft</DialogTitle>
            {replayStepIndex !== undefined ? <Badge variant="outline">Step {replayStepIndex}</Badge> : null}
            {draftQuery.data ? <Badge variant={hasDraftEdits ? "secondary" : "outline"}>{hasDraftEdits ? "Edited draft" : "Source snapshot"}</Badge> : null}
          </div>
          <DialogDescription>
            Create a new run that replays from the selected step. Edits apply only to the replay parameters; the source run remains immutable.
          </DialogDescription>
        </DialogHeader>

        {!replayAvailability.isAvailable ? (
          <Alert variant="destructive" data-testid="run-step-replay-invalid-step">
            <AlertCircle />
            <AlertTitle>Step replay unavailable</AlertTitle>
            <AlertDescription>{replayAvailability.reason ?? DEFAULT_STEP_REPLAY_UNAVAILABLE_REASON}</AlertDescription>
          </Alert>
        ) : null}

        {replayAvailability.isAvailable && draftQuery.isPending ? (
          <div className="flex items-center gap-2 rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground" data-testid="run-step-replay-loading">
            <Loader2 className="size-4 animate-spin" />
            Loading step replay draft...
          </div>
        ) : null}

        {replayAvailability.isAvailable && draftQuery.isError ? (
          <Alert variant="destructive" data-testid="run-step-replay-draft-error">
            <AlertCircle />
            <AlertTitle>Unable to load step replay draft</AlertTitle>
            <AlertDescription>{draftQuery.error instanceof Error ? draftQuery.error.message : "The step replay draft could not be loaded."}</AlertDescription>
          </Alert>
        ) : null}

        {apiError ? (
          <Alert variant="destructive" data-testid="run-step-replay-api-error">
            <AlertCircle />
            <AlertTitle>Step replay creation failed</AlertTitle>
            <AlertDescription>{apiError}</AlertDescription>
          </Alert>
        ) : null}

        {draftQuery.data ? (
          <Card className="gap-3" data-testid="run-step-replay-dialog-body">
            <CardHeader>
              <CardTitle className="text-base">Replay parameters</CardTitle>
              <CardDescription>Edit the parameter JSON that the replayed run will receive.</CardDescription>
            </CardHeader>
            <CardContent>
              <JsonEditorField
                disabled={createStepReplay.isPending}
                error={parametersValidation.error}
                id="run-step-replay-parameters-json"
                label="Step replay parameters JSON"
                onChange={(value) => {
                  setApiError(null);
                  setParametersText(value);
                }}
                rows={10}
                value={parametersText}
              />
            </CardContent>
          </Card>
        ) : null}

        <DialogFooter>
          <Button disabled={createStepReplay.isPending} onClick={closeDialog} type="button" variant="ghost">
            Cancel
          </Button>
          <Button disabled={!draftQuery.data || createStepReplay.isPending} onClick={resetToDraft} type="button" variant="outline">
            <RotateCcw data-icon="inline-start" />
            Reset draft
          </Button>
          <Button data-testid="run-step-replay-submit" disabled={isSubmitDisabled} onClick={() => void handleSubmit()} type="button">
            {createStepReplay.isPending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : null}
            Create step replay
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
            <GraphMetadataBadges metadata={invocation.graphMetadata} />
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
            { label: "Graph node", value: graphMetadataLabel(invocation.graphMetadata) },
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

function StepCard({ canReplay, onOpenReplay, step }: { canReplay: boolean; onOpenReplay: (stepIndex: number) => void; step: RunStepRead }) {
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
                  <GraphMetadataBadges metadata={step.graphMetadata} />
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

            {canReplay ? (
              <div className="flex flex-col gap-3 rounded-md border bg-muted/20 p-4 sm:flex-row sm:items-center sm:justify-between" data-testid={`runs-step-${step.index}-replay-entry`}>
                <div className="flex flex-col gap-1">
                  <p className="text-sm font-medium">Replay from this succeeded step</p>
                  <p className="text-sm text-muted-foreground">Edit replay parameters, then create a new run from step {step.index}.</p>
                </div>
                <Button onClick={() => onOpenReplay(step.index)} size="sm" type="button" variant="outline">
                  Replay step
                </Button>
              </div>
            ) : null}

            <DetailGrid
              items={[
                { label: "Step row", value: `#${step.id}` },
                { label: "Source step", value: <SourceStepLink step={step} /> },
                { label: "Graph node", value: graphMetadataLabel(step.graphMetadata) },
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
  const graphGroups = useMemo(() => groupRunGraphSteps(steps), [steps]);
  const stepReplayDialogOpen = searchParams.get("stepReplay") === "1";
  const replayStepIndexParam = searchParams.get("stepIndex");
  const rerunDialogOpen = searchParams.get("rerun") === "1";
  const replayStepIndex = useMemo(() => {
    if (replayStepIndexParam === null || replayStepIndexParam.trim() === "") {
      return undefined;
    }

    const parsed = Number(replayStepIndexParam);
    return Number.isInteger(parsed) && parsed >= 1 ? parsed : undefined;
  }, [replayStepIndexParam]);

  const openRerunDialog = () => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("rerun", "1");
      next.delete("stepReplay");
      next.delete("stepIndex");
      return next;
    });
  };

  const closeRerunDialog = () => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.delete("rerun");
      return next;
    });
  };

  const openStepReplayDialog = (stepIndex: number) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("stepReplay", "1");
      next.set("stepIndex", String(stepIndex));
      next.delete("rerun");
      return next;
    });
  };

  const closeStepReplayDialog = () => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.delete("stepReplay");
      next.delete("stepIndex");
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
  const replayAvailability = getStepReplayAvailability(run.targetKind, steps, replayStepIndex);

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
            {describeRunTarget(run.targetKind)} · {run.startedAt
              ? `Started ${formatDateTime(run.startedAt)}`
              : `Queued ${formatDateTime(run.queuedAt)}`}
            {run.finishedAt ? ` · Finished ${formatDateTime(run.finishedAt)}` : formatUnfinishedRunStatus(run.status)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {run.targetKind === "workflow" ? (
            <Button asChild data-testid="runs-detail-workflow-link" size="sm" variant="outline">
              <Link to={`/workflows/${run.targetId}`}>Back to workflow</Link>
            </Button>
          ) : null}
          {run.targetKind === "workflow" ? (
            <Button data-testid="runs-detail-rerun" onClick={openRerunDialog} size="sm" type="button" variant="outline">
              <PlayCircle data-icon="inline-start" />
              Rerun
            </Button>
          ) : null}
          <Button asChild size="sm" variant="outline">
            <Link to="/runs">Back to runs</Link>
          </Button>
        </div>
      </div>

      {run.error ? (
        <Alert variant="destructive">
          <AlertCircle />
          <AlertTitle>Run failed</AlertTitle>
          <AlertDescription>{run.error}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4">
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
          <CardContent className="flex flex-wrap gap-2 text-sm text-muted-foreground">
            <p className="min-w-0 max-w-full break-words rounded-md border bg-muted/30 px-2.5 py-1.5">Target kind: {targetKindLabel}</p>
            <p className="min-w-0 max-w-full break-words rounded-md border bg-muted/30 px-2.5 py-1.5">Target key: {run.targetKey}</p>
            <p className="min-w-0 max-w-full break-words rounded-md border bg-muted/30 px-2.5 py-1.5">Target version: {run.targetVersion}</p>
            <p className="min-w-0 max-w-full break-words rounded-md border bg-muted/30 px-2.5 py-1.5">Target id: {run.targetId}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Usage</CardTitle>
            <CardDescription>Copied, executed, and total usage.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2 text-sm text-muted-foreground">
            <p className="min-w-0 max-w-full break-words rounded-md border bg-muted/30 px-2.5 py-1.5">Total tokens: {run.totalTokens}</p>
            <p className="min-w-0 max-w-full break-words rounded-md border bg-muted/30 px-2.5 py-1.5">Total cost: {run.totalCostUsd}</p>
            <p className="min-w-0 max-w-full break-words rounded-md border bg-muted/30 px-2.5 py-1.5">Inherited tokens: {run.inheritedTokens}</p>
            <p className="min-w-0 max-w-full break-words rounded-md border bg-muted/30 px-2.5 py-1.5">Inherited cost: {run.inheritedCostUsd}</p>
            <p className="min-w-0 max-w-full break-words rounded-md border bg-muted/30 px-2.5 py-1.5">Executed tokens: {run.executedTokens}</p>
            <p className="min-w-0 max-w-full break-words rounded-md border bg-muted/30 px-2.5 py-1.5">Executed cost: {run.executedCostUsd}</p>
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

      <RunGraphSummary groups={graphGroups} />

      <MemoryArtifacts artifacts={run.memoryArtifacts ?? []} />

      <Card data-testid="runs-lineage-summary">
        <CardHeader>
          <CardTitle className="text-base">Lineage</CardTitle>
          <CardDescription>Replay and resume metadata for copied and planned execution origins.</CardDescription>
        </CardHeader>
        <CardContent>
          <DetailGrid
            items={[
              {
                label: "Source run",
                value: run.sourceRunId ? <SourceRunLink runId={run.sourceRunId}>Run #{run.sourceRunId}</SourceRunLink> : "Original run",
              },
              { label: "Lineage root", value: run.lineageRootRunId ? `Run #${run.lineageRootRunId}` : `Run #${run.id}` },
              { label: "Replay step", value: run.replayStepIndex === null ? "Not replayed" : `Step ${run.replayStepIndex}` },
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
                  canReplay={getStepReplayAvailability(run.targetKind, steps, step.index).isAvailable}
                  key={step.id}
                  onOpenReplay={openStepReplayDialog}
                  step={step}
                />
              ))}
            </Accordion>
          )}
        </CardContent>
      </Card>

      <RunRerunDialog onClose={closeRerunDialog} open={rerunDialogOpen && run.targetKind === "workflow"} runId={runId} />

      <RunStepReplayDialog
        onClose={closeStepReplayDialog}
        open={stepReplayDialogOpen}
        replayAvailability={replayAvailability}
        replayStepIndex={replayStepIndex}
        runId={runId}
      />
    </div>
  );
}
