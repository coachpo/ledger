import { ArrowRight, RefreshCcw } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";

import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import { ResourceTableFrame } from "@/components/shared/resource-table-frame";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import type { RunListItemRead, RunQueueReason, RunStatus } from "@/lib/types/run";

const ALL_STATUSES = "__all__";

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
  if (status === "cancelled") {
    return "neutral";
  }
  return status === "queued" ? "warning" : "neutral";
}

function targetSearchLabel(): string {
  return "Package key";
}

function targetSearchPlaceholder(): string {
  return "Filter by workflow package key...";
}

function isDefined<T>(value: T | null): value is T {
  return value !== null;
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
  workflowKey,
  onStatusChange,
  onWorkflowKeyChange,
}: {
  status: RunStatus | undefined;
  workflowKey: string;
  onStatusChange: (status: RunStatus | undefined) => void;
  onWorkflowKeyChange: (workflowKey: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
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
            <SelectItem value="cancelled">cancelled</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
      <Input
        aria-label="Workflow key"
        className="h-8 w-[220px] text-xs"
        placeholder="Filter by workflow key..."
        value={workflowKey}
        onChange={(event) => onWorkflowKeyChange(event.target.value)}
      />
    </div>
  );
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

export function RunsTable({ runs }: { runs: readonly RunListItemRead[] }) {
  return (
    <ResourceTableFrame>
      <Table>
        <TableHeader>
          <TableRow className="bg-ui-surface-grouped/80 hover:bg-ui-surface-grouped/80">
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
                    <span>
                      Package key:{" "}
                      <span className="break-all font-mono text-foreground">
                        {run.targetKey}
                      </span>
                    </span>
                    {run.workflowKey ? (
                      <span>
                        Workflow key:{" "}
                        <span className="break-all font-mono text-foreground">
                          {run.workflowKey}
                        </span>
                      </span>
                    ) : null}
                  </div>
                </TableCell>
                <TableCell>
                  <ResourceStatusBadge
                    label={run.status}
                    tone={statusTone(run.status)}
                  />
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
    </ResourceTableFrame>
  );
}

export function RunsListPage() {
  const [workflowPackageKey, setWorkflowPackageKey] = useState("");
  const [workflowKey, setWorkflowKey] = useState("");
  const [status, setStatus] = useState<RunStatus | undefined>(undefined);
  const normalizedWorkflowPackageKey = workflowPackageKey.trim();
  const normalizedWorkflowKey = workflowKey.trim();
  const appliedWorkflowPackageKey = normalizedWorkflowPackageKey || undefined;
  const appliedWorkflowKey = normalizedWorkflowKey || undefined;
  const runsQuery = useRuns(
    {
      limit: 50,
      workflowPackageKey: appliedWorkflowPackageKey,
      workflowKey: appliedWorkflowKey,
      status,
    },
    { refetchInterval: 2_000 },
  );
  const runs = useMemo(
    () => runsQuery.data?.items ?? [],
    [runsQuery.data?.items],
  );
  const activeFilterItems = [
    appliedWorkflowPackageKey
      ? {
          active: true,
          clearLabel: "Clear package key filter",
          id: "workflow-package-key",
          label: "Package key",
          value: appliedWorkflowPackageKey,
          onClear: () => setWorkflowPackageKey(""),
        }
      : null,
    appliedWorkflowKey
      ? {
          active: true,
          clearLabel: "Clear workflow key filter",
          id: "workflow-key",
          label: "Workflow key",
          value: appliedWorkflowKey,
          onClear: () => setWorkflowKey(""),
        }
      : null,
    status
      ? {
          active: true,
          clearLabel: "Clear run status filter",
          id: "status",
          label: "Status",
          value: status,
          onClear: () => setStatus(undefined),
        }
      : null,
  ].filter(isDefined);
  return (
    <InventoryPageShell
      filterBar={
        activeFilterItems.length > 0
          ? {
              items: activeFilterItems,
              onClearAll: () => {
                setWorkflowPackageKey("");
                setWorkflowKey("");
                setStatus(undefined);
              },
              testId: "runs-active-filters",
            }
          : null
      }
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
            workflowKey={workflowKey}
            onStatusChange={setStatus}
            onWorkflowKeyChange={setWorkflowKey}
          />
        ),
        resultSummary: `${runs.length} recent ${runs.length === 1 ? "run" : "runs"} returned`,
        search: {
          id: "runs-target-key",
          label: targetSearchLabel(),
          placeholder: targetSearchPlaceholder(),
          testId: "runs-target-key-filter",
          value: workflowPackageKey,
          onChange: setWorkflowPackageKey,
        },
      }}
    >
      {runsQuery.isPending ? (
        <InventoryStatePanel
          description="Reading the latest run monitor state from the backend."
          testId="runs-loading-state"
          title="Loading runs"
        />
      ) : null}

      {runsQuery.isError ? (
        <InventoryStatePanel
          description={
            runsQuery.error instanceof Error
              ? runsQuery.error.message
              : "Failed to load runs."
          }
          testId="runs-error-state"
          title="Failed to load runs"
          tone="danger"
        />
      ) : null}

      {!runsQuery.isPending && !runsQuery.isError && runs.length === 0 ? (
        <InventoryStatePanel
          description="Adjust package key, workflow key, or status to widen the polling window."
          testId="runs-empty-state"
          title="No runs match the current monitor filters"
        />
      ) : null}

      {!runsQuery.isPending && !runsQuery.isError && runs.length > 0 ? (
        <RunsTable runs={runs} />
      ) : null}
    </InventoryPageShell>
  );
}
