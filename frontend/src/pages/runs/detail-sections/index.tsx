import {
  applyNodeChanges,
  Background,
  BackgroundVariant,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeChange,
  type NodeProps,
  type Viewport,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Activity, AlertCircle, FileText, GitBranch, Download } from "lucide-react";
import { useCallback, useEffect, useState, type KeyboardEvent, type ReactNode } from "react";
import { Link } from "react-router";

import { EvidenceCluster } from "@/components/shared/evidence-cluster";
import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/components/ui/utils";
import { formatDateTime } from "@/lib/format";
import type {
  RunAgentInvocationRead,
  RunGraphMetadata,
  RunMemoryArtifactRead,
  RunMemoryEventRead,
  RunMemoryEventType,
  RunOperationInvocationRead,
  RunRead,
  RunStepRead,
  RunStepStatus,
} from "@/lib/types/run";

import { stringifyJson } from "../../platform-resource-helpers";
import {
  diagnosticsFromDraftReadiness,
  formatQueueReasonTitle,
  getRunForkAvailability,
  progressForInvocations,
  sortedInvocations,
  sortedOperationInvocations,
  type TraceSpanEntry,
} from "../detail-helpers";
import {
  inspectionPaneLabel,
  inspectionPanesForTarget,
  inspectionTargetKindLabel,
  type RunInspectionMode,
  type RunInspectionPane,
  type RunInspectionState,
  type RunInspectionTarget,
} from "../inspection-state";

export { RunForkDialog } from "./fork-dialog";
export {
  RunEvidenceAvailabilitySection,
  RunFinalOutputPane,
  RunInputWorkspace,
  RunOutputWorkspace,
  RunOverviewWorkspace,
} from "./payload-sections";
export { RunContextStrip, RunRuntimeProfileSection, RunTokensWorkspace } from "./runtime";

import {
  JsonBlock,
  RunEvidenceAvailabilitySection,
  RunFinalOutputPane,
  RunInputWorkspace,
  RunOutputWorkspace,
  RunOverviewWorkspace,
  RunPayloadPane,
} from "./payload-sections";
import { CAPABILITY_LABELS, CAPABILITY_ORDER, RunRuntimeProfileSection, RunTokensWorkspace } from "./runtime";
import {
  CollapsibleConsoleSection,
  CollapsibleDetailPanel,
  CompactModeEmptyState,
  DetailGrid,
  RunDetailEmptyState,
  RunDetailSectionBlock,
  RunDetailTableFrame,
  formatOptional,
  formatTimestamp,
  statusVariant,
  type DetailItem,
} from "./shared";

type MemoryEventGroupKey =
  | "retrievedContext"
  | "memoryWrites"
  | "reviewFollowUp"
  | "auditTrail";

type MemoryEventGroupDefinition = {
  description: string;
  emptyCopy: string;
  eventTypes: RunMemoryEventType[];
  key: MemoryEventGroupKey;
  title: string;
};

type LineageDiagramNodeData = {
  [key: string]: unknown;
  details: DetailItem[];
  eyebrow: string;
  testId: string;
  title: ReactNode;
  tone?: "current" | "source";
};

type LineageDiagramNode = Node<LineageDiagramNodeData, "lineage">;
type LineageDiagramEdge = Edge;

const LINEAGE_NODE_WIDTH = 192;
const LINEAGE_NODE_GAP = 56;
const LINEAGE_NODE_Y = 24;
const LINEAGE_INITIAL_VIEWPORT: Viewport = { x: 0, y: 0, zoom: 1 };
const LINEAGE_FIT_VIEW_MAX_ZOOM = 1;
const LINEAGE_MAX_ZOOM = 1.8;
const LINEAGE_CANVAS_HEIGHT_CLASS = "h-80";
const MEMORY_EVENT_GROUPS: MemoryEventGroupDefinition[] = [
  {
    description: "Memory context used by this run.",
    emptyCopy: "No retrieval memory events recorded.",
    eventTypes: ["retrieved", "injected"],
    key: "retrievedContext",
    title: "Retrieved context",
  },
  {
    description: "Memory writes and reuse decisions.",
    emptyCopy: "No memory write or reuse events recorded.",
    eventTypes: ["written", "reused", "superseded"],
    key: "memoryWrites",
    title: "Memory written and reused",
  },
  {
    description: "Memory review and follow-up events.",
    emptyCopy: "No review events recorded.",
    eventTypes: ["reviewed"],
    key: "reviewFollowUp",
    title: "Review and follow-up",
  },
  {
    description: "Memory failures and uncategorized events.",
    emptyCopy: "No audit-only events recorded.",
    eventTypes: ["failed"],
    key: "auditTrail",
    title: "Audit trail",
  },
];

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

function canForkInvocation(
  run: RunRead,
  step: RunStepRead,
  invocation: RunAgentInvocationRead,
): boolean {
  return getRunForkAvailability(run, [step], step.index, invocation.id)
    .isAvailable;
}

function lineageNodePosition(index: number) {
  return {
    x: index * (LINEAGE_NODE_WIDTH + LINEAGE_NODE_GAP),
    y: LINEAGE_NODE_Y,
  };
}

function LineageNode({ data }: NodeProps<LineageDiagramNode>) {
  return (
    <div
      className={cn(
        "nopan pointer-events-auto w-48 rounded-xl border bg-card p-3 text-left text-card-foreground shadow-sm",
        data.tone === "current" && "border-primary/30 bg-primary/5",
        data.tone === "source" && "border-positive/30 bg-positive/5",
      )}
      data-testid={data.testId}
    >
      <Handle
        className="size-1.5 border-border bg-muted-foreground"
        isConnectable={false}
        position={Position.Left}
        type="target"
      />
      <div className="space-y-2">
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            {data.eyebrow}
          </p>
          <p className="mt-0.5 break-words text-sm font-medium leading-5 text-foreground">
            {data.title}
          </p>
        </div>
        <dl className="space-y-1.5 text-xs">
          {data.details.map((item) => (
            <div className="min-w-0" key={item.label}>
              <dt className="font-medium uppercase tracking-wide text-muted-foreground">
                {item.label}
              </dt>
              <dd className="mt-0.5 break-words text-foreground">
                {formatOptional(item.value)}
              </dd>
            </div>
          ))}
        </dl>
      </div>
      <Handle
        className="size-1.5 border-border bg-muted-foreground"
        isConnectable={false}
        position={Position.Right}
        type="source"
      />
    </div>
  );
}

const lineageNodeTypes = { lineage: LineageNode };

const lineageDefaultEdgeOptions: Partial<LineageDiagramEdge> = {
  markerEnd: { type: MarkerType.ArrowClosed },
  style: { stroke: "var(--border)", strokeWidth: 1.5 },
  type: "smoothstep",
};

function LineageDiagram({
  ariaLabel,
  edges,
  nodes,
  testId,
}: {
  ariaLabel: string;
  edges: LineageDiagramEdge[];
  nodes: LineageDiagramNode[];
  testId: string;
}) {
  const [interactiveNodes, setInteractiveNodes] = useState(nodes);
  const [viewport, setViewport] = useState(LINEAGE_INITIAL_VIEWPORT);

  useEffect(() => {
    setInteractiveNodes((currentNodes) => {
      const currentNodesById = new Map(
        currentNodes.map((node) => [node.id, node]),
      );
      const hasSameNodes =
        currentNodes.length === nodes.length &&
        nodes.every((node) => currentNodesById.has(node.id));

      if (!hasSameNodes) {
        return nodes;
      }

      return nodes.map((node) => ({
        ...node,
        position: currentNodesById.get(node.id)?.position ?? node.position,
      }));
    });
  }, [nodes]);

  const handleNodesChange = useCallback(
    (changes: NodeChange<LineageDiagramNode>[]) => {
      setInteractiveNodes((currentNodes) =>
        applyNodeChanges(changes, currentNodes),
      );
    },
    [],
  );

  const handleViewportChange = useCallback((nextViewport: Viewport) => {
    setViewport(nextViewport);
  }, []);

  return (
    <div
      className={cn(
        LINEAGE_CANVAS_HEIGHT_CLASS,
        "overflow-hidden rounded-xl border bg-muted/20 [&_.react-flow__edge-text]:fill-muted-foreground [&_.react-flow__edge-textbg]:fill-background",
      )}
      data-testid={testId}
    >
      <ReactFlow
        aria-label={ariaLabel}
        autoPanOnNodeDrag={false}
        connectOnClick={false}
        defaultEdgeOptions={lineageDefaultEdgeOptions}
        deleteKeyCode={null}
        edges={edges}
        edgesFocusable={false}
        elementsSelectable={false}
        fitView
        fitViewOptions={{ maxZoom: LINEAGE_FIT_VIEW_MAX_ZOOM, padding: 0.22 }}
        maxZoom={LINEAGE_MAX_ZOOM}
        minZoom={0.55}
        multiSelectionKeyCode={null}
        nodeTypes={lineageNodeTypes}
        nodes={interactiveNodes}
        nodesConnectable={false}
        nodesDraggable
        nodesFocusable={false}
        onNodesChange={handleNodesChange}
        onViewportChange={handleViewportChange}
        panOnDrag={false}
        preventScrolling
        proOptions={{ hideAttribution: true }}
        selectNodesOnDrag={false}
        selectionKeyCode={null}
        viewport={viewport}
        zoomOnDoubleClick
        zoomOnPinch
        zoomOnScroll
      >
        <Background
          color="var(--border)"
          gap={16}
          size={1}
          variant={BackgroundVariant.Dots}
        />
      </ReactFlow>
    </div>
  );
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

function SourceRunLink({
  children,
  runId,
}: {
  children: ReactNode;
  runId: number | null;
}) {
  if (!runId) {
    return <>{children}</>;
  }

  return (
    <Link
      className="nodrag nopan text-primary underline-offset-4 hover:underline"
      to={`/runs/${runId}`}
    >
      {children}
    </Link>
  );
}

function SourceStepLink({ step }: { step: RunStepRead }) {
  if (!step.sourceRunId || step.sourceStepIndex === null) {
    return "Not recorded";
  }

  return (
    <Link
      className="nodrag nopan text-primary underline-offset-4 hover:underline"
      to={`/runs/${step.sourceRunId}#step-${step.sourceStepIndex}`}
    >
      Run #{step.sourceRunId} step {step.sourceStepIndex}
    </Link>
  );
}

function SourceInvocationLink({
  invocation,
  step,
}: {
  invocation: RunAgentInvocationRead;
  step: RunStepRead;
}) {
  if (invocation.sourceInvocationId === null) {
    return "Not recorded";
  }

  if (!step.sourceRunId) {
    return `Invocation #${invocation.sourceInvocationId}`;
  }

  return (
    <Link
      className="text-primary underline-offset-4 hover:underline"
      to={`/runs/${step.sourceRunId}#invocation-${invocation.sourceInvocationId}`}
    >
      Invocation #{invocation.sourceInvocationId}
    </Link>
  );
}

function SourceOperationInvocationLink({
  invocation,
}: {
  invocation: RunOperationInvocationRead;
}) {
  if (invocation.sourceOperationInvocationId === null) {
    return "Not recorded";
  }

  if (!invocation.sourceRunId) {
    return `Operation invocation #${invocation.sourceOperationInvocationId}`;
  }

  return (
    <Link
      className="text-primary underline-offset-4 hover:underline"
      to={`/runs/${invocation.sourceRunId}#operation-invocation-${invocation.sourceOperationInvocationId}`}
    >
      Operation invocation #{invocation.sourceOperationInvocationId}
    </Link>
  );
}

function memoryWorkspacePath(
  artifact: RunMemoryArtifactRead,
  run: RunRead,
): string | null {
  const packageKey = run.packageProvenance?.workflowPackageKey;
  if (!packageKey) {
    return null;
  }

  const params = new URLSearchParams({
    memoryId: artifact.memoryId,
    packageKey,
    runId: String(run.id),
  });
  if (artifact.provenance.workflowKey) {
    params.set("workflowKey", artifact.provenance.workflowKey);
  }
  if (artifact.provenance.agentKey) {
    params.set("agentKey", artifact.provenance.agentKey);
  }
  return `/memory?${params.toString()}`;
}

function memoryProvenanceLabel(artifact: RunMemoryArtifactRead): string {
  const provenance = artifact.provenance;
  const workflow = provenance.workflowKey
    ? `workflow ${provenance.workflowKey}`
    : null;

  return [
    `${provenance.agentKey}@${provenance.agentVersion}`,
    workflow,
    provenance.slot ? `slot ${provenance.slot}` : null,
    `run #${provenance.runId}`,
  ]
    .filter(Boolean)
    .join(" · ");
}

function hasRecordEntries(value: Record<string, unknown>): boolean {
  return Object.keys(value).length > 0;
}

function formatMemoryEventType(eventType: RunMemoryEventType): string {
  const labels: Record<RunMemoryEventType, string> = {
    failed: "Failed",
    injected: "Injected",
    retrieved: "Retrieved",
    reused: "Reused",
    reviewed: "Reviewed",
    superseded: "Superseded",
    written: "Written",
  };

  return labels[eventType];
}

function groupKeyForMemoryEvent(
  eventType: RunMemoryEventType,
): MemoryEventGroupKey {
  return (
    MEMORY_EVENT_GROUPS.find((definition) =>
      definition.eventTypes.includes(eventType),
    )?.key ?? "auditTrail"
  );
}

function groupedMemoryEvents(
  events: RunMemoryEventRead[],
): Record<MemoryEventGroupKey, RunMemoryEventRead[]> {
  const grouped: Record<MemoryEventGroupKey, RunMemoryEventRead[]> = {
    auditTrail: [],
    memoryWrites: [],
    retrievedContext: [],
    reviewFollowUp: [],
  };

  for (const event of events) {
    grouped[groupKeyForMemoryEvent(event.eventType)].push(event);
  }

  return grouped;
}

function memoryEventDetails(event: RunMemoryEventRead): DetailItem[] {
  const items: DetailItem[] = [
    { label: "Event", value: `#${event.id}` },
    { label: "Recorded", value: formatDateTime(event.createdAt) },
  ];

  if (event.runStepId) {
    items.push({ label: "Run step", value: `#${event.runStepId}` });
  }
  if (event.stepId) {
    items.push({ label: "Step key", value: event.stepId });
  }
  if (event.runAgentInvocationId) {
    items.push({
      label: "Agent invocation",
      value: `#${event.runAgentInvocationId}`,
    });
  }
  if (event.runOperationInvocationId) {
    items.push({
      label: "Operation invocation",
      value: `#${event.runOperationInvocationId}`,
    });
  }
  if (event.invocationId) {
    items.push({ label: "Invocation key", value: event.invocationId });
  }
  if (event.memoryId) {
    items.push({ label: "Memory id", value: event.memoryId });
  }
  if (event.revisionId) {
    items.push({ label: "Revision id", value: event.revisionId });
  }
  if (event.retrievalMode) {
    items.push({ label: "Retrieval mode", value: event.retrievalMode });
  }
  if (event.traceSpanId) {
    items.push({ label: "Trace span", value: event.traceSpanId });
  }

  return items;
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
  if (left.type === "memoryArtifact" && right.type === "memoryArtifact") {
    return left.memoryId === right.memoryId;
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
  if (target.type === "memoryArtifact") {
    return (
      run.memoryArtifacts.find(
        (artifact) => artifact.memoryId === target.memoryId,
      )?.summary ?? target.memoryId
    );
  }
  return `Run #${run.id}`;
}

function hasRunLineageEvidence({
  copiedInvocations,
  copiedSteps,
  run,
}: {
  copiedInvocations: number;
  copiedSteps: number;
  run: RunRead;
}): boolean {
  return Boolean(
    run.sourceRunId ||
    (run.lineageRootRunId && run.lineageRootRunId !== run.id) ||
    run.replayStepIndex !== null ||
    copiedSteps > 0 ||
    copiedInvocations > 0,
  );
}

export function RunLineageWorkspace({
  copiedInvocations,
  copiedSteps,
  isCurrentFork,
  plannedInvocations,
  plannedSteps,
  run,
}: {
  copiedInvocations: number;
  copiedSteps: number;
  isCurrentFork: boolean;
  plannedInvocations: number;
  plannedSteps: number;
  run: RunRead;
}) {
  if (!hasRunLineageEvidence({ copiedInvocations, copiedSteps, run })) {
    return (
      <section
        className="grid min-w-0 gap-3"
        data-testid="runs-lineage-workspace"
      >
        <RunDetailSectionBlock
          blockId="lineage"
          description="Fork, snapshot, and historical boundaries appear here when the run has upstream lineage."
          icon={GitBranch}
          title="Lineage"
        >
          <CompactModeEmptyState testId="runs-lineage-empty">
            No fork, snapshot replay, copied-step, or historical lineage
            boundary is recorded for this run.
          </CompactModeEmptyState>
        </RunDetailSectionBlock>
      </section>
    );
  }

  return (
    <section
      className="grid min-w-0 gap-3"
      data-testid="runs-lineage-workspace"
    >
      <RunDetailSectionBlock
        blockId="lineage"
        description="Lineage boundaries stay isolated from execution rows with fork, snapshot, and historical context."
        icon={GitBranch}
        title="Lineage"
      >
        <EvidenceCluster
          items={[
            {
              label: "Source",
              value: run.sourceRunId
                ? `Run #${run.sourceRunId}`
                : "Snapshot root",
              description: isCurrentFork
                ? "Current fork lineage"
                : "Historical or original lineage boundary",
            },
            {
              label: "Resume",
              value: `Step ${run.resumeStepIndex}`,
              description:
                run.replayStepIndex === null
                  ? "No replay source step recorded"
                  : `Replay source step ${run.replayStepIndex}`,
            },
            {
              label: "Steps",
              value: `${copiedSteps} copied · ${plannedSteps} planned`,
              description: "Snapshot copy versus executed run plan.",
            },
            {
              label: "Invocations",
              value: `${copiedInvocations} copied · ${plannedInvocations} planned/executed`,
              description:
                "Invocation-level inherited output or input boundaries.",
            },
          ]}
          layout="grid"
        />
      </RunDetailSectionBlock>
      <RunLineageEvidence
        copiedInvocations={copiedInvocations}
        copiedSteps={copiedSteps}
        isCurrentFork={isCurrentFork}
        plannedInvocations={plannedInvocations}
        plannedSteps={plannedSteps}
        run={run}
      />
    </section>
  );
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
  const forkCandidates = steps.flatMap((step) =>
    step.status === "succeeded"
      ? sortedInvocations(step.invocations).filter(
          (invocation) =>
            invocation.status === "succeeded" && invocation.persistedAt,
        )
      : [],
  );

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
    ...(run.targetKind === "workflowPackage" &&
    run.status === "succeeded" &&
    forkCandidates.length === 0
      ? [
          {
            field: "fork.invocation",
            issue:
              "No succeeded persisted agent invocation is available for invocation-specific fork creation.",
            key: "fork-no-candidate",
            severity: "warning" as const,
            source: "Fork safety",
            title: "Fork target unavailable",
          },
        ]
      : []),
  ];
}

export function RunDiagnosticsWorkspace({
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
        <RunDetailSectionBlock
          blockId="diagnostics"
          description="Warnings, failures, unsupported capabilities, and retry/fork safety checks appear here."
          icon={AlertCircle}
          title="Diagnostics"
        >
          <CompactModeEmptyState testId="runs-diagnostics-empty">
            No run diagnostics, queue warnings, runtime capability warnings, or
            safety blockers are recorded.
          </CompactModeEmptyState>
        </RunDetailSectionBlock>
      </section>
    );
  }

  return (
    <section
      className="grid min-w-0 gap-3"
      data-testid="runs-diagnostics-workspace"
    >
      <RunDetailSectionBlock
        blockId="diagnostics"
        description="Warnings stay visually separate from destructive failures so degraded runs are not confused with failed ones."
        icon={AlertCircle}
        title="Diagnostics"
        tone={errorCount > 0 ? "danger" : "warning"}
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
      </RunDetailSectionBlock>
    </section>
  );
}

export function RunMemoryWorkspace({ run }: { run: RunRead }) {
  const hasEvents = run.memoryEvents.length > 0;
  const hasArtifacts = run.memoryArtifacts.length > 0;

  if (!hasEvents && !hasArtifacts) {
    return (
      <section
        className="grid min-w-0 gap-3"
        data-testid="runs-memory-workspace"
      >
        <RunDetailSectionBlock
          blockId="memory"
          description="Memory retrieval, write, review, audit, and compact artifact evidence appears here when recorded."
          icon={FileText}
          title="Memory"
        >
          <CompactModeEmptyState testId="runs-memory-empty">
            No retrieval, write, review, audit, or compact memory artifact
            evidence was recorded for this run.
          </CompactModeEmptyState>
        </RunDetailSectionBlock>
      </section>
    );
  }

  return (
    <section className="grid min-w-0 gap-3" data-testid="runs-memory-workspace">
      <RunDetailSectionBlock
        blockId="memory"
        description="Memory retrieval, write, review, audit, and compact artifact evidence appears here when recorded."
        icon={FileText}
        title="Memory"
      >
        <RunMemoryEvidence run={run} />
      </RunDetailSectionBlock>
    </section>
  );
}

export function RunAuditEvidenceSection({
  activeInspection,
  copiedInvocations,
  copiedSteps,
  isCurrentFork,
  onOpenFork,
  onSelect,
  plannedInvocations,
  plannedSteps,
  run,
  steps,
  traceSpanEntries,
}: {
  activeInspection: RunInspectionState;
  copiedInvocations: number;
  copiedSteps: number;
  isCurrentFork: boolean;
  onOpenFork: (stepIndex: number, invocationId: number) => void;
  onSelect: (
    target: RunInspectionTarget,
    pane?: RunInspectionPane,
    mode?: RunInspectionMode,
  ) => void;
  plannedInvocations: number;
  plannedSteps: number;
  run: RunRead;
  steps: RunStepRead[];
  traceSpanEntries: TraceSpanEntry[];
}) {
  const groupedEvents = groupedMemoryEvents(run.memoryEvents ?? []);
  const reportAuditLinks = run.memoryArtifacts.filter(
    (artifact) => artifact.auditLinks?.report,
  ).length;
  const rows: Array<{
    category: string;
    id: string;
    pane?: RunInspectionPane;
    summary: ReactNode;
    target: RunInspectionTarget;
    title: string;
    tone?: "secondary" | "destructive" | "outline";
  }> = [
    {
      category: "Payload",
      id: "payload-output",
      pane: "finalOutput",
      summary: "Final output payload",
      target: { type: "run" },
      title: "Final output",
      tone: "outline",
    },
    {
      category: "Payload",
      id: "payload-input",
      pane: "input",
      summary: "Launch input captured",
      target: { type: "run" },
      title: "Run input",
      tone: "secondary",
    },
    {
      category: "Memory",
      id: "memory-groups",
      pane: "memory",
      summary: `${run.memoryEvents.length} event${run.memoryEvents.length === 1 ? "" : "s"} · ${groupedEvents.retrievedContext.length} retrieved · ${groupedEvents.memoryWrites.length} write/reuse · ${groupedEvents.reviewFollowUp.length} review · ${groupedEvents.auditTrail.length} audit`,
      target: { type: "run" },
      title: "Memory event groups",
      tone: run.memoryEvents.length > 0 ? "secondary" : "outline",
    },
    ...traceSpanEntries.map((entry) => ({
      category: "Trace span",
      id: `trace-${entry.invocationKind}-${entry.invocationId}`,
      pane: "output" as RunInspectionPane,
      summary: `Step ${entry.stepIndex} · ${entry.slot}/${entry.spanId}`,
      target:
        entry.invocationKind === "operation"
          ? ({
              type: "operationInvocation",
              invocationId: entry.invocationId,
            } satisfies RunInspectionTarget)
          : ({
              type: "agentInvocation",
              invocationId: entry.invocationId,
            } satisfies RunInspectionTarget),
      title:
        entry.invocationKind === "operation"
          ? `Operation invocation #${entry.invocationId}`
          : `Agent invocation #${entry.invocationId}`,
      tone: "secondary" as const,
    })),
    ...run.memoryArtifacts.map((artifact) => ({
      category: artifact.auditLinks?.report ? "Report artifact" : "Artifact",
      id: `artifact-${artifact.memoryId}`,
      pane: "details" as RunInspectionPane,
      summary: `${artifact.status} · ${memoryProvenanceLabel(artifact)}`,
      target: {
        type: "memoryArtifact" as const,
        memoryId: artifact.memoryId,
      },
      title: artifact.summary,
      tone: artifact.auditLinks?.report
        ? ("secondary" as const)
        : ("outline" as const),
    })),
  ];

  return (
    <CollapsibleConsoleSection
      blockId="metadata"
      description="Trace, payload, memory, and report evidence rows expand inline with contextual raw detail."
      icon={FileText}
      title="Metadata"
    >
      <div className="grid min-w-0 gap-3">
        <ResourceStatusStrip
          items={[
            {
              label: "Trace spans",
              value: traceSpanEntries.length,
              tone: traceSpanEntries.length > 0 ? "success" : "warning",
            },
            {
              label: "Memory events",
              value: run.memoryEvents.length,
            },
            {
              label: "Artifacts",
              value: run.memoryArtifacts.length,
            },
            {
              label: "Report links",
              value: reportAuditLinks,
            },
          ]}
        />
        <RunDetailTableFrame testId="runs-audit-table">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Evidence row</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Summary</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.flatMap((row) => {
                const targetMatches = isInspectionTargetEqual(
                  activeInspection.target,
                  row.target,
                );
                const paneMatches =
                  !row.pane || activeInspection.pane === row.pane;
                const isActive =
                  activeInspection.selected !== false &&
                  targetMatches &&
                  (row.target.type === "run" ? paneMatches : true);
                const shouldRenderInline =
                  isActive && activeInspection.mode === "metadata";
                const selectRow = () =>
                  onSelect(row.target, row.pane, "metadata");
                const dataRow = (
                  <TableRow
                    aria-label={`${row.title} evidence row`}
                    className="cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    data-state={isActive ? "selected" : undefined}
                    data-testid={`runs-audit-row-${row.id}`}
                    key={row.id}
                    onClick={selectRow}
                    onKeyDown={(event) =>
                      handleSelectableRowKeyDown(event, selectRow)
                    }
                    role="button"
                    tabIndex={0}
                  >
                    <TableCell className="min-w-56 whitespace-normal align-top">
                      <span className="block w-full rounded-md px-2 py-1.5 text-left font-medium text-foreground">
                        {row.title}
                      </span>
                    </TableCell>
                    <TableCell className="align-top">
                      <Badge variant={row.tone ?? "outline"}>
                        {row.category}
                      </Badge>
                    </TableCell>
                    <TableCell className="min-w-80 whitespace-normal align-top text-muted-foreground">
                      {row.summary}
                    </TableCell>
                  </TableRow>
                );
                if (!shouldRenderInline) {
                  return [dataRow];
                }
                return [
                  dataRow,
                  <TableRow key={`${row.id}-inline`}>
                    <TableCell
                      className="whitespace-normal p-3 align-top"
                      colSpan={3}
                    >
                      <RunInlineEvidence
                        activeInspection={activeInspection}
                        copiedInvocations={copiedInvocations}
                        copiedSteps={copiedSteps}
                        isCurrentFork={isCurrentFork}
                        onOpenFork={onOpenFork}
                        onSelect={onSelect}
                        plannedInvocations={plannedInvocations}
                        plannedSteps={plannedSteps}
                        run={run}
                        steps={steps}
                        testId={`runs-audit-row-${row.id}-inline-evidence`}
                      />
                    </TableCell>
                  </TableRow>,
                ];
              })}
            </TableBody>
          </Table>
        </RunDetailTableFrame>
      </div>
    </CollapsibleConsoleSection>
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

export function ExecutionOutline({
  activeInspection,
  copiedInvocations,
  copiedSteps,
  isCurrentFork,
  onOpenFork,
  onSelect,
  plannedInvocations,
  plannedSteps,
  run,
  steps,
  traceSpanEntries,
}: {
  activeInspection: RunInspectionState;
  copiedInvocations: number;
  copiedSteps: number;
  isCurrentFork: boolean;
  onOpenFork: (stepIndex: number, invocationId: number) => void;
  onSelect: (
    target: RunInspectionTarget,
    pane?: RunInspectionPane,
    mode?: RunInspectionMode,
  ) => void;
  plannedInvocations: number;
  plannedSteps: number;
  run: RunRead;
  steps: RunStepRead[];
  traceSpanEntries: TraceSpanEntry[];
}) {
  const shouldRenderExecutionInline =
    activeInspection.mode !== "metadata" &&
    activeInspection.target.type !== "run" &&
    activeInspection.target.type !== "memoryArtifact";
  const renderInlineEvidenceRow = (key: string, testId: string) => (
    <TableRow key={key}>
      <TableCell className="whitespace-normal p-3 align-top" colSpan={6}>
        <RunInlineEvidence
          activeInspection={activeInspection}
          copiedInvocations={copiedInvocations}
          copiedSteps={copiedSteps}
          isCurrentFork={isCurrentFork}
          onOpenFork={onOpenFork}
          onSelect={onSelect}
          plannedInvocations={plannedInvocations}
          plannedSteps={plannedSteps}
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
      <CollapsibleConsoleSection
        blockId="execution-steps"
        description="Step and invocation rows stay visible while selected row detail expands inline."
        icon={Activity}
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
                              {invocation.operationKey} · operation forks are
                              not supported in this phase
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
      </CollapsibleConsoleSection>
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

function RunLineageEvidence({
  copiedInvocations,
  copiedSteps,
  isCurrentFork,
  plannedInvocations,
  plannedSteps,
  run,
}: {
  copiedInvocations: number;
  copiedSteps: number;
  isCurrentFork: boolean;
  plannedInvocations: number;
  plannedSteps: number;
  run: RunRead;
}) {
  const lineageRootRunId = run.lineageRootRunId ?? run.id;
  const sourceRunValue = run.sourceRunId ? (
    <SourceRunLink runId={run.sourceRunId}>
      Run #{run.sourceRunId}
    </SourceRunLink>
  ) : (
    "Original run"
  );
  const sourceStepValue =
    run.replayStepIndex === null
      ? "Not recorded"
      : `Step ${run.replayStepIndex}`;
  const sourceKindLabel = run.sourceRunId
    ? isCurrentFork
      ? "Fork source"
      : "Historical lineage source"
    : "Original source";
  const sourceStepLabel = isCurrentFork
    ? "Fork source step"
    : "Historical lineage step";
  const nodes: LineageDiagramNode[] = [
    {
      data: {
        details: [{ label: "Lineage root", value: `Run #${lineageRootRunId}` }],
        eyebrow: "Root",
        testId: "runs-lineage-node-root",
        title: `Run #${lineageRootRunId}`,
      },
      id: "lineage-root",
      position: lineageNodePosition(0),
      type: "lineage",
    },
    {
      data: {
        details: [
          { label: "Source run", value: sourceRunValue },
          { label: sourceStepLabel, value: sourceStepValue },
        ],
        eyebrow: sourceKindLabel,
        testId: "runs-lineage-node-source",
        title: run.sourceRunId ? `Run #${run.sourceRunId}` : "Original run",
        tone: "source",
      },
      id: "lineage-source",
      position: lineageNodePosition(1),
      type: "lineage",
    },
    {
      data: {
        details: [
          { label: "Resume boundary", value: `Step ${run.resumeStepIndex}` },
          {
            label: "Step origins",
            value: `${copiedSteps} copied · ${plannedSteps} planned`,
          },
          {
            label: "Invocation origins",
            value: `${copiedInvocations} copied · ${plannedInvocations} planned/executed`,
          },
        ],
        eyebrow: "Current run",
        testId: "runs-lineage-node-current",
        title: `Run #${run.id}`,
        tone: "current",
      },
      id: "lineage-current",
      position: lineageNodePosition(2),
      type: "lineage",
    },
  ];
  const edges: LineageDiagramEdge[] = [
    {
      id: "root-source",
      label: "lineage root",
      source: "lineage-root",
      target: "lineage-source",
    },
    {
      id: "source-current",
      label: run.sourceRunId
        ? isCurrentFork
          ? "fork / resume"
          : "historical lineage / resume"
        : "original / resume",
      source: "lineage-source",
      target: "lineage-current",
    },
  ];

  return (
    <Card data-testid="runs-lineage-summary">
      <CardHeader>
        <CardTitle className="text-base">Lineage</CardTitle>
        <CardDescription>
          {isCurrentFork ? "Fork" : "Historical lineage"} diagram.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {run.sourceRunId && !isCurrentFork ? (
          <Alert data-testid="runs-historical-lineage">
            <GitBranch />
            <AlertTitle>Historical lineage</AlertTitle>
            <AlertDescription>Read-only audit lineage.</AlertDescription>
          </Alert>
        ) : null}
        <LineageDiagram
          ariaLabel="Run lineage diagram"
          edges={edges}
          nodes={nodes}
          testId="runs-lineage-diagram"
        />
      </CardContent>
    </Card>
  );
}

function MemoryTextEvidence({
  label,
  testId,
  value,
}: {
  label: string;
  testId?: string;
  value: string;
}) {
  return (
    <div
      className="rounded-md border bg-muted/20 p-3 text-sm"
      data-testid={testId}
    >
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 whitespace-pre-wrap break-words text-foreground">
        {value}
      </p>
    </div>
  );
}

function MemoryEventCard({ event }: { event: RunMemoryEventRead }) {
  return (
    <Card className="gap-3" data-testid={`runs-memory-event-${event.id}`}>
      <CardHeader className="px-4 pt-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">
            {formatMemoryEventType(event.eventType)}
          </Badge>
          {event.memoryId ? (
            <Badge variant="outline">{event.memoryId}</Badge>
          ) : null}
          {event.revisionId ? (
            <Badge variant="outline">{event.revisionId}</Badge>
          ) : null}
        </div>
        <CardDescription>{formatDateTime(event.createdAt)}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 px-4 pb-4">
        <DetailGrid items={memoryEventDetails(event)} />
        {event.excerpt ? (
          <MemoryTextEvidence
            label="Excerpt"
            testId={`runs-memory-event-${event.id}-excerpt`}
            value={event.excerpt}
          />
        ) : null}
        {event.injectedText ? (
          <MemoryTextEvidence
            label="Injected text"
            testId={`runs-memory-event-${event.id}-injected-text`}
            value={event.injectedText}
          />
        ) : null}
        {hasRecordEntries(event.filters) ? (
          <JsonBlock
            label="Filters"
            testId={`runs-memory-event-${event.id}-filters`}
            value={event.filters}
          />
        ) : null}
        {hasRecordEntries(event.budget) ? (
          <JsonBlock
            label="Budget"
            testId={`runs-memory-event-${event.id}-budget`}
            value={event.budget}
          />
        ) : null}
        {hasRecordEntries(event.resultSnapshot) ? (
          <JsonBlock
            label="Result snapshot"
            testId={`runs-memory-event-${event.id}-result`}
            value={event.resultSnapshot}
          />
        ) : null}
        {hasRecordEntries(event.statusSnapshot) ? (
          <JsonBlock
            label="Status snapshot"
            testId={`runs-memory-event-${event.id}-status`}
            value={event.statusSnapshot}
          />
        ) : null}
      </CardContent>
    </Card>
  );
}

function MemoryEventGroupSection({
  definition,
  events,
}: {
  definition: MemoryEventGroupDefinition;
  events: RunMemoryEventRead[];
}) {
  return (
    <CollapsibleDetailPanel
      description={
        <span className="inline-flex min-w-0 flex-wrap items-center gap-2">
          <span>{definition.description}</span>
          <Badge variant="outline">
            {events.length} event{events.length === 1 ? "" : "s"}
          </Badge>
        </span>
      }
      testId={`runs-memory-group-${definition.key}`}
      title={definition.title}
    >
      {events.length > 0 ? (
        <div className="grid gap-3">
          {events.map((event) => (
            <MemoryEventCard event={event} key={event.id} />
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{definition.emptyCopy}</p>
      )}
    </CollapsibleDetailPanel>
  );
}

function MemoryArtifactSummaryCard({
  artifact,
}: {
  artifact: RunMemoryArtifactRead;
}) {
  return (
    <div
      className="rounded-md border bg-muted/20 p-3 text-sm"
      data-testid={`runs-memory-compact-artifact-${artifact.memoryId}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium">{artifact.summary}</p>
          <p className="text-xs text-muted-foreground">
            {artifact.status} · {formatDateTime(artifact.createdAt)}
          </p>
        </div>
        <FileText className="size-4 shrink-0 text-muted-foreground" />
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        {memoryProvenanceLabel(artifact)}
      </p>
    </div>
  );
}

function RunMemoryEvidence({ run }: { run: RunRead }) {
  const memoryEvents = run.memoryEvents ?? [];
  const groupedEvents = groupedMemoryEvents(memoryEvents);
  const hasEvents = memoryEvents.length > 0;
  const hasArtifacts = run.memoryArtifacts.length > 0;

  return (
    <CollapsibleDetailPanel
      description="Run-scoped memory events and compact artifacts."
      testId="runs-memory-evidence"
      title="Run memory evidence"
    >
      {!hasEvents && !hasArtifacts ? (
        <CompactModeEmptyState testId="runs-memory-evidence-empty">
          No retrieval, write, review, audit, or compact memory artifact
          evidence was recorded for this run.
        </CompactModeEmptyState>
      ) : null}

      {hasEvents
        ? MEMORY_EVENT_GROUPS.map((definition) => (
            <MemoryEventGroupSection
              definition={definition}
              events={groupedEvents[definition.key]}
              key={definition.key}
            />
          ))
        : null}
    </CollapsibleDetailPanel>
  );
}

function MemoryArtifactEvidence({
  artifact,
  run,
}: {
  artifact: RunMemoryArtifactRead;
  run: RunRead;
}) {
  const auditReport = artifact.auditLinks?.report;
  const memoryHref = memoryWorkspacePath(artifact, run);

  return (
    <Card data-testid="runs-memory-artifacts">
      <CardHeader>
        <CardTitle className="text-base">Memory artifact</CardTitle>
        <CardDescription>
          Canonical platform memory artifact. Report links, when present, are
          audit actions only and not the memory source of truth.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div
          className="rounded-md border bg-muted/20 p-3 text-sm"
          data-testid={`runs-memory-artifact-${artifact.memoryId}`}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate font-medium">{artifact.summary}</p>
              <p className="text-xs text-muted-foreground">
                {artifact.status} · {formatDateTime(artifact.createdAt)}
              </p>
            </div>
            <FileText className="size-4 shrink-0 text-muted-foreground" />
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            {memoryProvenanceLabel(artifact)}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {graphMetadataLabel(artifact.sourceGraphMetadata)}
          </p>
          {memoryHref || auditReport ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {memoryHref ? (
                <Button asChild size="sm" variant="outline">
                  <Link to={memoryHref}>Open canonical memory</Link>
                </Button>
              ) : null}
              {auditReport ? (
                <Button asChild size="sm" variant="ghost">
                  <Link to={auditReport.url}>Open report</Link>
                </Button>
              ) : null}
              {auditReport ? (
                <Button asChild size="sm" variant="ghost">
                  <a href={auditReport.downloadUrl} download>
                    <Download data-icon="inline-start" />
                    Download
                  </a>
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function StepSummaryEvidence({ step }: { step: RunStepRead }) {
  const metadataItems: DetailItem[] = [
    { label: "Step row", value: `#${step.id}` },
    { label: "Status", value: step.status },
    { label: "Origin", value: step.origin },
    { label: "Source step", value: <SourceStepLink step={step} /> },
    { label: "Graph node", value: graphMetadataLabel(step.graphMetadata) },
    { label: "Started", value: formatTimestamp(step.startedAt) },
    { label: "Finished", value: formatTimestamp(step.finishedAt) },
    { label: "Persisted", value: formatTimestamp(step.persistedAt) },
    { label: "Updated", value: formatDateTime(step.updatedAt) },
  ];

  return (
    <div
      className="min-w-0 space-y-5"
      data-testid={`runs-step-${step.index}-summary`}
    >
      <section
        aria-labelledby={`runs-step-${step.index}-metadata-heading`}
        className="space-y-3"
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
        className="space-y-3"
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

function StepLineageEvidence({ step }: { step: RunStepRead }) {
  const sourceRunValue = step.sourceRunId ? (
    <SourceRunLink runId={step.sourceRunId}>
      Run #{step.sourceRunId}
    </SourceRunLink>
  ) : (
    "Not recorded"
  );
  const sourceStepValue = <SourceStepLink step={step} />;
  const sourceStepRowValue = step.sourceRunStepId
    ? `#${step.sourceRunStepId}`
    : "Not recorded";
  const hasUpstreamStep = Boolean(
    step.sourceRunId && step.sourceStepIndex !== null,
  );
  const nodes: LineageDiagramNode[] = hasUpstreamStep
    ? [
        {
          data: {
            details: [
              { label: "Source run", value: sourceRunValue },
              { label: "Source step", value: sourceStepValue },
              { label: "Source step row", value: sourceStepRowValue },
            ],
            eyebrow: "Upstream",
            testId: `runs-step-${step.index}-lineage-node-source`,
            title:
              step.sourceStepIndex === null
                ? "Source step"
                : `Step ${step.sourceStepIndex}`,
            tone: "source",
          },
          id: "step-source",
          position: lineageNodePosition(0),
          type: "lineage",
        },
        {
          data: {
            details: [{ label: "Origin", value: step.origin }],
            eyebrow: "Current step",
            testId: `runs-step-${step.index}-lineage-node-current`,
            title: `Step ${step.index}`,
            tone: "current",
          },
          id: "step-current",
          position: lineageNodePosition(1),
          type: "lineage",
        },
      ]
    : [
        {
          data: {
            details: [
              { label: "Origin", value: step.origin },
              { label: "Source run", value: sourceRunValue },
              { label: "Source step", value: sourceStepValue },
              { label: "Source step row", value: sourceStepRowValue },
            ],
            eyebrow: "Current step",
            testId: `runs-step-${step.index}-lineage-node-current`,
            title: `Step ${step.index}`,
            tone: "current",
          },
          id: "step-current",
          position: lineageNodePosition(0),
          type: "lineage",
        },
      ];
  const edges: LineageDiagramEdge[] = hasUpstreamStep
    ? [
        {
          id: "source-current",
          label: "provenance",
          source: "step-source",
          target: "step-current",
        },
      ]
    : [];

  return (
    <Card data-testid={`runs-step-${step.index}-lineage-summary`}>
      <CardHeader>
        <CardTitle className="text-base">Step lineage</CardTitle>
        <CardDescription>Step provenance diagram.</CardDescription>
      </CardHeader>
      <CardContent>
        <LineageDiagram
          ariaLabel={`Step ${step.index} provenance lineage diagram`}
          edges={edges}
          nodes={nodes}
          testId={`runs-step-${step.index}-lineage-diagram`}
        />
      </CardContent>
    </Card>
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
    <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground">
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
  if (pane === "lineage") {
    return <StepLineageEvidence step={step} />;
  }
  if (pane === "error") {
    return <StepErrorEvidence step={step} />;
  }

  return <StepSummaryEvidence step={step} />;
}

function InvocationEvidence({
  invocation,
  pane,
  step,
}: {
  invocation: RunAgentInvocationRead;
  pane: RunInspectionPane;
  step: RunStepRead;
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
  if (pane === "lineage") {
    return (
      <DetailGrid
        items={[
          {
            label: "Source invocation",
            value: <SourceInvocationLink invocation={invocation} step={step} />,
          },
          { label: "Input origin", value: invocation.resolvedInputOrigin },
          {
            label: "Output origin",
            value: invocation.outputOrigin ?? "pending",
          },
        ]}
      />
    );
  }
  if (pane === "error") {
    return hasError ? (
      <Alert variant="destructive">
        <AlertCircle />
        <AlertTitle>{invocation.errorCode ?? "Invocation failed"}</AlertTitle>
        <AlertDescription className="space-y-2">
          <p>{invocation.errorMessage ?? "No error message recorded."}</p>
          {invocation.errorDetails.length > 0 ? (
            <pre
              className="max-w-full overflow-x-auto whitespace-pre rounded-md border border-destructive/30 bg-muted/30 p-3 text-xs"
              data-wide-payload="scroll"
            >
              {stringifyJson(invocation.errorDetails)}
            </pre>
          ) : null}
        </AlertDescription>
      </Alert>
    ) : (
      <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground">
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
  if (pane === "lineage") {
    return (
      <DetailGrid
        items={[
          {
            label: "Source operation",
            value: <SourceOperationInvocationLink invocation={invocation} />,
          },
          {
            label: "Source run",
            value: invocation.sourceRunId
              ? `Run #${invocation.sourceRunId}`
              : "Not recorded",
          },
          {
            label: "Source step",
            value:
              invocation.sourceStepIndex === null
                ? "Not recorded"
                : `Step ${invocation.sourceStepIndex}`,
          },
        ]}
      />
    );
  }
  if (pane === "error") {
    return hasError ? (
      <Alert variant="destructive">
        <AlertCircle />
        <AlertTitle>{invocation.errorCode ?? "Operation failed"}</AlertTitle>
        <AlertDescription className="space-y-2">
          <p>{invocation.errorMessage ?? "No error message recorded."}</p>
          {invocation.errorDetails.length > 0 ? (
            <pre
              className="max-w-full overflow-x-auto whitespace-pre rounded-md border border-destructive/30 bg-muted/30 p-3 text-xs"
              data-wide-payload="scroll"
            >
              {stringifyJson(invocation.errorDetails)}
            </pre>
          ) : null}
        </AlertDescription>
      </Alert>
    ) : (
      <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground">
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
  copiedInvocations: number;
  copiedSteps: number;
  isCurrentFork: boolean;
  onOpenFork: (stepIndex: number, invocationId: number) => void;
  onSelect: (
    target: RunInspectionTarget,
    pane?: RunInspectionPane,
    mode?: RunInspectionMode,
  ) => void;
  plannedInvocations: number;
  plannedSteps: number;
  run: RunRead;
  runProgress: number;
  steps: RunStepRead[];
  targetKindLabel: string;
  terminalInvocationsCount: number;
  traceSpanEntries: TraceSpanEntry[];
};

export function RunDetailSectionStack(props: RunDetailSectionStackProps) {
  const {
    activeInspection,
    allInvocationsCount,
    copiedInvocations,
    copiedSteps,
    isCurrentFork,
    onOpenFork,
    onSelect,
    plannedInvocations,
    plannedSteps,
    run,
    runProgress,
    steps,
    targetKindLabel,
    terminalInvocationsCount,
    traceSpanEntries,
  } = props;

  return (
    <div className="grid min-w-0 gap-3" data-testid="runs-stacked-workspace">
      <section className="min-w-0" data-testid="runs-stacked-section-summary">
        <RunOverviewWorkspace
          allInvocationsCount={allInvocationsCount}
          run={run}
          runProgress={runProgress}
          targetKindLabel={targetKindLabel}
          terminalInvocationsCount={terminalInvocationsCount}
          traceSpanEntries={traceSpanEntries}
        />
      </section>
      <section
        className="min-w-0"
        data-testid="runs-stacked-section-final-output"
      >
        <RunFinalOutputPane run={run} />
      </section>
      <section
        className="min-w-0"
        data-testid="runs-stacked-section-output-provenance"
      >
        <RunOutputWorkspace run={run} />
      </section>
      <section
        className="min-w-0"
        data-testid="runs-stacked-section-evidence-availability"
      >
        <RunEvidenceAvailabilitySection run={run} />
      </section>
      <section
        className="min-w-0"
        data-testid="runs-stacked-section-diagnostics"
      >
        <RunDiagnosticsWorkspace run={run} steps={steps} />
      </section>
      <section className="min-w-0" data-testid="runs-stacked-section-execution">
        <ExecutionOutline
          activeInspection={activeInspection}
          copiedInvocations={copiedInvocations}
          copiedSteps={copiedSteps}
          isCurrentFork={isCurrentFork}
          onOpenFork={onOpenFork}
          onSelect={onSelect}
          plannedInvocations={plannedInvocations}
          plannedSteps={plannedSteps}
          run={run}
          steps={steps}
          traceSpanEntries={traceSpanEntries}
        />
      </section>
      <section className="min-w-0" data-testid="runs-stacked-section-inputs">
        <RunInputWorkspace run={run} />
      </section>
      <section className="min-w-0" data-testid="runs-stacked-section-memory">
        <RunMemoryWorkspace run={run} />
      </section>
      <section className="min-w-0" data-testid="runs-stacked-section-runtime">
        <div
          className="grid min-w-0 gap-3"
          data-testid="runs-runtime-workspace"
        >
          <RunRuntimeProfileSection run={run} />
          <RunTokensWorkspace run={run} />
        </div>
      </section>
      <section className="min-w-0" data-testid="runs-stacked-section-lineage">
        <RunLineageWorkspace
          copiedInvocations={copiedInvocations}
          copiedSteps={copiedSteps}
          isCurrentFork={isCurrentFork}
          plannedInvocations={plannedInvocations}
          plannedSteps={plannedSteps}
          run={run}
        />
      </section>
      {run.memoryArtifacts.length > 0 ? (
        <CollapsibleDetailPanel
          description="These artifacts summarize memory rows written for human audit; they do not replace the event groups above."
          testId="runs-memory-compact-artifacts"
          title="Compact artifact slice"
        >
          <div className="grid gap-3">
            {run.memoryArtifacts.map((artifact) => (
              <MemoryArtifactSummaryCard
                artifact={artifact}
                key={artifact.memoryId}
              />
            ))}
          </div>
        </CollapsibleDetailPanel>
      ) : null}
      <section className="min-w-0" data-testid="runs-stacked-section-metadata">
        <RunAuditEvidenceSection
          activeInspection={activeInspection}
          copiedInvocations={copiedInvocations}
          copiedSteps={copiedSteps}
          isCurrentFork={isCurrentFork}
          onOpenFork={onOpenFork}
          onSelect={onSelect}
          plannedInvocations={plannedInvocations}
          plannedSteps={plannedSteps}
          run={run}
          steps={steps}
          traceSpanEntries={traceSpanEntries}
        />
      </section>
    </div>
  );
}

function RunInlineEvidence({
  activeInspection,
  copiedInvocations,
  copiedSteps,
  isCurrentFork,
  onOpenFork,
  onSelect,
  plannedInvocations,
  plannedSteps,
  run,
  steps,
  testId,
}: {
  activeInspection: RunInspectionState;
  copiedInvocations: number;
  copiedSteps: number;
  isCurrentFork: boolean;
  onOpenFork: (stepIndex: number, invocationId: number) => void;
  onSelect: (
    target: RunInspectionTarget,
    pane?: RunInspectionPane,
    mode?: RunInspectionMode,
  ) => void;
  plannedInvocations: number;
  plannedSteps: number;
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
  let selectedInvocationForkAction: ReactNode = null;

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
        step={match.step}
      />
    ) : null;
    if (match && canForkInvocation(run, match.step, match.invocation)) {
      selectedInvocationForkAction = (
        <Button
          className="w-full cursor-pointer justify-start sm:w-auto"
          data-testid={`runs-invocation-${match.invocation.id}-fork-entry`}
          onClick={() => onOpenFork(match.step.index, match.invocation.id)}
          size="sm"
          type="button"
          variant="outline"
        >
          <GitBranch data-icon="inline-start" />
          Fork from this invocation
        </Button>
      );
    }
  } else if (target.type === "operationInvocation") {
    const invocation = findOperationInvocation(steps, target.invocationId);
    content = invocation ? (
      <OperationEvidence invocation={invocation} pane={activeInspection.pane} />
    ) : null;
  } else if (target.type === "memoryArtifact") {
    const artifact = run.memoryArtifacts.find(
      (item) => item.memoryId === target.memoryId,
    );
    content = artifact ? (
      <MemoryArtifactEvidence artifact={artifact} run={run} />
    ) : null;
  } else if (activeInspection.pane === "error") {
    content = run.error ? (
      <Alert variant="destructive">
        <AlertCircle />
        <AlertTitle>Run failed</AlertTitle>
        <AlertDescription>{run.error}</AlertDescription>
      </Alert>
    ) : (
      <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground">
        No run-level error recorded.
      </div>
    );
  } else if (activeInspection.pane === "input") {
    content =
      activeInspection.mode === "inputs" ? (
        <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground">
          Select an input field or metadata row to inspect raw detail.
        </div>
      ) : (
        <RunPayloadPane
          label="Run input"
          testId="runs-detail-input"
          value={run.input}
        />
      );
  } else if (activeInspection.pane === "lineage") {
    content =
      activeInspection.mode === "lineage" ? (
        <CompactModeEmptyState testId="runs-lineage-inspector-empty">
          Select lineage evidence from the center workspace to inspect raw
          detail.
        </CompactModeEmptyState>
      ) : (
        <RunLineageEvidence
          copiedInvocations={copiedInvocations}
          copiedSteps={copiedSteps}
          isCurrentFork={isCurrentFork}
          plannedInvocations={plannedInvocations}
          plannedSteps={plannedSteps}
          run={run}
        />
      );
  } else if (activeInspection.pane === "memory") {
    content =
      activeInspection.mode === "memory" ? (
        <CompactModeEmptyState testId="runs-memory-inspector-empty">
          Select a memory artifact or audit row to inspect raw detail.
        </CompactModeEmptyState>
      ) : (
        <RunMemoryEvidence run={run} />
      );
  } else {
    content =
      activeInspection.mode === "outputs" ? (
        <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground">
          Select an output field or metadata row to inspect raw detail.
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
          {selectedInvocationForkAction}
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
          <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground">
            Selected evidence is no longer available.
          </div>
        )}
      </div>
    </div>
  );
}
