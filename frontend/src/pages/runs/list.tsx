import { ArrowRight, RefreshCcw } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";

import { EmptyStatePanel } from "@/components/shared/empty-state-panel";
import { EvidenceCluster } from "@/components/shared/evidence-cluster";
import { ResourceFilterBar } from "@/components/shared/resource-filter-bar";
import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import { ResourceToolbar } from "@/components/shared/resource-toolbar";
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
import { useRuns } from "@/hooks/use-runs";
import { formatDateTime } from "@/lib/format";
import type {
  RunListItemRead,
  RunQueueReason,
  RunStatus,
  RunTargetKind,
} from "@/lib/types/run";

import {
  PlatformResourceCard,
  PlatformResourceList,
} from "../platform-resource-shared";

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
  const unit = run.progress.totalCount === 1 ? run.progress.unit : `${run.progress.unit}s`;
  return `${run.progress.terminalCount}/${run.progress.totalCount} ${unit} · ${run.progress.percent}%`;
}

function formatOptionalDate(value: string | null, fallback: string): string {
  return value ? formatDateTime(value) : fallback;
}

function statusTone(status: RunStatus): "neutral" | "success" | "warning" | "danger" {
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
    return run.status === "queued" ? "Queued without queue details" : "No queue hold";
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
          onStatusChange(value === ALL_STATUSES ? undefined : (value as RunStatus))
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

function RunQueueNotice({ run }: { run: RunListItemRead }) {
  if (run.status !== "queued" || !run.queue) {
    return null;
  }

  return (
    <div
      className="rounded-md border bg-muted/20 p-2"
      data-testid={`runs-row-queue-${run.id}`}
    >
      <p className="font-medium text-foreground">
        {formatQueueReasonTitle(run.queue.reason)}
      </p>
      <p>{run.queue.message}</p>
      {run.queue.blockingRunId ? (
        <p className="mt-1">Blocking run: #{run.queue.blockingRunId}</p>
      ) : null}
    </div>
  );
}

function RunProgressBar({ run }: { run: RunListItemRead }) {
  return (
    <div
      className="flex min-w-0 flex-col gap-1"
      data-testid={`runs-row-progress-${run.id}`}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium text-foreground">Progress</span>
        <span>{run.progress.percent}%</span>
      </div>
      <Progress value={run.progress.percent} />
    </div>
  );
}

function RunEvidence({ run }: { run: RunListItemRead }) {
  return (
    <EvidenceCluster
      layout="grid"
      items={[
        {
          label: "Progress",
          value: formatProgressValue(run),
          description: `Backend progress unit: ${run.progress.unit}`,
        },
        {
          label: "Tokens",
          value: run.totalTokens.toLocaleString(),
          description: "Total tokens reported by the run read model",
        },
        {
          label: "Queued",
          value: formatDateTime(run.queuedAt),
          description: "Queue timestamp from backend state",
        },
        {
          label: "Started",
          value: formatOptionalDate(run.startedAt, "Not started"),
          description: "Execution start timestamp",
        },
        {
          label: "Finished",
          value: formatOptionalDate(run.finishedAt, "Not finished"),
          description: "Terminal timestamp when available",
        },
      ]}
    />
  );
}

function RunStatusStrip({ run }: { run: RunListItemRead }) {
  return (
    <ResourceStatusStrip
      density="compact"
      items={[
        { label: "Status", value: run.status, tone: statusTone(run.status) },
        { label: "Progress", value: `${run.progress.percent}%` },
        { label: "Tokens", value: run.totalTokens.toLocaleString() },
        { label: "Queue", value: queueStateLabel(run) },
      ]}
    />
  );
}

function RunMonitorRow({ run }: { run: RunListItemRead }) {
  const runPath = `/runs/${run.id}`;

  return (
    <PlatformResourceCard
      density="compactPlus"
      testId={`runs-row-${run.id}`}
      title={`Run #${run.id}`}
      subtitle={<span className="font-mono">{run.targetKey}</span>}
      description={describeRunTarget(run.targetKind)}
      badges={
        <>
          <Badge variant="secondary">{run.status}</Badge>
          <Badge variant="outline">{formatTargetKindLabel(run.targetKind)}</Badge>
          <Badge variant="outline">{run.targetKey}</Badge>
        </>
      }
      primaryAction={{
        kind: "link",
        label: `Open run #${run.id}`,
        testId: `runs-row-primary-${run.id}`,
        to: runPath,
      }}
      metadata={
        <div className="grid min-w-0 gap-x-5 gap-y-1.5 sm:grid-cols-2">
          <div className="min-w-0">
            <span className="font-medium text-foreground">Target:</span>{" "}
            <span className="break-words">{targetIdentity(run)}</span>
          </div>
          <div className="min-w-0">
            <span className="font-medium text-foreground">Trace:</span>{" "}
            <span className="break-all">{run.traceId ?? "Not recorded"}</span>
          </div>
        </div>
      }
      statusStrip={<RunStatusStrip run={run} />}
      evidence={<RunEvidence run={run} />}
      footer={
        <div className="flex flex-col gap-2">
          <RunQueueNotice run={run} />
          <RunProgressBar run={run} />
        </div>
      }
      actions={
        <Button
          asChild
          className="w-full cursor-pointer sm:w-auto"
          data-testid={`runs-row-action-${run.id}`}
          size="sm"
        >
          <Link to={runPath}>
            Open Run
            <ArrowRight data-icon="inline-end" />
          </Link>
        </Button>
      }
    />
  );
}

export function RunsListPage() {
  const [targetKind, setTargetKind] = useState<RunTargetKind | undefined>(
    undefined,
  );
  const [targetKey, setTargetKey] = useState("");
  const [status, setStatus] = useState<RunStatus | undefined>(undefined);
  const normalizedTargetKey = targetKey.trim();
  const appliedTargetKey = targetKind && normalizedTargetKey ? normalizedTargetKey : undefined;
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
    <div className="flex flex-col gap-4 p-4" data-testid="runs-list-page">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-semibold tracking-tight">Runs</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Live monitor for recent agent and workflow package executions with
            route-owned polling, backend progress, queue state, token usage, and
            direct run inspection.
          </p>
        </div>
      </div>

      <ResourceToolbar
        actions={
          <Button
            className="cursor-pointer"
            size="sm"
            variant="outline"
            onClick={() => void runsQuery.refetch()}
          >
            <RefreshCcw data-icon="inline-start" />
            Refresh
          </Button>
        }
        filters={
          <RunMonitorFilters
            status={status}
            targetKind={targetKind}
            onStatusChange={setStatus}
            onTargetKindChange={setTargetKind}
          />
        }
        resultSummary={`${runs.length} recent ${runs.length === 1 ? "run" : "runs"} returned`}
        search={{
          id: "runs-target-key",
          label: "Target key",
          placeholder: "Filter by package, workflow, or agent key...",
          testId: "runs-target-key-filter",
          value: targetKey,
          onChange: setTargetKey,
        }}
      />

      <ResourceFilterBar
        testId="runs-monitor-filter-card"
        summary="Polling every 2 seconds while queued or running rows are present."
        items={[
          {
            active: Boolean(targetKind),
            id: "target-kind",
            label: "Target kind",
            value: targetKind ? formatTargetKindLabel(targetKind) : "All targets",
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
        ]}
        onClearAll={activeFilterCount > 0 ? clearFilters : undefined}
      />

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
        <PlatformResourceList>
          {runs.map((run) => (
            <RunMonitorRow key={run.id} run={run} />
          ))}
        </PlatformResourceList>
      ) : null}
    </div>
  );
}
