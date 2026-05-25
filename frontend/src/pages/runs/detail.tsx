import { AlertCircle, GitBranch, PlayCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { useIsMobile } from "@/components/ui/use-mobile";
import { useRun } from "@/hooks/use-runs";
import { formatDateTime } from "@/lib/format";
import type { RunQueueReason } from "@/lib/types/run";

import {
  findForkTargetContext,
  formatTargetKindLabel,
  formatUnfinishedRunStatus,
  getRunForkAvailability,
  hasCurrentForkLineage,
  isTerminalStatus,
  sortedInvocations,
  sortedOperationInvocations,
} from "./detail-helpers";
import {
  EvidenceViewer,
  ExecutionOutline,
  RunContextStrip,
  RunForkDialog,
} from "./detail-sections";
import {
  resolveRunInspectionState,
  serializeInspectionTarget,
  type RunInspectionPane,
  type RunInspectionTarget,
} from "./inspection-state";
import { RunRerunDialog } from "./rerun-dialog";

function formatQueueReasonTitle(reason: RunQueueReason): string {
  return reason === "blocked-by-package-serial-policy"
    ? "Blocked by package serial policy"
    : "Awaiting worker capacity";
}

export function RunsDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const runQuery = useRun(runId, { refetchInterval: 2_000 });
  const isMobileConsole = useIsMobile();

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
  const inspectParam = searchParams.get("inspect");
  const paneParam = searchParams.get("pane");
  const requestedTab = inspectParam || paneParam ? "execution" : "summary";
  const [activeTab, setActiveTab] = useState<"summary" | "execution">(
    requestedTab,
  );

  useEffect(() => {
    setActiveTab(requestedTab);
  }, [requestedTab]);

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
  const consoleLayout = isMobileConsole ? "stacked" : "split";
  const consoleDirection = isMobileConsole ? "vertical" : "horizontal";

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
  };

  return (
    <div
      className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-background"
      data-testid="runs-detail-page"
    >
      <Tabs
        className="flex h-full min-h-0 flex-1 flex-col gap-0"
        value={activeTab}
        onValueChange={(value) =>
          setActiveTab(value as "summary" | "execution")
        }
      >
        <div
          className="shrink-0 border-b border-border bg-card/95 px-4 py-3 backdrop-blur"
          data-testid="runs-detail-header"
        >
          <div className="flex min-w-0 flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0 space-y-2">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <h1 className="text-xl font-semibold tracking-tight">
                  Run #{run.id}
                </h1>
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
              <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
                <span>
                  {run.startedAt
                    ? `Started ${formatDateTime(run.startedAt)}`
                    : `Queued ${formatDateTime(run.queuedAt)}`}
                </span>
                <span>
                  {run.finishedAt
                    ? `Finished ${formatDateTime(run.finishedAt)}`
                    : formatUnfinishedRunStatus(run.status).replace(/^ · /, "")}
                </span>
                <span
                  className="inline-flex min-w-0 items-center gap-1.5"
                  data-testid="runs-detail-lineage-indicator"
                >
                  {run.sourceRunId ? (
                    <>
                      <GitBranch className="size-3.5 shrink-0" />
                      {isCurrentFork
                        ? `Forked from Run #${run.sourceRunId}`
                        : `Historical lineage from Run #${run.sourceRunId}`}
                    </>
                  ) : (
                    "Original run"
                  )}
                </span>
              </div>
            </div>
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
          </div>
          <TabsList className="mt-3 grid w-full max-w-md grid-cols-2">
            <TabsTrigger value="summary">Run summary</TabsTrigger>
            <TabsTrigger value="execution">Execution trace</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent
          className="m-0 min-h-0 flex-1 overflow-hidden data-[state=inactive]:hidden"
          forceMount
          value="summary"
        >
          <div
            className="flex h-full min-h-0 min-w-0 flex-col gap-3 overflow-y-auto overscroll-contain px-4 py-4"
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
            <RunContextStrip
              allInvocationsCount={allInvocations.length}
              run={run}
              runProgress={runProgress}
              targetKindLabel={targetKindLabel}
              terminalInvocationsCount={terminalInvocationsCount}
            />
          </div>
        </TabsContent>
        <TabsContent
          className="m-0 min-h-0 flex-1 overflow-hidden data-[state=inactive]:hidden"
          forceMount
          value="execution"
        >
          <ResizablePanelGroup
            className="h-full min-h-0 min-w-0 flex-1 basis-0"
            data-console-layout={consoleLayout}
            data-testid="runs-inspection-workspace"
            direction={consoleDirection}
          >
            <ResizablePanel
              className="min-h-0 min-w-0"
              defaultSize={isMobileConsole ? 36 : 28}
              maxSize={isMobileConsole ? 55 : 45}
              minSize={isMobileConsole ? 24 : 18}
            >
              <ExecutionOutline
                activeInspection={activeInspection}
                onSelect={selectInspection}
                run={run}
                steps={steps}
                traceSpanEntries={traceSpanEntries}
              />
            </ResizablePanel>
            <ResizableHandle
              className="bg-border/80"
              data-testid="runs-inspection-resize-handle"
              withHandle
            />
            <ResizablePanel
              className="min-h-0 min-w-0"
              defaultSize={isMobileConsole ? 64 : 72}
              minSize={isMobileConsole ? 45 : 45}
            >
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
            </ResizablePanel>
          </ResizablePanelGroup>
        </TabsContent>
      </Tabs>

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
    </div>
  );
}
