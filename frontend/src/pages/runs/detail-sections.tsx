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
  Database,
  Download,
  FileText,
  GitBranch,
  Loader2,
  RotateCcw,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Link, useNavigate } from "react-router";

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
import { ScrollArea } from "@/components/ui/scroll-area";
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
  getRunForkAvailability,
  progressForInvocations,
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
  headingId,
  label,
  testId,
  value,
}: {
  headingId: string;
  label: string;
  testId: string;
  value: unknown;
}) {
  return (
    <section aria-labelledby={headingId} className="min-w-0 space-y-3">
      <h3 className="text-base font-medium leading-none" id={headingId}>
        {label}
      </h3>
      <PayloadViewTabs label={label} testId={testId} value={value} />
    </section>
  );
}

function RunFinalOutputPane({ run }: { run: RunRead }) {
  const isPendingFinalOutput =
    (run.status === "queued" || run.status === "running") &&
    run.finalOutput === null;

  return (
    <Card data-testid="runs-detail-final-output-card">
      <CardContent className="min-w-0 space-y-5 pt-6">
        {!isPendingFinalOutput ? (
          <RunPayloadPane
            headingId="runs-final-output-heading"
            label="Final output"
            testId="runs-detail-final-output"
            value={run.finalOutput}
          />
        ) : (
          <section
            aria-labelledby="runs-final-output-heading"
            className="space-y-3"
          >
            <h3
              className="text-base font-medium leading-none"
              id="runs-final-output-heading"
            >
              Final output
            </h3>
            <div
              className="rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground"
              data-testid="runs-detail-final-output"
            >
              Final output is not available yet.
            </div>
          </section>
        )}
      </CardContent>
    </Card>
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

const PROTOCOL_PROFILE_LABELS: Record<ModelConnectionProtocolProfile, string> = {
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

const REASONING_POLICY_LABELS: Record<ModelConnectionReasoningPolicy, string> = {
  allow: "Allow reasoning",
  forbid: "Forbid reasoning",
};

const STREAMING_POLICY_LABELS: Record<ModelConnectionStreamingPolicy, string> = {
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

type RuntimeProfileMode = "summary" | "audit";

type RuntimeCapabilityCounts = Record<
  ModelConnectionCapabilityStatus,
  number
>;

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

function runtimeSummaryItems(
  connection: RunPackageResolvedModelConnectionRead,
): DetailItem[] {
  return [
    { label: "Captured model", value: connection.modelId },
    { label: "Endpoint", value: connection.baseUrl },
    {
      label: "Protocol",
      value: PROTOCOL_PROFILE_LABELS[connection.protocolProfile],
    },
    {
      label: "Runtime controls",
      value: [
        OUTPUT_STRATEGY_POLICY_LABELS[connection.outputStrategyPolicy],
        PARALLEL_TOOL_CALLS_POLICY_LABELS[connection.parallelToolCallsPolicy],
        REASONING_POLICY_LABELS[connection.reasoningPolicy],
        STREAMING_POLICY_LABELS[connection.streamingPolicy],
      ].join(" · "),
    },
    {
      label: "Capability summary",
      value: formatRuntimeCapabilitySummary(connection),
    },
    {
      label: "Captured execution settings",
      value: `${connection.timeoutSeconds}s timeout · reasoning ${connection.reasoningEffort ?? "omitted"}`,
    },
  ];
}

function unsupportedRuntimeCapabilities(
  connection: RunPackageResolvedModelConnectionRead,
): Array<keyof ModelConnectionCapabilities> {
  return CAPABILITY_ORDER.filter(
    (capabilityKey) => connection.capabilities[capabilityKey].status === "unsupported",
  );
}

function RunRuntimeProfileSection({ run }: { run: RunRead }) {
  const [profileMode, setProfileMode] = useState<RuntimeProfileMode>("summary");
  const provenance = run.packageProvenance;
  if (run.targetKind !== "workflowPackage" || !provenance) {
    return null;
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
    <section
      className="min-w-0 space-y-3"
      data-testid="runs-runtime-profile"
    >
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="text-base font-medium leading-none">Runtime profile</h3>
        <div
          className="flex min-w-0 flex-wrap items-center gap-2"
          data-testid="runs-runtime-profile-mode"
        >
          <Button
            className="h-8 cursor-pointer"
            onClick={() => setProfileMode("summary")}
            size="sm"
            type="button"
            variant={profileMode === "summary" ? "secondary" : "outline"}
          >
            Summary
          </Button>
          <Button
            className="h-8 cursor-pointer"
            onClick={() => setProfileMode("audit")}
            size="sm"
            type="button"
            variant={profileMode === "audit" ? "secondary" : "outline"}
          >
            Audit evidence
          </Button>
        </div>
      </div>

      {resolvedModelConnections.length === 0 ? (
        <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
          No resolved model connections were recorded for this run.
        </div>
      ) : profileMode === "summary" ? (
        <div
          className="grid gap-4 2xl:grid-cols-2"
          data-testid="runs-runtime-summary"
        >
          {resolvedModelConnections.map((connection) => {
            const capabilityCounts = runtimeCapabilityCounts(connection);
            const unsupportedCapabilities =
              unsupportedRuntimeCapabilities(connection);
            return (
              <article
                className="min-w-0 space-y-3 border-t border-border pt-3 first:border-t-0 first:pt-0"
                data-testid={`runs-runtime-profile-connection-${connection.key}`}
                key={connection.key}
              >
                <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 space-y-1">
                    <p className="truncate text-sm font-medium text-foreground">
                      {connection.name}
                    </p>
                    <p className="break-all text-xs text-muted-foreground">
                      {connection.key}
                    </p>
                  </div>
                  <div className="flex min-w-0 flex-wrap items-center gap-1.5 sm:justify-end">
                    <Badge variant="outline">
                      {runtimeConnectionKindLabel(connection.connectionKind)}
                    </Badge>
                    <Badge variant="secondary">
                      {PROTOCOL_PROFILE_LABELS[connection.protocolProfile]}
                    </Badge>
                    <Badge variant="outline">
                      {capabilityCounts.supported} supported
                    </Badge>
                    <Badge
                      variant={
                        capabilityCounts.unsupported > 0 ? "destructive" : "outline"
                      }
                    >
                      {capabilityCounts.unsupported} unsupported
                    </Badge>
                    <Badge
                      variant={connection.hasApiKey ? "secondary" : "outline"}
                    >
                      {connection.hasApiKey
                        ? "Credential present"
                        : "No credential"}
                    </Badge>
                  </div>
                </div>
                <DetailGrid items={runtimeSummaryItems(connection)} />
                {unsupportedCapabilities.length > 0 ? (
                  <p className="break-words border-l border-border pl-3 text-sm text-muted-foreground">
                    Unsupported: {" "}
                    {unsupportedCapabilities
                      .map((capabilityKey) => CAPABILITY_LABELS[capabilityKey])
                      .join(", ")}
                  </p>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : (
        <div className="space-y-3" data-testid="runs-runtime-audit-evidence">
          {resolvedModelConnections.map((connection) => (
            <article
              className="space-y-3 rounded-md border bg-card/80 p-3"
              data-testid={`runs-runtime-audit-connection-${connection.key}`}
              key={connection.key}
            >
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-foreground">
                    {connection.name}
                  </p>
                  <p className="break-all text-xs text-muted-foreground">
                    {connection.key}
                  </p>
                </div>
                <Badge variant="outline">
                  {runtimeConnectionKindLabel(connection.connectionKind)}
                </Badge>
                <Badge variant="secondary">
                  {PROTOCOL_PROFILE_LABELS[connection.protocolProfile]}
                </Badge>
              </div>
              <DetailGrid
                items={[
                  {
                    label: "Protocol profile",
                    value: PROTOCOL_PROFILE_LABELS[connection.protocolProfile],
                  },
                  { label: "Model id", value: connection.modelId },
                  { label: "Base URL", value: connection.baseUrl },
                  {
                    label: "Reasoning effort",
                    value: connection.reasoningEffort ?? "Not recorded",
                  },
                  {
                    label: "Timeout",
                    value: `${connection.timeoutSeconds}s`,
                  },
                  {
                    label: "Probe cache TTL",
                    value: `${connection.probeCacheTtlSeconds}s`,
                  },
                ]}
              />
              <section className="space-y-2">
                <h4 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Compatibility policies
                </h4>
                <DetailGrid
                  items={[
                    {
                      label: "Output strategy",
                      value:
                        OUTPUT_STRATEGY_POLICY_LABELS[
                          connection.outputStrategyPolicy
                        ],
                    },
                    {
                      label: "Parallel tool calls",
                      value:
                        PARALLEL_TOOL_CALLS_POLICY_LABELS[
                          connection.parallelToolCallsPolicy
                        ],
                    },
                    {
                      label: "Reasoning",
                      value: REASONING_POLICY_LABELS[connection.reasoningPolicy],
                    },
                    {
                      label: "Streaming",
                      value: STREAMING_POLICY_LABELS[connection.streamingPolicy],
                    },
                  ]}
                />
              </section>
              <section className="space-y-2">
                <h4 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Capability probes
                </h4>
                <div className="grid gap-2 xl:grid-cols-2">
                  {CAPABILITY_ORDER.map((capabilityKey) => {
                    const state = connection.capabilities[capabilityKey];
                    return (
                      <div
                        className="flex min-w-0 items-start justify-between gap-3 rounded-md border bg-background/70 p-3"
                        key={capabilityKey}
                      >
                        <div className="min-w-0 space-y-1">
                          <p className="text-sm font-medium text-foreground">
                            {CAPABILITY_LABELS[capabilityKey]}
                          </p>
                          <p className="break-words text-xs text-muted-foreground">
                            {state.detail || "No probe detail recorded."}
                          </p>
                        </div>
                        <div className="flex shrink-0 flex-col items-end gap-1 text-right">
                          <Badge variant={capabilityStatusVariant(state.status)}>
                            {capabilityStatusLabel(state.status)}
                          </Badge>
                          {state.lastProbedAt ? (
                            <p className="text-[11px] text-muted-foreground">
                              Last probed {formatDateTime(state.lastProbedAt)}
                            </p>
                          ) : null}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            </article>
          ))}
          <section
            className="space-y-3 rounded-md border bg-card/70 p-3"
            data-testid="runs-runtime-selected-strategies"
          >
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
              <h4 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Selected strategies
              </h4>
              <Badge variant="outline">
                {strategySummaries.length} invocation
                {strategySummaries.length === 1 ? "" : "s"}
              </Badge>
            </div>
            {strategySummaries.length === 0 ? (
              <div className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
                No adapter-selected strategy metadata was recorded for this run.
              </div>
            ) : (
              <div className="space-y-3">
                {hiddenStrategyCount > 0 ? (
                  <p className="text-xs text-muted-foreground">
                    Showing the first {visibleStrategySummaries.length} of {strategySummaries.length} invocation records.
                  </p>
                ) : null}
                {visibleStrategySummaries.map((summary) => (
                  <article
                    className="space-y-3 rounded-md border bg-background/70 p-3"
                    data-testid={`runs-runtime-strategy-${summary.key}`}
                    key={summary.key}
                  >
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <Badge variant="outline">Step {summary.stepIndex}</Badge>
                      <Badge variant={statusVariant(summary.status)}>
                        {summary.status}
                      </Badge>
                      <span className="min-w-0 break-words text-sm font-medium text-foreground">
                        {summary.agentLabel}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        Invocation #{summary.invocationId}
                      </span>
                    </div>
                    <DetailGrid items={strategyItems(summary.strategies)} />
                    {summary.usage ? (
                      <DetailGrid items={usageItems(summary.usage)} />
                    ) : null}
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </section>
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
  const isActiveTarget = isInspectionTargetEqual(
    activeInspection.target,
    target,
  );
  const isActive = isActiveTarget && (!pane || activeInspection.pane === pane);

  return (
    <Button
      className={cn(
        "h-auto w-full cursor-pointer justify-start px-3 py-2 text-left",
        className,
      )}
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
  return (
    <section
      className="grid min-w-0 gap-4 text-sm"
      data-testid="runs-workspace-context"
    >
      <section
        aria-label="Execution status"
        className="min-w-0 space-y-2"
        data-testid="runs-summary-execution-row"
      >
        <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Execution status
        </h2>
        <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2">
          <Badge
            data-testid="runs-detail-status"
            variant={statusVariant(run.status)}
          >
            {run.status}
          </Badge>
          <Badge data-testid="runs-detail-target-kind" variant="outline">
            {targetKindLabel}
          </Badge>
          <span className="min-w-0 break-words text-muted-foreground">
            {terminalInvocationsCount} of {allInvocationsCount} invocation(s)
            terminal.
          </span>
        </div>
      </section>

      <section aria-label="Token summary" className="min-w-0 space-y-2">
        <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Token summary
        </h2>
        <dl
          className="flex min-w-0 flex-wrap items-center gap-x-6 gap-y-2 text-muted-foreground"
          data-testid="runs-summary-usage-row"
        >
          <div className="flex items-center gap-2">
            <dt>Total tokens</dt>
            <dd className="font-medium text-foreground">{run.totalTokens}</dd>
          </div>
          <div className="flex items-center gap-2">
            <dt>Inherited tokens</dt>
            <dd className="font-medium text-foreground">
              {run.inheritedTokens}
            </dd>
          </div>
          <div className="flex items-center gap-2">
            <dt>Executed tokens</dt>
            <dd className="font-medium text-foreground">
              {run.executedTokens}
            </dd>
          </div>
        </dl>
      </section>

      <section
        aria-label="Progress"
        className="min-w-0 space-y-2"
        data-testid="runs-summary-progress-row"
      >
        <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Progress
        </h2>
        <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
          <div className="flex items-center justify-between gap-3 text-muted-foreground sm:w-44 sm:justify-start">
            <span>Run progress</span>
            <span className="font-medium text-foreground">{runProgress}%</span>
          </div>
          <Progress className="min-w-0 flex-1" value={runProgress} />
        </div>
      </section>

      <RunRuntimeProfileSection run={run} />
    </section>
  );
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
  onSelect,
  run,
  steps,
  traceSpanEntries,
}: {
  activeInspection: RunInspectionState;
  onSelect: (target: RunInspectionTarget, pane?: RunInspectionPane) => void;
  run: RunRead;
  steps: RunStepRead[];
  traceSpanEntries: TraceSpanEntry[];
}) {
  return (
    <aside
      className="flex h-full min-h-0 min-w-0 flex-col bg-background"
      data-testid="runs-execution-outline"
    >
      <div className="shrink-0 border-b border-border bg-background px-4 py-3">
        <div className="flex items-center gap-2">
          <Activity className="size-4 text-muted-foreground" />
          <h2 className="text-base font-semibold tracking-tight">
            Execution outline
          </h2>
        </div>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-2 p-3">
          <div id="run-context">
            <InspectionSelectorButton
              activeInspection={activeInspection}
              className="px-2 py-1.5"
              onSelect={onSelect}
              pane="finalOutput"
              target={{ type: "run" }}
            >
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="font-medium">Run result</span>
                <span className="text-xs text-muted-foreground">
                  Final output, input, lineage, and memory
                </span>
              </span>
            </InspectionSelectorButton>
          </div>
          {steps.length === 0 ? (
            <div
              className="rounded-md border border-dashed p-4 text-sm text-muted-foreground"
              data-testid="runs-empty-steps"
            >
              No steps have been planned for this run yet.
            </div>
          ) : null}
          {steps.map((step) => {
            const invocations = sortedInvocations(step.invocations);
            const operationInvocations = sortedOperationInvocations(
              step.operationInvocations,
            );
            const allInvocations = [...invocations, ...operationInvocations];
            const firstAgentInvocation = invocations[0];
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

            return (
              <div
                className={cn(
                  "min-w-0 border-l border-border pl-2 transition-colors",
                  isStepActive && "border-primary",
                  indicatorState === "executing" && "border-primary",
                  indicatorState === "completed" && !isStepActive && "border-positive/60",
                )}
                data-testid={`runs-step-${step.index}`}
                id={`step-${step.index}`}
                key={step.id}
              >
                <InspectionSelectorButton
                  activeInspection={activeInspection}
                  className="px-2 py-1.5"
                  onSelect={onSelect}
                  target={stepTarget}
                >
                  <span className="flex min-w-0 flex-1 flex-col gap-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <StepStatusIndicator
                        state={indicatorState}
                        stepIndex={step.index}
                      />
                      <span className="font-medium">Step {step.index}</span>
                      <Badge variant={statusVariant(step.status)}>
                        {step.status}
                      </Badge>
                      <Badge variant="outline">{step.origin} origin</Badge>
                      <Badge variant="secondary">{stepProgress}%</Badge>
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {invocations.length} agent invocation(s) ·{" "}
                      {operationInvocations.length} operation invocation(s)
                      {firstAgentInvocation
                        ? ` · first agent ${firstAgentInvocation.slot} #${firstAgentInvocation.id}`
                        : ""}
                    </span>
                    <StepTraceSummary
                      entries={stepTraceEntries}
                      stepIndex={step.index}
                    />
                  </span>
                </InspectionSelectorButton>
                {allInvocations.length > 0 ? (
                  <div
                    className="mt-1 space-y-1 pl-2"
                    data-testid={`runs-step-${step.index}-invocation-targets`}
                  >
                    {invocations.map((invocation) => {
                      const invocationTarget: RunInspectionTarget = {
                        type: "agentInvocation",
                        invocationId: invocation.id,
                      };

                      return (
                        <div
                          className="min-w-0"
                          data-testid={`runs-invocation-${invocation.id}-outline-entry`}
                          id={`invocation-${invocation.id}`}
                          key={invocation.id}
                        >
                          <InspectionSelectorButton
                            activeInspection={activeInspection}
                            className="px-2 py-1.5 text-xs"
                            onSelect={onSelect}
                            target={invocationTarget}
                          >
                            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                              <span className="flex flex-wrap items-center gap-1.5">
                                <Badge
                                  variant={statusVariant(invocation.status)}
                                >
                                  {invocation.status}
                                </Badge>
                                <span className="font-medium">
                                  {invocation.slot} agent
                                </span>
                                <span className="text-muted-foreground">
                                  #{invocation.id}
                                </span>
                              </span>
                              <span className="text-muted-foreground">
                                {invocation.agentKey} v{invocation.agentVersion} ·
                                input {invocation.resolvedInputOrigin}
                              </span>
                            </span>
                          </InspectionSelectorButton>
                        </div>
                      );
                    })}
                    {operationInvocations.map((invocation) => {
                      const operationTarget: RunInspectionTarget = {
                        type: "operationInvocation",
                        invocationId: invocation.id,
                      };

                      return (
                        <div
                          className="min-w-0"
                          data-testid={`runs-operation-${invocation.id}-outline-entry`}
                          id={`operation-invocation-${invocation.id}`}
                          key={invocation.id}
                        >
                          <InspectionSelectorButton
                            activeInspection={activeInspection}
                            className="px-2 py-1.5 text-xs"
                            onSelect={onSelect}
                            target={operationTarget}
                          >
                            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                              <span className="flex flex-wrap items-center gap-1.5">
                                <Badge
                                  variant={statusVariant(invocation.status)}
                                >
                                  {invocation.status}
                                </Badge>
                                <span className="font-medium">
                                  {invocation.slot} operation
                                </span>
                                <span className="text-muted-foreground">
                                  #{invocation.id}
                                </span>
                              </span>
                              <span className="text-muted-foreground">
                                {invocation.operationKey} · operation forks are
                                not supported in this phase
                              </span>
                            </span>
                          </InspectionSelectorButton>
                        </div>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            );
          })}
          {run.memoryArtifacts.length > 0 ? (
            <div className="border-l border-border pl-2">
              <p className="px-2 py-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Compact memory artifacts
              </p>
              <div className="space-y-1">
                {run.memoryArtifacts.map((artifact) => (
                  <InspectionSelectorButton
                    activeInspection={activeInspection}
                    className="px-2 py-1.5 text-xs"
                    key={artifact.memoryId}
                    onSelect={onSelect}
                    target={{
                      type: "memoryArtifact",
                      memoryId: artifact.memoryId,
                    }}
                    testId={`runs-memory-outline-${artifact.memoryId}`}
                  >
                    <span
                      className="flex min-w-0 flex-col gap-0.5"
                      id={`memory-${artifact.memoryId}`}
                    >
                      <span className="flex items-center gap-2">
                        <Database className="size-3.5" />
                        {artifact.summary}
                      </span>
                      <span className="text-muted-foreground">
                        {artifact.status} · {memoryProvenanceLabel(artifact)}
                      </span>
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
    <div
      className="flex min-w-0 flex-wrap gap-2"
      data-testid="runs-evidence-pane-nav"
    >
      {inspectionPanesForTarget(activeInspection.target).map((pane) => (
        <Button
          className="max-w-full cursor-pointer"
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
    <section
      aria-labelledby={`runs-memory-group-${definition.key}-heading`}
      className="space-y-3"
      data-testid={`runs-memory-group-${definition.key}`}
    >
      <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3
            className="text-base font-medium leading-none"
            id={`runs-memory-group-${definition.key}-heading`}
          >
            {definition.title}
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {definition.description}
          </p>
        </div>
        <Badge variant="outline">
          {events.length} event{events.length === 1 ? "" : "s"}
        </Badge>
      </div>
      {events.length > 0 ? (
        <div className="grid gap-3">
          {events.map((event) => (
            <MemoryEventCard event={event} key={event.id} />
          ))}
        </div>
      ) : (
        <div className="rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground">
          {definition.emptyCopy}
        </div>
      )}
    </section>
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
    <Card data-testid="runs-memory-evidence">
      <CardHeader>
        <CardTitle className="text-base">Run memory evidence</CardTitle>
        <CardDescription>
          Run-scoped memory events and artifacts.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {!hasEvents ? (
          <div
            className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground"
            data-testid="runs-memory-evidence-empty"
          >
            No run memory evidence recorded.
          </div>
        ) : (
          MEMORY_EVENT_GROUPS.map((definition) => (
            <MemoryEventGroupSection
              definition={definition}
              events={groupedEvents[definition.key]}
              key={definition.key}
            />
          ))
        )}

        <section
          aria-labelledby="runs-memory-compact-artifacts-heading"
          className="space-y-3"
          data-testid="runs-memory-compact-artifacts"
        >
          <div>
            <h3
              className="text-base font-medium leading-none"
              id="runs-memory-compact-artifacts-heading"
            >
              Compact artifact slice
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              These artifacts summarize memory rows written for human audit;
              they do not replace the event groups above.
            </p>
          </div>
          {hasArtifacts ? (
            <div className="grid gap-3">
              {run.memoryArtifacts.map((artifact) => (
                <MemoryArtifactSummaryCard
                  artifact={artifact}
                  key={artifact.memoryId}
                />
              ))}
            </div>
          ) : (
            <div
              className="rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground"
              data-testid="runs-memory-artifacts-empty"
            >
              No compact memory artifacts were written by this run.
            </div>
          )}
        </section>
      </CardContent>
    </Card>
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

export function EvidenceViewer({
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
}: {
  activeInspection: RunInspectionState;
  copiedInvocations: number;
  copiedSteps: number;
  isCurrentFork: boolean;
  onOpenFork: (stepIndex: number, invocationId: number) => void;
  onSelect: (target: RunInspectionTarget, pane?: RunInspectionPane) => void;
  plannedInvocations: number;
  plannedSteps: number;
  run: RunRead;
  steps: RunStepRead[];
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
    content = artifact ? <MemoryArtifactEvidence artifact={artifact} run={run} /> : null;
  } else if (activeInspection.pane === "input") {
    content = (
      <RunPayloadPane
        headingId="runs-input-heading"
        label="Run input"
        testId="runs-detail-input"
        value={run.input}
      />
    );
  } else if (activeInspection.pane === "lineage") {
    content = (
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
    content = <RunMemoryEvidence run={run} />;
  } else {
    content = <RunFinalOutputPane run={run} />;
  }

  return (
    <section
      className="flex h-full min-h-0 min-w-0 flex-col"
      data-testid="runs-evidence-viewer"
    >
      <div className="shrink-0 border-b border-border bg-background px-4 py-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold tracking-tight">
                {title}
              </h2>
              <Badge variant="outline">
                {inspectionPaneLabel(activeInspection.pane)}
              </Badge>
            </div>
          </div>
          <div className="flex min-w-0 flex-col gap-2 sm:items-end">
            {selectedInvocationForkAction}
            <EvidencePaneNav
              activeInspection={activeInspection}
              onSelect={onSelect}
            />
          </div>
        </div>
      </div>
      <ScrollArea className="min-h-0 min-w-0 flex-1 [&_[data-slot=scroll-area-viewport]>div]:!block [&_[data-slot=scroll-area-viewport]>div]:!min-w-0 [&_[data-slot=scroll-area-viewport]>div]:w-full [&_[data-slot=scroll-area-viewport]>div]:max-w-full [&_[data-slot=scroll-area-viewport]>div]:overflow-x-hidden">
        <div
          className="min-h-full min-w-0 overflow-hidden p-4"
          data-testid="runs-active-evidence-viewer"
        >
          {content ?? (
            <div className="rounded-md border bg-muted/20 p-4 text-sm text-muted-foreground">
              Selected evidence is no longer available.
            </div>
          )}
        </div>
      </ScrollArea>
    </section>
  );
}
