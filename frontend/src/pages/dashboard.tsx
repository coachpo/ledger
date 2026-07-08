import { RefreshCw, TriangleAlert } from "lucide-react";
import { useMemo } from "react";

import { EmptyStatePanel } from "@/components/shared/empty-state-panel";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import { Button } from "@/components/ui/button";
import { useRuns } from "@/hooks/use-runs";
import { RunsTable } from "@/pages/runs/list";
import type { RunStatus } from "@/lib/types/run";

const RUN_STATUSES: RunStatus[] = [
  "queued",
  "running",
  "succeeded",
  "failed",
  "cancelled",
];

function DashboardHeader() {
  return (
    <PageContextBar
      description="Recent workflow runs."
      layout="toolbar"
      title="Dashboard"
    />
  );
}

export function Dashboard() {
  const runsQuery = useRuns({ limit: 10 }, { refetchInterval: 2_000 });
  const runs = useMemo(() => runsQuery.data?.items ?? [], [runsQuery.data?.items]);
  const statusCounts = useMemo(
    () =>
      RUN_STATUSES.map((status) => ({
        count: runs.filter((run) => run.status === status).length,
        status,
      })),
    [runs],
  );

  if (runsQuery.isPending) {
    return (
      <div className="flex max-w-7xl flex-col gap-4 p-4" data-testid="dashboard-page">
        <DashboardHeader />
      </div>
    );
  }

  if (runsQuery.isError) {
    return (
      <div className="flex max-w-7xl flex-col gap-4 p-4" data-testid="dashboard-page">
        <DashboardHeader />

        <EmptyStatePanel
          action={
            <Button
              className="cursor-pointer"
              disabled={runsQuery.isFetching}
              onClick={() => void runsQuery.refetch()}
              size="sm"
              variant="outline"
            >
              <RefreshCw data-icon="inline-start" />
              {runsQuery.isFetching ? "Retrying" : "Retry"}
            </Button>
          }
          description={
            runsQuery.error instanceof Error
              ? runsQuery.error.message
              : "Check the backend connection and try again."
          }
          icon={<TriangleAlert className="size-4 text-destructive" />}
          title="Unable to load the dashboard summary."
          tone="danger"
        />
      </div>
    );
  }

  return (
    <div className="flex max-w-7xl flex-col gap-4 p-4" data-testid="dashboard-page">
      <DashboardHeader />
      <div className="grid gap-2 sm:grid-cols-5">
        {statusCounts.map(({ count, status }) => (
          <div
            className="flex items-center justify-between gap-3 rounded-md border border-border bg-card px-3 py-2"
            data-testid={`dashboard-status-${status}`}
            key={status}
          >
            <ResourceStatusBadge label={status} tone={statusTone(status)} />
            <span className="font-mono text-lg font-semibold">{count}</span>
          </div>
        ))}
      </div>
      {runs.length > 0 ? (
        <RunsTable runs={runs} />
      ) : (
        <EmptyStatePanel
          description="Launch or schedule a Workflow Package to create run history."
          title="No recent runs"
        />
      )}
    </div>
  );
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
