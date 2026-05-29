import { ArrowRight, RefreshCcw } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";

import { EmptyStatePanel } from "@/components/shared/empty-state-panel";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useRuns } from "@/hooks/use-runs";
import { formatDateTime } from "@/lib/format";
import type {
  RunListItemRead,
  RunQueueReason,
  RunStatus,
  RunTargetKind,
} from "@/lib/types/run";

const ALL_STATUSES = "__all__";
const ALL_TARGET_KINDS = "__all_target_kinds__";

function formatTargetKindLabel(targetKind: RunTargetKind): string {
  if (targetKind === "workflowPackage") {
    return "Workflow Package";
  }
  return targetKind === "agent" ? "Agent" : "Workflow";
}

function describeRunTarget(targetKind: RunTargetKind): string {
  if (targetKind === "workflowPackage") {
    return "Captured package snapshot execution";
  }
  return targetKind === "agent"
    ? "Standalone agent execution"
    : "Multi-step workflow execution";
}

function formatQueueReasonTitle(reason: RunQueueReason): string {
  return reason === "blocked-by-package-serial-policy"
    ? "Blocked by package serial policy"
    : "Awaiting worker capacity";
}

function formatProgressValue(run: RunListItemRead): string {
  const unit =
    run.progress.totalCount === 1 ? run.progress.unit : `${run.progress.unit}s`;
  return `${run.progress.terminalCount}/${run.progress.totalCount} ${unit} · ${run.progress.percent}%`;
}

function formatOptionalDate(value: string | null, fallback: string): string {
  return value ? formatDateTime(value) : fallback;
}

function statusTone(
  status: RunStatus,
): "neutral" | "success" | "warning" | "danger" {
  if (status === "succeeded") {
    return "success";
  }
  if (status === "failed") {
    return "danger";
  }
  return status === "queued" ? "warning" : "neutral";
}

function targetIdentity(run: RunListItemRead): string {
  if (run.targetKind === "workflowPackage") {
    return `Captured snapshot: ${run.targetKey} · Package id at launch: #${run.targetId}`;
  }
  return `${formatTargetKindLabel(run.targetKind)} id: ${run.targetId}`;
}

function queueStateLabel(run: RunListItemRead): string {
  if (!run.queue) {
    return run.status === "queued"
      ? "Queued without queue details"
      : "No queue hold";
  }
  return `${run.queue.state} · ${formatQueueReasonTitle(run.queue.reason)}`;
}

function RunMonitorFilters({
  status,
  targetKind,
  onStatusChange,
  onTargetKindChange,
}: {
  status: RunStatus | undefined;
  targetKind: RunTargetKind | undefined;
  onStatusChange: (status: RunStatus | undefined) => void;
  onTargetKindChange: (targetKind: RunTargetKind | undefined) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Select
        value={targetKind ?? ALL_TARGET_KINDS}
        onValueChange={(value) =>
          onTargetKindChange(
            value === ALL_TARGET_KINDS ? undefined : (value as RunTargetKind),
          )
        }
      >
        <SelectTrigger
          aria-label="Target kind"
          className="h-8 w-[160px] text-xs"
          id="runs-target-kind"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectItem value={ALL_TARGET_KINDS}>All targets</SelectItem>
            <SelectItem value="agent">agent</SelectItem>
            <SelectItem value="workflow">workflow</SelectItem>
            <SelectItem value="workflowPackage">workflow package</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
      <Select
        value={status ?? ALL_STATUSES}
        onValueChange={(value) =>
          onStatusChange(
            value === ALL_STATUSES ? undefined : (value as RunStatus),
          )
        }
      >
        <SelectTrigger
          aria-label="Run status"
          className="h-8 w-[150px] text-xs"
          id="runs-status"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectItem value={ALL_STATUSES}>All statuses</SelectItem>
            <SelectItem value="queued">queued</SelectItem>
            <SelectItem value="running">running</SelectItem>
            <SelectItem value="succeeded">succeeded</SelectItem>
            <SelectItem value="failed">failed</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
    </div>
  );
}

function getStatusBadgeVariant(
  status: RunStatus,
): "secondary" | "outline" | "destructive" {
  if (status === "succeeded") {
    return "secondary";
  }
  return status === "failed" ? "destructive" : "outline";
}

function RunProgressCell({ run }: { run: RunListItemRead }) {
  return (
    <div
      className="flex min-w-44 flex-col gap-1.5 text-xs text-muted-foreground"
      data-testid={`runs-row-progress-${run.id}`}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium text-foreground">
          {formatProgressValue(run)}
        </span>
        <span>{run.progress.percent}%</span>
      </div>
      <Progress value={run.progress.percent} />
    </div>
  );
}

function RunQueueCell({ run }: { run: RunListItemRead }) {
  return (
    <div
      className="flex min-w-56 flex-col gap-1 whitespace-normal text-xs text-muted-foreground"
      data-testid={`runs-row-queue-${run.id}`}
    >
      <span className="font-medium text-foreground">
        {queueStateLabel(run)}
      </span>
      {run.queue ? <span>{run.queue.message}</span> : null}
      {run.queue?.blockingRunId ? (
        <span>Blocking run: #{run.queue.blockingRunId}</span>
      ) : null}
    </div>
  );
}

function RunTimestampCell({ run }: { run: RunListItemRead }) {
  return (
    <div className="flex min-w-52 flex-col gap-1 text-xs text-muted-foreground">
      <span>
        <span className="font-medium text-foreground">Queued:</span>{" "}
        {formatDateTime(run.queuedAt)}
      </span>
      <span>
        <span className="font-medium text-foreground">Started:</span>{" "}
        {formatOptionalDate(run.startedAt, "Not started")}
      </span>
      <span>
        <span className="font-medium text-foreground">Finished:</span>{" "}
        {formatOptionalDate(run.finishedAt, "Not finished")}
      </span>
    </div>
  );
}

function RunsTable({ runs }: { runs: readonly RunListItemRead[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow className="bg-muted/30 hover:bg-muted/30">
          <TableHead>Run</TableHead>
          <TableHead>Target</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Progress</TableHead>
          <TableHead>Queue</TableHead>
          <TableHead>Tokens</TableHead>
          <TableHead>Timestamps</TableHead>
          <TableHead className="text-right">Open</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {runs.map((run) => {
          const runPath = `/runs/${run.id}`;

          return (
            <TableRow key={run.id} data-testid={`runs-row-${run.id}`}>
              <TableCell className="min-w-40 whitespace-normal">
                <div className="flex flex-col gap-1">
                  <p className="font-medium text-foreground">Run #{run.id}</p>
                  <p className="break-all font-mono text-xs text-muted-foreground">
                    Trace: {run.traceId ?? "Not recorded"}
                  </p>
                </div>
              </TableCell>
              <TableCell className="min-w-64 whitespace-normal">
                <div className="flex flex-col gap-1 text-xs text-muted-foreground">
                  <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                    <Badge variant="outline">
                      {formatTargetKindLabel(run.targetKind)}
                    </Badge>
                    <span className="break-all font-mono">{run.targetKey}</span>
                  </div>
                  <span>{describeRunTarget(run.targetKind)}</span>
                  <span>{targetIdentity(run)}</span>
                </div>
              </TableCell>
              <TableCell>
                <Badge
                  data-tone={statusTone(run.status)}
                  variant={getStatusBadgeVariant(run.status)}
                >
                  {run.status}
                </Badge>
              </TableCell>
              <TableCell className="whitespace-normal">
                <RunProgressCell run={run} />
              </TableCell>
              <TableCell className="whitespace-normal">
                <RunQueueCell run={run} />
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {run.totalTokens.toLocaleString()}
              </TableCell>
              <TableCell className="whitespace-normal">
                <RunTimestampCell run={run} />
              </TableCell>
              <TableCell>
                <div className="flex justify-end">
                  <Button
                    asChild
                    data-testid={`runs-row-action-${run.id}`}
                    size="sm"
                    variant="outline"
                  >
                    <Link aria-label={`Open run #${run.id}`} to={runPath}>
                      Open
                      <ArrowRight data-icon="inline-end" />
                    </Link>
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

export function RunsListPage() {
  const [targetKind, setTargetKind] = useState<RunTargetKind | undefined>(
    undefined,
  );
  const [targetKey, setTargetKey] = useState("");
  const [status, setStatus] = useState<RunStatus | undefined>(undefined);
  const normalizedTargetKey = targetKey.trim();
  const appliedTargetKey =
    targetKind && normalizedTargetKey ? normalizedTargetKey : undefined;
  const targetKeyFilterValue = normalizedTargetKey
    ? targetKind
      ? normalizedTargetKey
      : `${normalizedTargetKey} · select target kind to apply`
    : "Any key";
  const runsQuery = useRuns(
    {
      limit: 50,
      targetKind,
      targetKey: appliedTargetKey,
      status,
    },
    { refetchInterval: 2_000 },
  );
  const runs = useMemo(
    () => runsQuery.data?.items ?? [],
    [runsQuery.data?.items],
  );
  const activeFilterCount = [targetKind, normalizedTargetKey, status].filter(
    Boolean,
  ).length;
  const clearFilters = () => {
    setTargetKind(undefined);
    setTargetKey("");
    setStatus(undefined);
  };

  return (
    <InventoryPageShell
      pageContext={{
        description: "Monitor workflow runs.",
        layout: "toolbar",
        title: "Runs",
      }}
      testId="runs-list-page"
      toolbar={{
        actions: (
          <Button
            className="cursor-pointer"
            size="sm"
            variant="outline"
            onClick={() => void runsQuery.refetch()}
          >
            <RefreshCcw data-icon="inline-start" />
            Refresh
          </Button>
        ),
        filters: (
          <RunMonitorFilters
            status={status}
            targetKind={targetKind}
            onStatusChange={setStatus}
            onTargetKindChange={setTargetKind}
          />
        ),
        resultSummary: `${runs.length} recent ${runs.length === 1 ? "run" : "runs"} returned`,
        search: {
          id: "runs-target-key",
          label: "Target key",
          placeholder: "Filter by package, workflow, or agent key...",
          testId: "runs-target-key-filter",
          value: targetKey,
          onChange: setTargetKey,
        },
      }}
      filterBar={{
        testId: "runs-monitor-filter-card",
        summary:
          "Polling every 2 seconds while queued or running rows are present.",
        items: [
          {
            active: Boolean(targetKind),
            id: "target-kind",
            label: "Target kind",
            value: targetKind
              ? formatTargetKindLabel(targetKind)
              : "All targets",
            onClear: targetKind ? () => setTargetKind(undefined) : undefined,
          },
          {
            active: Boolean(normalizedTargetKey),
            id: "target-key",
            label: "Target key",
            value: targetKeyFilterValue,
            onClear: normalizedTargetKey ? () => setTargetKey("") : undefined,
          },
          {
            active: Boolean(status),
            id: "status",
            label: "Status",
            value: status ?? "All statuses",
            onClear: status ? () => setStatus(undefined) : undefined,
          },
        ],
        onClearAll: activeFilterCount > 0 ? clearFilters : undefined,
      }}
    >
      {runsQuery.isPending ? (
        <EmptyStatePanel
          title="Loading runs"
          description="Reading the latest run monitor state from the backend."
        />
      ) : null}

      {runsQuery.isError ? (
        <EmptyStatePanel
          tone="danger"
          title="Failed to load runs"
          description={
            runsQuery.error instanceof Error
              ? runsQuery.error.message
              : "Failed to load runs."
          }
        />
      ) : null}

      {!runsQuery.isPending && !runsQuery.isError && runs.length === 0 ? (
        <EmptyStatePanel
          title="No runs match the current monitor filters"
          description="Adjust target kind, target key, or status to widen the polling window."
        />
      ) : null}

      {!runsQuery.isPending && !runsQuery.isError && runs.length > 0 ? (
        <RunsTable runs={runs} />
      ) : null}
    </InventoryPageShell>
  );
}
