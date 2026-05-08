import { ArrowRight, Clock, PlayCircle, SquarePen } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router";

import { useRuns } from "@/hooks/use-runs";
import { useWorkflow } from "@/hooks/use-workflows";
import { formatDateTime } from "@/lib/format";
import type { RunStatus } from "@/lib/types/run";
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

import { PlatformResourceBadges } from "../platform-resource-shared";
import { RunRerunDialog } from "../runs/rerun-dialog";

function progressForStatus(status: RunStatus): number {
  if (status === "queued") {
    return 0;
  }

  if (status === "running") {
    return 50;
  }

  return 100;
}

function formatRunTiming(status: RunStatus, queuedAt: string, startedAt: string | null, finishedAt: string | null) {
  const startLabel = startedAt ? `Started ${formatDateTime(startedAt)}` : `Queued ${formatDateTime(queuedAt)}`;
  const endLabel = finishedAt
    ? `Finished ${formatDateTime(finishedAt)}`
    : status === "queued"
      ? "Awaiting execution"
      : "Still running";

  return `${startLabel} · ${endLabel}`;
}

export function WorkflowDetailPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const navigate = useNavigate();
  const workflowQuery = useWorkflow(workflowId);
  const [rerunRunId, setRerunRunId] = useState<string | null>(null);
  const runsQuery = useRuns(
    workflowId ? { limit: 20, targetId: Number(workflowId), targetKind: "workflow" } : { limit: 20 },
    { refetchInterval: 2_000 },
  );
  const workflow = workflowQuery.data;
  const runs = useMemo(() => runsQuery.data?.items ?? [], [runsQuery.data?.items]);

  if (workflowQuery.isPending) {
    return <div className="p-4 text-sm text-muted-foreground">Loading workflow details...</div>;
  }

  if (workflowQuery.isError || !workflow) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        {workflowQuery.error instanceof Error ? workflowQuery.error.message : "Workflow not found."}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4" data-testid="workflow-detail-page">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-2">
          <div className="flex flex-col gap-1">
            <h1 className="text-xl font-semibold tracking-tight">{workflow.name}</h1>
            {workflow.description ? (
              <p className="text-sm text-muted-foreground">{workflow.description}</p>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <PlatformResourceBadges status={workflow.status} version={workflow.version} />
            <Badge variant="outline">{workflow.key}</Badge>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button data-testid="workflow-detail-edit" size="sm" variant="outline" onClick={() => navigate(`/workflows/${workflow.id}/edit`)}>
            <SquarePen data-icon="inline-start" />
            Edit Workflow
          </Button>
          <Button data-testid="workflow-detail-run" size="sm" onClick={() => navigate(`/workflows/${workflow.id}/run`)}>
            <PlayCircle data-icon="inline-start" />
            Run Now
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Workflow</CardTitle>
            <CardDescription>Saved version identity.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>Key: <span className="font-mono text-foreground">{workflow.key}</span></p>
            <p>API version: <span className="font-mono text-foreground">{workflow.manifestApiVersion}</span></p>
            <p>Updated {formatDateTime(workflow.updatedAt)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Execution Shape</CardTitle>
            <CardDescription>Planned step and budget summary.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>{workflow.steps.length} step(s)</p>
            <p>Aggregate budget {workflow.aggregateBudgetUsd}</p>
            <p>Output slot {workflow.outputSpec.slot} from step {workflow.outputSpec.stepIndex}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Runs</CardTitle>
            <CardDescription>Scoped history for this workflow.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>{runs.length} recent run(s)</p>
            <p>{runsQuery.isFetching ? "Refreshing run history..." : "History loaded from the runs monitor."}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle className="text-base">Run History</CardTitle>
            <CardDescription>Recent runs filtered to workflow #{workflow.id}.</CardDescription>
          </div>
          <Button size="sm" variant="outline" onClick={() => void runsQuery.refetch()}>
            <Clock data-icon="inline-start" />
            Refresh
          </Button>
        </CardHeader>
        <CardContent className="flex flex-col gap-3" data-testid="workflow-run-history">
          {runsQuery.isPending ? <p className="text-sm text-muted-foreground">Loading run history...</p> : null}
          {runsQuery.isError ? (
            <p className="text-sm text-muted-foreground">
              {runsQuery.error instanceof Error ? runsQuery.error.message : "Failed to load workflow runs."}
            </p>
          ) : null}
          {!runsQuery.isPending && !runsQuery.isError && runs.length === 0 ? (
            <div className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
              No runs have been launched for this workflow yet.
            </div>
          ) : null}
          {!runsQuery.isPending && !runsQuery.isError && runs.length > 0 ? (
            <div className="grid gap-3">
              {runs.map((run) => (
                <div className="rounded-lg border border-border p-3" data-testid={`workflow-run-history-row-${run.id}`} key={run.id}>
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="flex flex-col gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">Run #{run.id}</span>
                        <Badge variant="secondary">{run.status}</Badge>
                        <Badge variant="outline">{run.targetKey}@{run.targetVersion}</Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {formatRunTiming(run.status, run.queuedAt, run.startedAt, run.finishedAt)}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button data-testid={`workflow-run-history-rerun-${run.id}`} size="sm" variant="outline" onClick={() => setRerunRunId(String(run.id))}>
                        <PlayCircle data-icon="inline-start" />
                        Rerun
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => navigate(`/runs/${run.id}`)}>
                        Open Run
                        <ArrowRight data-icon="inline-end" />
                      </Button>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-col gap-2 text-sm text-muted-foreground">
                    <div className="flex items-center justify-between">
                      <span>Progress</span>
                      <span>{progressForStatus(run.status)}%</span>
                    </div>
                    <Progress value={progressForStatus(run.status)} />
                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="rounded-md border border-border p-3">Total tokens: {run.totalTokens}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {rerunRunId ? <RunRerunDialog onClose={() => setRerunRunId(null)} open runId={rerunRunId} /> : null}
    </div>
  );
}
