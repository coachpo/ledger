import { useMemo } from "react";
import { useParams } from "react-router";

import { useStudioRun, useStudioRunArtifact, useStudioRunTrace } from "@/hooks/use-studio";
import { formatDateTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

import { stringifyJson } from "../shared-utils";

export function StudioRunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const runQuery = useStudioRun(runId);
  const artifactQuery = useStudioRunArtifact(runId);
  const traceQuery = useStudioRunTrace(runId);

  const recentTraceEvents = useMemo(
    () => (traceQuery.data?.items ?? []).slice(-5).reverse(),
    [traceQuery.data?.items],
  );

  if (!runId) {
    return <div className="p-4 text-sm text-muted-foreground">Studio run route is missing an id.</div>;
  }

  if (runQuery.isPending) {
    return <div className="p-4 text-sm text-muted-foreground">Loading Studio run...</div>;
  }

  if (runQuery.isError || !runQuery.data) {
    return <div className="p-4 text-sm text-muted-foreground">{runQuery.error instanceof Error ? runQuery.error.message : "Studio run not found."}</div>;
  }

  const run = runQuery.data;
  const artifact = artifactQuery.data;

  return (
    <div className="space-y-4 p-4" data-testid="studio-run-detail">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold tracking-tight">Studio Run #{run.runId}</h1>
          <Badge data-testid="studio-run-status-badge" variant="secondary">{run.status}</Badge>
        </div>
        <p className="text-sm text-muted-foreground">Workflow {run.workflowSpecKey ?? "n/a"} · Created {formatDateTime(run.createdAt)}</p>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Card data-testid="studio-run-summary-card">
          <CardHeader>
            <CardTitle className="text-base">Run summary</CardTitle>
            <CardDescription>Caller, execution kind, and pending approvals.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>Caller type: {run.callerType}</p>
            <p>Execution kind: {run.executionKind}</p>
            <p>Pending approvals: {run.pendingApprovalIds.length}</p>
            <p>Updated: {formatDateTime(run.updatedAt)}</p>
          </CardContent>
        </Card>

        <Card data-testid="studio-run-trace-summary-card">
          <CardHeader>
            <CardTitle className="text-base">Trace summary</CardTitle>
            <CardDescription>High-level event totals captured for this run.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>Events: {run.traceSummary.eventCount}</p>
            <p>Tool calls: {run.traceSummary.toolCallCount}</p>
            <p>Warnings: {run.traceSummary.warningCount}</p>
          </CardContent>
        </Card>

        <Card data-testid="studio-run-approval-summary-card">
          <CardHeader>
            <CardTitle className="text-base">Approval summary</CardTitle>
            <CardDescription>Current approval states for this Studio run.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>Total: {run.approvalSummary.totalCount}</p>
            <p>Pending: {run.approvalSummary.pendingCount}</p>
            <p>Approved: {run.approvalSummary.approvedCount}</p>
          </CardContent>
        </Card>
      </div>

      <Card data-testid="studio-run-artifact-card">
        <CardHeader>
          <CardTitle className="text-base">Artifact snapshot</CardTitle>
          <CardDescription>Final output, resolved profiles, capabilities, and prompt payloads.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3 text-sm">
            <div className="rounded-md border p-3">Resolved personas: {artifact?.resolvedPersonaProfileRefs.length ?? 0}</div>
            <div className="rounded-md border p-3">Resolved capabilities: {artifact?.resolvedCapabilities.length ?? 0}</div>
            <div className="rounded-md border p-3">Prompt report slug: {artifact?.promptReportSlug ?? "None"}</div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <p className="text-sm font-medium">Final output</p>
              <pre className="overflow-x-auto rounded-md border bg-muted/30 p-3 text-xs" data-testid="studio-run-final-output">
                {stringifyJson(run.finalOutput)}
              </pre>
            </div>
            <div className="space-y-2">
              <p className="text-sm font-medium">Execution context</p>
              <pre className="overflow-x-auto rounded-md border bg-muted/30 p-3 text-xs">
                {artifact?.executionContextBody ?? "No execution context captured."}
              </pre>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card data-testid="studio-run-trace-card">
        <CardHeader>
          <CardTitle className="text-base">Recent trace events</CardTitle>
          <CardDescription>Last five Studio trace events for this run.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {traceQuery.isPending ? <p className="text-sm text-muted-foreground">Loading trace events...</p> : null}
          {!traceQuery.isPending && recentTraceEvents.length === 0 ? <p className="text-sm text-muted-foreground">No trace events recorded.</p> : null}
          {recentTraceEvents.map((event) => (
            <div className="rounded-md border p-3" data-testid={`studio-run-trace-event-${event.eventIndex}`} key={event.eventIndex}>
              <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
                <span>{event.eventType}</span>
                <Badge variant="outline">#{event.eventIndex}</Badge>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{formatDateTime(event.createdAt)}</p>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
