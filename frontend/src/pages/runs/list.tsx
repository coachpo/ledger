import { ArrowRight, RefreshCcw } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router";

import { useRuns } from "@/hooks/use-runs";
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

function progressForStatus(status: RunStatus): number {
  if (status === "running") {
    return 50;
  }

  return 100;
}

export function RunsListPage() {
  const navigate = useNavigate();
  const [workflowKey, setWorkflowKey] = useState("");
  const [status, setStatus] = useState<RunStatus | undefined>(undefined);
  const runsQuery = useRuns(
    {
      limit: 50,
      status,
      workflowKey: workflowKey.trim() || undefined,
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
            Monitor recent workflow executions with live status, total token/cost summaries,
            and direct links into per-run detail.
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={() => void runsQuery.refetch()}>
          <RefreshCcw data-icon="inline-start" />
          Refresh
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Filters</CardTitle>
          <CardDescription>Filter the monitor by workflow key or terminal status.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor="runs-workflow-key">Workflow key</Label>
            <Input
              id="runs-workflow-key"
              aria-label="Workflow key"
              placeholder="market_review"
              value={workflowKey}
              onChange={(event) => setWorkflowKey(event.target.value)}
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
        <div className="grid gap-3">
          {runs.map((run) => (
            <Card key={run.id} data-testid={`runs-row-${run.id}`}>
              <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="flex flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <CardTitle className="text-base">Run #{run.id}</CardTitle>
                    <Badge variant="secondary">{run.status}</Badge>
                    <Badge variant="outline">
                      {run.workflowKey}@{run.workflowVersion}
                    </Badge>
                  </div>
                  <CardDescription>
                    Started {formatDateTime(run.startedAt)}
                    {run.finishedAt ? ` · Finished ${formatDateTime(run.finishedAt)}` : " · Still running"}
                  </CardDescription>
                </div>
                <Button size="sm" variant="outline" onClick={() => navigate(`/runs/${run.id}`)}>
                  Open Run
                  <ArrowRight data-icon="inline-end" />
                </Button>
              </CardHeader>
              <CardContent className="flex flex-col gap-4 text-sm text-muted-foreground">
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <span>Progress</span>
                    <span>{progressForStatus(run.status)}%</span>
                  </div>
                  <Progress value={progressForStatus(run.status)} />
                </div>
                <div className="grid gap-3 md:grid-cols-3">
                  <div className="rounded-md border p-3">Workflow id: {run.workflowId}</div>
                  <div className="rounded-md border p-3">Total tokens: {run.totalTokens}</div>
                  <div className="rounded-md border p-3">Total cost: {run.totalCostUsd}</div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </div>
  );
}
