import { AlertCircle, GitBranch, PlayCircle, Timer } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router";

import { PageContextBar } from "@/components/shared/page-context-bar";
import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import {
  SheetInspectorLayout,
  SplitInspectorLayout,
} from "@/components/shared/split-inspector-layout";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useIsMobile } from "@/components/ui/use-mobile";
import { useRun } from "@/hooks/use-runs";
import { formatDateTime } from "@/lib/format";

import {
  finalOutputState,
  findForkTargetContext,
  formatQueueReasonTitle,
  formatTargetKindLabel,
  formatUnfinishedRunStatus,
  getRunForkAvailability,
  hasCurrentForkLineage,
  isTerminalStatus,
  runStatusTone,
  sortedInvocations,
  sortedOperationInvocations,
} from "./detail-helpers";
import {
  EvidenceViewer,
  RunDetailTabPanel,
  RunForkDialog,
} from "./detail-sections";
import {
  RUN_INSPECTION_MODES,
  resolveRunInspectionState,
  serializeInspectionTarget,
  type RunInspectionMode,
  type RunInspectionPane,
  type RunInspectionTarget,
} from "./inspection-state";
import { RunRerunDialog } from "./rerun-dialog";

const RUN_TAB_LABELS: Record<
  RunInspectionMode,
  { description: string; label: string }
> = {
  summary: {
    description: "Run metrics, queue, progress, and availability",
    label: "Summary",
  },
  execution: {
    description: "Execution steps and invocation flow",
    label: "Execution",
  },
  diagnostics: {
    description: "Warnings, failures, and safety checks",
    label: "Diagnostics",
  },
  inputs: {
    description: "Launch input and source context",
    label: "Inputs",
  },
  outputs: {
    description: "Final output and provenance",
    label: "Outputs",
  },
  runtime: {
    description: "Provider, model, and token runtime profile",
    label: "Runtime",
  },
  memory: {
    description: "Memory events and artifacts",
    label: "Memory",
  },
  lineage: {
    description: "Fork, snapshot, and historical lineage",
    label: "Lineage",
  },
  metadata: {
    description: "Trace, payload, memory, and report evidence",
    label: "Metadata",
  },
};

function paneForRunMode(mode: RunInspectionMode): RunInspectionPane | null {
  if (mode === "outputs") {
    return "finalOutput";
  }
  if (mode === "inputs") {
    return "input";
  }
  if (mode === "lineage") {
    return "lineage";
  }
  if (mode === "memory") {
    return "memory";
  }
  if (mode === "diagnostics") {
    return "error";
  }
  return null;
}

export function RunsDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const runQuery = useRun(runId, { refetchInterval: 2_000 });
  const isMobileConsole = useIsMobile();
  const [mobileEvidenceOpen, setMobileEvidenceOpen] = useState(false);

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
  const forkDialogOpen = searchParams.get("fork") === "1";
  const resumeStepIndexParam = searchParams.get("resumeStepIndex");
  const forkInvocationIdParam = searchParams.get("invocationId");
  const rerunDialogOpen = searchParams.get("rerun") === "1";
  const resumeStepIndex = useMemo(() => {
    if (resumeStepIndexParam === null || resumeStepIndexParam.trim() === "") {
      return undefined;
    }

    const parsed = Number(resumeStepIndexParam);
    return Number.isInteger(parsed) && parsed >= 1 ? parsed : undefined;
  }, [resumeStepIndexParam]);
  const forkInvocationId = useMemo(() => {
    if (forkInvocationIdParam === null || forkInvocationIdParam.trim() === "") {
      return undefined;
    }

    const parsed = Number(forkInvocationIdParam);
    return Number.isInteger(parsed) && parsed >= 1 ? parsed : undefined;
  }, [forkInvocationIdParam]);

  const openRerunDialog = () => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("rerun", "1");
      next.delete("fork");
      next.delete("resumeStepIndex");
      next.delete("invocationId");
      next.delete("stepReplay");
      next.delete("stepIndex");
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

  const openForkDialog = (stepIndex: number, invocationId: number) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("fork", "1");
      next.set("resumeStepIndex", String(stepIndex));
      next.set("invocationId", String(invocationId));
      next.delete("rerun");
      next.delete("stepReplay");
      next.delete("stepIndex");
      return next;
    });
  };

  const closeForkDialog = () => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.delete("fork");
      next.delete("resumeStepIndex");
      next.delete("invocationId");
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
  const copiedSteps = steps.filter((step) => step.origin === "copied").length;
  const plannedSteps = steps.filter((step) => step.origin === "planned").length;
  const copiedInvocations = steps.reduce(
    (count, step) =>
      count +
      step.invocations.filter(
        (invocation) =>
          invocation.outputOrigin === "copied" ||
          invocation.resolvedInputOrigin === "copied",
      ).length +
      step.operationInvocations.filter(
        (invocation) => invocation.outputOrigin === "copied",
      ).length,
    0,
  );
  const plannedInvocations = allInvocations.length - copiedInvocations;
  const runProgress = run.progress.percent;
  const targetKindLabel = formatTargetKindLabel(run.targetKind);
  const forkTarget = findForkTargetContext(
    steps,
    resumeStepIndex,
    forkInvocationId,
  );
  const forkAvailability = getRunForkAvailability(
    run,
    steps,
    resumeStepIndex,
    forkInvocationId,
  );
  const isCurrentFork = hasCurrentForkLineage(run, steps);
  const activeInspection = resolveRunInspectionState({
    hash: location.hash,
    run,
    searchParams,
    steps,
  });
  const terminalInvocationsCount = allInvocations.filter((invocation) =>
    isTerminalStatus(invocation.status),
  ).length;
  const canRerunRun = run.targetKind === "workflowPackage";
  const consoleLayout = isMobileConsole ? "sheet" : "split";

  const selectInspection = (
    target: RunInspectionTarget,
    pane?: RunInspectionPane,
  ) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("inspect", serializeInspectionTarget(target));
      if (pane) {
        next.set("pane", pane);
      } else {
        next.delete("pane");
      }
      return next;
    });
    if (isMobileConsole) {
      setMobileEvidenceOpen(true);
    }
  };

  const selectMode = (mode: RunInspectionMode) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      const pane = paneForRunMode(mode);
      next.set("mode", mode);
      if (pane) {
        next.set("inspect", "run");
        next.set("pane", pane);
      } else if (next.get("inspect") === "run") {
        next.delete("pane");
      }
      return next;
    });
  };

  const lineageLabel = run.sourceRunId
    ? isCurrentFork
      ? `Forked from Run #${run.sourceRunId}`
      : `Historical lineage from Run #${run.sourceRunId}`
    : "Original run";
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
  const outputState = finalOutputState(run);
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
  const currentStateSummary = failedAgent
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
              : `Output ${outputState.label.toLowerCase()}`;

  const runTabs = (
    <Tabs
      className="min-w-0 gap-2"
      data-active-mode={activeInspection.mode}
      data-testid="runs-tab-console"
      onValueChange={(value) => selectMode(value as RunInspectionMode)}
      value={activeInspection.mode}
    >
      <div className="max-w-full overflow-x-auto pb-1" data-testid="runs-tab-scroll">
        <TabsList
          aria-label="Run inspection tabs"
          className="h-9 min-w-max justify-start rounded-xl"
          data-testid="runs-tab-list"
        >
          {RUN_INSPECTION_MODES.map((mode) => {
            const tabLabel = RUN_TAB_LABELS[mode];
            return (
              <TabsTrigger
                aria-label={`${tabLabel.label} tab`}
                className="px-3 text-xs"
                data-mode={mode}
                data-testid={`runs-tab-trigger-${mode}`}
                key={mode}
                title={tabLabel.description}
                value={mode}
              >
                {tabLabel.label}
              </TabsTrigger>
            );
          })}
        </TabsList>
      </div>
    </Tabs>
  );

  const primaryModeWorkspace = (
    <RunDetailTabPanel
      activeInspection={activeInspection}
      allInvocationsCount={allInvocations.length}
      copiedInvocations={copiedInvocations}
      copiedSteps={copiedSteps}
      isCurrentFork={isCurrentFork}
      onSelect={selectInspection}
      plannedInvocations={plannedInvocations}
      plannedSteps={plannedSteps}
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
      className="flex min-w-0 flex-wrap items-center gap-2"
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

  const evidenceViewer = (
    <EvidenceViewer
      activeInspection={activeInspection}
      copiedInvocations={copiedInvocations}
      copiedSteps={copiedSteps}
      isCurrentFork={isCurrentFork}
      onOpenFork={openForkDialog}
      onSelect={selectInspection}
      plannedInvocations={plannedInvocations}
      plannedSteps={plannedSteps}
      run={run}
      steps={steps}
    />
  );

  const consoleWorkspace = (
    <section
      className="flex h-full min-h-0 min-w-0 flex-col bg-background"
      data-run-mode={activeInspection.mode}
      data-testid="runs-mode-workspace"
    >
      <div
        className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto overscroll-contain p-3"
        data-testid="runs-detail-context-frame"
      >
        {isMobileConsole ? (
          <div
            className="flex min-w-0 flex-col gap-2 rounded-xl border bg-card/80 p-3 text-sm sm:flex-row sm:items-center sm:justify-between"
            data-testid="runs-mobile-inspector-callout"
          >
            <div className="min-w-0">
              <p className="font-medium">Evidence inspector</p>
              <p className="text-xs text-muted-foreground">
                Opens as a sheet on mobile instead of stacking below the workspace.
              </p>
            </div>
            <Button
              className="w-full cursor-pointer sm:w-auto"
              data-testid="runs-mobile-inspector-trigger"
              onClick={() => setMobileEvidenceOpen(true)}
              size="sm"
              type="button"
              variant="outline"
            >
              Open evidence inspector
            </Button>
          </div>
        ) : null}
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
        bodyClassName="overflow-hidden"
        contextBar={
          <div className="space-y-3" data-testid="runs-detail-header">
            <PageContextBar
              className="border-0 bg-transparent shadow-none"
              description={
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="flex min-w-0 flex-wrap items-center gap-2">
                    <Badge
                      className="max-w-full min-w-0 break-all"
                      data-testid="runs-detail-target-identity"
                      variant="outline"
                    >
                      {run.packageProvenance?.workflowPackageKey ?? run.targetKey}
                    </Badge>
                    {run.packageProvenance ? (
                      <Badge
                        className="max-w-full min-w-0 break-all"
                        variant="secondary"
                      >
                        {run.packageProvenance.workflowPackageName}
                      </Badge>
                    ) : null}
                    <Badge variant="outline">{targetKindLabel}</Badge>
                  </span>
                  <span
                    className="break-words text-xs text-muted-foreground"
                    data-testid="runs-detail-state-summary"
                  >
                    {currentStateSummary}
                  </span>
                </span>
              }
              meta={
                <span className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1">
                  <span>{startedLabel}</span>
                  <span>{finishedLabel}</span>
                  <span className="inline-flex min-w-0 items-center gap-1.5">
                    <Timer className="size-3.5 shrink-0" />
                    {durationLabel}
                  </span>
                  <span
                    className="inline-flex min-w-0 items-center gap-1.5"
                    data-testid="runs-detail-lineage-indicator"
                  >
                    {run.sourceRunId ? (
                      <GitBranch className="size-3.5 shrink-0" />
                    ) : null}
                    {lineageLabel}
                  </span>
                </span>
              }
              status={
                <ResourceStatusStrip
                  items={[
                    {
                      label: "Status",
                      value: run.status,
                      tone: runStatusTone(run.status),
                    },
                    { label: "Progress", value: `${runProgress}%` },
                    {
                      label: "Output",
                      value: outputState.label,
                      tone: outputState.tone,
                    },
                    { label: "Tokens", value: run.totalTokens.toLocaleString() },
                  ]}
                />
              }
              title={`Run #${run.id}`}
            />
            {runActions}
            {runTabs}
          </div>
        }
        testId="runs-detail-page"
      >
        <div
          className="h-full min-h-0 min-w-0 flex-1 basis-0"
          data-console-layout={consoleLayout}
          data-run-mode={activeInspection.mode}
          data-testid="runs-inspection-workspace"
        >
          {isMobileConsole ? (
            <SheetInspectorLayout
              className="h-full"
              emptyInspector={
                <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground">
                  Select execution evidence to inspect the captured payloads.
                </div>
              }
              inspectorAriaLabel="Run evidence inspector sheet"
              inspectorOpen={mobileEvidenceOpen}
              inspectorTitle="Run evidence inspector"
              leftPane={consoleWorkspace}
              leftPaneAriaLabel="Run mode workspace"
              onInspectorOpenChange={setMobileEvidenceOpen}
              rightPane={evidenceViewer}
              sheetDescription="Inspect captured payloads in an overlay instead of an inline stacked split panel on mobile."
              testId="runs-inspection-sheet-layout"
            />
          ) : (
            <SplitInspectorLayout
              className="h-full"
              emptyInspector={
                <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground">
                  Select execution evidence to inspect the captured payloads.
                </div>
              }
              inspectorAriaLabel="Run evidence inspector"
              leftPane={consoleWorkspace}
              leftPaneAriaLabel="Run mode workspace"
              leftPanel={{ defaultSize: 58, maxSize: 70, minSize: 45 }}
              rightPane={evidenceViewer}
              rightPanel={{ defaultSize: 42, minSize: 30 }}
              testId="runs-inspection-split-layout"
            />
          )}
        </div>
      </WorkspacePageShell>

      <RunRerunDialog
        onClose={closeRerunDialog}
        open={rerunDialogOpen && canRerunRun}
        runId={runId}
      />

      <RunForkDialog
        forkAvailability={forkAvailability}
        forkTarget={forkTarget}
        invocationId={forkInvocationId}
        onClose={closeForkDialog}
        open={forkDialogOpen}
        resumeStepIndex={resumeStepIndex}
        runId={runId}
      />
    </>
  );
}
