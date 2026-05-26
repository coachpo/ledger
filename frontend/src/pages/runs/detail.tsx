import { AlertCircle, GitBranch, PlayCircle } from "lucide-react";
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
import { useIsMobile } from "@/components/ui/use-mobile";
import { useRun } from "@/hooks/use-runs";
import { formatDateTime } from "@/lib/format";

import {
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
  ExecutionOutline,
  RunAuditEvidenceSection,
  RunDiagnosticsWorkspace,
  RunForkDialog,
  RunInputWorkspace,
  RunLineageWorkspace,
  RunMemoryWorkspace,
  RunOutputWorkspace,
  RunOverviewWorkspace,
  RunRuntimeProfileSection,
  RunTokensWorkspace,
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

const RUN_MODE_LABELS: Record<
  RunInspectionMode,
  { description: string; label: string }
> = {
  overview: {
    description: "Run metrics, queue, progress, and availability",
    label: "Overview",
  },
  output: {
    description: "Final output and provenance",
    label: "Output",
  },
  input: {
    description: "Launch input and source context",
    label: "Input",
  },
  steps: {
    description: "Execution steps and invocation flow",
    label: "Steps",
  },
  runtime: {
    description: "Provider and model runtime profile",
    label: "Runtime",
  },
  audit: {
    description: "Trace, payload, memory, and report evidence",
    label: "Audit",
  },
  lineage: {
    description: "Fork, snapshot, and historical lineage",
    label: "Lineage",
  },
  memory: {
    description: "Memory events and artifacts",
    label: "Memory",
  },
  tokens: {
    description: "Token accounting and boundaries",
    label: "Tokens",
  },
  diagnostics: {
    description: "Warnings, failures, and safety checks",
    label: "Diagnostics",
  },
};

function paneForRunMode(mode: RunInspectionMode): RunInspectionPane | null {
  if (mode === "output") {
    return "finalOutput";
  }
  if (mode === "input") {
    return "input";
  }
  if (mode === "lineage") {
    return "lineage";
  }
  if (mode === "memory") {
    return "memory";
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

  const modeRail = (
    <nav
      aria-label="Run inspection modes"
      className="flex max-h-48 min-w-0 gap-1 overflow-x-auto rounded-xl border bg-card/80 p-2 shadow-sm lg:max-h-full lg:flex-col lg:overflow-y-auto lg:overflow-x-hidden"
      data-active-mode={activeInspection.mode}
      data-testid="runs-mode-rail"
    >
      {RUN_INSPECTION_MODES.map((mode) => {
        const modeLabel = RUN_MODE_LABELS[mode];
        const isActive = activeInspection.mode === mode;
        return (
          <Button
            aria-current={isActive ? "page" : undefined}
            aria-label={`${modeLabel.label} mode`}
            className="h-auto min-w-24 shrink-0 cursor-pointer justify-start px-3 py-2 text-left lg:min-w-0"
            data-mode={mode}
            data-testid={`runs-mode-trigger-${mode}`}
            key={mode}
            onClick={() => selectMode(mode)}
            size="sm"
            type="button"
            variant={isActive ? "secondary" : "ghost"}
          >
            <span className="flex min-w-0 flex-col gap-0.5">
              <span className="truncate text-xs font-medium">
                {modeLabel.label}
              </span>
              <span className="hidden truncate text-[11px] font-normal text-muted-foreground lg:block">
                {modeLabel.description}
              </span>
            </span>
          </Button>
        );
      })}
    </nav>
  );

  const primaryModeWorkspace = (() => {
    if (activeInspection.mode === "output") {
      return <RunOutputWorkspace run={run} />;
    }
    if (activeInspection.mode === "input") {
      return <RunInputWorkspace run={run} />;
    }
    if (activeInspection.mode === "steps") {
      return (
        <div
          className="min-h-96 min-w-0 overflow-hidden rounded-xl border"
          data-testid="runs-execution-outline-frame"
        >
          <ExecutionOutline
            activeInspection={activeInspection}
            onSelect={selectInspection}
            run={run}
            steps={steps}
            traceSpanEntries={traceSpanEntries}
          />
        </div>
      );
    }
    if (activeInspection.mode === "runtime") {
      return <RunRuntimeProfileSection run={run} />;
    }
    if (activeInspection.mode === "audit") {
      return (
        <RunAuditEvidenceSection
          activeInspection={activeInspection}
          onSelect={selectInspection}
          run={run}
          traceSpanEntries={traceSpanEntries}
        />
      );
    }
    if (activeInspection.mode === "lineage") {
      return (
        <RunLineageWorkspace
          copiedInvocations={copiedInvocations}
          copiedSteps={copiedSteps}
          isCurrentFork={isCurrentFork}
          plannedInvocations={plannedInvocations}
          plannedSteps={plannedSteps}
          run={run}
        />
      );
    }
    if (activeInspection.mode === "memory") {
      return <RunMemoryWorkspace run={run} />;
    }
    if (activeInspection.mode === "tokens") {
      return <RunTokensWorkspace run={run} />;
    }
    if (activeInspection.mode === "diagnostics") {
      return <RunDiagnosticsWorkspace run={run} steps={steps} />;
    }
    return (
      <RunOverviewWorkspace
        allInvocationsCount={allInvocations.length}
        run={run}
        runProgress={runProgress}
        targetKindLabel={targetKindLabel}
        terminalInvocationsCount={terminalInvocationsCount}
        traceSpanEntries={traceSpanEntries}
      />
    );
  })();

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
          <div data-testid="runs-detail-header">
            <PageContextBar
              actions={
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
                      <Link
                        to={`/workflow-packages/${run.packageProvenance.workflowPackageId}`}
                      >
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
              }
              className="border-0 bg-transparent shadow-none"
              description={
                <span className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1">
                  <span>{startedLabel}</span>
                  <span>{finishedLabel}</span>
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
              meta={
                <div className="flex min-w-0 flex-wrap items-center gap-2">
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
                </div>
              }
              status={
                <ResourceStatusStrip
                  items={[
                    {
                      label: "Status",
                      value: run.status,
                      tone: runStatusTone(run.status),
                    },
                    { label: "Target", value: targetKindLabel },
                    { label: "Progress", value: `${runProgress}%` },
                    { label: "Tokens", value: run.totalTokens.toLocaleString() },
                  ]}
                />
              }
              title={`Run #${run.id}`}
            />
          </div>
        }
        leftRail={modeRail}
        leftRailAriaLabel="Run inspection modes"
        leftRailClassName="lg:sticky lg:top-3 lg:w-52 xl:w-56"
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
