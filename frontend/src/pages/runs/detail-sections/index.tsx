import {
  Activity,
  AlertCircle,
  Download,
  FileText,
  type LucideIcon,
} from "lucide-react";
import {
  type KeyboardEvent,
  type ReactNode,
} from "react";

import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/components/ui/utils";
import { formatDateTime } from "@/lib/format";
import type {
  RunAgentInvocationRead,
  RunGraphMetadata,
  RunOperationInvocationRead,
  RunRead,
  RunStepRead,
  RunStepStatus,
} from "@/lib/types/run";

import { stringifyJson } from "../../platform-resource-helpers";
import {
  diagnosticsFromDraftReadiness,
  formatQueueReasonTitle,
  progressForInvocations,
  sortedInvocations,
  sortedOperationInvocations,
  type TraceSpanEntry,
} from "../detail-helpers";
import {
  RUN_DETAIL_TAB_LABELS,
  RUN_DETAIL_TAB_ORDER,
  type RunDetailTabKey,
} from "../detail-tabs";
import {
  inspectionPaneLabel,
  inspectionPanesForTarget,
  inspectionTargetKindLabel,
  type RunInspectionMode,
  type RunInspectionPane,
  type RunInspectionState,
  type RunInspectionTarget,
} from "../inspection-state";

import {
  JsonBlock,
  RunEvidenceAvailabilitySection,
  RunFinalOutputPane,
  RunInputWorkspace,
  RunOutputWorkspace,
  RunOverviewWorkspace,
  RunPayloadPane,
} from "./payload-sections";
import { CAPABILITY_LABELS, CAPABILITY_ORDER } from "./runtime-metadata";
import { RunRuntimeProfileSection, RunTokensWorkspace } from "./runtime";
import {
  CompactModeEmptyState,
  RunDetailContentSection,
  RunDetailEmptyState,
  RunDetailSectionBlock,
  RunDetailTableFrame,
  type DetailItem,
} from "./shared";
import {
  formatOptional,
  formatTimestamp,
  statusVariant,
} from "./shared-helpers";

const EXECUTION_DEFERRED_SECTION_CLASS_NAME =
  "[content-visibility:auto] [contain-intrinsic-size:auto_960px]";

const RUN_DETAIL_TAB_ICONS: Record<RunDetailTabKey, LucideIcon> = {
  execution: Activity,
  input: FileText,
  output: Download,
  overview: Activity,
  runtime: Activity,
  usage: Activity,
};

const RUN_DETAIL_TAB_DESCRIPTIONS: Record<RunDetailTabKey, string> = {
  execution: "Diagnostics and execution steps for this run.",
  input: "Launch input and provenance captured with the run snapshot.",
  output: "Final output and output provenance for this run.",
  overview: "Operational status and evidence availability for this run.",
  runtime: "Runtime profile, selected strategies, and capability matrix.",
  usage: "Token accounting and invocation usage rows.",
};

type StepIndicatorState = "completed" | "executing" | "neutral";

function stepIndicatorState(status: RunStepStatus): StepIndicatorState {
  if (status === "running") {
    return "executing";
  }

  if (status === "succeeded") {
    return "completed";
  }

  return "neutral";
}

function aggregatedStepOutput(step: RunStepRead) {
  return {
    stepIndex: step.index,
    agentInvocations: sortedInvocations(step.invocations).map((invocation) => ({
      id: invocation.id,
      position: invocation.position,
      slot: invocation.slot,
      status: invocation.status,
      agentKey: invocation.agentKey,
      agentVersion: invocation.agentVersion,
      outputOrigin: invocation.outputOrigin,
      output: invocation.output,
    })),
    operationInvocations: sortedOperationInvocations(
      step.operationInvocations,
    ).map((invocation) => ({
      id: invocation.id,
      position: invocation.position,
      slot: invocation.slot,
      status: invocation.status,
      operationKey: invocation.operationKey,
      operationKind: invocation.operationKind,
      method: invocation.method,
      outputOrigin: invocation.outputOrigin,
      output: invocation.output,
    })),
  };
}

function graphMetadataLabel(
  metadata: RunGraphMetadata | null | undefined,
): string {
  if (!metadata) {
    return "Not recorded";
  }

  return [
    metadata.nodeKind,
    metadata.nodeId,
    metadata.fanoutId ? `fanout ${metadata.fanoutId}` : null,
    metadata.branchId ? `branch ${metadata.branchId}` : null,
    metadata.loopId ? `loop ${metadata.loopId}` : null,
    metadata.loopIteration ? `iteration ${metadata.loopIteration}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

function isInspectionTargetEqual(
  left: RunInspectionTarget,
  right: RunInspectionTarget,
): boolean {
  if (left.type !== right.type) {
    return false;
  }
  if (left.type === "step" && right.type === "step") {
    return left.stepIndex === right.stepIndex;
  }
  if (left.type === "agentInvocation" && right.type === "agentInvocation") {
    return left.invocationId === right.invocationId;
  }
  if (
    left.type === "operationInvocation" &&
    right.type === "operationInvocation"
  ) {
    return left.invocationId === right.invocationId;
  }
  return left.type === "run";
}

function findAgentInvocation(
  steps: RunStepRead[],
  invocationId: number,
): { invocation: RunAgentInvocationRead; step: RunStepRead } | null {
  for (const step of steps) {
    const invocation = step.invocations.find(
      (item) => item.id === invocationId,
    );
    if (invocation) {
      return { invocation, step };
    }
  }
  return null;
}

function findOperationInvocation(
  steps: RunStepRead[],
  invocationId: number,
): RunOperationInvocationRead | null {
  for (const step of steps) {
    const invocation = step.operationInvocations.find(
      (item) => item.id === invocationId,
    );
    if (invocation) {
      return invocation;
    }
  }
  return null;
}

function selectedTargetLabel(
  target: RunInspectionTarget,
  steps: RunStepRead[],
  run: RunRead,
): string {
  if (target.type === "step") {
    return `Step ${target.stepIndex}`;
  }
  if (target.type === "agentInvocation") {
    const match = findAgentInvocation(steps, target.invocationId);
    return match
      ? `${match.invocation.slot} invocation`
      : `Invocation #${target.invocationId}`;
  }
  if (target.type === "operationInvocation") {
    const invocation = findOperationInvocation(steps, target.invocationId);
    return invocation
      ? `${invocation.slot} operation`
      : `Operation #${target.invocationId}`;
  }
  return `Run #${run.id}`;
}

type RunDiagnosticSeverity = "error" | "warning";

type RunDiagnosticRow = {
  field: string;
  issue: string;
  key: string;
  severity: RunDiagnosticSeverity;
  source: string;
  title: string;
};

function diagnosticBadge(severity: RunDiagnosticSeverity) {
  return severity === "error" ? (
    <Badge data-severity="error" variant="destructive">
      Failure
    </Badge>
  ) : (
    <Badge
      className="border-chart-3/30 bg-chart-3/10 text-chart-3"
      data-severity="warning"
      variant="outline"
    >
      Warning
    </Badge>
  );
}

function packageReadinessDiagnostics(run: RunRead): RunDiagnosticRow[] {
  const preflight = run.packageProvenance?.preflightSummary;
  return diagnosticsFromDraftReadiness(preflight).map((diagnostic, index) => ({
    field: diagnostic.field,
    issue: diagnostic.issue,
    key: `preflight-${diagnostic.severity}-${index}`,
    severity: diagnostic.severity,
    source: "Launch preflight",
    title:
      diagnostic.severity === "error"
        ? "Preflight blocker"
        : "Preflight warning",
  }));
}

function packageCurrentDiagnostics(run: RunRead): RunDiagnosticRow[] {
  const currentPackage = run.packageProvenance?.currentPackage;
  if (!currentPackage) {
    return [];
  }

  const diagnostics: RunDiagnosticRow[] = [];
  if (!currentPackage.available) {
    diagnostics.push({
      field: "package.currentPackage.available",
      issue:
        currentPackage.unavailableReason ??
        "Current package snapshot is unavailable.",
      key: "current-package-unavailable",
      severity: "warning",
      source: "Current package",
      title: "Current package unavailable",
    });
  }
  if (currentPackage.manifestHashMatchesSnapshot === false) {
    diagnostics.push({
      field: "package.currentPackage.manifestHash",
      issue: "Current manifest hash differs from the run snapshot.",
      key: "manifest-hash-mismatch",
      severity: "warning",
      source: "Current package",
      title: "Manifest hash drift",
    });
  }
  if (currentPackage.compiledHashMatchesSnapshot === false) {
    diagnostics.push({
      field: "package.currentPackage.compiledHash",
      issue: "Current compiled hash differs from the run snapshot.",
      key: "compiled-hash-mismatch",
      severity: "warning",
      source: "Current package",
      title: "Compiled hash drift",
    });
  }
  return diagnostics;
}

function unsupportedCapabilityDiagnostics(run: RunRead): RunDiagnosticRow[] {
  return (run.packageProvenance?.resolvedModelConnections ?? []).flatMap(
    (connection) =>
      CAPABILITY_ORDER.filter(
        (capabilityKey) =>
          connection.capabilities[capabilityKey].status === "unsupported",
      ).map((capabilityKey) => ({
        field: `runtime.${connection.key}.${capabilityKey}`,
        issue:
          connection.capabilities[capabilityKey].detail ||
          `${CAPABILITY_LABELS[capabilityKey]} is unsupported for this frozen runtime profile.`,
        key: `unsupported-${connection.key}-${capabilityKey}`,
        severity: "warning" as const,
        source: "Runtime capability",
        title: `${connection.name}: ${CAPABILITY_LABELS[capabilityKey]}`,
      })),
  );
}

function runDiagnostics(
  run: RunRead,
  steps: RunStepRead[],
): RunDiagnosticRow[] {
  const stepDiagnostics = steps.flatMap((step) => {
    const diagnostics: RunDiagnosticRow[] = [];
    if (step.error) {
      diagnostics.push({
        field: `steps.${step.index}.error`,
        issue: step.error,
        key: `step-${step.index}-error`,
        severity: "error",
        source: "Step",
        title: `Step ${step.index} failed`,
      });
    }
    sortedInvocations(step.invocations).forEach((invocation) => {
      const hasError = Boolean(
        invocation.errorCode ||
        invocation.errorMessage ||
        invocation.errorDetails.length > 0,
      );
      if (!hasError) {
        return;
      }
      diagnostics.push({
        field: `steps.${step.index}.invocations.${invocation.id}`,
        issue:
          invocation.errorMessage ?? "No invocation error message recorded.",
        key: `agent-${invocation.id}-error`,
        severity: "error",
        source: "Agent invocation",
        title: invocation.errorCode ?? `${invocation.slot} invocation failed`,
      });
    });
    sortedOperationInvocations(step.operationInvocations).forEach(
      (invocation) => {
        const hasError = Boolean(
          invocation.errorCode ||
          invocation.errorMessage ||
          invocation.errorDetails.length > 0,
        );
        if (!hasError) {
          return;
        }
        diagnostics.push({
          field: `steps.${step.index}.operations.${invocation.id}`,
          issue:
            invocation.errorMessage ?? "No operation error message recorded.",
          key: `operation-${invocation.id}-error`,
          severity: "error",
          source: "Operation invocation",
          title: invocation.errorCode ?? `${invocation.slot} operation failed`,
        });
      },
    );
    return diagnostics;
  });

  return [
    ...(run.error
      ? [
          {
            field: "run.error",
            issue: run.error,
            key: "run-error",
            severity: "error" as const,
            source: "Run",
            title: "Run failed",
          },
        ]
      : []),
    ...(run.queue
      ? [
          {
            field: "run.queue",
            issue: `${run.queue.message}${run.queue.blockingRunId ? ` Blocking run: #${run.queue.blockingRunId}.` : ""}`,
            key: "run-queue",
            severity: "warning" as const,
            source: "Queue",
            title: formatQueueReasonTitle(run.queue.reason),
          },
        ]
      : []),
    ...stepDiagnostics,
    ...packageReadinessDiagnostics(run),
    ...packageCurrentDiagnostics(run),
    ...unsupportedCapabilityDiagnostics(run),
  ];
}

function RunDiagnosticsWorkspace({
  run,
  steps,
}: {
  run: RunRead;
  steps: RunStepRead[];
}) {
  const diagnostics = runDiagnostics(run, steps);
  const errorCount = diagnostics.filter(
    (item) => item.severity === "error",
  ).length;
  const warningCount = diagnostics.length - errorCount;

  if (diagnostics.length === 0) {
    return (
      <section
        className="grid min-w-0 gap-3"
        data-testid="runs-diagnostics-workspace"
      >
        <RunDetailContentSection
          className={EXECUTION_DEFERRED_SECTION_CLASS_NAME}
          description="Warnings, failures, unsupported capabilities, and retry safety checks appear here."
          sectionId="diagnostics"
          testId="runs-detail-section-diagnostics"
          title="Diagnostics"
        >
          <CompactModeEmptyState testId="runs-diagnostics-empty">
            No run diagnostics, queue warnings, runtime capability warnings, or
            retry blockers are recorded.
          </CompactModeEmptyState>
        </RunDetailContentSection>
      </section>
    );
  }

  return (
    <section
      className="grid min-w-0 gap-3"
      data-testid="runs-diagnostics-workspace"
    >
      <RunDetailContentSection
        className={EXECUTION_DEFERRED_SECTION_CLASS_NAME}
        description="Warnings stay visually separate from destructive failures so degraded runs are not confused with failed ones."
        sectionId="diagnostics"
        testId="runs-detail-section-diagnostics"
        title="Diagnostics"
      >
        <div className="grid min-w-0 gap-3">
          <ResourceStatusStrip
            items={[
              {
                label: "Failures",
                value: errorCount,
                tone: errorCount > 0 ? "danger" : "muted",
              },
              {
                label: "Warnings",
                value: warningCount,
                tone: warningCount > 0 ? "warning" : "muted",
              },
            ]}
          />
          <RunDetailTableFrame>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Severity</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Diagnostic</TableHead>
                  <TableHead>Field</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {diagnostics.map((diagnostic) => (
                  <TableRow
                    data-severity={diagnostic.severity}
                    data-testid={`runs-diagnostic-${diagnostic.key}`}
                    key={diagnostic.key}
                  >
                    <TableCell className="align-top">
                      {diagnosticBadge(diagnostic.severity)}
                    </TableCell>
                    <TableCell className="whitespace-normal align-top text-muted-foreground">
                      {diagnostic.source}
                    </TableCell>
                    <TableCell className="min-w-80 whitespace-normal align-top">
                      <div className="flex min-w-0 flex-col gap-1">
                        <span className="font-medium text-foreground">
                          {diagnostic.title}
                        </span>
                        <span className="break-words text-muted-foreground">
                          {diagnostic.issue}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="min-w-56 whitespace-normal align-top">
                      <code className="break-all rounded bg-muted/40 px-2 py-1 text-xs">
                        {diagnostic.field}
                      </code>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </RunDetailTableFrame>
        </div>
      </RunDetailContentSection>
    </section>
  );
}

function handleSelectableRowKeyDown(
  event: KeyboardEvent<HTMLTableRowElement>,
  onSelect: () => void,
) {
  if (event.key !== "Enter" && event.key !== " ") {
    return;
  }

  event.preventDefault();
  onSelect();
}

function StepStatusIndicator({
  state,
  stepIndex,
}: {
  state: StepIndicatorState;
  stepIndex: number;
}) {
  if (state === "neutral") {
    return null;
  }

  const isExecuting = state === "executing";
  const label = isExecuting
    ? `Step ${stepIndex} currently executing`
    : `Step ${stepIndex} completed`;

  return (
    <span
      aria-label={label}
      className={cn(
        "inline-flex size-3 shrink-0 rounded-full border",
        isExecuting
          ? "border-primary bg-primary/70 ring-4 ring-primary/10 motion-safe:animate-pulse"
          : "border-positive bg-positive",
      )}
      data-testid={`runs-step-${stepIndex}-${isExecuting ? "executing" : "completed"}-indicator`}
      role="img"
      title={label}
    />
  );
}

function StepTraceSummary({
  entries,
  stepIndex,
}: {
  entries: TraceSpanEntry[];
  stepIndex: number;
}) {
  if (entries.length === 0) {
    return null;
  }

  return (
    <span
      className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground"
      data-testid={`runs-step-${stepIndex}-trace-summary`}
    >
      <Badge variant="outline">
        {entries.length} trace span{entries.length === 1 ? "" : "s"}
      </Badge>
      {entries.slice(0, 2).map((entry) => (
        <span
          className="break-all"
          key={`${entry.invocationId}-${entry.spanId}`}
        >
          {entry.invocationKind === "operation" ? "operation " : ""}
          {entry.slot}/{entry.spanId}
        </span>
      ))}
      {entries.length > 2 ? <span>+{entries.length - 2} more</span> : null}
    </span>
  );
}

function ExecutionOutline({
  activeInspection,
  onSelect,
  run,
  steps,
  traceSpanEntries,
}: {
  activeInspection: RunInspectionState;
  onSelect: (
    target: RunInspectionTarget,
    pane?: RunInspectionPane,
    mode?: RunInspectionMode,
  ) => void;
  run: RunRead;
  steps: RunStepRead[];
  traceSpanEntries: TraceSpanEntry[];
}) {
  const shouldRenderExecutionInline =
    activeInspection.mode !== "metadata" &&
    activeInspection.target.type !== "run";
  const renderInlineEvidenceRow = (key: string, testId: string) => (
    <TableRow key={key}>
      <TableCell className="whitespace-normal p-3 align-top" colSpan={6}>
        <RunInlineEvidence
          activeInspection={activeInspection}
          onSelect={onSelect}
          run={run}
          steps={steps}
          testId={testId}
        />
      </TableCell>
    </TableRow>
  );

  return (
    <section
      className="flex h-full min-h-0 min-w-0 flex-col bg-background"
      data-testid="runs-execution-outline"
    >
      <RunDetailContentSection
        className={EXECUTION_DEFERRED_SECTION_CLASS_NAME}
        description="Step and invocation rows stay visible while selected row detail expands inline."
        sectionId="execution-steps"
        testId="runs-detail-section-execution-steps"
        title="Execution steps"
      >
        {steps.length === 0 ? (
          <RunDetailEmptyState testId="runs-empty-steps">
            No steps have been planned for this run yet.
          </RunDetailEmptyState>
        ) : (
          <div className="min-w-0 pt-1">
            <RunDetailTableFrame
              className="border-transparent bg-transparent"
              testId="runs-execution-table"
            >
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Timeline row</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Origin</TableHead>
                    <TableHead>Progress</TableHead>
                    <TableHead>Trace</TableHead>
                    <TableHead>Context</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {steps.flatMap((step) => {
                    const invocations = sortedInvocations(step.invocations);
                    const operationInvocations = sortedOperationInvocations(
                      step.operationInvocations,
                    );
                    const allInvocations = [
                      ...invocations,
                      ...operationInvocations,
                    ];
                    const stepProgress = progressForInvocations(
                      allInvocations,
                      step.status,
                    );
                    const stepTarget: RunInspectionTarget = {
                      type: "step",
                      stepIndex: step.index,
                    };
                    const indicatorState = stepIndicatorState(step.status);
                    const isStepActive = isInspectionTargetEqual(
                      activeInspection.target,
                      stepTarget,
                    );
                    const stepTraceEntries = traceSpanEntries.filter(
                      (entry) => entry.stepIndex === step.index,
                    );
                    const selectStep = () =>
                      onSelect(stepTarget, undefined, "execution");
                    const stepRow = (
                      <TableRow
                        aria-label={`Step ${step.index} execution row`}
                        className="cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                        data-state={isStepActive ? "selected" : undefined}
                        data-testid={`runs-step-${step.index}`}
                        id={`step-${step.index}`}
                        key={`step-${step.id}`}
                        onClick={selectStep}
                        onKeyDown={(event) =>
                          handleSelectableRowKeyDown(event, selectStep)
                        }
                        role="button"
                        tabIndex={0}
                      >
                        <TableCell className="min-w-56 whitespace-normal align-top">
                          <span className="flex min-w-0 items-center gap-2 rounded-md px-2 py-1.5 text-left text-foreground">
                            <StepStatusIndicator
                              state={indicatorState}
                              stepIndex={step.index}
                            />
                            <span className="font-medium">
                              Step {step.index}
                            </span>
                          </span>
                        </TableCell>
                        <TableCell className="align-top">
                          <Badge variant={statusVariant(step.status)}>
                            {step.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="align-top">
                          <Badge variant="outline">{step.origin} origin</Badge>
                        </TableCell>
                        <TableCell className="align-top">
                          <Badge variant="secondary">{stepProgress}%</Badge>
                        </TableCell>
                        <TableCell className="min-w-64 whitespace-normal align-top">
                          <StepTraceSummary
                            entries={stepTraceEntries}
                            stepIndex={step.index}
                          />
                        </TableCell>
                        <TableCell className="min-w-72 whitespace-normal align-top text-muted-foreground">
                          {invocations.length} agent invocation(s) ·{" "}
                          {operationInvocations.length} operation invocation(s)
                        </TableCell>
                      </TableRow>
                    );
                    const agentRows = invocations.flatMap((invocation) => {
                      const invocationTarget: RunInspectionTarget = {
                        type: "agentInvocation",
                        invocationId: invocation.id,
                      };
                      const isActive = isInspectionTargetEqual(
                        activeInspection.target,
                        invocationTarget,
                      );
                      const selectInvocation = () =>
                        onSelect(invocationTarget, undefined, "execution");
                      const row = (
                        <TableRow
                          aria-label={`${invocation.slot} agent invocation row`}
                          className="cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                          data-state={isActive ? "selected" : undefined}
                          data-testid={`runs-invocation-${invocation.id}-outline-entry`}
                          id={`invocation-${invocation.id}`}
                          key={`agent-${invocation.id}`}
                          onClick={selectInvocation}
                          onKeyDown={(event) =>
                            handleSelectableRowKeyDown(event, selectInvocation)
                          }
                          role="button"
                          tabIndex={0}
                        >
                          <TableCell className="min-w-56 whitespace-normal align-top">
                            <span className="flex min-w-0 flex-col gap-0.5 rounded-md px-2 py-1.5 text-left text-foreground">
                              <span className="font-medium">
                                {invocation.slot} agent
                              </span>
                              <span className="text-xs text-muted-foreground">
                                Invocation #{invocation.id}
                              </span>
                            </span>
                          </TableCell>
                          <TableCell className="align-top">
                            <Badge variant={statusVariant(invocation.status)}>
                              {invocation.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="whitespace-normal align-top text-muted-foreground">
                            input {invocation.resolvedInputOrigin}
                          </TableCell>
                          <TableCell className="whitespace-normal align-top text-muted-foreground">
                            {invocation.outputOrigin ?? "pending"}
                          </TableCell>
                          <TableCell className="whitespace-normal align-top text-muted-foreground">
                            {invocation.traceSpanId ?? "Not recorded"}
                          </TableCell>
                          <TableCell className="min-w-72 whitespace-normal align-top text-muted-foreground">
                            {invocation.agentKey} v{invocation.agentVersion}
                          </TableCell>
                        </TableRow>
                      );
                      if (!isActive || !shouldRenderExecutionInline) {
                        return [row];
                      }
                      return [
                        row,
                        renderInlineEvidenceRow(
                          `agent-${invocation.id}-inline`,
                          `runs-invocation-${invocation.id}-inline-evidence`,
                        ),
                      ];
                    });
                    const operationRows = operationInvocations.flatMap(
                      (invocation) => {
                        const operationTarget: RunInspectionTarget = {
                          type: "operationInvocation",
                          invocationId: invocation.id,
                        };
                        const isActive = isInspectionTargetEqual(
                          activeInspection.target,
                          operationTarget,
                        );
                        const selectOperation = () =>
                          onSelect(operationTarget, undefined, "execution");
                        const row = (
                          <TableRow
                            aria-label={`${invocation.slot} operation invocation row`}
                            className="cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                            data-state={isActive ? "selected" : undefined}
                            data-testid={`runs-operation-${invocation.id}-outline-entry`}
                            id={`operation-invocation-${invocation.id}`}
                            key={`operation-${invocation.id}`}
                            onClick={selectOperation}
                            onKeyDown={(event) =>
                              handleSelectableRowKeyDown(event, selectOperation)
                            }
                            role="button"
                            tabIndex={0}
                          >
                            <TableCell className="min-w-56 whitespace-normal align-top">
                              <span className="flex min-w-0 flex-col gap-0.5 rounded-md px-2 py-1.5 text-left text-foreground">
                                <span className="font-medium">
                                  {invocation.slot} operation
                                </span>
                                <span className="text-xs text-muted-foreground">
                                  Invocation #{invocation.id}
                                </span>
                              </span>
                            </TableCell>
                            <TableCell className="align-top">
                              <Badge variant={statusVariant(invocation.status)}>
                                {invocation.status}
                              </Badge>
                            </TableCell>
                            <TableCell className="whitespace-normal align-top text-muted-foreground">
                              {invocation.operationKind}
                            </TableCell>
                            <TableCell className="whitespace-normal align-top text-muted-foreground">
                              {invocation.outputOrigin ?? "pending"}
                            </TableCell>
                            <TableCell className="whitespace-normal align-top text-muted-foreground">
                              {invocation.traceSpanId ?? "Not recorded"}
                            </TableCell>
                          <TableCell className="min-w-72 whitespace-normal align-top text-muted-foreground">
                              {invocation.operationKey}
                          </TableCell>
                          </TableRow>
                        );
                        if (!isActive || !shouldRenderExecutionInline) {
                          return [row];
                        }
                        return [
                          row,
                          renderInlineEvidenceRow(
                            `operation-${invocation.id}-inline`,
                            `runs-operation-${invocation.id}-inline-evidence`,
                          ),
                        ];
                      },
                    );

                    const stepRows =
                      isStepActive && shouldRenderExecutionInline
                        ? [
                            stepRow,
                            renderInlineEvidenceRow(
                              `step-${step.id}-inline`,
                              `runs-step-${step.index}-inline-evidence`,
                            ),
                          ]
                        : [stepRow];

                    return [...stepRows, ...agentRows, ...operationRows];
                  })}
                </TableBody>
              </Table>
            </RunDetailTableFrame>
          </div>
        )}
      </RunDetailContentSection>
    </section>
  );
}

function EvidencePaneNav({
  activeInspection,
  onSelect,
}: {
  activeInspection: RunInspectionState;
  onSelect: (
    target: RunInspectionTarget,
    pane?: RunInspectionPane,
    mode?: RunInspectionMode,
  ) => void;
}) {
  return (
    <div
      className="flex min-w-0 flex-wrap gap-2"
      data-testid="runs-evidence-pane-nav"
    >
      {inspectionPanesForTarget(activeInspection.target).map((pane) => (
        <Button
          className="max-w-full cursor-pointer"
          key={pane}
          onClick={() =>
            onSelect(activeInspection.target, pane, activeInspection.mode)
          }
          size="sm"
          type="button"
          variant={activeInspection.pane === pane ? "secondary" : "outline"}
        >
          {inspectionPaneLabel(pane)}
        </Button>
      ))}
    </div>
  );
}

function StepSummaryEvidence({ step }: { step: RunStepRead }) {
  const metadataItems: DetailItem[] = [
    { label: "Step row", value: `#${step.id}` },
    { label: "Status", value: step.status },
    { label: "Origin", value: step.origin },
    { label: "Graph node", value: graphMetadataLabel(step.graphMetadata) },
    { label: "Started", value: formatTimestamp(step.startedAt) },
    { label: "Finished", value: formatTimestamp(step.finishedAt) },
    { label: "Persisted", value: formatTimestamp(step.persistedAt) },
    { label: "Updated", value: formatDateTime(step.updatedAt) },
  ];

  return (
    <div
      className="flex min-w-0 flex-col gap-5"
      data-testid={`runs-step-${step.index}-summary`}
    >
      <section
        aria-labelledby={`runs-step-${step.index}-metadata-heading`}
        className="flex flex-col gap-3"
      >
        <h3
          className="text-base font-medium leading-none"
          id={`runs-step-${step.index}-metadata-heading`}
        >
          Step metadata
        </h3>
        <dl
          className="grid gap-x-5 gap-y-2 text-sm sm:grid-cols-2 xl:grid-cols-3"
          data-testid={`runs-step-${step.index}-metadata`}
        >
          {metadataItems.map((item) => (
            <div className="min-w-0" key={item.label}>
              <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {item.label}
              </dt>
              <dd className="mt-0.5 break-words text-foreground">
                {formatOptional(item.value)}
              </dd>
            </div>
          ))}
        </dl>
      </section>
      <section
        aria-labelledby={`runs-step-${step.index}-output-heading`}
        className="flex flex-col gap-3"
      >
        <h3
          className="text-base font-medium leading-none"
          id={`runs-step-${step.index}-output-heading`}
        >
          Aggregated output
        </h3>
        <JsonBlock
          testId={`runs-step-${step.index}-aggregated-output`}
          value={aggregatedStepOutput(step)}
        />
      </section>
    </div>
  );
}

function StepErrorEvidence({ step }: { step: RunStepRead }) {
  return step.error ? (
    <Alert variant="destructive">
      <AlertCircle />
      <AlertTitle>Step failed</AlertTitle>
      <AlertDescription>{step.error}</AlertDescription>
    </Alert>
  ) : (
    <div className="rounded-lg border border-border/70 bg-card/70 p-4 text-sm text-muted-foreground shadow-ui-xs">
      No step error recorded.
    </div>
  );
}

function StepEvidence({
  pane,
  step,
}: {
  pane: RunInspectionPane;
  step: RunStepRead;
}) {
  if (pane === "error") {
    return <StepErrorEvidence step={step} />;
  }

  return <StepSummaryEvidence step={step} />;
}

function InvocationEvidence({
  invocation,
  pane,
}: {
  invocation: RunAgentInvocationRead;
  pane: RunInspectionPane;
}) {
  const hasError = Boolean(
    invocation.errorCode ||
    invocation.errorMessage ||
    invocation.errorDetails.length > 0,
  );
  if (pane === "input") {
    return (
      <JsonBlock label="Resolved input" value={invocation.resolvedInput} />
    );
  }
  if (pane === "wiring") {
    return <JsonBlock label="Wiring" value={invocation.wiring} />;
  }
  if (pane === "error") {
    return hasError ? (
      <Alert variant="destructive">
        <AlertCircle />
        <AlertTitle>{invocation.errorCode ?? "Invocation failed"}</AlertTitle>
        <AlertDescription className="flex flex-col gap-2">
          <p>{invocation.errorMessage ?? "No error message recorded."}</p>
          {invocation.errorDetails.length > 0 ? (
            <pre
              className="max-w-full overflow-x-auto whitespace-pre rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs shadow-ui-xs"
              data-wide-payload="scroll"
            >
              {stringifyJson(invocation.errorDetails)}
            </pre>
          ) : null}
        </AlertDescription>
      </Alert>
    ) : (
      <div className="rounded-lg border border-border/70 bg-card/70 p-4 text-sm text-muted-foreground shadow-ui-xs">
        No invocation error recorded.
      </div>
    );
  }
  return <JsonBlock label="Output" value={invocation.output} />;
}

function OperationEvidence({
  invocation,
  pane,
}: {
  invocation: RunOperationInvocationRead;
  pane: RunInspectionPane;
}) {
  const hasError = Boolean(
    invocation.errorCode ||
    invocation.errorMessage ||
    invocation.errorDetails.length > 0,
  );
  if (pane === "request") {
    return (
      <JsonBlock
        label="Redacted request metadata"
        testId={`runs-operation-${invocation.id}-request-metadata`}
        value={invocation.requestMetadata}
      />
    );
  }
  if (pane === "response") {
    return (
      <JsonBlock
        label="Response metadata"
        testId={`runs-operation-${invocation.id}-response-metadata`}
        value={invocation.responseMetadata}
      />
    );
  }
  if (pane === "error") {
    return hasError ? (
      <Alert variant="destructive">
        <AlertCircle />
        <AlertTitle>{invocation.errorCode ?? "Operation failed"}</AlertTitle>
        <AlertDescription className="flex flex-col gap-2">
          <p>{invocation.errorMessage ?? "No error message recorded."}</p>
          {invocation.errorDetails.length > 0 ? (
            <pre
              className="max-w-full overflow-x-auto whitespace-pre rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs shadow-ui-xs"
              data-wide-payload="scroll"
            >
              {stringifyJson(invocation.errorDetails)}
            </pre>
          ) : null}
        </AlertDescription>
      </Alert>
    ) : (
      <div className="rounded-lg border border-border/70 bg-card/70 p-4 text-sm text-muted-foreground shadow-ui-xs">
        No operation error recorded.
      </div>
    );
  }
  return (
    <JsonBlock
      label="Output preview"
      testId={`runs-operation-${invocation.id}-output-preview`}
      value={invocation.output}
    />
  );
}

type RunDetailSectionStackProps = {
  activeInspection: RunInspectionState;
  allInvocationsCount: number;
  onSelect: (
    target: RunInspectionTarget,
    pane?: RunInspectionPane,
    mode?: RunInspectionMode,
  ) => void;
  onTabChange: (tab: RunDetailTabKey) => void;
  run: RunRead;
  runProgress: number;
  steps: RunStepRead[];
  targetKindLabel: string;
  terminalInvocationsCount: number;
  traceSpanEntries: TraceSpanEntry[];
  selectedTab: RunDetailTabKey;
};

function isRunDetailTabKey(value: string): value is RunDetailTabKey {
  return RUN_DETAIL_TAB_ORDER.includes(value as RunDetailTabKey);
}

export function RunDetailSectionStack(props: RunDetailSectionStackProps) {
  const {
    activeInspection,
    allInvocationsCount,
    onSelect,
    onTabChange,
    run,
    runProgress,
    selectedTab,
    steps,
    targetKindLabel,
    terminalInvocationsCount,
    traceSpanEntries,
  } = props;

  const overviewContent = (
    <div
      className="grid min-w-0 gap-3"
      data-testid="runs-overview-tab-workspace"
    >
      <RunOverviewWorkspace
        allInvocationsCount={allInvocationsCount}
        run={run}
        runProgress={runProgress}
        targetKindLabel={targetKindLabel}
        terminalInvocationsCount={terminalInvocationsCount}
        traceSpanEntries={traceSpanEntries}
      />
      <RunEvidenceAvailabilitySection run={run} />
    </div>
  );

  const outputContent = (
    <div className="grid min-w-0 gap-3" data-testid="runs-output-tab-workspace">
      <RunFinalOutputPane run={run} />
      <RunOutputWorkspace run={run} />
    </div>
  );

  const executionContent = (
    <div
      className="grid min-w-0 gap-3"
      data-testid="runs-execution-tab-workspace"
    >
      <RunDiagnosticsWorkspace run={run} steps={steps} />
      <ExecutionOutline
        activeInspection={activeInspection}
        onSelect={onSelect}
        run={run}
        steps={steps}
        traceSpanEntries={traceSpanEntries}
      />
    </div>
  );

  const inputContent = <RunInputWorkspace run={run} />;

  const runtimeContent = <RunRuntimeProfileSection run={run} />;

  const usageContent = <RunTokensWorkspace run={run} />;

  const tabContentByKey: Record<RunDetailTabKey, ReactNode> = {
    execution: executionContent,
    input: inputContent,
    output: outputContent,
    overview: overviewContent,
    runtime: runtimeContent,
    usage: usageContent,
  };

  return (
    <Tabs
      className="min-w-0 gap-3"
      data-testid="runs-detail-tabs"
      onValueChange={(value) => {
        if (isRunDetailTabKey(value)) {
          onTabChange(value);
        }
      }}
      value={selectedTab}
    >
      <TabsList
        aria-label="Run detail sections"
        className="h-8 max-w-full shrink-0 justify-start overflow-x-auto"
      >
        {RUN_DETAIL_TAB_ORDER.map((tab) => (
          <TabsTrigger
            data-testid={`runs-detail-tab-trigger-${tab}`}
            key={tab}
            value={tab}
          >
            {RUN_DETAIL_TAB_LABELS[tab]}
          </TabsTrigger>
        ))}
      </TabsList>
      {RUN_DETAIL_TAB_ORDER.map((tab) => (
        <TabsContent
          className="min-w-0"
          data-testid={`runs-detail-tab-panel-${tab}`}
          key={tab}
          value={tab}
        >
          {selectedTab === tab ? (
            <RunDetailSectionBlock
              blockId={tab}
              description={RUN_DETAIL_TAB_DESCRIPTIONS[tab]}
              icon={RUN_DETAIL_TAB_ICONS[tab]}
              title={RUN_DETAIL_TAB_LABELS[tab]}
            >
              {tabContentByKey[tab]}
            </RunDetailSectionBlock>
          ) : null}
        </TabsContent>
      ))}
    </Tabs>
  );
}

function RunInlineEvidence({
  activeInspection,
  onSelect,
  run,
  steps,
  testId,
}: {
  activeInspection: RunInspectionState;
  onSelect: (
    target: RunInspectionTarget,
    pane?: RunInspectionPane,
    mode?: RunInspectionMode,
  ) => void;
  run: RunRead;
  steps: RunStepRead[];
  testId: string;
}) {
  const target = activeInspection.target;
  const title = selectedTargetLabel(target, steps, run);
  const flattenInlineExecutionChrome =
    activeInspection.mode === "execution" &&
    (target.type === "step" || target.type === "agentInvocation");
  let content: ReactNode;

  if (target.type === "step") {
    const step = steps.find((item) => item.index === target.stepIndex);
    content = step ? (
      <StepEvidence pane={activeInspection.pane} step={step} />
    ) : null;
  } else if (target.type === "agentInvocation") {
    const match = findAgentInvocation(steps, target.invocationId);
    content = match ? (
      <InvocationEvidence
        invocation={match.invocation}
        pane={activeInspection.pane}
      />
    ) : null;
  } else if (target.type === "operationInvocation") {
    const invocation = findOperationInvocation(steps, target.invocationId);
    content = invocation ? (
      <OperationEvidence invocation={invocation} pane={activeInspection.pane} />
    ) : null;
  } else if (activeInspection.pane === "error") {
    content = run.error ? (
      <Alert variant="destructive">
        <AlertCircle />
        <AlertTitle>Run failed</AlertTitle>
        <AlertDescription>{run.error}</AlertDescription>
      </Alert>
    ) : (
      <div className="rounded-lg border border-border/70 bg-card/70 p-4 text-sm text-muted-foreground shadow-ui-xs">
        No run-level error recorded.
      </div>
    );
  } else if (activeInspection.pane === "input") {
    content =
      activeInspection.mode === "inputs" ? (
        <div className="rounded-lg border border-border/70 bg-card/70 p-4 text-sm text-muted-foreground shadow-ui-xs">
          Select an input field to inspect raw detail.
        </div>
      ) : (
        <RunPayloadPane
          label="Run input"
          testId="runs-detail-input"
          value={run.input}
        />
      );
  } else {
    content =
      activeInspection.mode === "outputs" ? (
        <div className="rounded-lg border border-border/70 bg-card/70 p-4 text-sm text-muted-foreground shadow-ui-xs">
          Select an output field to inspect raw detail.
        </div>
      ) : (
        <RunFinalOutputPane run={run} />
      );
  }

  return (
    <div
      className={cn(
        "grid min-w-0 gap-3",
        flattenInlineExecutionChrome
          ? null
          : "rounded-lg border bg-card/80 p-3",
      )}
      data-testid={testId}
    >
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold tracking-tight">{title}</h2>
            <Badge variant="outline">
              {inspectionTargetKindLabel(activeInspection.target)}
            </Badge>
            <Badge variant="secondary">
              {inspectionPaneLabel(activeInspection.pane)}
            </Badge>
          </div>
        </div>
        <div className="flex min-w-0 flex-col gap-2 sm:items-end">
          {activeInspection.target.type !== "run" ? (
            <EvidencePaneNav
              activeInspection={activeInspection}
              onSelect={onSelect}
            />
          ) : null}
        </div>
      </div>
      <div
        className="min-w-0 overflow-hidden"
        data-testid="runs-active-evidence-viewer"
      >
        {content ?? (
          <div className="rounded-lg border border-border/70 bg-card/70 p-4 text-sm text-muted-foreground shadow-ui-xs">
            Selected evidence is no longer available.
          </div>
        )}
      </div>
    </div>
  );
}
