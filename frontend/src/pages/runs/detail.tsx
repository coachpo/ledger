import { AlertCircle, PlayCircle, StopCircle, Timer } from "lucide-react";
import { useMemo } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";

import { PageContextBar } from "@/components/shared/page-context-bar";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useCancelRun, useRun } from "@/hooks/use-runs";
import { formatDateTime } from "@/lib/format";

import {
  formatQueueReasonTitle,
  formatTargetKindLabel,
  formatUnfinishedRunStatus,
  isTerminalStatus,
  sortedInvocations,
  sortedOperationInvocations,
} from "./detail-helpers";
import {
  resolveRunDetailTab,
  withRunDetailTab,
  type RunDetailTabKey,
} from "./detail-tabs";
import { RunDetailSectionStack } from "./detail-sections";
import {
  resolveRunInspectionState,
  serializeInspectionTarget,
  type RunInspectionMode,
  type RunInspectionPane,
  type RunInspectionTarget,
} from "./inspection-state";
import { RunRerunDialog } from "./rerun-dialog";

export function RunsDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const runQuery = useRun(runId, { refetchInterval: 2_000 });
  const cancelRun = useCancelRun();

  const steps = useMemo(
    () =>
      [...(runQuery.data?.steps ?? [])].sort(
        (left, right) => left.index - right.index,
      ),
    [runQuery.data?.steps],
  );
  const allInvocations = useMemo(
    () =>
      steps.flatMap((step) => [
        ...sortedInvocations(step.invocations),
        ...sortedOperationInvocations(step.operationInvocations),
      ]),
    [steps],
  );
  const traceSpanEntries = useMemo(
    () =>
      steps.flatMap((step) => [
        ...sortedInvocations(step.invocations)
          .filter((invocation) => invocation.traceSpanId)
          .map((invocation) => ({
            invocationId: invocation.id,
            invocationKind: "agent" as const,
            slot: invocation.slot,
            spanId: invocation.traceSpanId as string,
            stepIndex: step.index,
          })),
        ...sortedOperationInvocations(step.operationInvocations)
          .filter((invocation) => invocation.traceSpanId)
          .map((invocation) => ({
            invocationId: invocation.id,
            invocationKind: "operation" as const,
            slot: invocation.slot,
            spanId: invocation.traceSpanId as string,
            stepIndex: step.index,
          })),
      ]),
    [steps],
  );
  const rerunDialogOpen = searchParams.get("rerun") === "1";

  const openRerunDialog = () => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("rerun", "1");
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

  if (!runId) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        Run route is missing an id.
      </div>
    );
  }

  if (runQuery.isPending) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        Loading run details...
      </div>
    );
  }

  if (runQuery.isError || !runQuery.data) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        {runQuery.error instanceof Error
          ? runQuery.error.message
          : "Run not found."}
      </div>
    );
  }

  const run = runQuery.data;
  const runProgress = run.progress.percent;
  const targetKindLabel = formatTargetKindLabel(run.targetKind);
  const activeInspection = resolveRunInspectionState({
    hash: location.hash,
    run,
    searchParams,
    steps,
  });
  const selectedTab = resolveRunDetailTab({
    rawHash: location.hash,
    rawInspect: searchParams.get("inspect"),
    rawMode: searchParams.get("mode"),
    rawPane: searchParams.get("pane"),
    rawTab: searchParams.get("tab"),
  });
  const terminalInvocationsCount = allInvocations.filter((invocation) =>
    isTerminalStatus(invocation.status),
  ).length;
  const canRerunRun = run.targetKind === "workflowPackage";
  const canCancelRun = run.status === "queued" || run.status === "running";

  const handleCancelRun = async () => {
    try {
      await cancelRun.mutateAsync(run.id);
      toast.success("Run cancellation requested");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to cancel run");
    }
  };

  const updateSelectedTab = (tab: RunDetailTabKey) => {
    setSearchParams((current) => withRunDetailTab(current, tab));
  };

  const selectInspection = (
    target: RunInspectionTarget,
    pane?: RunInspectionPane,
    mode?: RunInspectionMode,
  ) => {
    const serializedTarget = serializeInspectionTarget(target);
    const isSameSelection =
      activeInspection.selected !== false &&
      serializeInspectionTarget(activeInspection.target) === serializedTarget &&
      activeInspection.pane === (pane ?? activeInspection.pane) &&
      (!mode || activeInspection.mode === mode);

    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      if (isSameSelection) {
        next.delete("inspect");
        next.delete("pane");
        if (mode) {
          next.set("mode", mode);
        }
        return next;
      }
      next.set("inspect", serializedTarget);
      if (pane) {
        next.set("pane", pane);
      } else {
        next.delete("pane");
      }
      if (mode) {
        next.set("mode", mode);
      }
      return next;
    });
  };

  const sourceRunLabel = run.sourceRunId ? `Rerun of Run #${run.sourceRunId}` : "Original run";
  const startedLabel = run.startedAt
    ? `Started ${formatDateTime(run.startedAt)}`
    : `Queued ${formatDateTime(run.queuedAt)}`;
  const finishedLabel = run.finishedAt
    ? `Finished ${formatDateTime(run.finishedAt)}`
    : formatUnfinishedRunStatus(run.status).replace(/^ · /, "");
  const durationLabel =
    run.startedAt && run.finishedAt
      ? `${Math.max(0, new Date(run.finishedAt).getTime() - new Date(run.startedAt).getTime()).toLocaleString()} ms`
      : run.startedAt
        ? "In progress"
        : "Not started";
  const statusBadgeVariant =
    run.status === "failed"
      ? "destructive"
      : run.status === "succeeded"
        ? "secondary"
        : "outline";
  const shouldShowHeaderProgress = run.status !== "succeeded";
  const failedAgent = steps
    .flatMap((step) =>
      sortedInvocations(step.invocations).map((invocation) => ({
        invocation,
        step,
      })),
    )
    .find(
      ({ invocation }) =>
        invocation.status === "failed" ||
        Boolean(
          invocation.errorCode ||
            invocation.errorMessage ||
            invocation.errorDetails.length > 0,
        ),
    );
  const failedOperation = steps
    .flatMap((step) =>
      sortedOperationInvocations(step.operationInvocations).map((invocation) => ({
        invocation,
        step,
      })),
    )
    .find(
      ({ invocation }) =>
        invocation.status === "failed" ||
        Boolean(
          invocation.errorCode ||
            invocation.errorMessage ||
            invocation.errorDetails.length > 0,
        ),
    );
  const failedStep = steps.find(
    (step) => step.status === "failed" || Boolean(step.error),
  );
  const headerStateDetail = failedAgent
    ? `Failure: Step ${failedAgent.step.index} · ${failedAgent.invocation.slot} agent invocation #${failedAgent.invocation.id}`
    : failedOperation
      ? `Failure: Step ${failedOperation.step.index} · ${failedOperation.invocation.slot} operation invocation #${failedOperation.invocation.id}`
      : failedStep
        ? `Failure: Step ${failedStep.index}`
        : run.error
          ? "Failure: run-level error"
          : run.status === "running"
            ? `Running: ${run.progress.terminalCount} of ${run.progress.totalCount} invocation(s) terminal`
            : run.status === "queued"
              ? run.queue?.message ?? "Queued for execution"
              : null;

  const primaryModeWorkspace = (
    <RunDetailSectionStack
      {...{ onTabChange: updateSelectedTab, selectedTab }}
      activeInspection={activeInspection}
      allInvocationsCount={allInvocations.length}
      onSelect={selectInspection}
      run={run}
      runProgress={runProgress}
      steps={steps}
      targetKindLabel={targetKindLabel}
      terminalInvocationsCount={terminalInvocationsCount}
      traceSpanEntries={traceSpanEntries}
    />
  );

  const runActions = (
    <div
      className="flex min-w-0 flex-wrap items-center justify-start gap-2 sm:justify-end"
      data-testid="runs-detail-actions"
    >
      {run.targetKind === "workflowPackage" &&
      run.packageProvenance?.currentPackage?.available ? (
        <Button
          asChild
          data-testid="runs-detail-package-link"
          size="sm"
          variant="outline"
        >
          <Link to={`/workflow-packages/${run.packageProvenance.workflowPackageId}`}>
            Open current package
          </Link>
        </Button>
      ) : null}
      {canCancelRun ? (
        <Button
          className="cursor-pointer"
          data-testid="runs-detail-cancel"
          disabled={cancelRun.isPending}
          onClick={handleCancelRun}
          size="sm"
          type="button"
          variant="outline"
        >
          <StopCircle data-icon="inline-start" />
          Cancel run
        </Button>
      ) : null}
      {canRerunRun ? (
        <Button
          className="cursor-pointer"
          data-testid="runs-detail-rerun"
          onClick={openRerunDialog}
          size="sm"
          type="button"
        >
          <PlayCircle data-icon="inline-start" />
          Run snapshot again
        </Button>
      ) : null}
      <Button asChild size="sm" variant="outline">
        <Link to="/runs">Back to runs</Link>
      </Button>
    </div>
  );

  const consoleWorkspace = (
    <section
      className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-card"
      data-run-mode={activeInspection.mode}
      data-testid="runs-mode-workspace"
    >
      <div
        className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto overscroll-contain p-3"
        data-testid="runs-detail-context-frame"
      >
        {run.error ? (
          <Alert variant="destructive">
            <AlertCircle />
            <AlertTitle>Run failed</AlertTitle>
            <AlertDescription>{run.error}</AlertDescription>
          </Alert>
        ) : null}
        {run.status === "queued" && run.queue ? (
          <Alert data-testid="runs-detail-queue-reason">
            <AlertCircle />
            <AlertTitle>{formatQueueReasonTitle(run.queue.reason)}</AlertTitle>
            <AlertDescription>
              {run.queue.message}
              {run.queue.blockingRunId
                ? ` Blocking run: #${run.queue.blockingRunId}.`
                : null}
            </AlertDescription>
          </Alert>
        ) : null}
        {primaryModeWorkspace}
      </div>
    </section>
  );

  return (
    <>
      <WorkspacePageShell
        bodyAriaLabel="Run inspection workspace"
        bodyClassName="overflow-hidden rounded-lg border bg-card shadow-xs"
        contextBar={
          <div className="min-w-0" data-testid="runs-detail-header">
            <PageContextBar
              actions={runActions}
              className="min-w-0 border-0 bg-transparent shadow-none"
              layout="toolbar"
              title={
                <span className="flex min-w-0 flex-col gap-1.5">
                  <span
                    className="flex min-w-0 flex-wrap items-center gap-1.5"
                    data-testid="runs-detail-summary-line"
                  >
                    <span className="mr-1 text-base font-semibold tracking-tight text-foreground">
                      Run #{run.id}
                    </span>
                    <Badge variant={statusBadgeVariant}>{run.status}</Badge>
                    {shouldShowHeaderProgress ? (
                      <Badge variant="outline">{runProgress}%</Badge>
                    ) : null}
                    <span className="text-xs font-medium text-muted-foreground">
                      {run.totalTokens.toLocaleString()} tokens
                    </span>
                    {headerStateDetail ? (
                      <span
                        className="min-w-0 break-words text-xs font-normal text-muted-foreground"
                        data-testid="runs-detail-state-summary"
                      >
                        {headerStateDetail}
                      </span>
                    ) : null}
                  </span>
                  <span
                    className="flex min-w-0 flex-wrap items-center gap-1.5 text-xs font-normal text-muted-foreground"
                    data-testid="runs-detail-identity-line"
                  >
                    <Badge variant="outline">{targetKindLabel}</Badge>
                    {run.packageProvenance?.workflowPackageKey ?? run.targetKey}
                    {run.packageProvenance ? (
                      <span className="min-w-0 max-w-full break-words">
                        {run.packageProvenance.workflowPackageName}
                      </span>
                    ) : (
                      <span className="min-w-0 max-w-full break-words">
                        {run.targetKey}
                      </span>
                    )}
                  </span>
                  <span
                    className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs font-normal text-muted-foreground"
                    data-testid="runs-detail-metadata-line"
                  >
                    <span>{startedLabel}</span>
                    <span>{finishedLabel}</span>
                    <span className="inline-flex min-w-0 items-center gap-1.5">
                      <Timer className="size-3.5 shrink-0" />
                      {durationLabel}
                    </span>
                    <span data-testid="runs-detail-source-run">{sourceRunLabel}</span>
                  </span>
                </span>
              }
            />
          </div>
        }
        testId="runs-detail-page"
      >
        <div
          className="h-full min-h-0 min-w-0 flex-1 basis-0"
          data-run-mode={activeInspection.mode}
          data-testid="runs-inspection-workspace"
        >
          {consoleWorkspace}
        </div>
      </WorkspacePageShell>

      <RunRerunDialog
        onClose={closeRerunDialog}
        open={rerunDialogOpen && canRerunRun}
        runId={runId}
      />

    </>
  );
}
