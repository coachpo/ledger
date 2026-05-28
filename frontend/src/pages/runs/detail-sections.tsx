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
import {
  Activity,
  AlertCircle,
  Download,
  FileText,
  GitBranch,
  Loader2,
  RotateCcw,
  type LucideIcon,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { Link, useNavigate } from "react-router";

import { StructuredValueInspector } from "@/components/platform-authoring/inspectors/structured-value-inspector";
import { ConsoleSection } from "@/components/shared/console-section";
import { EvidenceCluster } from "@/components/shared/evidence-cluster";
import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/components/ui/utils";
import { useCreateRunFork, useRunForkDraft } from "@/hooks/use-runs";
import { formatDateTime } from "@/lib/format";
import type {
  RunAgentInvocationRead,
  RunGraphMetadata,
  RunMemoryArtifactRead,
  RunMemoryEventRead,
  RunMemoryEventType,
  RunModelGatewaySelectedStrategiesRead,
  RunModelGatewayUsageRead,
  RunOperationInvocationRead,
  RunPackageResolvedModelConnectionRead,
  RunRead,
  RunStatus,
  RunStepRead,
  RunStepStatus,
} from "@/lib/types/run";
import type {
  ModelConnectionCapabilities,
  ModelConnectionCapabilityStatus,
  ModelConnectionOutputStrategyPolicy,
  ModelConnectionParallelToolCallsPolicy,
  ModelConnectionProtocolProfile,
  ModelConnectionReasoningPolicy,
  ModelConnectionStreamingPolicy,
} from "@/lib/types/model-connection";

import { stringifyJson } from "../platform-resource-helpers";
import {
  DEFAULT_FORK_UNAVAILABLE_REASON,
  diagnosticsFromDraftReadiness,
  finalOutputState,
  formatQueueReasonTitle,
  getRunForkAvailability,
  progressForInvocations,
  runStatusTone,
  sortedInvocations,
  sortedOperationInvocations,
  type ForkTargetContext,
  type RunDraftReadiness,
  type RunDraftReadinessDiagnostic,
  type RunForkAvailability,
  type TraceSpanEntry,
} from "./detail-helpers";
import {
  inspectionPaneLabel,
  inspectionPanesForTarget,
  inspectionTargetKindLabel,
  type RunInspectionMode,
  type RunInspectionPane,
  type RunInspectionState,
  type RunInspectionTarget,
} from "./inspection-state";

type DetailItem = {
  label: string;
  value: ReactNode;
};

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

type JsonValidationResult<T> = {
  error: string | null;
  value: T | null;
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

const FORK_DIALOG_CLOSE_CLEANUP_DELAY_MS = 200;
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

type RunDetailSectionBlockProps = {
  actions?: ReactNode;
  blockId: string;
  cardClassName?: string;
  cardTestId?: string;
  children: ReactNode;
  contentClassName?: string;
  description: ReactNode;
  icon: LucideIcon;
  title: ReactNode;
  tone?: "default" | "muted" | "warning" | "danger";
};

function RunDetailSectionTitle({
  blockId,
  icon: Icon,
  title,
}: {
  blockId: string;
  icon: LucideIcon;
  title: ReactNode;
}) {
  return (
    <span className="inline-flex min-w-0 items-center gap-2">
      <span
        aria-hidden="true"
        className="inline-flex size-7 shrink-0 items-center justify-center rounded-lg border bg-muted/40 text-muted-foreground"
        data-testid={`runs-detail-section-icon-${blockId}`}
      >
        <Icon className="size-4" />
      </span>
      <span
        className="min-w-0 break-words text-sm font-semibold tracking-tight text-foreground"
        data-testid={`runs-detail-section-title-${blockId}`}
      >
        {title}
      </span>
    </span>
  );
}

function RunDetailSectionDescription({
  blockId,
  children,
}: {
  blockId: string;
  children: ReactNode;
}) {
  return (
    <span
      className="block text-xs leading-5 text-muted-foreground"
      data-testid={`runs-detail-section-description-${blockId}`}
    >
      {children}
    </span>
  );
}

function RunDetailSectionBlock({
  actions,
  blockId,
  cardClassName,
  cardTestId,
  children,
  contentClassName,
  description,
  icon,
  title,
  tone = "default",
}: RunDetailSectionBlockProps) {
  return (
    <Collapsible
      className="min-w-0"
      data-run-detail-section-block="true"
      data-testid={`runs-detail-section-${blockId}`}
      defaultOpen={false}
    >
      <ConsoleSection
        actions={
          <div className="flex min-w-0 flex-wrap justify-end gap-2">
            {actions}
            <CollapsibleTrigger asChild>
              <Button className="cursor-pointer" size="sm" type="button" variant="outline">
                Toggle
              </Button>
            </CollapsibleTrigger>
          </div>
        }
        className={cardClassName}
        contentClassName={contentClassName}
        description={
          <RunDetailSectionDescription blockId={blockId}>
            {description}
          </RunDetailSectionDescription>
        }
        testId={cardTestId}
        title={
          <RunDetailSectionTitle blockId={blockId} icon={icon} title={title} />
        }
        tone={tone}
      >
        <CollapsibleContent
          className="grid min-w-0 gap-3 data-[state=closed]:hidden"
          forceMount
        >
          {children}
        </CollapsibleContent>
      </ConsoleSection>
    </Collapsible>
  );
}

function RunDetailEmptyState({
  children,
  testId,
}: {
  children: ReactNode;
  testId: string;
}) {
  return (
    <div
      className="rounded-md border border-dashed bg-muted/20 p-3 text-sm text-muted-foreground"
      data-testid={testId}
    >
      {children}
    </div>
  );
}

function RunDetailTableFrame({
  children,
  className,
  testId,
}: {
  children: ReactNode;
  className?: string;
  testId?: string;
}) {
  return (
    <div
      className={cn("min-w-0 overflow-x-auto rounded-lg border bg-card", className)}
      data-testid={testId}
    >
      {children}
    </div>
  );
}

function CollapsibleConsoleSection({
  blockId,
  children,
  description,
  icon,
  title,
}: {
  blockId: string;
  children: ReactNode;
  description: ReactNode;
  icon: LucideIcon;
  title: ReactNode;
}) {
  return (
    <RunDetailSectionBlock
      blockId={blockId}
      description={description}
      icon={icon}
      title={title}
    >
      {children}
    </RunDetailSectionBlock>
  );
}

function CollapsibleDetailPanel({
  children,
  description,
  testId,
  title,
}: {
  children: ReactNode;
  description: ReactNode;
  testId: string;
  title: ReactNode;
}) {
  return (
    <Collapsible className="min-w-0" data-testid={testId} defaultOpen={false}>
      <ConsoleSection
        actions={
          <CollapsibleTrigger asChild>
            <Button className="cursor-pointer" size="sm" type="button" variant="outline">
              Toggle
            </Button>
          </CollapsibleTrigger>
        }
        description={description}
        title={title}
      >
        <CollapsibleContent
          className="grid min-w-0 gap-3 data-[state=closed]:hidden"
          forceMount
        >
          {children}
        </CollapsibleContent>
      </ConsoleSection>
    </Collapsible>
  );
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

function statusVariant(
  status: RunStatus | RunStepStatus,
): "secondary" | "destructive" | "outline" {
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

function formatJsonEditorValue(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function parseJsonValue(
  text: string,
  label: string,
): JsonValidationResult<unknown> {
  try {
    return { error: null, value: JSON.parse(text) as unknown };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Invalid JSON";
    return { error: `${label} must be valid JSON. ${message}`, value: null };
  }
}

function parseJsonRecord(
  text: string,
  label: string,
): JsonValidationResult<Record<string, unknown>> {
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
    <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2 xl:grid-cols-3">
      {items.map((item) => (
        <div className="min-w-0 space-y-1" key={item.label}>
          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {item.label}
          </dt>
          <dd className="break-words text-foreground">
            {formatOptional(item.value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function CompactModeEmptyState({
  children,
  testId,
}: {
  children: ReactNode;
  testId: string;
}) {
  return <RunDetailEmptyState testId={testId}>{children}</RunDetailEmptyState>;
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

function formatRawPayload(value: unknown): string {
  return JSON.stringify(value, null, 2) ?? "";
}

function RawPayloadBlock({
  testId,
  value,
}: {
  testId?: string;
  value: unknown;
}) {
  return (
    <pre
      className="max-w-full overflow-x-auto whitespace-pre rounded-md border bg-muted/20 p-3 text-xs"
      data-testid={testId}
      data-wide-payload="scroll"
    >
      {formatRawPayload(value)}
    </pre>
  );
}

function PayloadViewTabs({
  label,
  testId,
  value,
}: {
  label: string;
  testId?: string;
  value: unknown;
}) {
  return (
    <Tabs
      defaultValue="rendered"
      className="min-w-0 gap-3"
      data-testid={testId}
    >
      <div
        className="max-w-full overflow-x-auto pb-1"
        data-testid={testId ? `${testId}-tab-scroll` : undefined}
      >
        <TabsList
          aria-label={`${label} payload view modes`}
          className="h-8 rounded-lg"
        >
          <TabsTrigger className="rounded-md px-2 text-xs" value="rendered">
            Rendered
          </TabsTrigger>
          <TabsTrigger className="rounded-md px-2 text-xs" value="raw">
            Raw
          </TabsTrigger>
        </TabsList>
      </div>
      <TabsContent className="min-w-0" value="rendered">
        <StructuredValueInspector
          className="min-w-0 rounded-md border bg-muted/20 p-3 text-sm"
          data-testid={testId ? `${testId}-rendered` : undefined}
          enableMarkdownStringPreview
          label={null}
          preserveObjectKeyOrder
          presentation="tree"
          value={value}
        />
      </TabsContent>
      <TabsContent className="min-w-0" value="raw">
        <RawPayloadBlock
          testId={testId ? `${testId}-raw` : undefined}
          value={value}
        />
      </TabsContent>
    </Tabs>
  );
}

function JsonBlock({
  label,
  testId,
  value,
}: {
  label?: string;
  testId?: string;
  value: unknown;
}) {
  return (
    <div className="min-w-0 space-y-2">
      {label ? <p className="text-sm font-medium">{label}</p> : null}
      <PayloadViewTabs
        label={label ?? "Payload"}
        testId={testId}
        value={value}
      />
    </div>
  );
}

function RunPayloadPane({
  label,
  testId,
  value,
}: {
  label: string;
  testId: string;
  value: unknown;
}) {
  return (
    <section aria-label={label} className="min-w-0 space-y-3">
      <PayloadViewTabs label={label} testId={testId} value={value} />
    </section>
  );
}

export function RunFinalOutputPane({ run }: { run: RunRead }) {
  const outputState = finalOutputState(run);
  const showPayload = !outputState.isPending && outputState.label === "Captured";

  return (
    <RunDetailSectionBlock
      blockId="final-output"
      cardClassName="min-h-[136px]"
      cardTestId="runs-detail-final-output-card"
      contentClassName="space-y-5"
      description="Rendered payload view for the immutable run result."
      icon={Download}
      title="Final output"
    >
      {showPayload ? (
        <RunPayloadPane
          label="Final output"
          testId="runs-detail-final-output"
          value={run.finalOutput}
        />
      ) : (
        <section aria-label="Final output" className="space-y-3">
          <RunDetailEmptyState testId="runs-detail-final-output">
            {outputState.description}
          </RunDetailEmptyState>
        </section>
      )}
    </RunDetailSectionBlock>
  );
}

export function RunOutputWorkspace({ run }: { run: RunRead }) {
  const provenance = run.packageProvenance;
  const outputState = finalOutputState(run);

  return (
    <div className="grid min-w-0 gap-3" data-testid="runs-output-workspace">
      <RunDetailSectionBlock
        blockId="output-provenance"
        description="Output provenance stays beside the rendered payload while raw payload detail is available from metadata rows."
        icon={FileText}
        title="Output provenance"
      >
        <EvidenceCluster
          items={[
            {
              label: "Workflow",
              value: provenance?.workflowName ?? "Snapshot workflow",
              description:
                provenance?.workflowKey ?? run.targetKey ?? "Not recorded",
            },
            {
              label: "Availability",
              value: outputState.label,
              description: outputState.description,
              tone:
                outputState.tone === "danger"
                  ? "danger"
                  : outputState.tone === "warning"
                    ? "warning"
                    : "verified",
            },
          ]}
          layout="grid"
        />
      </RunDetailSectionBlock>
    </div>
  );
}

export function RunInputWorkspace({ run }: { run: RunRead }) {
  return (
    <div className="grid min-w-0 gap-3" data-testid="runs-input-workspace">
      <RunDetailSectionBlock
        blockId="run-input"
        cardTestId="runs-detail-input-card"
        contentClassName="space-y-5"
        description="Launch payload captured with the immutable run snapshot."
        icon={FileText}
        title="Run input"
      >
        <RunPayloadPane
          label="Run input"
          testId="runs-detail-input"
          value={run.input}
        />
      </RunDetailSectionBlock>
    </div>
  );
}

export function RunOverviewWorkspace({
  allInvocationsCount,
  run,
  runProgress,
  targetKindLabel,
  terminalInvocationsCount,
  traceSpanEntries,
}: {
  allInvocationsCount: number;
  run: RunRead;
  runProgress: number;
  targetKindLabel: string;
  terminalInvocationsCount: number;
  traceSpanEntries: TraceSpanEntry[];
}) {
  const queueValue = run.queue
    ? `${run.queue.state} · ${formatQueueReasonTitle(run.queue.reason)}`
    : run.status === "queued"
      ? "Queued without queue detail"
      : "No queue hold";
  const outputState = finalOutputState(run);

  return (
    <section className="grid min-w-0 gap-3" data-testid="runs-overview-workspace">
      <RunDetailSectionBlock
        blockId="operational-overview"
        description="Operational availability and progress cues for this immutable run snapshot."
        icon={Activity}
        title="Operational overview"
      >
        <div className="flex min-w-0 flex-col gap-3">
          <div className="sr-only" data-testid="runs-summary-execution-row">
            <span data-testid="runs-detail-status">{run.status}</span>
            <span data-testid="runs-detail-target-kind">{targetKindLabel}</span>
            <span>
              {terminalInvocationsCount} of {allInvocationsCount} invocation(s)
              terminal.
            </span>
          </div>
          <ResourceStatusStrip
            items={[
              {
                label: "Queue",
                value: queueValue,
                tone: run.queue ? "warning" : "muted",
              },
              {
                label: "Invocations",
                value: `${terminalInvocationsCount} of ${allInvocationsCount} invocation(s) terminal`,
              },
              {
                label: "Output",
                value: outputState.label,
                tone: outputState.tone,
              },
              {
                label: "Trace",
                value: run.traceId ?? `${traceSpanEntries.length} span(s)`,
                tone:
                  run.traceId || traceSpanEntries.length > 0
                    ? "success"
                    : "warning",
              },
            ]}
          />
          <div
            className="flex min-w-0 flex-col gap-2"
            data-testid="runs-summary-progress-row"
          >
            <div className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
              <span>Run progress</span>
              <span className="font-medium text-foreground">
                {runProgress}%
              </span>
            </div>
            <Progress className="min-w-0" value={runProgress} />
          </div>
        </div>
      </RunDetailSectionBlock>
    </section>
  );
}

export function RunEvidenceAvailabilitySection({ run }: { run: RunRead }) {
  const providerCount =
    run.packageProvenance?.resolvedModelConnections.length ?? 0;

  return (
    <RunDetailSectionBlock
      blockId="evidence-availability"
      description="Evidence availability without opening the secondary evidence modes."
      icon={FileText}
      title="Evidence availability"
    >
      <EvidenceCluster
        items={[
          {
            label: "Runtime",
            value: `${providerCount} provider/model row${providerCount === 1 ? "" : "s"}`,
            description: "Open Runtime for provider and capability rows.",
          },
          {
            label: "Audit",
            value: `${run.memoryEvents.length} memory event${run.memoryEvents.length === 1 ? "" : "s"}`,
            description: `${run.memoryArtifacts.length} artifact${run.memoryArtifacts.length === 1 ? "" : "s"} available for audit drill-down.`,
          },
          {
            label: "Usage",
            value: `${run.executedTokens.toLocaleString()} executed tokens`,
            description: `${run.inheritedTokens.toLocaleString()} inherited tokens copied into this snapshot.`,
          },
        ]}
        layout="grid"
      />
    </RunDetailSectionBlock>
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

const PROTOCOL_PROFILE_LABELS: Record<ModelConnectionProtocolProfile, string> =
  {
    openai_chat_completions: "Chat Completions-compatible",
    openai_responses: "Responses-compatible",
  };

const OUTPUT_STRATEGY_POLICY_LABELS: Record<
  ModelConnectionOutputStrategyPolicy,
  string
> = {
  allow_json_object_validation: "Allow JSON object validation",
  allow_plain_text: "Allow plain text",
  prefer_strict_schema: "Prefer strict schema",
  require_strict_schema: "Require strict schema",
};

const PARALLEL_TOOL_CALLS_POLICY_LABELS: Record<
  ModelConnectionParallelToolCallsPolicy,
  string
> = {
  allow: "Allow parallel calls",
  forbid: "Forbid parallel calls",
  serialize: "Serialize calls",
};

const REASONING_POLICY_LABELS: Record<ModelConnectionReasoningPolicy, string> =
  {
    allow: "Allow reasoning",
    forbid: "Forbid reasoning",
  };

const STREAMING_POLICY_LABELS: Record<ModelConnectionStreamingPolicy, string> =
  {
    allow: "Allow streaming",
    forbid: "Forbid streaming",
  };

const CAPABILITY_ORDER: (keyof ModelConnectionCapabilities)[] = [
  "textGeneration",
  "chatCompletions",
  "responsesApi",
  "streaming",
  "nativeToolCalls",
  "parallelToolCalls",
  "jsonObjectOutput",
  "strictJsonSchemaOutput",
  "reasoningHints",
  "usageReporting",
  "systemMessages",
];

const CAPABILITY_LABELS: Record<keyof ModelConnectionCapabilities, string> = {
  textGeneration: "Text generation",
  chatCompletions: "Chat completions",
  responsesApi: "Responses API",
  streaming: "Streaming",
  nativeToolCalls: "Native tool calls",
  parallelToolCalls: "Parallel tool calls",
  jsonObjectOutput: "JSON object output",
  strictJsonSchemaOutput: "Strict JSON schema output",
  reasoningHints: "Reasoning hints",
  usageReporting: "Usage reporting",
  systemMessages: "System messages",
};

function capabilityStatusLabel(
  status: ModelConnectionCapabilityStatus,
): string {
  if (status === "supported") {
    return "Supported";
  }
  if (status === "unsupported") {
    return "Unsupported";
  }
  if (status === "notApplicable") {
    return "Not applicable";
  }
  return "Unknown";
}

function capabilityStatusVariant(
  status: ModelConnectionCapabilityStatus,
): "secondary" | "destructive" | "outline" {
  if (status === "supported") {
    return "secondary";
  }
  if (status === "unsupported") {
    return "destructive";
  }
  return "outline";
}

function runtimeConnectionKindLabel(
  value: RunPackageResolvedModelConnectionRead["connectionKind"],
): string {
  return value === "deterministic_smoke"
    ? "Deterministic smoke"
    : "Provider-backed";
}

type RuntimeStrategySummary = {
  agentLabel: string;
  invocationId: number;
  key: string;
  status: RunStepStatus;
  stepIndex: number;
  strategies: RunModelGatewaySelectedStrategiesRead | null;
  usage: RunModelGatewayUsageRead | null;
};

type RuntimeCapabilityCounts = Record<ModelConnectionCapabilityStatus, number>;

const RUNTIME_AUDIT_STRATEGY_LIMIT = 20;

function formatRuntimeStrategyValue(value: unknown): string {
  if (value === true) {
    return "Enabled";
  }
  if (value === false) {
    return "Disabled";
  }
  if (typeof value === "string" && value.trim()) {
    return value.replaceAll("_", " ");
  }
  if (typeof value === "number") {
    return String(value);
  }
  return "Not recorded";
}

function strategyItems(
  strategies: RunModelGatewaySelectedStrategiesRead | null,
): DetailItem[] {
  return [
    {
      label: "Output strategy",
      value: formatRuntimeStrategyValue(strategies?.outputStrategy),
    },
    {
      label: "Tool call strategy",
      value: formatRuntimeStrategyValue(strategies?.toolCallStrategy),
    },
    {
      label: "Parallel tool calls",
      value: formatRuntimeStrategyValue(strategies?.parallelToolCalls),
    },
    {
      label: "Reasoning strategy",
      value: formatRuntimeStrategyValue(strategies?.reasoningStrategy),
    },
    {
      label: "Reasoning effort",
      value: formatRuntimeStrategyValue(strategies?.reasoningEffort),
    },
    {
      label: "Streaming strategy",
      value: formatRuntimeStrategyValue(strategies?.streamingStrategy),
    },
  ];
}

function usageItems(usage: RunModelGatewayUsageRead | null): DetailItem[] {
  return [
    {
      label: "Input tokens",
      value: formatRuntimeStrategyValue(usage?.inputTokens),
    },
    {
      label: "Output tokens",
      value: formatRuntimeStrategyValue(usage?.outputTokens),
    },
    {
      label: "Total tokens",
      value: formatRuntimeStrategyValue(usage?.totalTokens),
    },
  ];
}

function runtimeStrategySummaries(run: RunRead): RuntimeStrategySummary[] {
  return run.steps.flatMap((step) =>
    sortedInvocations(step.invocations)
      .map((invocation) => {
        const gatewayMetadata = invocation.graphMetadata?.modelGateway;
        const strategies = gatewayMetadata?.selectedStrategies ?? null;
        const usage = gatewayMetadata?.usage ?? null;
        if (!strategies && !usage) {
          return null;
        }
        return {
          agentLabel: `${invocation.agentKey}@${invocation.agentVersion}`,
          invocationId: invocation.id,
          key: `${step.index}-${invocation.id}`,
          status: invocation.status,
          stepIndex: step.index,
          strategies,
          usage,
        } satisfies RuntimeStrategySummary;
      })
      .filter((item): item is RuntimeStrategySummary => item !== null),
  );
}

function runtimeInvocationTokenRows(run: RunRead) {
  return run.steps.flatMap((step) =>
    sortedInvocations(step.invocations)
      .filter((invocation) => invocation.tokens > 0)
      .map((invocation) => ({
        agentLabel: `${invocation.agentKey}@${invocation.agentVersion}`,
        invocationId: invocation.id,
        key: `${step.index}-${invocation.id}`,
        slot: invocation.slot,
        status: invocation.status,
        stepIndex: step.index,
        tokens: invocation.tokens,
      })),
  );
}

function runtimeCapabilityCounts(
  connection: RunPackageResolvedModelConnectionRead,
): RuntimeCapabilityCounts {
  return CAPABILITY_ORDER.reduce<RuntimeCapabilityCounts>(
    (counts, capabilityKey) => {
      const status = connection.capabilities[capabilityKey].status;
      counts[status] += 1;
      return counts;
    },
    { notApplicable: 0, supported: 0, unknown: 0, unsupported: 0 },
  );
}

function formatRuntimeCapabilitySummary(
  connection: RunPackageResolvedModelConnectionRead,
): string {
  const counts = runtimeCapabilityCounts(connection);
  return `${counts.supported} supported · ${counts.unsupported} unsupported · ${counts.unknown} unknown · ${counts.notApplicable} not applicable`;
}

export function RunRuntimeProfileSection({ run }: { run: RunRead }) {
  const provenance = run.packageProvenance;
  if (run.targetKind !== "workflowPackage" || !provenance) {
    return (
      <RunDetailSectionBlock
        blockId="runtime-profile"
        description="Runtime profile data is only recorded for Workflow Package runs."
        icon={Activity}
        title="Runtime profile"
      >
        <RunDetailEmptyState testId="runs-runtime-profile-empty">
          No runtime profile was recorded for this run.
        </RunDetailEmptyState>
      </RunDetailSectionBlock>
    );
  }

  const resolvedModelConnections = provenance.resolvedModelConnections;
  const strategySummaries = runtimeStrategySummaries(run);
  const visibleStrategySummaries = strategySummaries.slice(
    0,
    RUNTIME_AUDIT_STRATEGY_LIMIT,
  );
  const hiddenStrategyCount = Math.max(
    0,
    strategySummaries.length - visibleStrategySummaries.length,
  );

  return (
    <div className="grid min-w-0 gap-3" data-testid="runs-runtime-profile">
      <RunDetailSectionBlock
        blockId="runtime-profile"
        description="Frozen provider, model, policy, and capability rows captured when the run executed."
        icon={Activity}
        title="Runtime profile"
      >
        {resolvedModelConnections.length === 0 ? (
          <RunDetailEmptyState testId="runs-runtime-provider-empty">
            No resolved model connections were recorded for this run.
          </RunDetailEmptyState>
        ) : (
          <RunDetailTableFrame testId="runs-runtime-provider-rows">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Provider/model</TableHead>
                  <TableHead>Protocol</TableHead>
                  <TableHead>Capabilities</TableHead>
                  <TableHead>Policies</TableHead>
                  <TableHead>Execution settings</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {resolvedModelConnections.map((connection) => (
                  <TableRow
                    data-testid={`runs-runtime-profile-connection-${connection.key}`}
                    key={connection.key}
                  >
                    <TableCell className="min-w-56 whitespace-normal align-top">
                      <div className="flex min-w-0 flex-col gap-1">
                        <span className="font-medium text-foreground">
                          {connection.name}
                        </span>
                        <span className="break-all text-xs text-muted-foreground">
                          {connection.key}
                        </span>
                        <span className="break-all text-xs text-muted-foreground">
                          {connection.modelId}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="whitespace-normal align-top">
                      <div className="flex flex-wrap gap-1.5">
                        <Badge variant="outline">
                          {runtimeConnectionKindLabel(connection.connectionKind)}
                        </Badge>
                        <Badge variant="secondary">
                          {PROTOCOL_PROFILE_LABELS[connection.protocolProfile]}
                        </Badge>
                        <Badge
                          variant={connection.hasApiKey ? "secondary" : "outline"}
                        >
                          {connection.hasApiKey
                            ? "Credential present"
                            : "No credential"}
                        </Badge>
                      </div>
                    </TableCell>
                    <TableCell className="min-w-52 whitespace-normal align-top text-muted-foreground">
                      {formatRuntimeCapabilitySummary(connection)}
                    </TableCell>
                    <TableCell className="min-w-64 whitespace-normal align-top text-muted-foreground">
                      {[
                        OUTPUT_STRATEGY_POLICY_LABELS[
                          connection.outputStrategyPolicy
                        ],
                        PARALLEL_TOOL_CALLS_POLICY_LABELS[
                          connection.parallelToolCallsPolicy
                        ],
                        REASONING_POLICY_LABELS[connection.reasoningPolicy],
                        STREAMING_POLICY_LABELS[connection.streamingPolicy],
                      ].join(" · ")}
                    </TableCell>
                    <TableCell className="min-w-48 whitespace-normal align-top text-muted-foreground">
                      {connection.timeoutSeconds}s timeout · reasoning {connection.reasoningEffort ?? "omitted"} · probe TTL {connection.probeCacheTtlSeconds}s
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </RunDetailTableFrame>
        )}
      </RunDetailSectionBlock>

      <RunDetailSectionBlock
        blockId="selected-strategies"
        description="Adapter-selected strategy metadata is repeated invocation evidence, so it stays in rows."
        icon={Activity}
        title="Selected strategies"
      >
        {strategySummaries.length === 0 ? (
          <RunDetailEmptyState testId="runs-runtime-strategy-empty">
            No adapter-selected strategy metadata was recorded for this run.
          </RunDetailEmptyState>
        ) : (
          <div className="grid min-w-0 gap-2">
            {hiddenStrategyCount > 0 ? (
              <p className="text-xs text-muted-foreground">
                Showing the first {visibleStrategySummaries.length} of {strategySummaries.length} invocation records.
              </p>
            ) : null}
            <RunDetailTableFrame>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Invocation</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Strategies</TableHead>
                    <TableHead>Usage</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visibleStrategySummaries.map((summary) => (
                    <TableRow
                      data-testid={`runs-runtime-strategy-${summary.key}`}
                      key={summary.key}
                    >
                      <TableCell className="min-w-48 whitespace-normal align-top">
                        <div className="flex min-w-0 flex-col gap-1">
                          <span className="font-medium text-foreground">
                            {summary.agentLabel}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            Step {summary.stepIndex} · Invocation #{summary.invocationId}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="align-top">
                        <Badge variant={statusVariant(summary.status)}>
                          {summary.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="min-w-80 whitespace-normal align-top text-muted-foreground">
                        {strategyItems(summary.strategies)
                          .map((item) => `${item.label}: ${item.value}`)
                          .join(" · ")}
                      </TableCell>
                      <TableCell className="min-w-52 whitespace-normal align-top text-muted-foreground">
                        {summary.usage
                          ? usageItems(summary.usage)
                              .map((item) => `${item.label}: ${item.value}`)
                              .join(" · ")
                          : "Usage not recorded"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </RunDetailTableFrame>
          </div>
        )}
      </RunDetailSectionBlock>

      <RunDetailSectionBlock
        blockId="capability-matrix"
        description="Capability probes are row-first so repeated provider evidence stays comparable."
        icon={Activity}
        title="Capability matrix"
      >
        {resolvedModelConnections.length === 0 ? (
          <RunDetailEmptyState testId="runs-runtime-capability-empty">
            No capability probes were recorded.
          </RunDetailEmptyState>
        ) : (
          <RunDetailTableFrame testId="runs-runtime-capability-matrix">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Provider</TableHead>
                  <TableHead>Capability</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Probe detail</TableHead>
                  <TableHead>Last probed</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {resolvedModelConnections.flatMap((connection) =>
                  CAPABILITY_ORDER.map((capabilityKey) => {
                    const state = connection.capabilities[capabilityKey];
                    return (
                      <TableRow
                        data-testid={`runs-runtime-capability-${connection.key}-${capabilityKey}`}
                        key={`${connection.key}-${capabilityKey}`}
                      >
                        <TableCell className="whitespace-normal align-top font-medium">
                          {connection.name}
                        </TableCell>
                        <TableCell className="whitespace-normal align-top">
                          {CAPABILITY_LABELS[capabilityKey]}
                        </TableCell>
                        <TableCell className="align-top">
                          <Badge variant={capabilityStatusVariant(state.status)}>
                            {capabilityStatusLabel(state.status)}
                          </Badge>
                        </TableCell>
                        <TableCell className="min-w-72 whitespace-normal align-top text-muted-foreground">
                          {state.detail || "No probe detail recorded."}
                        </TableCell>
                        <TableCell className="whitespace-normal align-top text-muted-foreground">
                          {state.lastProbedAt
                            ? formatDateTime(state.lastProbedAt)
                            : "Not recorded"}
                        </TableCell>
                      </TableRow>
                    );
                  }),
                )}
              </TableBody>
            </Table>
          </RunDetailTableFrame>
        )}
      </RunDetailSectionBlock>
    </div>
  );
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
      <Label className="text-sm" htmlFor={id}>
        {label}
      </Label>
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

function draftDiagnosticBadge(diagnostic: RunDraftReadinessDiagnostic) {
  return diagnostic.severity === "error" ? (
    <Badge variant="destructive">Blocking</Badge>
  ) : (
    <Badge
      className="border-chart-3/30 bg-chart-3/10 text-chart-3"
      variant="outline"
    >
      Warning
    </Badge>
  );
}

function RunForkReadinessPanel({
  readiness,
}: {
  readiness: RunDraftReadiness;
}) {
  const diagnostics = diagnosticsFromDraftReadiness(readiness);
  const title = readiness.ready
    ? "Current fork readiness passed"
    : "Current fork readiness blocked";
  const description = readiness.ready
    ? "The backend reports this fork draft is ready to create from current package dependencies."
    : "The backend reports this fork draft is not ready to create from current package dependencies.";

  return (
    <Alert
      data-testid="run-fork-readiness"
      variant={readiness.ready ? "default" : "destructive"}
    >
      <AlertCircle />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="space-y-3">
        <p>{description}</p>
        {diagnostics.length > 0 ? (
          <div className="space-y-2">
            {diagnostics.map((diagnostic) => (
              <div
                className="grid min-w-0 gap-2 rounded-md border bg-background/60 p-3 text-sm md:grid-cols-[auto_minmax(0,10rem)_minmax(0,1fr)] md:items-center"
                key={`${diagnostic.severity}-${diagnostic.field}-${diagnostic.issue}`}
              >
                <div>{draftDiagnosticBadge(diagnostic)}</div>
                <code className="min-w-0 break-all rounded bg-muted/40 px-2 py-1 text-xs">
                  {diagnostic.field}
                </code>
                <span className="min-w-0 break-words">{diagnostic.issue}</span>
              </div>
            ))}
          </div>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}

export function RunForkDialog({
  forkAvailability,
  forkTarget,
  invocationId,
  onClose,
  open,
  resumeStepIndex,
  runId,
}: {
  forkAvailability: RunForkAvailability;
  forkTarget: ForkTargetContext | null;
  invocationId: number | undefined;
  onClose: () => void;
  open: boolean;
  resumeStepIndex: number | undefined;
  runId: string;
}) {
  const navigate = useNavigate();
  const createFork = useCreateRunFork();
  const [presentedForkState, setPresentedForkState] = useState(() => ({
    forkAvailability,
    forkTarget,
    invocationId,
    resumeStepIndex,
  }));
  const [draftTargetKey, setDraftTargetKey] = useState<string | null>(null);
  const [invocationInputText, setInvocationInputText] = useState("");
  const [apiError, setApiError] = useState<string | null>(null);
  const presentedAvailability = open
    ? forkAvailability
    : presentedForkState.forkAvailability;
  const presentedTarget = open ? forkTarget : presentedForkState.forkTarget;
  const presentedInvocationId = open
    ? invocationId
    : presentedForkState.invocationId;
  const presentedResumeStepIndex = open
    ? resumeStepIndex
    : presentedForkState.resumeStepIndex;
  const draftQuery = useRunForkDraft(runId, presentedInvocationId, {
    enabled: open && presentedAvailability.isAvailable,
  });

  const resetLocalState = useCallback(() => {
    setDraftTargetKey(null);
    setInvocationInputText("");
    setApiError(null);
  }, []);

  const closeDialog = () => {
    onClose();
  };

  useEffect(() => {
    if (open) {
      setPresentedForkState({
        forkAvailability: {
          isAvailable: forkAvailability.isAvailable,
          reason: forkAvailability.reason,
        },
        forkTarget,
        invocationId,
        resumeStepIndex,
      });
    }
  }, [
    forkAvailability.isAvailable,
    forkAvailability.reason,
    forkTarget,
    invocationId,
    open,
    resumeStepIndex,
  ]);

  useEffect(() => {
    if (open) {
      return undefined;
    }

    const cleanupTimer = window.setTimeout(
      resetLocalState,
      FORK_DIALOG_CLOSE_CLEANUP_DELAY_MS,
    );
    return () => window.clearTimeout(cleanupTimer);
  }, [open, resetLocalState]);

  useEffect(() => {
    if (!open || !draftQuery.data) {
      return;
    }

    const nextTargetKey = `${draftQuery.data.sourceRunId}:${draftQuery.data.sourceInvocationId}`;
    if (draftTargetKey === nextTargetKey) {
      return;
    }

    setDraftTargetKey(nextTargetKey);
    setInvocationInputText(
      formatJsonEditorValue(draftQuery.data.invocationInput),
    );
    setApiError(null);
  }, [draftQuery.data, draftTargetKey, open]);

  const invocationInputValidation = useMemo(
    () =>
      parseJsonRecord(
        invocationInputText || "{}",
        "Target invocation input JSON",
      ),
    [invocationInputText],
  );
  const forkPayload = useMemo(() => {
    if (
      !draftQuery.data ||
      invocationInputValidation.error ||
      !invocationInputValidation.value
    ) {
      return null;
    }

    return {
      invocationInput: invocationInputValidation.value,
      sourceInvocationId: draftQuery.data.sourceInvocationId,
    };
  }, [
    draftQuery.data,
    invocationInputValidation.error,
    invocationInputValidation.value,
  ]);
  const hasDraftEdits = Boolean(
    draftQuery.data &&
    !areJsonValuesEqual(
      invocationInputValidation.value,
      draftQuery.data.invocationInput,
    ),
  );
  const isSubmitDisabled =
    !forkPayload ||
    createFork.isPending ||
    draftQuery.isPending ||
    Boolean(invocationInputValidation.error) ||
    (draftQuery.data ? !draftQuery.data.ready : false);
  const targetLabel = presentedTarget
    ? `${presentedTarget.invocation.slot} invocation`
    : presentedInvocationId === undefined
      ? "selected invocation"
      : `invocation #${presentedInvocationId}`;

  const resetToDraft = () => {
    if (!draftQuery.data) {
      return;
    }

    setDraftTargetKey(
      `${draftQuery.data.sourceRunId}:${draftQuery.data.sourceInvocationId}`,
    );
    setInvocationInputText(
      formatJsonEditorValue(draftQuery.data.invocationInput),
    );
    setApiError(null);
  };

  const handleSubmit = async () => {
    if (!forkPayload) {
      return;
    }

    setApiError(null);

    try {
      const createdRun = await createFork.mutateAsync({
        runId,
        payload: forkPayload,
      });
      resetLocalState();
      navigate(`/runs/${createdRun.id}`);
    } catch (error) {
      setApiError(
        error instanceof Error ? error.message : "Failed to create the fork.",
      );
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !createFork.isPending) {
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
            <DialogTitle>Fork from {targetLabel}</DialogTitle>
            {presentedResumeStepIndex !== undefined ? (
              <Badge variant="outline">
                Resume at Step {presentedResumeStepIndex}
              </Badge>
            ) : null}
            {presentedInvocationId !== undefined ? (
              <Badge variant="outline">
                Invocation #{presentedInvocationId}
              </Badge>
            ) : null}
            {presentedTarget ? (
              <Badge variant="outline">
                {presentedTarget.invocation.agentKey} v
                {presentedTarget.invocation.agentVersion}
              </Badge>
            ) : null}
            {draftQuery.data ? (
              <Badge variant={hasDraftEdits ? "secondary" : "outline"}>
                {hasDraftEdits
                  ? "Invocation input edited"
                  : "Invocation input unchanged"}
              </Badge>
            ) : null}
          </div>
          <DialogDescription>
            Fork copies upstream context before the resume boundary, edits only
            the selected agent invocation input, and leaves the source run
            unchanged.
          </DialogDescription>
        </DialogHeader>

        {!presentedAvailability.isAvailable ? (
          <Alert variant="destructive" data-testid="run-fork-invalid-target">
            <AlertCircle />
            <AlertTitle>Fork unavailable</AlertTitle>
            <AlertDescription>
              {presentedAvailability.reason ?? DEFAULT_FORK_UNAVAILABLE_REASON}
            </AlertDescription>
          </Alert>
        ) : null}

        {presentedAvailability.isAvailable && draftQuery.isPending ? (
          <div
            className="flex items-center gap-2 rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground"
            data-testid="run-fork-loading"
          >
            <Loader2 className="size-4 animate-spin" />
            Loading target invocation input...
          </div>
        ) : null}

        {presentedAvailability.isAvailable && draftQuery.isError ? (
          <Alert variant="destructive" data-testid="run-fork-draft-error">
            <AlertCircle />
            <AlertTitle>Unable to load fork draft</AlertTitle>
            <AlertDescription>
              {draftQuery.error instanceof Error
                ? draftQuery.error.message
                : "The target invocation input could not be loaded."}
            </AlertDescription>
          </Alert>
        ) : null}

        {apiError ? (
          <Alert variant="destructive" data-testid="run-fork-api-error">
            <AlertCircle />
            <AlertTitle>Fork creation failed</AlertTitle>
            <AlertDescription>{apiError}</AlertDescription>
          </Alert>
        ) : null}

        {draftQuery.data ? (
          <RunForkReadinessPanel readiness={draftQuery.data} />
        ) : null}

        {draftQuery.data ? (
          <Card className="gap-3" data-testid="run-fork-dialog-body">
            <CardHeader>
              <CardTitle className="text-base">
                Target invocation input
              </CardTitle>
              <CardDescription>
                Edit the persisted input for {targetLabel}. Root run parameters
                stay unchanged; use rerun for root parameter edits.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <DetailGrid
                items={[
                  {
                    label: "Source run",
                    value: `Run #${draftQuery.data.sourceRunId}`,
                  },
                  {
                    label: "Source invocation",
                    value: `#${draftQuery.data.sourceInvocationId}`,
                  },
                  {
                    label: "Resume boundary",
                    value:
                      presentedResumeStepIndex === undefined
                        ? "Not recorded"
                        : `Step ${presentedResumeStepIndex}`,
                  },
                  {
                    label: "Target slot",
                    value: presentedTarget?.invocation.slot ?? "Not recorded",
                  },
                ]}
              />
              <JsonEditorField
                disabled={createFork.isPending}
                error={invocationInputValidation.error}
                id="run-fork-invocation-input-json"
                label="Target invocation input JSON"
                onChange={(value) => {
                  setApiError(null);
                  setInvocationInputText(value);
                }}
                rows={10}
                value={invocationInputText}
              />
            </CardContent>
          </Card>
        ) : null}

        <DialogFooter>
          <Button
            disabled={createFork.isPending}
            onClick={closeDialog}
            type="button"
            variant="ghost"
          >
            Cancel
          </Button>
          <Button
            disabled={!draftQuery.data || createFork.isPending}
            onClick={resetToDraft}
            type="button"
            variant="outline"
          >
            <RotateCcw data-icon="inline-start" />
            Reset target input
          </Button>
          <Button
            data-testid="run-fork-submit"
            disabled={isSubmitDisabled}
            onClick={() => void handleSubmit()}
            type="button"
          >
            {createFork.isPending ? (
              <Loader2 className="animate-spin" data-icon="inline-start" />
            ) : null}
            Create fork from invocation
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
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

export function RunContextStrip({
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
  const queueValue = run.queue
    ? `${run.queue.state} · ${formatQueueReasonTitle(run.queue.reason)}`
    : run.status === "queued"
      ? "Queued without queue detail"
      : "No queue hold";

  return (
    <section
      className="grid min-w-0 gap-3 text-sm"
      data-testid="runs-workspace-context"
    >
      <ConsoleSection
        description="Backend-owned progress, queue, status, and token truth for this immutable run snapshot."
        title="Summary"
      >
        <div className="flex min-w-0 flex-col gap-3">
          <ResourceStatusStrip
            items={[
              {
                label: "Status",
                value: run.status,
                tone: runStatusTone(run.status),
              },
              { label: "Target", value: targetKindLabel },
              {
                label: "Queue",
                value: queueValue,
                tone: run.queue ? "warning" : "muted",
              },
            ]}
          />
          <div className="min-w-0" data-testid="runs-summary-execution-row">
            <Badge
              data-testid="runs-detail-status"
              variant={statusVariant(run.status)}
            >
              {run.status}
            </Badge>{" "}
            <Badge data-testid="runs-detail-target-kind" variant="outline">
              {targetKindLabel}
            </Badge>{" "}
            <span className="min-w-0 break-words text-muted-foreground">
              {terminalInvocationsCount} of {allInvocationsCount} invocation(s)
              terminal.
            </span>
          </div>
          <div
            className="flex min-w-0 flex-col gap-2"
            data-testid="runs-summary-progress-row"
          >
            <div className="flex items-center justify-between gap-3 text-muted-foreground">
              <span>Run progress</span>
              <span className="font-medium text-foreground">
                {runProgress}%
              </span>
            </div>
            <Progress className="min-w-0" value={runProgress} />
          </div>
        </div>
      </ConsoleSection>

      <RunTokensWorkspace run={run} />
      <RunRuntimeProfileSection run={run} />
    </section>
  );
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
      <section className="grid min-w-0 gap-3" data-testid="runs-lineage-workspace">
        <RunDetailSectionBlock
          blockId="lineage"
          description="Fork, snapshot, and historical boundaries appear here when the run has upstream lineage."
          icon={GitBranch}
          title="Lineage"
        >
          <CompactModeEmptyState testId="runs-lineage-empty">
            No fork, snapshot replay, copied-step, or historical lineage boundary is recorded for this run.
          </CompactModeEmptyState>
        </RunDetailSectionBlock>
      </section>
    );
  }

  return (
    <section className="grid min-w-0 gap-3" data-testid="runs-lineage-workspace">
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
              value: run.sourceRunId ? `Run #${run.sourceRunId}` : "Snapshot root",
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
              description: "Invocation-level inherited output or input boundaries.",
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

export function RunTokensWorkspace({ run }: { run: RunRead }) {
  const tokenRows = runtimeInvocationTokenRows(run);
  const strategySummaries = runtimeStrategySummaries(run).filter(
    (summary) => summary.usage,
  );
  const hasTokenAccounting = Boolean(
    run.totalTokens ||
      run.inheritedTokens ||
      run.executedTokens ||
      tokenRows.length > 0 ||
      strategySummaries.length > 0,
  );

  if (!hasTokenAccounting) {
    return (
      <section className="grid min-w-0 gap-3" data-testid="runs-tokens-workspace">
        <RunDetailSectionBlock
          blockId="token-accounting"
          description="Token usage appears here when the backend reports run-level or invocation-level accounting."
          icon={Activity}
          title="Token accounting"
        >
          <CompactModeEmptyState testId="runs-tokens-empty">
            No token accounting was reported for this run.
          </CompactModeEmptyState>
        </RunDetailSectionBlock>
      </section>
    );
  }

  return (
    <section className="grid min-w-0 gap-3" data-testid="runs-tokens-workspace">
      <RunDetailSectionBlock
        blockId="token-accounting"
        description="Run-level accounting stays split across total, inherited, and newly executed usage."
        icon={Activity}
        title="Token accounting"
      >
        <div className="grid min-w-0 gap-3">
          <ResourceStatusStrip
            items={[
              { label: "Total", value: run.totalTokens.toLocaleString() },
              {
                label: "Executed",
                value: run.executedTokens.toLocaleString(),
                tone: run.executedTokens > 0 ? "success" : "muted",
              },
              {
                label: "Inherited",
                value: run.inheritedTokens.toLocaleString(),
                tone: run.inheritedTokens > 0 ? "warning" : "muted",
              },
            ]}
          />
          <EvidenceCluster
            items={[
              {
                label: "Read model total",
                value: run.totalTokens.toLocaleString(),
                description: "All usage counted on the run read model.",
              },
              {
                label: "Fresh execution",
                value: run.executedTokens.toLocaleString(),
                description: "Tokens generated by this run execution.",
              },
              {
                label: "Inherited context",
                value: run.inheritedTokens.toLocaleString(),
                description: run.sourceRunId
                  ? `Copied from upstream source run #${run.sourceRunId}.`
                  : "No upstream source run boundary.",
                tone: run.inheritedTokens > 0 ? "warning" : "neutral",
              },
            ]}
            layout="grid"
          />
          <dl className="sr-only" data-testid="runs-summary-usage-row">
            <div>
              <dt>Total tokens</dt>
              <dd>{run.totalTokens}</dd>
            </div>
            <div>
              <dt>Inherited tokens</dt>
              <dd>{run.inheritedTokens}</dd>
            </div>
            <div>
              <dt>Executed tokens</dt>
              <dd>{run.executedTokens}</dd>
            </div>
          </dl>
        </div>
      </RunDetailSectionBlock>

      <RunDetailSectionBlock
        blockId="invocation-usage-rows"
        description="Per-invocation token fields and provider usage metadata stay row-based for auditability."
        icon={Activity}
        title="Invocation usage rows"
      >
        {tokenRows.length === 0 && strategySummaries.length === 0 ? (
          <CompactModeEmptyState testId="runs-tokens-rows-empty">
            No invocation-level token rows were recorded; only run-level accounting is available.
          </CompactModeEmptyState>
        ) : (
          <RunDetailTableFrame>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Invocation</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Run tokens</TableHead>
                  <TableHead>Gateway usage</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tokenRows.map((row) => {
                const gatewayUsage = strategySummaries.find(
                  (summary) => summary.key === row.key,
                )?.usage;
                return (
                  <TableRow data-testid={`runs-token-row-${row.key}`} key={row.key}>
                    <TableCell className="min-w-52 whitespace-normal align-top">
                      <div className="flex min-w-0 flex-col gap-1">
                        <span className="font-medium text-foreground">
                          {row.agentLabel}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          Step {row.stepIndex} · {row.slot} · Invocation #{row.invocationId}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="align-top">
                      <Badge variant={statusVariant(row.status)}>{row.status}</Badge>
                    </TableCell>
                    <TableCell className="align-top text-muted-foreground">
                      {row.tokens.toLocaleString()}
                    </TableCell>
                    <TableCell className="min-w-64 whitespace-normal align-top text-muted-foreground">
                      {gatewayUsage
                        ? usageItems(gatewayUsage)
                            .map((item) => `${item.label}: ${item.value}`)
                            .join(" · ")
                        : "Gateway usage not recorded"}
                    </TableCell>
                  </TableRow>
                );
              })}
              </TableBody>
            </Table>
          </RunDetailTableFrame>
        )}
      </RunDetailSectionBlock>
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
    title: diagnostic.severity === "error" ? "Preflight blocker" : "Preflight warning",
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
      issue: currentPackage.unavailableReason ?? "Current package snapshot is unavailable.",
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
        (capabilityKey) => connection.capabilities[capabilityKey].status === "unsupported",
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

function runDiagnostics(run: RunRead, steps: RunStepRead[]): RunDiagnosticRow[] {
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
        invocation.errorCode || invocation.errorMessage || invocation.errorDetails.length > 0,
      );
      if (!hasError) {
        return;
      }
      diagnostics.push({
        field: `steps.${step.index}.invocations.${invocation.id}`,
        issue: invocation.errorMessage ?? "No invocation error message recorded.",
        key: `agent-${invocation.id}-error`,
        severity: "error",
        source: "Agent invocation",
        title: invocation.errorCode ?? `${invocation.slot} invocation failed`,
      });
    });
    sortedOperationInvocations(step.operationInvocations).forEach((invocation) => {
      const hasError = Boolean(
        invocation.errorCode || invocation.errorMessage || invocation.errorDetails.length > 0,
      );
      if (!hasError) {
        return;
      }
      diagnostics.push({
        field: `steps.${step.index}.operations.${invocation.id}`,
        issue: invocation.errorMessage ?? "No operation error message recorded.",
        key: `operation-${invocation.id}-error`,
        severity: "error",
        source: "Operation invocation",
        title: invocation.errorCode ?? `${invocation.slot} operation failed`,
      });
    });
    return diagnostics;
  });
  const forkCandidates = steps.flatMap((step) =>
    step.status === "succeeded"
      ? sortedInvocations(step.invocations).filter(
          (invocation) => invocation.status === "succeeded" && invocation.persistedAt,
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
    ...(run.targetKind === "workflowPackage" && run.status === "succeeded" && forkCandidates.length === 0
      ? [
          {
            field: "fork.invocation",
            issue: "No succeeded persisted agent invocation is available for invocation-specific fork creation.",
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
  const errorCount = diagnostics.filter((item) => item.severity === "error").length;
  const warningCount = diagnostics.length - errorCount;

  if (diagnostics.length === 0) {
    return (
      <section className="grid min-w-0 gap-3" data-testid="runs-diagnostics-workspace">
        <RunDetailSectionBlock
          blockId="diagnostics"
          description="Warnings, failures, unsupported capabilities, and retry/fork safety checks appear here."
          icon={AlertCircle}
          title="Diagnostics"
        >
          <CompactModeEmptyState testId="runs-diagnostics-empty">
            No run diagnostics, queue warnings, runtime capability warnings, or safety blockers are recorded.
          </CompactModeEmptyState>
        </RunDetailSectionBlock>
      </section>
    );
  }

  return (
    <section className="grid min-w-0 gap-3" data-testid="runs-diagnostics-workspace">
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
      <section className="grid min-w-0 gap-3" data-testid="runs-memory-workspace">
        <RunDetailSectionBlock
          blockId="memory"
          description="Memory retrieval, write, review, audit, and compact artifact evidence appears here when recorded."
          icon={FileText}
          title="Memory"
        >
          <CompactModeEmptyState testId="runs-memory-empty">
            No retrieval, write, review, audit, or compact memory artifact evidence was recorded for this run.
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
  const outputState = finalOutputState(run);
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
      summary: `Final output ${outputState.label.toLowerCase()}`,
      target: { type: "run" },
      title: "Final output",
      tone:
        outputState.tone === "danger"
          ? "destructive"
          : outputState.tone === "warning"
            ? "outline"
            : "secondary",
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
      tone: artifact.auditLinks?.report ? ("secondary" as const) : ("outline" as const),
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
                const paneMatches = !row.pane || activeInspection.pane === row.pane;
                const isActive =
                  activeInspection.selected !== false &&
                  targetMatches &&
                  (row.target.type === "run" ? paneMatches : true);
                const shouldRenderInline = isActive && activeInspection.mode === "metadata";
                const selectRow = () => onSelect(row.target, row.pane, "metadata");
                const dataRow = (
                  <TableRow
                    aria-label={`${row.title} evidence row`}
                    className="cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    data-state={isActive ? "selected" : undefined}
                    data-testid={`runs-audit-row-${row.id}`}
                    key={row.id}
                    onClick={selectRow}
                    onKeyDown={(event) => handleSelectableRowKeyDown(event, selectRow)}
                    role="button"
                    tabIndex={0}
                  >
                    <TableCell className="min-w-56 whitespace-normal align-top">
                      <Button
                        className="h-auto w-full cursor-pointer justify-start px-2 py-1.5 text-left"
                        onClick={(event) => {
                          event.stopPropagation();
                          selectRow();
                        }}
                        size="sm"
                        type="button"
                        variant={isActive ? "secondary" : "ghost"}
                      >
                        {row.title}
                      </Button>
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
                  const selectStep = () => onSelect(stepTarget, undefined, "execution");
                  const stepRow = (
                    <TableRow
                      aria-label={`Step ${step.index} execution row`}
                      className="cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                      data-state={isStepActive ? "selected" : undefined}
                      data-testid={`runs-step-${step.index}`}
                      id={`step-${step.index}`}
                      key={`step-${step.id}`}
                      onClick={selectStep}
                      onKeyDown={(event) => handleSelectableRowKeyDown(event, selectStep)}
                      role="button"
                      tabIndex={0}
                    >
                      <TableCell className="min-w-56 whitespace-normal align-top">
                        <Button
                          className="h-auto w-full cursor-pointer justify-start px-2 py-1.5 text-left"
                          onClick={(event) => {
                            event.stopPropagation();
                            selectStep();
                          }}
                          size="sm"
                          type="button"
                          variant={isStepActive ? "secondary" : "ghost"}
                        >
                          <span className="flex min-w-0 items-center gap-2">
                            <StepStatusIndicator
                              state={indicatorState}
                              stepIndex={step.index}
                            />
                            <span className="font-medium">Step {step.index}</span>
                          </span>
                        </Button>
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
                        {invocations.length} agent invocation(s) · {operationInvocations.length} operation invocation(s)
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
                          <Button
                            className="h-auto w-full cursor-pointer justify-start px-2 py-1.5 text-left"
                            onClick={(event) => {
                              event.stopPropagation();
                              selectInvocation();
                            }}
                            size="sm"
                            type="button"
                            variant={isActive ? "secondary" : "ghost"}
                          >
                            <span className="flex min-w-0 flex-col gap-0.5">
                              <span className="font-medium">
                                {invocation.slot} agent
                              </span>
                              <span className="text-xs text-muted-foreground">
                                Invocation #{invocation.id}
                              </span>
                            </span>
                          </Button>
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
                  const operationRows = operationInvocations.flatMap((invocation) => {
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
                          <Button
                            className="h-auto w-full cursor-pointer justify-start px-2 py-1.5 text-left"
                            onClick={(event) => {
                              event.stopPropagation();
                              selectOperation();
                            }}
                            size="sm"
                            type="button"
                            variant={isActive ? "secondary" : "ghost"}
                          >
                            <span className="flex min-w-0 flex-col gap-0.5">
                              <span className="font-medium">
                                {invocation.slot} operation
                              </span>
                              <span className="text-xs text-muted-foreground">
                                Invocation #{invocation.id}
                              </span>
                            </span>
                          </Button>
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
                          {invocation.operationKey} · operation forks are not supported in this phase
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
                  });

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
          onClick={() => onSelect(activeInspection.target, pane, activeInspection.mode)}
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
          No retrieval, write, review, audit, or compact memory artifact evidence was recorded for this run.
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
    <Card data-testid={`runs-step-${step.index}-summary`}>
      <CardContent className="min-w-0 space-y-5 pt-6">
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
            className="grid gap-x-5 gap-y-2 rounded-md border bg-muted/20 p-3 text-sm sm:grid-cols-2 xl:grid-cols-3"
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
      </CardContent>
    </Card>
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
      <section className="min-w-0" data-testid="runs-stacked-section-final-output">
        <RunFinalOutputPane run={run} />
      </section>
      <section
        className="min-w-0"
        data-testid="runs-stacked-section-evidence-availability"
      >
        <RunEvidenceAvailabilitySection run={run} />
      </section>
      <section className="min-w-0" data-testid="runs-stacked-section-diagnostics">
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
        <div className="grid min-w-0 gap-3" data-testid="runs-runtime-workspace">
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
          Select lineage evidence from the center workspace to inspect raw detail.
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
      className="grid min-w-0 gap-3 rounded-lg border bg-card/80 p-3"
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
            <EvidencePaneNav activeInspection={activeInspection} onSelect={onSelect} />
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
