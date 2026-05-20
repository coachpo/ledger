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
import { Activity, AlertCircle, Database, Download, FileText, GitBranch, Loader2, PlayCircle, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";

import { useCreateRunStepReplay, useRun, useRunStepReplayDraft } from "@/hooks/use-runs";
import { formatDateTime } from "@/lib/format";
import type {
  RunAgentInvocationRead,
  RunGraphMetadata,
  RunMemoryArtifactRead,
  RunMemoryEventRead,
  RunMemoryEventType,
  RunOperationInvocationRead,
  RunRead,
  RunStatus,
  RunStepRead,
  RunStepStatus,
  RunTargetKind,
} from "@/lib/types/run";
import { StructuredValueInspector } from "@/components/platform-authoring/inspectors/structured-value-inspector";
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/components/ui/utils";

import { stringifyJson } from "../platform-resource-helpers";
import {
  inspectionPaneLabel,
  inspectionPanesForTarget,
  resolveRunInspectionState,
  serializeInspectionTarget,
  type RunInspectionPane,
  type RunInspectionState,
  type RunInspectionTarget,
} from "./inspection-state";
import { RunRerunDialog } from "./rerun-dialog";

type TraceSpanEntry = {
  invocationId: number;
  invocationKind: "agent" | "operation";
  slot: string;
  spanId: string;
  stepIndex: number;
};

type DetailItem = {
  label: string;
  value: ReactNode;
};

type MemoryEventGroupKey = "retrievedContext" | "memoryWrites" | "reviewFollowUp" | "auditTrail";

type MemoryEventGroupDefinition = {
  description: string;
  emptyCopy: string;
  eventTypes: RunMemoryEventType[];
  key: MemoryEventGroupKey;
  title: string;
};

type JsonValidationResult<T> = {
  error: string | null;
  value: T | null;
};

type StepReplayAvailability = {
  isAvailable: boolean;
  reason: string | null;
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

const DEFAULT_STEP_REPLAY_UNAVAILABLE_REASON = "This feature is available for succeeded Workflow Package runs and succeeded steps.";
const STEP_REPLAY_DIALOG_CLOSE_CLEANUP_DELAY_MS = 200;
const LINEAGE_NODE_WIDTH = 192;
const LINEAGE_NODE_GAP = 56;
const LINEAGE_NODE_Y = 24;
const LINEAGE_INITIAL_VIEWPORT: Viewport = { x: 0, y: 0, zoom: 1 };
const LINEAGE_FIT_VIEW_MAX_ZOOM = 1;
const LINEAGE_MAX_ZOOM = 1.8;
const LINEAGE_CANVAS_HEIGHT_CLASS = "h-80";
const MEMORY_EVENT_GROUPS: MemoryEventGroupDefinition[] = [
  {
    description: "Lookup and prompt-injection context captured while this run assembled memory for agents.",
    emptyCopy: "No retrieval or prompt-injection memory events were recorded.",
    eventTypes: ["retrieved", "injected"],
    key: "retrievedContext",
    title: "Retrieved context",
  },
  {
    description: "Writes, duplicate reuses, and supersession decisions emitted by core memory tools.",
    emptyCopy: "No memory write, reuse, or supersession events were recorded.",
    eventTypes: ["written", "reused", "superseded"],
    key: "memoryWrites",
    title: "Memory written and reused",
  },
  {
    description: "Review and follow-up lifecycle evidence attached to memories touched by this run.",
    emptyCopy: "No review or follow-up memory events were recorded.",
    eventTypes: ["reviewed"],
    key: "reviewFollowUp",
    title: "Review and follow-up",
  },
  {
    description: "Failure or uncategorized memory events retained as an audit trail for this run.",
    emptyCopy: "No audit-only memory events were recorded.",
    eventTypes: ["failed"],
    key: "auditTrail",
    title: "Audit trail",
  },
];

function isTerminalStatus(status: RunStepStatus): boolean {
  return status === "succeeded" || status === "failed" || status === "skipped";
}

function progressForInvocations(invocations: Array<{ status: RunStepStatus }>, fallbackStatus?: RunStepStatus | RunStatus): number {
  if (invocations.length === 0) {
    return fallbackStatus && fallbackStatus !== "running" && fallbackStatus !== "pending" ? 100 : 0;
  }

  const completed = invocations.filter((invocation) => isTerminalStatus(invocation.status)).length;
  return Math.round((completed / invocations.length) * 100);
}

function progressForRun(status: RunStatus, steps: RunStepRead[]): number {
  if (status === "queued") {
    return 0;
  }

  const invocations = steps.flatMap((step) => [...step.invocations, ...step.operationInvocations]);

  if (invocations.length === 0) {
    return status === "running" ? 0 : 100;
  }

  if (status !== "running") {
    return 100;
  }

  return progressForInvocations(invocations);
}

function formatUnfinishedRunStatus(status: RunStatus): string {
  return status === "queued" ? " · Awaiting execution" : " · Still running";
}

function formatTargetKindLabel(targetKind: RunTargetKind): string {
  if (targetKind === "workflowPackage") {
    return "Workflow Package";
  }
  return targetKind === "agent" ? "Agent" : "Workflow";
}

function describeRunTarget(targetKind: RunTargetKind): string {
  if (targetKind === "workflowPackage") {
    return "Workflow package run captured an immutable executable snapshot at launch.";
  }
  return targetKind === "agent"
    ? "Standalone agent execution with a single runnable target."
    : "Workflow execution with step-by-step agent orchestration.";
}

function formatOptional(value: ReactNode | null | undefined): ReactNode {
  if (value === null || value === undefined || value === "") {
    return "Not recorded";
  }

  return value;
}

function formatTimestamp(value: string | null): string {
  return value ? formatDateTime(value) : "Not recorded";
}

function statusVariant(status: RunStatus | RunStepStatus): "secondary" | "destructive" | "outline" {
  if (status === "failed") {
    return "destructive";
  }

  if (status === "pending" || status === "skipped") {
    return "outline";
  }

  return "secondary";
}

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

function sortedInvocations(invocations: RunAgentInvocationRead[]): RunAgentInvocationRead[] {
  return [...invocations].sort((left, right) => left.position - right.position || left.slot.localeCompare(right.slot));
}

function sortedOperationInvocations(invocations: RunOperationInvocationRead[]): RunOperationInvocationRead[] {
  return [...invocations].sort((left, right) => left.position - right.position || left.slot.localeCompare(right.slot));
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
    operationInvocations: sortedOperationInvocations(step.operationInvocations).map((invocation) => ({
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

function getStepReplayAvailability(
  targetKind: RunTargetKind,
  steps: RunStepRead[],
  replayStepIndex: number | undefined,
): StepReplayAvailability {
  if (targetKind !== "workflowPackage") {
    return {
      isAvailable: false,
      reason: DEFAULT_STEP_REPLAY_UNAVAILABLE_REASON,
    };
  }

  if (replayStepIndex === undefined) {
    return {
      isAvailable: false,
      reason: DEFAULT_STEP_REPLAY_UNAVAILABLE_REASON,
    };
  }

  const selectedStep = steps.find((step) => step.index === replayStepIndex);
  if (!selectedStep) {
    return {
      isAvailable: false,
      reason: `Step ${replayStepIndex} is not available on this run.`,
    };
  }

  if (selectedStep.status !== "succeeded") {
    return {
      isAvailable: false,
      reason: `Step ${replayStepIndex} is ${selectedStep.status}; only succeeded workflow steps can be used to start a new run.`,
    };
  }

  return { isAvailable: true, reason: null };
}

function formatJsonEditorValue(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function parseJsonValue(text: string, label: string): JsonValidationResult<unknown> {
  try {
    return { error: null, value: JSON.parse(text) as unknown };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Invalid JSON";
    return { error: `${label} must be valid JSON. ${message}`, value: null };
  }
}

function parseJsonRecord(text: string, label: string): JsonValidationResult<Record<string, unknown>> {
  const parsed = parseJsonValue(text, label);

  if (parsed.error) {
    return { error: parsed.error, value: null };
  }

  if (!isRecord(parsed.value)) {
    return { error: `${label} must be a JSON object.`, value: null };
  }

  return { error: null, value: parsed.value };
}

function areJsonValuesEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function DetailGrid({ items }: { items: DetailItem[] }) {
  return (
    <dl className="grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-3">
      {items.map((item) => (
        <div className="rounded-md border bg-muted/20 p-3" key={item.label}>
          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{item.label}</dt>
          <dd className="mt-1 break-words text-foreground">{formatOptional(item.value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function lineageNodePosition(index: number) {
  return { x: index * (LINEAGE_NODE_WIDTH + LINEAGE_NODE_GAP), y: LINEAGE_NODE_Y };
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
      <Handle className="size-1.5 border-border bg-muted-foreground" isConnectable={false} position={Position.Left} type="target" />
      <div className="space-y-2">
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{data.eyebrow}</p>
          <p className="mt-0.5 break-words text-sm font-medium leading-5 text-foreground">{data.title}</p>
        </div>
        <dl className="space-y-1.5 text-xs">
          {data.details.map((item) => (
            <div className="min-w-0" key={item.label}>
              <dt className="font-medium uppercase tracking-wide text-muted-foreground">{item.label}</dt>
              <dd className="mt-0.5 break-words text-foreground">{formatOptional(item.value)}</dd>
            </div>
          ))}
        </dl>
      </div>
      <Handle className="size-1.5 border-border bg-muted-foreground" isConnectable={false} position={Position.Right} type="source" />
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
      const currentNodesById = new Map(currentNodes.map((node) => [node.id, node]));
      const hasSameNodes = currentNodes.length === nodes.length && nodes.every((node) => currentNodesById.has(node.id));

      if (!hasSameNodes) {
        return nodes;
      }

      return nodes.map((node) => ({
        ...node,
        position: currentNodesById.get(node.id)?.position ?? node.position,
      }));
    });
  }, [nodes]);

  const handleNodesChange = useCallback((changes: NodeChange<LineageDiagramNode>[]) => {
    setInteractiveNodes((currentNodes) => applyNodeChanges(changes, currentNodes));
  }, []);

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
        <Background color="var(--border)" gap={16} size={1} variant={BackgroundVariant.Dots} />
      </ReactFlow>
    </div>
  );
}

function formatRawPayload(value: unknown): string {
  return JSON.stringify(value, null, 2) ?? "";
}

function RawPayloadBlock({ testId, value }: { testId?: string; value: unknown }) {
  return (
    <pre
      className="overflow-x-auto rounded-md border bg-muted/20 p-3 text-xs"
      data-testid={testId}
    >
      {formatRawPayload(value)}
    </pre>
  );
}

function PayloadViewTabs({ label, testId, value }: { label: string; testId?: string; value: unknown }) {
  return (
    <Tabs defaultValue="rendered" className="min-w-0 gap-3" data-testid={testId}>
      <TabsList aria-label={`${label} payload view modes`} className="h-8 rounded-lg">
        <TabsTrigger className="rounded-md px-2 text-xs" value="rendered">
          Rendered
        </TabsTrigger>
        <TabsTrigger className="rounded-md px-2 text-xs" value="raw">
          Raw
        </TabsTrigger>
      </TabsList>
      <TabsContent value="rendered">
        <StructuredValueInspector className="rounded-md border bg-muted/20 p-3 text-sm" data-testid={testId ? `${testId}-rendered` : undefined} enableMarkdownStringPreview label={null} preserveObjectKeyOrder presentation="tree" value={value} />
      </TabsContent>
      <TabsContent value="raw">
        <RawPayloadBlock testId={testId ? `${testId}-raw` : undefined} value={value} />
      </TabsContent>
    </Tabs>
  );
}

function JsonBlock({ label, testId, value }: { label?: string; testId?: string; value: unknown }) {
  return (
    <div className="min-w-0 space-y-2">
      {label ? <p className="text-sm font-medium">{label}</p> : null}
      <PayloadViewTabs label={label ?? "Payload"} testId={testId} value={value} />
    </div>
  );
}

function RunPayloadPane({ headingId, label, testId, value }: { headingId: string; label: string; testId: string; value: unknown }) {
  return (
    <section aria-labelledby={headingId} className="space-y-3">
      <h3 className="text-base font-medium leading-none" id={headingId}>{label}</h3>
      <PayloadViewTabs label={label} testId={testId} value={value} />
    </section>
  );
}

function RunFinalOutputPane({ run }: { run: RunRead }) {
  const isPendingFinalOutput = (run.status === "queued" || run.status === "running") && run.finalOutput === null;

  return (
    <Card data-testid="runs-detail-final-output-card">
      <CardContent className="space-y-5 pt-6">
        {!isPendingFinalOutput ? (
          <RunPayloadPane headingId="runs-final-output-heading" label="Final output" testId="runs-detail-final-output" value={run.finalOutput} />
        ) : (
          <section aria-labelledby="runs-final-output-heading" className="space-y-3">
            <h3 className="text-base font-medium leading-none" id="runs-final-output-heading">Final output</h3>
            <div className="rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground" data-testid="runs-detail-final-output">
              Final output is not available yet.
            </div>
          </section>
        )}
      </CardContent>
    </Card>
  );
}

function graphMetadataLabel(metadata: RunGraphMetadata | null | undefined): string {
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
  ].filter(Boolean).join(" · ");
}

function SourceRunLink({ children, runId }: { children: ReactNode; runId: number | null }) {
  if (!runId) {
    return <>{children}</>;
  }

  return (
    <Link className="nodrag nopan text-primary underline-offset-4 hover:underline" to={`/runs/${runId}`}>
      {children}
    </Link>
  );
}

function SourceStepLink({ step }: { step: RunStepRead }) {
  if (!step.sourceRunId || step.sourceStepIndex === null) {
    return "Not recorded";
  }

  return (
    <Link className="nodrag nopan text-primary underline-offset-4 hover:underline" to={`/runs/${step.sourceRunId}#step-${step.sourceStepIndex}`}>
      Run #{step.sourceRunId} step {step.sourceStepIndex}
    </Link>
  );
}

function SourceInvocationLink({ invocation, step }: { invocation: RunAgentInvocationRead; step: RunStepRead }) {
  if (invocation.sourceInvocationId === null) {
    return "Not recorded";
  }

  if (!step.sourceRunId) {
    return `Invocation #${invocation.sourceInvocationId}`;
  }

  return (
    <Link className="text-primary underline-offset-4 hover:underline" to={`/runs/${step.sourceRunId}#invocation-${invocation.sourceInvocationId}`}>
      Invocation #{invocation.sourceInvocationId}
    </Link>
  );
}

function SourceOperationInvocationLink({ invocation }: { invocation: RunOperationInvocationRead }) {
  if (invocation.sourceOperationInvocationId === null) {
    return "Not recorded";
  }

  if (!invocation.sourceRunId) {
    return `Operation invocation #${invocation.sourceOperationInvocationId}`;
  }

  return (
    <Link className="text-primary underline-offset-4 hover:underline" to={`/runs/${invocation.sourceRunId}#operation-invocation-${invocation.sourceOperationInvocationId}`}>
      Operation invocation #{invocation.sourceOperationInvocationId}
    </Link>
  );
}

function memoryProvenanceLabel(artifact: RunMemoryArtifactRead): string {
  const provenance = artifact.provenance;
  const workflow = provenance.workflowKey ? `workflow ${provenance.workflowKey}` : null;

  return [
    `${provenance.agentKey}@${provenance.agentVersion}`,
    workflow,
    provenance.slot ? `slot ${provenance.slot}` : null,
    `run #${provenance.runId}`,
  ].filter(Boolean).join(" · ");
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

function groupKeyForMemoryEvent(eventType: RunMemoryEventType): MemoryEventGroupKey {
  return MEMORY_EVENT_GROUPS.find((definition) => definition.eventTypes.includes(eventType))?.key ?? "auditTrail";
}

function groupedMemoryEvents(events: RunMemoryEventRead[]): Record<MemoryEventGroupKey, RunMemoryEventRead[]> {
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
    items.push({ label: "Agent invocation", value: `#${event.runAgentInvocationId}` });
  }
  if (event.runOperationInvocationId) {
    items.push({ label: "Operation invocation", value: `#${event.runOperationInvocationId}` });
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

function JsonEditorField({
  disabled,
  error,
  id,
  label,
  onChange,
  rows = 8,
  value,
}: {
  disabled?: boolean;
  error: string | null;
  id: string;
  label: string;
  onChange: (value: string) => void;
  rows?: number;
  value: string;
}) {
  return (
    <div className="flex flex-col gap-2">
      <Label className="text-sm" htmlFor={id}>{label}</Label>
      <Textarea
        aria-invalid={Boolean(error)}
        className="min-h-40 font-mono text-xs leading-relaxed"
        disabled={disabled}
        id={id}
        onChange={(event) => onChange(event.target.value)}
        rows={rows}
        spellCheck={false}
        value={value}
      />
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  );
}

function RunStepReplayDialog({
  onClose,
  open,
  replayAvailability,
  replayStepIndex,
  runId,
}: {
  onClose: () => void;
  open: boolean;
  replayAvailability: StepReplayAvailability;
  replayStepIndex: number | undefined;
  runId: string;
}) {
  const navigate = useNavigate();
  const createStepReplay = useCreateRunStepReplay();
  const [presentedReplayState, setPresentedReplayState] = useState(() => ({ replayAvailability, replayStepIndex }));
  const [draftTargetKey, setDraftTargetKey] = useState<string | null>(null);
  const [parametersText, setParametersText] = useState("");
  const [apiError, setApiError] = useState<string | null>(null);
  const presentedReplayStepIndex = open ? replayStepIndex : presentedReplayState.replayStepIndex;
  const presentedReplayAvailability = open ? replayAvailability : presentedReplayState.replayAvailability;
  const draftQuery = useRunStepReplayDraft(runId, presentedReplayStepIndex, { enabled: open && presentedReplayAvailability.isAvailable });

  const resetLocalState = useCallback(() => {
    setDraftTargetKey(null);
    setParametersText("");
    setApiError(null);
  }, []);

  const closeDialog = () => {
    onClose();
  };

  useEffect(() => {
    if (open) {
      setPresentedReplayState({
        replayAvailability: {
          isAvailable: replayAvailability.isAvailable,
          reason: replayAvailability.reason,
        },
        replayStepIndex,
      });
    }
  }, [open, replayAvailability.isAvailable, replayAvailability.reason, replayStepIndex]);

  useEffect(() => {
    if (open) {
      return undefined;
    }

    const cleanupTimer = window.setTimeout(resetLocalState, STEP_REPLAY_DIALOG_CLOSE_CLEANUP_DELAY_MS);
    return () => window.clearTimeout(cleanupTimer);
  }, [open, resetLocalState]);

  useEffect(() => {
    if (!open || !draftQuery.data) {
      return;
    }

    const nextTargetKey = `${draftQuery.data.sourceRunId}:${draftQuery.data.replayStepIndex}`;
    if (draftTargetKey === nextTargetKey) {
      return;
    }

    setDraftTargetKey(nextTargetKey);
    setParametersText(formatJsonEditorValue(draftQuery.data.parameters));
    setApiError(null);
  }, [draftQuery.data, draftTargetKey, open]);

  const parametersValidation = useMemo(
    () => parseJsonRecord(parametersText || "{}", "New run inputs JSON"),
    [parametersText],
  );
  const replayPayload = useMemo(() => {
    if (!draftQuery.data || parametersValidation.error || !parametersValidation.value) {
      return null;
    }

    return {
      parameters: parametersValidation.value,
      replayStepIndex: draftQuery.data.replayStepIndex,
    };
  }, [draftQuery.data, parametersValidation.error, parametersValidation.value]);
  const hasDraftEdits = Boolean(draftQuery.data && !areJsonValuesEqual(parametersValidation.value, draftQuery.data.parameters));
  const isSubmitDisabled = !replayPayload || createStepReplay.isPending || draftQuery.isPending || Boolean(parametersValidation.error);

  const resetToDraft = () => {
    if (!draftQuery.data) {
      return;
    }

    setDraftTargetKey(`${draftQuery.data.sourceRunId}:${draftQuery.data.replayStepIndex}`);
    setParametersText(formatJsonEditorValue(draftQuery.data.parameters));
    setApiError(null);
  };

  const handleSubmit = async () => {
    if (!replayPayload) {
      return;
    }

    setApiError(null);

    try {
      const createdRun = await createStepReplay.mutateAsync({ runId, payload: replayPayload });
      resetLocalState();
      navigate(`/runs/${createdRun.id}`);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Failed to create the new run.");
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !createStepReplay.isPending) {
          closeDialog();
        }
      }}
    >
      <DialogContent
        className="max-h-dvh overflow-y-auto sm:max-w-3xl"
        onAnimationEnd={(event) => {
          if (event.currentTarget === event.target && !open) {
            resetLocalState();
          }
        }}
      >
        <DialogHeader>
          <div className="flex flex-wrap items-center gap-2 pr-6">
            <DialogTitle>Start a new run from Step {presentedReplayStepIndex}</DialogTitle>
            {presentedReplayStepIndex !== undefined ? <Badge variant="outline">Step {presentedReplayStepIndex}</Badge> : null}
            {draftQuery.data ? <Badge variant={hasDraftEdits ? "secondary" : "outline"}>{hasDraftEdits ? "Step input edited" : "Step input unchanged"}</Badge> : null}
          </div>
          <DialogDescription>
            A new run is created, prior context is copied, Step {presentedReplayStepIndex} and later run again, and the original run remains unchanged.
          </DialogDescription>
        </DialogHeader>

        {!presentedReplayAvailability.isAvailable ? (
          <Alert variant="destructive" data-testid="run-step-replay-invalid-step">
            <AlertCircle />
            <AlertTitle>New run unavailable</AlertTitle>
            <AlertDescription>{presentedReplayAvailability.reason ?? DEFAULT_STEP_REPLAY_UNAVAILABLE_REASON}</AlertDescription>
          </Alert>
        ) : null}

        {presentedReplayAvailability.isAvailable && draftQuery.isPending ? (
          <div className="flex items-center gap-2 rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground" data-testid="run-step-replay-loading">
            <Loader2 className="size-4 animate-spin" />
            Loading new run inputs...
          </div>
        ) : null}

        {presentedReplayAvailability.isAvailable && draftQuery.isError ? (
          <Alert variant="destructive" data-testid="run-step-replay-draft-error">
            <AlertCircle />
            <AlertTitle>Unable to load new run inputs</AlertTitle>
            <AlertDescription>{draftQuery.error instanceof Error ? draftQuery.error.message : "The new run inputs could not be loaded."}</AlertDescription>
          </Alert>
        ) : null}

        {apiError ? (
          <Alert variant="destructive" data-testid="run-step-replay-api-error">
            <AlertCircle />
            <AlertTitle>New run creation failed</AlertTitle>
            <AlertDescription>{apiError}</AlertDescription>
          </Alert>
        ) : null}

        {draftQuery.data ? (
          <Card className="gap-3" data-testid="run-step-replay-dialog-body">
            <CardHeader>
              <CardTitle className="text-base">Inputs for the new run</CardTitle>
              <CardDescription>Edit the input JSON that the new run will receive.</CardDescription>
            </CardHeader>
            <CardContent>
              <JsonEditorField
                disabled={createStepReplay.isPending}
                error={parametersValidation.error}
                id="run-step-replay-parameters-json"
                label="New run inputs JSON"
                onChange={(value) => {
                  setApiError(null);
                  setParametersText(value);
                }}
                rows={10}
                value={parametersText}
              />
            </CardContent>
          </Card>
        ) : null}

        <DialogFooter>
          <Button disabled={createStepReplay.isPending} onClick={closeDialog} type="button" variant="ghost">
            Cancel
          </Button>
          <Button disabled={!draftQuery.data || createStepReplay.isPending} onClick={resetToDraft} type="button" variant="outline">
            <RotateCcw data-icon="inline-start" />
            Reset to original inputs
          </Button>
          <Button data-testid="run-step-replay-submit" disabled={isSubmitDisabled} onClick={() => void handleSubmit()} type="button">
            {createStepReplay.isPending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : null}
            Start new run from Step {presentedReplayStepIndex}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


function isInspectionTargetEqual(left: RunInspectionTarget, right: RunInspectionTarget): boolean {
  if (left.type !== right.type) {
    return false;
  }
  if (left.type === "step" && right.type === "step") {
    return left.stepIndex === right.stepIndex;
  }
  if (left.type === "agentInvocation" && right.type === "agentInvocation") {
    return left.invocationId === right.invocationId;
  }
  if (left.type === "operationInvocation" && right.type === "operationInvocation") {
    return left.invocationId === right.invocationId;
  }
  if (left.type === "memoryArtifact" && right.type === "memoryArtifact") {
    return left.memoryId === right.memoryId;
  }
  return left.type === "run";
}

function findAgentInvocation(steps: RunStepRead[], invocationId: number): { invocation: RunAgentInvocationRead; step: RunStepRead } | null {
  for (const step of steps) {
    const invocation = step.invocations.find((item) => item.id === invocationId);
    if (invocation) {
      return { invocation, step };
    }
  }
  return null;
}

function findOperationInvocation(steps: RunStepRead[], invocationId: number): RunOperationInvocationRead | null {
  for (const step of steps) {
    const invocation = step.operationInvocations.find((item) => item.id === invocationId);
    if (invocation) {
      return invocation;
    }
  }
  return null;
}

function selectedTargetLabel(target: RunInspectionTarget, steps: RunStepRead[], run: RunRead): string {
  if (target.type === "step") {
    return `Step ${target.stepIndex}`;
  }
  if (target.type === "agentInvocation") {
    const match = findAgentInvocation(steps, target.invocationId);
    return match ? `${match.invocation.slot} invocation` : `Invocation #${target.invocationId}`;
  }
  if (target.type === "operationInvocation") {
    const invocation = findOperationInvocation(steps, target.invocationId);
    return invocation ? `${invocation.slot} operation` : `Operation #${target.invocationId}`;
  }
  if (target.type === "memoryArtifact") {
    return run.memoryArtifacts.find((artifact) => artifact.memoryId === target.memoryId)?.summary ?? target.memoryId;
  }
  return `Run #${run.id}`;
}

function InspectionSelectorButton({
  activeInspection,
  children,
  className,
  onSelect,
  pane,
  target,
  testId,
}: {
  activeInspection: RunInspectionState;
  children: ReactNode;
  className?: string;
  onSelect: (target: RunInspectionTarget, pane?: RunInspectionPane) => void;
  pane?: RunInspectionPane;
  target: RunInspectionTarget;
  testId?: string;
}) {
  const isActiveTarget = isInspectionTargetEqual(activeInspection.target, target);
  const isActive = isActiveTarget && (!pane || activeInspection.pane === pane);

  return (
    <Button
      className={cn("h-auto w-full cursor-pointer justify-start px-3 py-2 text-left", className)}
      data-testid={testId}
      onClick={() => onSelect(target, pane)}
      size="sm"
      type="button"
      variant={isActive ? "secondary" : "ghost"}
    >
      {children}
    </Button>
  );
}

function RunContextStrip({
  allInvocationsCount,
  run,
  runProgress,
  targetKindLabel,
  terminalInvocationsCount,
}: {
  allInvocationsCount: number;
  run: RunRead;
  runProgress: number;
  targetKindLabel: string;
  terminalInvocationsCount: number;
}) {
  return (
    <Card className="overflow-hidden bg-muted/20" data-testid="runs-workspace-context">
      <CardContent className="grid gap-3 p-3 text-sm">
        <div
          className="flex flex-wrap items-center gap-x-4 gap-y-2"
          data-testid="runs-summary-execution-row"
        >
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Execution</span>
          <Badge data-testid="runs-detail-status" variant={statusVariant(run.status)}>{run.status}</Badge>
          <Badge data-testid="runs-detail-target-kind" variant="outline">{targetKindLabel}</Badge>
          <span className="text-muted-foreground">{terminalInvocationsCount} of {allInvocationsCount} invocation(s) terminal.</span>
        </div>

        <dl
          className="flex flex-wrap items-center gap-x-6 gap-y-2 text-muted-foreground"
          data-testid="runs-summary-usage-row"
        >
          <div className="flex items-center gap-2">
            <dt>Total tokens</dt>
            <dd className="font-medium text-foreground">{run.totalTokens}</dd>
          </div>
          <div className="flex items-center gap-2">
            <dt>Inherited tokens</dt>
            <dd className="font-medium text-foreground">{run.inheritedTokens}</dd>
          </div>
          <div className="flex items-center gap-2">
            <dt>Executed tokens</dt>
            <dd className="font-medium text-foreground">{run.executedTokens}</dd>
          </div>
        </dl>

        <div
          className="flex flex-col gap-2 sm:flex-row sm:items-center"
          data-testid="runs-summary-progress-row"
        >
          <div className="flex items-center justify-between gap-3 text-muted-foreground sm:w-44 sm:justify-start">
            <span>Run progress</span>
            <span className="font-medium text-foreground">{runProgress}%</span>
          </div>
          <Progress className="min-w-0 flex-1" value={runProgress} />
        </div>
      </CardContent>
    </Card>
  );
}

function StepStatusIndicator({ state, stepIndex }: { state: StepIndicatorState; stepIndex: number }) {
  if (state === "neutral") {
    return null;
  }

  const isExecuting = state === "executing";
  const label = isExecuting ? `Step ${stepIndex} currently executing` : `Step ${stepIndex} completed`;

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

function StepTraceSummary({ entries, stepIndex }: { entries: TraceSpanEntry[]; stepIndex: number }) {
  if (entries.length === 0) {
    return null;
  }

  return (
    <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground" data-testid={`runs-step-${stepIndex}-trace-summary`}>
      <Badge variant="outline">{entries.length} trace span{entries.length === 1 ? "" : "s"}</Badge>
      {entries.slice(0, 2).map((entry) => (
        <span className="break-all" key={`${entry.invocationId}-${entry.spanId}`}>
          {entry.invocationKind === "operation" ? "operation " : ""}{entry.slot}/{entry.spanId}
        </span>
      ))}
      {entries.length > 2 ? <span>+{entries.length - 2} more</span> : null}
    </span>
  );
}

function ExecutionOutline({
  activeInspection,
  canReplayRun,
  onOpenReplay,
  onSelect,
  run,
  steps,
  traceSpanEntries,
}: {
  activeInspection: RunInspectionState;
  canReplayRun: boolean;
  onOpenReplay: (stepIndex: number) => void;
  onSelect: (target: RunInspectionTarget, pane?: RunInspectionPane) => void;
  run: RunRead;
  steps: RunStepRead[];
  traceSpanEntries: TraceSpanEntry[];
}) {
  return (
    <aside className="flex h-full min-h-0 min-w-0 flex-col bg-card/40" data-testid="runs-execution-outline">
      <div className="shrink-0 border-b border-border bg-muted/40 px-4 py-3">
        <div className="flex items-center gap-2">
          <Activity className="size-4 text-muted-foreground" />
          <h2 className="text-base font-semibold tracking-tight">Execution outline</h2>
        </div>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-3 p-3">
          <div id="run-context" className="rounded-xl border bg-background p-2">
            <InspectionSelectorButton activeInspection={activeInspection} onSelect={onSelect} pane="finalOutput" target={{ type: "run" }}>
              <span className="flex min-w-0 flex-col gap-1">
                <span className="font-medium">Run result</span>
                <span className="text-xs text-muted-foreground">Final output, input, lineage, and memory</span>
              </span>
            </InspectionSelectorButton>
          </div>
          {steps.length === 0 ? (
            <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground" data-testid="runs-empty-steps">
              No steps have been planned for this run yet.
            </div>
          ) : null}
          {steps.map((step) => {
            const invocations = sortedInvocations(step.invocations);
            const operationInvocations = sortedOperationInvocations(step.operationInvocations);
            const allInvocations = [...invocations, ...operationInvocations];
            const stepProgress = progressForInvocations(allInvocations, step.status);
            const stepTarget: RunInspectionTarget = { type: "step", stepIndex: step.index };
            const canReplay = canReplayRun && getStepReplayAvailability(run.targetKind, steps, step.index).isAvailable;
            const indicatorState = stepIndicatorState(step.status);
            const stepTraceEntries = traceSpanEntries.filter((entry) => entry.stepIndex === step.index);

            return (
              <div
                className={cn(
                  "rounded-xl border bg-background p-2 transition-colors",
                  indicatorState === "executing" && "border-primary/50 bg-primary/5",
                  indicatorState === "completed" && "border-positive/40 bg-positive/5",
                )}
                data-testid={`runs-step-${step.index}`}
                id={`step-${step.index}`}
                key={step.id}
              >
                <InspectionSelectorButton activeInspection={activeInspection} onSelect={onSelect} target={stepTarget}>
                  <span className="flex min-w-0 flex-1 flex-col gap-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <StepStatusIndicator state={indicatorState} stepIndex={step.index} />
                      <span className="font-medium">Step {step.index}</span>
                      <Badge variant={statusVariant(step.status)}>{step.status}</Badge>
                      <Badge variant="outline">{step.origin} origin</Badge>
                      <Badge variant="secondary">{stepProgress}%</Badge>
                    </span>
                    <span className="text-xs text-muted-foreground">{invocations.length} agent invocation(s) · {operationInvocations.length} operation invocation(s)</span>
                    <StepTraceSummary entries={stepTraceEntries} stepIndex={step.index} />
                  </span>
                </InspectionSelectorButton>
                {canReplay ? (
                  <div className="mt-2 rounded-lg border bg-muted/20 p-2" data-testid={`runs-step-${step.index}-replay-entry`}>
                    <Button className="w-full cursor-pointer justify-start" onClick={() => onOpenReplay(step.index)} size="sm" type="button" variant="outline">
                      Start new run from Step {step.index}
                    </Button>
                  </div>
                ) : null}
              </div>
            );
          })}
          {run.memoryArtifacts.length > 0 ? (
            <div className="rounded-xl border bg-background p-2">
              <p className="px-3 py-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Compact memory artifacts</p>
              <div className="space-y-1">
                {run.memoryArtifacts.map((artifact) => (
                  <InspectionSelectorButton
                    activeInspection={activeInspection}
                    key={artifact.memoryId}
                    onSelect={onSelect}
                    target={{ type: "memoryArtifact", memoryId: artifact.memoryId }}
                    testId={`runs-memory-outline-${artifact.memoryId}`}
                  >
                    <span className="flex min-w-0 flex-col gap-1" id={`memory-${artifact.memoryId}`}>
                      <span className="flex items-center gap-2"><Database className="size-3.5" />{artifact.summary}</span>
                      <span className="text-xs text-muted-foreground">{artifact.status} · {memoryProvenanceLabel(artifact)}</span>
                    </span>
                  </InspectionSelectorButton>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </ScrollArea>
    </aside>
  );
}

function EvidencePaneNav({
  activeInspection,
  onSelect,
}: {
  activeInspection: RunInspectionState;
  onSelect: (target: RunInspectionTarget, pane?: RunInspectionPane) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2" data-testid="runs-evidence-pane-nav">
      {inspectionPanesForTarget(activeInspection.target).map((pane) => (
        <Button
          className="cursor-pointer"
          key={pane}
          onClick={() => onSelect(activeInspection.target, pane)}
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

function RunLineageEvidence({ copiedInvocations, copiedSteps, plannedInvocations, plannedSteps, run }: { copiedInvocations: number; copiedSteps: number; plannedInvocations: number; plannedSteps: number; run: RunRead }) {
  const lineageRootRunId = run.lineageRootRunId ?? run.id;
  const sourceRunValue = run.sourceRunId ? <SourceRunLink runId={run.sourceRunId}>Run #{run.sourceRunId}</SourceRunLink> : "Original run";
  const replayStepValue = run.replayStepIndex === null ? "Not replayed" : `Step ${run.replayStepIndex}`;
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
          { label: "Replay step", value: replayStepValue },
        ],
        eyebrow: "Replay source",
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
          { label: "Resume step", value: `Step ${run.resumeStepIndex}` },
          { label: "Step origins", value: `${copiedSteps} copied · ${plannedSteps} planned` },
          { label: "Invocation origins", value: `${copiedInvocations} copied · ${plannedInvocations} planned/executed` },
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
    { id: "root-source", label: "lineage root", source: "lineage-root", target: "lineage-source" },
    { id: "source-current", label: run.sourceRunId ? "replay / resume" : "original / resume", source: "lineage-source", target: "lineage-current" },
  ];

  return (
    <Card data-testid="runs-lineage-summary">
      <CardHeader>
        <CardTitle className="text-base">Lineage</CardTitle>
        <CardDescription>Readonly replay and resume diagram for copied and planned execution origins.</CardDescription>
      </CardHeader>
      <CardContent>
        <LineageDiagram ariaLabel="Run replay and resume lineage diagram" edges={edges} nodes={nodes} testId="runs-lineage-diagram" />
      </CardContent>
    </Card>
  );
}

function MemoryTextEvidence({ label, testId, value }: { label: string; testId?: string; value: string }) {
  return (
    <div className="rounded-md border bg-muted/20 p-3 text-sm" data-testid={testId}>
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 whitespace-pre-wrap break-words text-foreground">{value}</p>
    </div>
  );
}

function MemoryEventCard({ event }: { event: RunMemoryEventRead }) {
  return (
    <Card className="gap-3" data-testid={`runs-memory-event-${event.id}`}>
      <CardHeader className="px-4 pt-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{formatMemoryEventType(event.eventType)}</Badge>
          {event.memoryId ? <Badge variant="outline">{event.memoryId}</Badge> : null}
          {event.revisionId ? <Badge variant="outline">{event.revisionId}</Badge> : null}
        </div>
        <CardDescription>{formatDateTime(event.createdAt)}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 px-4 pb-4">
        <DetailGrid items={memoryEventDetails(event)} />
        {event.excerpt ? <MemoryTextEvidence label="Excerpt" testId={`runs-memory-event-${event.id}-excerpt`} value={event.excerpt} /> : null}
        {event.injectedText ? <MemoryTextEvidence label="Injected text" testId={`runs-memory-event-${event.id}-injected-text`} value={event.injectedText} /> : null}
        {hasRecordEntries(event.filters) ? <JsonBlock label="Filters" testId={`runs-memory-event-${event.id}-filters`} value={event.filters} /> : null}
        {hasRecordEntries(event.budget) ? <JsonBlock label="Budget" testId={`runs-memory-event-${event.id}-budget`} value={event.budget} /> : null}
        {hasRecordEntries(event.resultSnapshot) ? <JsonBlock label="Result snapshot" testId={`runs-memory-event-${event.id}-result`} value={event.resultSnapshot} /> : null}
        {hasRecordEntries(event.statusSnapshot) ? <JsonBlock label="Status snapshot" testId={`runs-memory-event-${event.id}-status`} value={event.statusSnapshot} /> : null}
      </CardContent>
    </Card>
  );
}

function MemoryEventGroupSection({ definition, events }: { definition: MemoryEventGroupDefinition; events: RunMemoryEventRead[] }) {
  return (
    <section aria-labelledby={`runs-memory-group-${definition.key}-heading`} className="space-y-3" data-testid={`runs-memory-group-${definition.key}`}>
      <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-base font-medium leading-none" id={`runs-memory-group-${definition.key}-heading`}>{definition.title}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{definition.description}</p>
        </div>
        <Badge variant="outline">{events.length} event{events.length === 1 ? "" : "s"}</Badge>
      </div>
      {events.length > 0 ? (
        <div className="grid gap-3">
          {events.map((event) => <MemoryEventCard event={event} key={event.id} />)}
        </div>
      ) : (
        <div className="rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground">{definition.emptyCopy}</div>
      )}
    </section>
  );
}

function MemoryArtifactSummaryCard({ artifact }: { artifact: RunMemoryArtifactRead }) {
  return (
    <div className="rounded-md border bg-muted/20 p-3 text-sm" data-testid={`runs-memory-compact-artifact-${artifact.memoryId}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium">{artifact.summary}</p>
          <p className="text-xs text-muted-foreground">{artifact.status} · {formatDateTime(artifact.createdAt)}</p>
        </div>
        <FileText className="size-4 shrink-0 text-muted-foreground" />
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{memoryProvenanceLabel(artifact)}</p>
    </div>
  );
}

function RunMemoryEvidence({ run }: { run: RunRead }) {
  const memoryEvents = run.memoryEvents ?? [];
  const groupedEvents = groupedMemoryEvents(memoryEvents);
  const hasEvents = memoryEvents.length > 0;
  const hasArtifacts = run.memoryArtifacts.length > 0;

  return (
    <Card data-testid="runs-memory-evidence">
      <CardHeader>
        <CardTitle className="text-base">Run memory evidence</CardTitle>
        <CardDescription>
          Run-scoped memory events are the full evidence trail; compact artifacts below are only the human-auditable slice.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {!hasEvents ? (
          <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground" data-testid="runs-memory-evidence-empty">
            No run memory evidence was recorded for this run. The backend did not emit retrieval, injection, write, reuse, review, follow-up, or audit events.
          </div>
        ) : (
          MEMORY_EVENT_GROUPS.map((definition) => (
            <MemoryEventGroupSection definition={definition} events={groupedEvents[definition.key]} key={definition.key} />
          ))
        )}

        <section aria-labelledby="runs-memory-compact-artifacts-heading" className="space-y-3" data-testid="runs-memory-compact-artifacts">
          <div>
            <h3 className="text-base font-medium leading-none" id="runs-memory-compact-artifacts-heading">Compact artifact slice</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              These artifacts summarize memory rows written for human audit; they do not replace the event groups above.
            </p>
          </div>
          {hasArtifacts ? (
            <div className="grid gap-3">
              {run.memoryArtifacts.map((artifact) => <MemoryArtifactSummaryCard artifact={artifact} key={artifact.memoryId} />)}
            </div>
          ) : (
            <div className="rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground" data-testid="runs-memory-artifacts-empty">
              No compact memory artifacts were written by this run.
            </div>
          )}
        </section>
      </CardContent>
    </Card>
  );
}

function MemoryArtifactEvidence({ artifact }: { artifact: RunMemoryArtifactRead }) {
  const auditReport = artifact.auditLinks?.report;

  return (
    <Card data-testid="runs-memory-artifacts">
      <CardHeader>
        <CardTitle className="text-base">Memory artifact</CardTitle>
        <CardDescription>Agent memory artifact and optional report audit actions.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-md border bg-muted/20 p-3 text-sm" data-testid={`runs-memory-artifact-${artifact.memoryId}`}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate font-medium">{artifact.summary}</p>
              <p className="text-xs text-muted-foreground">{artifact.status} · {formatDateTime(artifact.createdAt)}</p>
            </div>
            <FileText className="size-4 shrink-0 text-muted-foreground" />
          </div>
          <p className="mt-2 text-xs text-muted-foreground">{memoryProvenanceLabel(artifact)}</p>
          <p className="mt-1 text-xs text-muted-foreground">{graphMetadataLabel(artifact.sourceGraphMetadata)}</p>
          {auditReport ? (
            <div className="mt-3 flex flex-wrap gap-2">
              <Button asChild size="sm" variant="outline"><Link to={auditReport.url}>Open report</Link></Button>
              <Button asChild size="sm" variant="ghost"><a href={auditReport.downloadUrl} download><Download data-icon="inline-start" />Download</a></Button>
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
    <Card data-testid={`runs-step-${step.index}-summary`}>
      <CardContent className="space-y-5 pt-6">
        <section aria-labelledby={`runs-step-${step.index}-metadata-heading`} className="space-y-3">
          <h3 className="text-base font-medium leading-none" id={`runs-step-${step.index}-metadata-heading`}>Step metadata</h3>
          <dl className="grid gap-x-5 gap-y-2 rounded-md border bg-muted/20 p-3 text-sm sm:grid-cols-2 xl:grid-cols-3" data-testid={`runs-step-${step.index}-metadata`}>
            {metadataItems.map((item) => (
              <div className="min-w-0" key={item.label}>
                <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{item.label}</dt>
                <dd className="mt-0.5 break-words text-foreground">{formatOptional(item.value)}</dd>
              </div>
            ))}
          </dl>
        </section>
        <section aria-labelledby={`runs-step-${step.index}-output-heading`} className="space-y-3">
          <h3 className="text-base font-medium leading-none" id={`runs-step-${step.index}-output-heading`}>Aggregated output</h3>
          <JsonBlock
            testId={`runs-step-${step.index}-aggregated-output`}
            value={aggregatedStepOutput(step)}
          />
        </section>
      </CardContent>
    </Card>
  );
}

function StepLineageEvidence({ step }: { step: RunStepRead }) {
  const sourceRunValue = step.sourceRunId ? <SourceRunLink runId={step.sourceRunId}>Run #{step.sourceRunId}</SourceRunLink> : "Not recorded";
  const sourceStepValue = <SourceStepLink step={step} />;
  const sourceStepRowValue = step.sourceRunStepId ? `#${step.sourceRunStepId}` : "Not recorded";
  const hasUpstreamStep = Boolean(step.sourceRunId && step.sourceStepIndex !== null);
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
            title: step.sourceStepIndex === null ? "Source step" : `Step ${step.sourceStepIndex}`,
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
    ? [{ id: "source-current", label: "provenance", source: "step-source", target: "step-current" }]
    : [];

  return (
    <Card data-testid={`runs-step-${step.index}-lineage-summary`}>
      <CardHeader>
        <CardTitle className="text-base">Step lineage</CardTitle>
        <CardDescription>Readonly provenance diagram for this workflow step.</CardDescription>
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
  ) : <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground">No step error recorded.</div>;
}

function StepEvidence({ pane, step }: { pane: RunInspectionPane; step: RunStepRead }) {
  if (pane === "lineage") {
    return <StepLineageEvidence step={step} />;
  }
  if (pane === "error") {
    return <StepErrorEvidence step={step} />;
  }

  return <StepSummaryEvidence step={step} />;
}

function InvocationEvidence({ invocation, pane, step }: { invocation: RunAgentInvocationRead; pane: RunInspectionPane; step: RunStepRead }) {
  const hasError = Boolean(invocation.errorCode || invocation.errorMessage || invocation.errorDetails.length > 0);
  if (pane === "input") {
    return <JsonBlock label="Resolved input" value={invocation.resolvedInput} />;
  }
  if (pane === "wiring") {
    return <JsonBlock label="Wiring" value={invocation.wiring} />;
  }
  if (pane === "lineage") {
    return <DetailGrid items={[{ label: "Source invocation", value: <SourceInvocationLink invocation={invocation} step={step} /> }, { label: "Input origin", value: invocation.resolvedInputOrigin }, { label: "Output origin", value: invocation.outputOrigin ?? "pending" }]} />;
  }
  if (pane === "error") {
    return hasError ? <Alert variant="destructive"><AlertCircle /><AlertTitle>{invocation.errorCode ?? "Invocation failed"}</AlertTitle><AlertDescription className="space-y-2"><p>{invocation.errorMessage ?? "No error message recorded."}</p>{invocation.errorDetails.length > 0 ? <pre className="overflow-x-auto rounded-md border border-destructive/30 bg-muted/30 p-3 text-xs">{stringifyJson(invocation.errorDetails)}</pre> : null}</AlertDescription></Alert> : <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground">No invocation error recorded.</div>;
  }
  return <JsonBlock label="Output" value={invocation.output} />;
}

function OperationEvidence({ invocation, pane }: { invocation: RunOperationInvocationRead; pane: RunInspectionPane }) {
  const hasError = Boolean(invocation.errorCode || invocation.errorMessage || invocation.errorDetails.length > 0);
  if (pane === "request") {
    return <JsonBlock label="Redacted request metadata" testId={`runs-operation-${invocation.id}-request-metadata`} value={invocation.requestMetadata} />;
  }
  if (pane === "response") {
    return <JsonBlock label="Response metadata" testId={`runs-operation-${invocation.id}-response-metadata`} value={invocation.responseMetadata} />;
  }
  if (pane === "lineage") {
    return <DetailGrid items={[{ label: "Source operation", value: <SourceOperationInvocationLink invocation={invocation} /> }, { label: "Source run", value: invocation.sourceRunId ? `Run #${invocation.sourceRunId}` : "Not recorded" }, { label: "Source step", value: invocation.sourceStepIndex === null ? "Not recorded" : `Step ${invocation.sourceStepIndex}` }]} />;
  }
  if (pane === "error") {
    return hasError ? <Alert variant="destructive"><AlertCircle /><AlertTitle>{invocation.errorCode ?? "Operation failed"}</AlertTitle><AlertDescription className="space-y-2"><p>{invocation.errorMessage ?? "No error message recorded."}</p>{invocation.errorDetails.length > 0 ? <pre className="overflow-x-auto rounded-md border border-destructive/30 bg-muted/30 p-3 text-xs">{stringifyJson(invocation.errorDetails)}</pre> : null}</AlertDescription></Alert> : <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground">No operation error recorded.</div>;
  }
  return <JsonBlock label="Output preview" testId={`runs-operation-${invocation.id}-output-preview`} value={invocation.output} />;
}

function EvidenceViewer({
  activeInspection,
  copiedInvocations,
  copiedSteps,
  onSelect,
  plannedInvocations,
  plannedSteps,
  run,
  steps,
}: {
  activeInspection: RunInspectionState;
  copiedInvocations: number;
  copiedSteps: number;
  onSelect: (target: RunInspectionTarget, pane?: RunInspectionPane) => void;
  plannedInvocations: number;
  plannedSteps: number;
  run: RunRead;
  steps: RunStepRead[];
}) {
  const target = activeInspection.target;
  const title = selectedTargetLabel(target, steps, run);
  let content: ReactNode;

  if (target.type === "step") {
    const step = steps.find((item) => item.index === target.stepIndex);
    content = step ? <StepEvidence pane={activeInspection.pane} step={step} /> : null;
  } else if (target.type === "agentInvocation") {
    const match = findAgentInvocation(steps, target.invocationId);
    content = match ? <InvocationEvidence invocation={match.invocation} pane={activeInspection.pane} step={match.step} /> : null;
  } else if (target.type === "operationInvocation") {
    const invocation = findOperationInvocation(steps, target.invocationId);
    content = invocation ? <OperationEvidence invocation={invocation} pane={activeInspection.pane} /> : null;
  } else if (target.type === "memoryArtifact") {
    const artifact = run.memoryArtifacts.find((item) => item.memoryId === target.memoryId);
    content = artifact ? <MemoryArtifactEvidence artifact={artifact} /> : null;
  } else if (activeInspection.pane === "input") {
    content = <RunPayloadPane headingId="runs-input-heading" label="Run input" testId="runs-detail-input" value={run.input} />;
  } else if (activeInspection.pane === "lineage") {
    content = <RunLineageEvidence copiedInvocations={copiedInvocations} copiedSteps={copiedSteps} plannedInvocations={plannedInvocations} plannedSteps={plannedSteps} run={run} />;
  } else if (activeInspection.pane === "memory") {
    content = <RunMemoryEvidence run={run} />;
  } else {
    content = <RunFinalOutputPane run={run} />;
  }

  return (
    <section className="flex h-full min-h-0 min-w-0 flex-col" data-testid="runs-evidence-viewer">
      <div className="shrink-0 border-b border-border bg-muted/40 px-4 py-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold tracking-tight">{title}</h2>
              <Badge variant="outline">{inspectionPaneLabel(activeInspection.pane)}</Badge>
            </div>
          </div>
          <EvidencePaneNav activeInspection={activeInspection} onSelect={onSelect} />
        </div>
      </div>
      <ScrollArea className="min-h-0 min-w-0 flex-1 [&_[data-slot=scroll-area-viewport]>div]:!block [&_[data-slot=scroll-area-viewport]>div]:!min-w-0 [&_[data-slot=scroll-area-viewport]>div]:w-full [&_[data-slot=scroll-area-viewport]>div]:max-w-full [&_[data-slot=scroll-area-viewport]>div]:overflow-x-hidden">
        <div className="min-h-full min-w-0 overflow-hidden p-4" data-testid="runs-active-evidence-viewer">
          {content ?? <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground">Selected evidence is no longer available.</div>}
        </div>
      </ScrollArea>
    </section>
  );
}

export function RunsDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const runQuery = useRun(runId, { refetchInterval: 2_000 });

  const steps = useMemo(
    () => [...(runQuery.data?.steps ?? [])].sort((left, right) => left.index - right.index),
    [runQuery.data?.steps],
  );
  const allInvocations = useMemo(() => steps.flatMap((step) => [...sortedInvocations(step.invocations), ...sortedOperationInvocations(step.operationInvocations)]), [steps]);
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
  const stepReplayDialogOpen = searchParams.get("stepReplay") === "1";
  const replayStepIndexParam = searchParams.get("stepIndex");
  const rerunDialogOpen = searchParams.get("rerun") === "1";
  const replayStepIndex = useMemo(() => {
    if (replayStepIndexParam === null || replayStepIndexParam.trim() === "") {
      return undefined;
    }

    const parsed = Number(replayStepIndexParam);
    return Number.isInteger(parsed) && parsed >= 1 ? parsed : undefined;
  }, [replayStepIndexParam]);

  const openRerunDialog = () => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("rerun", "1");
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

  const openStepReplayDialog = (stepIndex: number) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("stepReplay", "1");
      next.set("stepIndex", String(stepIndex));
      next.delete("rerun");
      return next;
    });
  };

  const closeStepReplayDialog = () => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.delete("stepReplay");
      next.delete("stepIndex");
      return next;
    });
  };

  if (!runId) {
    return <div className="p-4 text-sm text-muted-foreground">Run route is missing an id.</div>;
  }

  if (runQuery.isPending) {
    return <div className="p-4 text-sm text-muted-foreground">Loading run details...</div>;
  }

  if (runQuery.isError || !runQuery.data) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        {runQuery.error instanceof Error ? runQuery.error.message : "Run not found."}
      </div>
    );
  }

  const run = runQuery.data;
  const copiedSteps = steps.filter((step) => step.origin === "copied").length;
  const plannedSteps = steps.filter((step) => step.origin === "planned").length;
  const copiedInvocations = steps.reduce(
    (count, step) => count
      + step.invocations.filter((invocation) => invocation.outputOrigin === "copied" || invocation.resolvedInputOrigin === "copied").length
      + step.operationInvocations.filter((invocation) => invocation.outputOrigin === "copied").length,
    0,
  );
  const plannedInvocations = allInvocations.length - copiedInvocations;
  const runProgress = progressForRun(run.status, steps);
  const targetKindLabel = formatTargetKindLabel(run.targetKind);
  const replayAvailability = getStepReplayAvailability(run.targetKind, steps, replayStepIndex);
  const activeInspection = resolveRunInspectionState({
    hash: location.hash,
    run,
    searchParams,
    steps,
  });
  const terminalInvocationsCount = allInvocations.filter((invocation) => isTerminalStatus(invocation.status)).length;
  const canReplayRun = run.targetKind === "workflowPackage";

  const selectInspection = (target: RunInspectionTarget, pane?: RunInspectionPane) => {
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
    <div className="flex h-full min-h-0 flex-col bg-background" data-testid="runs-detail-page">
      <div className="shrink-0 border-b border-border bg-card/95 px-4 py-3 backdrop-blur">
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0 space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-xl font-semibold tracking-tight">Run #{run.id}</h1>
                <Badge data-testid="runs-detail-target-identity" variant="outline">{run.targetKind === "workflowPackage" ? `Snapshot: ${run.packageProvenance?.workflowPackageKey ?? run.targetKey}` : run.targetKey}</Badge>
                <Badge variant="outline">{run.targetKind === "workflowPackage" ? `Captured package id: ${run.packageProvenance?.workflowPackageId ?? run.targetId}` : `Target id: ${run.targetId}`}</Badge>
                {run.sourceRunId ? <Badge variant="secondary"><GitBranch className="size-3" /> Replay lineage</Badge> : null}
              </div>
              <p className="text-sm text-muted-foreground">
                {describeRunTarget(run.targetKind)} · {run.startedAt
                  ? `Started ${formatDateTime(run.startedAt)}`
                  : `Queued ${formatDateTime(run.queuedAt)}`}
                {run.finishedAt ? ` · Finished ${formatDateTime(run.finishedAt)}` : formatUnfinishedRunStatus(run.status)}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {run.targetKind === "workflowPackage" && run.packageProvenance?.currentPackage?.available ? (
                <Button asChild data-testid="runs-detail-package-link" size="sm" variant="outline">
                  <Link to={`/workflow-packages/${run.packageProvenance.workflowPackageId}`}>Open current package</Link>
                </Button>
              ) : null}
              {canReplayRun ? (
                <Button className="cursor-pointer" data-testid="runs-detail-rerun" onClick={openRerunDialog} size="sm" type="button" variant="outline">
                  <PlayCircle data-icon="inline-start" />
                  Run snapshot again
                </Button>
              ) : null}
              <Button asChild size="sm" variant="outline"><Link to="/runs">Back to runs</Link></Button>
            </div>
          </div>
          {run.error ? (
            <Alert variant="destructive">
              <AlertCircle />
              <AlertTitle>Run failed</AlertTitle>
              <AlertDescription>{run.error}</AlertDescription>
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
      </div>

      <ResizablePanelGroup
        className="min-h-0 flex-1"
        data-testid="runs-inspection-workspace"
        direction="horizontal"
      >
        <ResizablePanel className="min-w-0" defaultSize={28} maxSize={45} minSize={18}>
          <ExecutionOutline
            activeInspection={activeInspection}
            canReplayRun={canReplayRun}
            onOpenReplay={openStepReplayDialog}
            onSelect={selectInspection}
            run={run}
            steps={steps}
            traceSpanEntries={traceSpanEntries}
          />
        </ResizablePanel>
        <ResizableHandle className="bg-border/80" data-testid="runs-inspection-resize-handle" withHandle />
        <ResizablePanel className="min-w-0" defaultSize={72} minSize={45}>
          <EvidenceViewer
            activeInspection={activeInspection}
            copiedInvocations={copiedInvocations}
            copiedSteps={copiedSteps}
            onSelect={selectInspection}
            plannedInvocations={plannedInvocations}
            plannedSteps={plannedSteps}
            run={run}
            steps={steps}
          />
        </ResizablePanel>
      </ResizablePanelGroup>

      <RunRerunDialog onClose={closeRerunDialog} open={rerunDialogOpen && canReplayRun} runId={runId} />

      <RunStepReplayDialog
        onClose={closeStepReplayDialog}
        open={stepReplayDialogOpen}
        replayAvailability={replayAvailability}
        replayStepIndex={replayStepIndex}
        runId={runId}
      />
    </div>
  );
}          
