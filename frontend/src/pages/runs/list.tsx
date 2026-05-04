import { ArrowRight, RefreshCcw } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router";

import { useRuns } from "@/hooks/use-runs";
import { formatDateTime } from "@/lib/format";
import type { RunStatus, RunTargetKind } from "@/lib/types/run";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const ALL_STATUSES = "__all__";
const ALL_TARGET_KINDS = "__all_target_kinds__";

function formatTargetKindLabel(targetKind: RunTargetKind): string {
  return targetKind === "agent" ? "Agent" : "Workflow";
}

function describeRunTarget(targetKind: RunTargetKind): string {
  return targetKind === "agent" ? "Standalone agent execution" : "Multi-step workflow execution";
}

function progressForStatus(status: RunStatus): number {
  if (status === "queued") {
    return 0;
  }

  if (status === "running") {
    return 50;
  }

  return 100;
}

function formatUnfinishedRunStatus(status: RunStatus): string {
  return status === "queued" ? " · Awaiting execution" : " · Still running";
}

export function RunsListPage() {
  const navigate = useNavigate();
  const [targetKind, setTargetKind] = useState<RunTargetKind | undefined>(undefined);
  const [targetKey, setTargetKey] = useState("");
  const [status, setStatus] = useState<RunStatus | undefined>(undefined);
  const runsQuery = useRuns(
    {
      limit: 50,
      targetKind,
      targetKey: targetKey.trim() || undefined,
      status,
    },
    { refetchInterval: 2_000 },
  );
  const runs = useMemo(() => runsQuery.data?.items ?? [], [runsQuery.data?.items]);

  return (
    <div className="flex flex-col gap-4 p-4" data-testid="runs-list-page">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-semibold tracking-tight">Runs</h1>
          <p className="text-sm text-muted-foreground">
            Monitor recent agent and workflow executions with live status, target identity,
            total token/cost summaries, and direct links into per-run detail.
          </p>
        </div>
        <Button
          className="cursor-pointer"
          size="sm"
          variant="outline"
          onClick={() => void runsQuery.refetch()}
        >
          <RefreshCcw data-icon="inline-start" />
          Refresh
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Filters</CardTitle>
          <CardDescription>
            Filter the monitor by target kind, target key, or terminal status.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          <div className="flex flex-col gap-2">
            <Label>Target kind</Label>
            <Select
              value={targetKind ?? ALL_TARGET_KINDS}
              onValueChange={(value) =>
                setTargetKind(value === ALL_TARGET_KINDS ? undefined : (value as RunTargetKind))
              }
            >
              <SelectTrigger aria-label="Target kind">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value={ALL_TARGET_KINDS}>All targets</SelectItem>
                  <SelectItem value="agent">agent</SelectItem>
                  <SelectItem value="workflow">workflow</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="runs-target-key">Target key</Label>
            <Input
              id="runs-target-key"
              aria-label="Target key"
              placeholder="market_review or macro_agent"
              value={targetKey}
              onChange={(event) => setTargetKey(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label>Run status</Label>
            <Select
              value={status ?? ALL_STATUSES}
              onValueChange={(value) =>
                setStatus(value === ALL_STATUSES ? undefined : (value as RunStatus))
              }
            >
              <SelectTrigger aria-label="Run status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value={ALL_STATUSES}>All statuses</SelectItem>
                  <SelectItem value="running">running</SelectItem>
                  <SelectItem value="succeeded">succeeded</SelectItem>
                  <SelectItem value="failed">failed</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {runsQuery.isPending ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Loading runs...
          </CardContent>
        </Card>
      ) : null}

      {runsQuery.isError ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            {runsQuery.error instanceof Error ? runsQuery.error.message : "Failed to load runs."}
          </CardContent>
        </Card>
      ) : null}

      {!runsQuery.isPending && !runsQuery.isError && runs.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No runs match the current filter set.
          </CardContent>
        </Card>
      ) : null}

      {!runsQuery.isPending && !runsQuery.isError && runs.length > 0 ? (
        <div className="grid gap-2 sm:gap-3">
          {runs.map((run) => (
            <Card key={run.id} data-testid={`runs-row-${run.id}`} className="overflow-hidden">
              <CardContent className="p-3 sm:p-4">
                <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 flex-1 space-y-3">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <CardTitle className="text-base">Run #{run.id}</CardTitle>
                        <Badge variant="secondary">{run.status}</Badge>
                        <Badge variant="outline">{formatTargetKindLabel(run.targetKind)}</Badge>
                        <Badge variant="outline">{run.targetKey}@{run.targetVersion}</Badge>
                      </div>
                      <CardDescription className="break-words text-sm">
                        {describeRunTarget(run.targetKind)} · {run.startedAt
                          ? `Started ${formatDateTime(run.startedAt)}`
                          : `Queued ${formatDateTime(run.queuedAt)}`}
                        {run.finishedAt
                          ? ` · Finished ${formatDateTime(run.finishedAt)}`
                          : formatUnfinishedRunStatus(run.status)}
                      </CardDescription>
                      <p className="text-sm text-muted-foreground">
                        Target {formatTargetKindLabel(run.targetKind).toLowerCase()} #{run.targetId}
                      </p>
                    </div>

                    <div className="grid gap-3 lg:grid-cols-[minmax(12rem,0.75fr)_minmax(0,1fr)]">
                      <div className="rounded-md border border-border bg-muted/20 p-3">
                        <div className="flex items-center justify-between text-sm text-muted-foreground">
                          <span>Progress</span>
                          <span>{progressForStatus(run.status)}%</span>
                        </div>
                        <Progress className="mt-2" value={progressForStatus(run.status)} />
                      </div>
                      <div className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-3">
                        <div className="rounded-md border border-border bg-muted/20 px-3 py-2">
                          {formatTargetKindLabel(run.targetKind)} id: {run.targetId}
                        </div>
                        <div className="rounded-md border border-border bg-muted/20 px-3 py-2">
                          Total tokens: {run.totalTokens}
                        </div>
                        <div className="rounded-md border border-border bg-muted/20 px-3 py-2">
                          Total cost: {run.totalCostUsd}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="flex w-full flex-wrap gap-2 sm:w-auto sm:shrink-0 sm:justify-end">
                    <Button
                      className="w-full cursor-pointer sm:w-auto"
                      size="sm"
                      variant="outline"
                      onClick={() => navigate(`/runs/${run.id}`)}
                    >
                      Open Run
                      <ArrowRight data-icon="inline-end" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </div>
  );
}
