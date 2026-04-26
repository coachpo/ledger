import { AlertCircle } from "lucide-react";
import { useMemo } from "react";
import { Link, useParams } from "react-router";

import { useRun } from "@/hooks/use-runs";
import { formatDateTime } from "@/lib/format";
import type { RunStatus, RunStepAgentRead, RunTargetKind } from "@/lib/types/run";
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
import { Progress } from "@/components/ui/progress";

import { stringifyJson } from "../platform-resource-shared";

function progressForEntries(entries: RunStepAgentRead[]): number {
  if (entries.length === 0) {
    return 0;
  }

  const completed = entries.filter((entry) => entry.status !== "running").length;
  return Math.round((completed / entries.length) * 100);
}

function progressForRun(status: RunStatus, perStepOutputs: Record<string, RunStepAgentRead[]>): number {
  const entries = Object.values(perStepOutputs).flat();
  if (status !== "running") {
    return 100;
  }

  return progressForEntries(entries);
}

function formatTracePath(
  traceId: string | null,
  traceSpanEntries: Array<{ slot: string; spanId: string; stepKey: string }>,
): string | null {
  const segments = traceSpanEntries.map((entry) => `step ${entry.stepKey}/${entry.slot}/${entry.spanId}`);

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

export function RunsDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const runQuery = useRun(runId, { refetchInterval: 2_000 });

  const stepEntries = useMemo(
    () => Object.entries(runQuery.data?.perStepOutputs ?? {}).sort((left, right) => Number(left[0]) - Number(right[0])),
    [runQuery.data?.perStepOutputs],
  );
  const traceSpanEntries = useMemo(
    () =>
      stepEntries.flatMap(([stepKey, entries]) =>
        entries
          .filter((entry) => entry.traceSpanId)
          .map((entry) => ({ slot: entry.slot, spanId: entry.traceSpanId as string, stepKey })),
      ),
    [stepEntries],
  );

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
  const runProgress = progressForRun(run.status, run.perStepOutputs);
  const tracePath = formatTracePath(run.traceId, traceSpanEntries);
  const traceIdLabel = run.traceId ?? (traceSpanEntries.length > 0 ? "Captured through per-agent span linkage" : "No trace id recorded");
  const targetKindLabel = formatTargetKindLabel(run.targetKind);

  return (
    <div className="flex flex-col gap-4 p-4" data-testid="runs-detail-page">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold tracking-tight">Run #{run.id}</h1>
          <Badge data-testid="runs-detail-status" variant="secondary">
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

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Progress</CardTitle>
            <CardDescription>User-visible run completion.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>Run progress</span>
              <span>{runProgress}%</span>
            </div>
            <Progress value={runProgress} />
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
            <CardDescription>Total token and cost summary.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>Total tokens: {run.totalTokens}</p>
            <p>Total cost: {run.totalCostUsd}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Trace</CardTitle>
            <CardDescription>Run-level trace linkage.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>Run trace id: {traceIdLabel}</p>
            <p data-testid="runs-trace-path">
              {tracePath ? `Linkage path: ${tracePath}` : `Span links: ${traceSpanEntries.length}`}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Outcome</CardTitle>
            <CardDescription>Terminal message and timestamps.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>Created: {formatDateTime(run.createdAt)}</p>
            <p>Updated: {formatDateTime(run.updatedAt)}</p>
            <p>{run.error ?? "No terminal error recorded."}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Final output</CardTitle>
          <CardDescription>Run input and resolved final payload.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <p className="text-sm font-medium">Input</p>
            <pre className="overflow-x-auto rounded-md border bg-muted/30 p-3 text-xs">{stringifyJson(run.input)}</pre>
          </div>
          <div className="space-y-2">
            <p className="text-sm font-medium">Final output</p>
            <pre className="overflow-x-auto rounded-md border bg-muted/30 p-3 text-xs" data-testid="runs-detail-final-output">{stringifyJson(run.finalOutput)}</pre>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader id="run-trace-linkage">
          <CardTitle className="text-base">Trace linkage</CardTitle>
          <CardDescription>Run trace id plus per-agent span references.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground" data-testid="runs-trace-linkage">
          <p>Run trace id: {traceIdLabel}</p>
          {tracePath ? <p>Trace path: {tracePath}</p> : null}
          {traceSpanEntries.length === 0 ? <p>No per-agent trace spans captured.</p> : null}
          {traceSpanEntries.map((entry) => (
            <div className="rounded-md border p-3" key={`${entry.stepKey}-${entry.slot}-${entry.spanId}`}>
              <p>
                {run.traceId ? `Path ${run.traceId} / step ${entry.stepKey} / ${entry.slot}` : `Path step ${entry.stepKey} / ${entry.slot}`}
              </p>
              <p>Span id: {entry.spanId}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Per-agent detail</CardTitle>
          <CardDescription>Step-by-step status, inputs, outputs, errors, and trace links.</CardDescription>
        </CardHeader>
        <CardContent>
          <Accordion className="w-full" collapsible type="single">
            {stepEntries.map(([stepKey, entries]) => (
              <AccordionItem key={stepKey} value={`step-${stepKey}`}>
                <AccordionTrigger>
                  <div className="flex flex-wrap items-center gap-2">
                    <span>Step {stepKey}</span>
                    <Badge variant="outline">{entries.length} agent(s)</Badge>
                    <Badge variant="secondary">{progressForEntries(entries)}%</Badge>
                  </div>
                </AccordionTrigger>
                <AccordionContent>
                  <div className="flex flex-col gap-3">
                    {entries.map((entry) => (
                      <Card key={`${stepKey}-${entry.slot}`} data-testid={`runs-step-${stepKey}-slot-${entry.slot}`}>
                        <CardHeader>
                          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                            <div className="flex flex-col gap-1">
                              <CardTitle className="text-base">{entry.slot}</CardTitle>
                              <CardDescription>
                                {entry.agentKey}@{entry.agentVersion}
                              </CardDescription>
                            </div>
                            <div className="flex flex-wrap gap-2">
                              <Badge variant="secondary">{entry.status}</Badge>
                              <Badge variant="outline">Tokens {entry.tokens}</Badge>
                              <Badge variant="outline">Cost {entry.costUsd}</Badge>
                            </div>
                          </div>
                        </CardHeader>
                        <CardContent className="flex flex-col gap-4">
                          {entry.error ? (
                            <Alert variant="destructive">
                              <AlertCircle />
                              <AlertTitle>{entry.error.code}</AlertTitle>
                              <AlertDescription>{entry.error.message}</AlertDescription>
                            </Alert>
                          ) : null}
                          <div className="grid gap-4 md:grid-cols-2">
                            <div className="space-y-2">
                              <p className="text-sm font-medium">Resolved input</p>
                              <pre className="overflow-x-auto rounded-md border bg-muted/30 p-3 text-xs">{stringifyJson(entry.resolvedInput)}</pre>
                            </div>
                            <div className="space-y-2">
                              <p className="text-sm font-medium">Output</p>
                              <pre className="overflow-x-auto rounded-md border bg-muted/30 p-3 text-xs">{stringifyJson(entry.output)}</pre>
                            </div>
                          </div>
                          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                            <span>Duration: {entry.durationMs ?? "n/a"} ms</span>
                            {entry.traceSpanId ? (
                              <Button asChild size="sm" variant="outline">
                                <Link to="#run-trace-linkage">Trace link · {entry.traceSpanId}</Link>
                              </Button>
                            ) : (
                              <span>No trace span id</span>
                            )}
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </CardContent>
      </Card>
    </div>
  );
}
