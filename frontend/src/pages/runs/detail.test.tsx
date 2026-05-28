import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import type {
  RunAgentInvocationRead,
  RunForkDraftRead,
  RunMemoryEventRead,
  RunPackageResolvedModelConnectionRead,
  RunRead,
  RunRerunDraftRead,
  RunStepRead,
} from "@/lib/types/run";
import type {
  ModelConnectionCapabilities,
  ModelConnectionCapabilityState,
} from "@/lib/types/model-connection";

import { RunsDetailPage } from "./detail";

const createRunRerunMutateAsyncMock = vi.fn();
const createRunForkMutateAsyncMock = vi.fn();
const navigateMock = vi.fn();
const setSearchParamsMock = vi.fn();
const useCreateRunForkMock = vi.fn();
const useCreateRunRerunMock = vi.fn();
const useRunForkDraftMock = vi.fn();
const useRunRerunDraftMock = vi.fn();
const useRunMock = vi.fn();
let searchParamsMock = new URLSearchParams();

vi.mock("react-router", () => ({
  Link: ({ children, to }: { children: ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
  useLocation: () => ({
    hash: "",
    pathname: "/runs/42",
    search: searchParamsMock.toString(),
  }),
  useNavigate: () => navigateMock,
  useParams: () => ({ runId: "42" }),
  useSearchParams: () => [searchParamsMock, setSearchParamsMock],
}));

vi.mock("@/hooks/use-runs", () => ({
  useCreateRunFork: () => useCreateRunForkMock(),
  useCreateRunRerun: () => useCreateRunRerunMock(),
  useRun: () => useRunMock(),
  useRunForkDraft: (...args: unknown[]) => useRunForkDraftMock(...args),
  useRunRerunDraft: (...args: unknown[]) => useRunRerunDraftMock(...args),
}));

vi.mock("@xyflow/react", () => ({
  applyNodeChanges: (
    changes: Array<{
      id: string;
      position?: { x: number; y: number };
      type: string;
    }>,
    nodes: Array<{ id: string; position?: { x: number; y: number } }>,
  ) =>
    nodes.map((node) => {
      const positionChange = changes.find(
        (change) => change.id === node.id && change.type === "position",
      );
      return positionChange?.position
        ? { ...node, position: positionChange.position }
        : node;
    }),
  Background: () => <div data-testid="mock-react-flow-background" />,
  BackgroundVariant: { Dots: "dots" },
  Handle: () => <span data-testid="mock-react-flow-handle" />,
  MarkerType: { ArrowClosed: "arrowclosed" },
  Position: { Left: "left", Right: "right" },
  ReactFlow: ({
    autoPanOnNodeDrag,
    children,
    connectOnClick,
    edges = [],
    edgesFocusable,
    elementsSelectable,
    fitViewOptions,
    maxZoom,
    minZoom,
    nodes = [],
    nodesConnectable,
    nodesDraggable,
    nodesFocusable,
    onNodesChange,
    onViewportChange,
    panOnDrag,
    preventScrolling,
    selectNodesOnDrag,
    viewport,
    zoomOnDoubleClick,
    zoomOnPinch,
    zoomOnScroll,
    ...props
  }: {
    "aria-label"?: string;
    autoPanOnNodeDrag?: boolean;
    children?: ReactNode;
    connectOnClick?: boolean;
    edges?: Array<{ id: string; label?: ReactNode }>;
    edgesFocusable?: boolean;
    elementsSelectable?: boolean;
    fitViewOptions?: { maxZoom?: number; padding?: number };
    maxZoom?: number;
    minZoom?: number;
    nodes?: Array<{
      data: {
        details: Array<{ label: string; value: ReactNode }>;
        eyebrow: string;
        testId: string;
        title: ReactNode;
      };
      id: string;
      position?: { x: number; y: number };
    }>;
    nodesConnectable?: boolean;
    nodesDraggable?: boolean;
    nodesFocusable?: boolean;
    onNodesChange?: (
      changes: Array<{
        id: string;
        position?: { x: number; y: number };
        type: string;
      }>,
    ) => void;
    onViewportChange?: (viewport: {
      x: number;
      y: number;
      zoom: number;
    }) => void;
    panOnDrag?: boolean;
    preventScrolling?: boolean;
    selectNodesOnDrag?: boolean;
    viewport?: { x: number; y: number; zoom: number };
    zoomOnDoubleClick?: boolean;
    zoomOnPinch?: boolean;
    zoomOnScroll?: boolean;
  }) => (
    <div
      aria-label={props["aria-label"]}
      data-auto-pan-on-node-drag={String(autoPanOnNodeDrag)}
      data-connect-on-click={String(connectOnClick)}
      data-edges-focusable={String(edgesFocusable)}
      data-elements-selectable={String(elementsSelectable)}
      data-fit-view-max-zoom={String(fitViewOptions?.maxZoom)}
      data-has-on-nodes-change={String(typeof onNodesChange === "function")}
      data-has-on-viewport-change={String(
        typeof onViewportChange === "function",
      )}
      data-max-zoom={String(maxZoom)}
      data-min-zoom={String(minZoom)}
      data-nodes-connectable={String(nodesConnectable)}
      data-nodes-draggable={String(nodesDraggable)}
      data-nodes-focusable={String(nodesFocusable)}
      data-pan-on-drag={String(panOnDrag)}
      data-prevent-scrolling={String(preventScrolling)}
      data-select-nodes-on-drag={String(selectNodesOnDrag)}
      data-testid="mock-react-flow"
      data-viewport-zoom={String(viewport?.zoom)}
      data-zoom-on-double-click={String(zoomOnDoubleClick)}
      data-zoom-on-pinch={String(zoomOnPinch)}
      data-zoom-on-scroll={String(zoomOnScroll)}
    >
      <button
        aria-label="mock drag first lineage node"
        data-testid="mock-react-flow-drag-first-node"
        onClick={() => {
          const firstNode = nodes[0];
          if (firstNode) {
            onNodesChange?.([
              {
                id: firstNode.id,
                position: { x: 123, y: 45 },
                type: "position",
              },
            ]);
          }
        }}
        type="button"
      />
      <button
        aria-label="mock zoom lineage viewport"
        data-testid="mock-react-flow-zoom-viewport"
        onClick={() => onViewportChange?.({ x: 0, y: 0, zoom: 1.25 })}
        type="button"
      />
      {nodes.map((node) => (
        <div
          data-node-x={String(node.position?.x)}
          data-node-y={String(node.position?.y)}
          data-testid={node.data.testId}
          key={node.id}
        >
          <p>{node.data.eyebrow}</p>
          <p>{node.data.title}</p>
          <dl>
            {node.data.details.map((item) => (
              <div key={item.label}>
                <dt>{item.label}</dt>
                <dd>{item.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
      {edges.map((edge) => (
        <p data-testid={`mock-react-flow-edge-${edge.id}`} key={edge.id}>
          {edge.label}
        </p>
      ))}
      {children}
    </div>
  ),
}));

const NOW = "2026-04-20T10:00:00Z";

function buildInvocation(
  overrides: Partial<RunAgentInvocationRead> = {},
): RunAgentInvocationRead {
  return {
    agentRef: { scope: "global", id: 11, key: "research_agent", version: 3 },
    agentKey: "research_agent",
    agentVersion: 3,
    createdAt: NOW,
    durationMs: 8,
    errorCode: null,
    errorDetails: [],
    errorMessage: null,
    finishedAt: "2026-04-20T10:00:03Z",
    id: 1001,
    inputMode: "wired",
    graphMetadata: null,
    optional: false,
    output: { summary: "analysis" },
    outputOrigin: "executed",
    outputSchemaRef: { scope: "global", id: 21, version: 4 },
    outputSchemaVersion: 4,
    persistedAt: "2026-04-20T10:00:03Z",
    position: 1,
    resolvedInput: { ticker: "AAPL" },
    resolvedInputOrigin: "derived",
    runId: 42,
    runStepId: 101,
    slot: "analysis",
    sourceInvocationId: null,
    startedAt: NOW,
    status: "succeeded",
    stepIndex: 1,
    tokens: 21,
    traceSpanId: "span-1",
    updatedAt: "2026-04-20T10:00:03Z",
    wiring: { from: "inputs.ticker" },
    ...overrides,
  };
}

function buildStep(overrides: Partial<RunStepRead> = {}): RunStepRead {
  return {
    createdAt: NOW,
    error: null,
    finishedAt: "2026-04-20T10:00:03Z",
    id: 101,
    index: 1,
    graphMetadata: null,
    invocations: [buildInvocation()],
    operationInvocations: [],
    origin: "planned",
    persistedAt: "2026-04-20T10:00:03Z",
    runId: 42,
    sourceRunId: null,
    sourceRunStepId: null,
    sourceStepIndex: null,
    startedAt: NOW,
    status: "succeeded",
    updatedAt: "2026-04-20T10:00:03Z",
    ...overrides,
  };
}

function buildMemoryEvent(
  overrides: Partial<RunMemoryEventRead> = {},
): RunMemoryEventRead {
  return {
    budget: {},
    createdAt: NOW,
    eventType: "retrieved",
    excerpt: null,
    filters: {},
    id: 9001,
    injectedText: null,
    invocationId: null,
    memoryId: null,
    resultSnapshot: {},
    retrievalMode: null,
    revisionId: null,
    runAgentInvocationId: null,
    runId: 42,
    runOperationInvocationId: null,
    runStepId: null,
    statusSnapshot: {},
    stepId: null,
    traceSpanId: null,
    ...overrides,
  };
}

function buildPackageProvenance(
  overrides: Partial<NonNullable<RunRead["packageProvenance"]>> = {},
): NonNullable<RunRead["packageProvenance"]> {
  return {
    compiledPlan: { workflow: { key: "market_review" } },
    currentPackage: {
      available: true,
      compiledHash: "compiled-hash-abc",
      compiledHashMatchesSnapshot: true,
      manifestHash: "manifest-hash-abc",
      manifestHashMatchesSnapshot: true,
    },
    extensionDependencies: [],
    launchSnapshot: {
      inputSchema: { type: "object" },
      parameters: { ticker: "AAPL" },
      workflowDescription: "Review market context.",
      workflowKey: "market_review",
      workflowName: "Market review",
    },
    localResourceRefs: {
      agents: ["research_agent"],
      capabilityProfiles: [],
      mcpServers: [],
      outputSchemas: [],
      workflows: ["market_review"],
    },
    manifestSource: "apiVersion: signaldeck.workflowPackage/v1",
    packageDefinition: { package: { key: "market_review_package" } },
    preflightSummary: { ready: true, blockingErrors: [], warnings: [] },
    resolvedModelConnections: [],
    workflowDescription: "Review market context.",
    workflowKey: "market_review",
    workflowName: "Market review",
    workflowPackageCompiledHash: "compiled-hash-abc",
    workflowPackageDescription: "Snapshot package for market reviews.",
    workflowPackageId: 7,
    workflowPackageKey: "market_review_package",
    workflowPackageManifestHash: "manifest-hash-abc",
    workflowPackageName: "Market Review Package",
    workflowPackageStatus: "active",
    ...overrides,
  };
}

function buildCapabilityState(
  status: ModelConnectionCapabilityState["status"],
  detail: string,
  lastProbedAt: string,
): ModelConnectionCapabilityState {
  return { detail, lastProbedAt, status };
}

function buildCapabilities(
  overrides: Partial<
    Record<keyof ModelConnectionCapabilities, ModelConnectionCapabilityState>
  > = {},
): ModelConnectionCapabilities {
  return {
    chatCompletions: buildCapabilityState(
      "supported",
      "Chat completions support was recorded for the frozen run profile.",
      "2026-05-08T07:10:00Z",
    ),
    jsonObjectOutput: buildCapabilityState(
      "supported",
      "JSON object validation is available.",
      "2026-05-08T07:11:00Z",
    ),
    nativeToolCalls: buildCapabilityState(
      "unsupported",
      "Native tool calls are not available on this run snapshot.",
      "2026-05-08T07:13:00Z",
    ),
    parallelToolCalls: buildCapabilityState(
      "unsupported",
      "Parallel tool calls were serialized to preserve compatibility.",
      "2026-05-08T07:14:00Z",
    ),
    reasoningHints: buildCapabilityState(
      "supported",
      "Reasoning hints were accepted.",
      "2026-05-08T07:15:00Z",
    ),
    responsesApi: buildCapabilityState(
      "supported",
      "Responses API support was recorded for the frozen run profile.",
      "2026-05-08T07:16:00Z",
    ),
    streaming: buildCapabilityState(
      "supported",
      "Streaming was available during the probe.",
      "2026-05-08T07:17:00Z",
    ),
    strictJsonSchemaOutput: buildCapabilityState(
      "supported",
      "Strict JSON schema output was accepted.",
      "2026-05-08T07:18:00Z",
    ),
    systemMessages: buildCapabilityState(
      "supported",
      "System messages were accepted.",
      "2026-05-08T07:19:00Z",
    ),
    textGeneration: buildCapabilityState(
      "supported",
      "Text generation is supported.",
      "2026-05-08T07:20:00Z",
    ),
    usageReporting: buildCapabilityState(
      "supported",
      "Usage metadata was reported.",
      "2026-05-08T07:21:00Z",
    ),
    ...overrides,
  };
}

function buildResolvedModelConnection(
  overrides: Partial<RunPackageResolvedModelConnectionRead>,
): RunPackageResolvedModelConnectionRead {
  return {
    apiStyle: "responses",
    baseUrl: "https://api.openai.com/v1",
    capabilities: buildCapabilities(),
    connectionKind: "provider",
    hasApiKey: true,
    key: "primary_openai",
    modelId: "gpt-5.5",
    name: "Primary OpenAI",
    outputStrategyPolicy: "prefer_strict_schema",
    parallelToolCallsPolicy: "serialize",
    probeCacheTtlSeconds: 900,
    protocolProfile: "openai_responses",
    reasoningEffort: "medium",
    reasoningPolicy: "allow",
    streamingPolicy: "allow",
    timeoutSeconds: 60,
    ...overrides,
  };
}

function buildRun(overrides: Partial<RunRead> = {}): RunRead {
  return {
    createdAt: NOW,
    error: null,
    executedTokens: 51,
    finalOutput: { summary: "All clear" },
    finishedAt: "2026-04-20T10:00:04Z",
    replayStepIndex: null,
    id: 42,
    inheritedTokens: 0,
    input: { ticker: "AAPL" },
    lineageRootRunId: null,
    memoryArtifacts: [],
    memoryEvents: [],
    extensionDependencies: [],
    packageProvenance: null,
    progress: {
      unit: "invocation",
      terminalCount: 1,
      totalCount: 1,
      percent: 100,
    },
    queue: null,
    queuedAt: NOW,
    resumeStepIndex: 1,
    sourceRunId: null,
    startedAt: NOW,
    status: "succeeded",
    steps: [buildStep()],
    targetId: 7,
    targetKey: "market_review_package",
    targetKind: "workflowPackage",
    totalTokens: 51,
    traceId: "trace-42",
    updatedAt: "2026-04-20T10:00:04Z",
    ...overrides,
  };
}

function buildReplayableWorkflowRun(overrides: Partial<RunRead> = {}): RunRead {
  return buildRun({
    targetKind: "workflowPackage",
    targetKey: "market_review_package",
    steps: [
      buildStep(),
      buildStep({
        id: 102,
        index: 2,
        invocations: [
          buildInvocation({
            id: 1002,
            position: 1,
            runStepId: 102,
            slot: "decision",
            stepIndex: 2,
            traceSpanId: "span-2",
          }),
        ],
      }),
    ],
    ...overrides,
  });
}

function buildRerunDraft(
  overrides: Partial<RunRerunDraftRead> = {},
): RunRerunDraftRead {
  return {
    parameters: { ticker: "AAPL" },
    ready: true,
    blockingErrors: [],
    warnings: [],
    sourceRunId: 42,
    targetId: 7,
    targetKey: "market_review_package",
    targetKind: "workflowPackage",
    packageProvenance: null,
    ...overrides,
  };
}

function buildForkDraft(
  overrides: Partial<RunForkDraftRead> = {},
): RunForkDraftRead {
  return {
    invocationInput: { ticker: "AAPL" },
    ready: true,
    blockingErrors: [],
    warnings: [],
    sourceInvocationId: 1001,
    sourceRunId: 42,
    targetId: 7,
    targetKey: "market_review",
    targetKind: "workflowPackage",
    packageProvenance: null,
    ...overrides,
  };
}

function queryResult(data: RunRead) {
  return {
    data,
    isError: false,
    isPending: false,
  };
}

function draftQueryResult<T>(data: T | undefined = undefined) {
  return {
    data,
    error: null,
    isError: false,
    isPending: false,
  };
}

function forkDraftQueryResult(data: RunForkDraftRead | undefined = undefined) {
  return draftQueryResult(data);
}

function expectDraggableZoomableLineageContract(flow: HTMLElement) {
  expect(flow).toHaveAttribute("data-nodes-draggable", "true");
  expect(flow).toHaveAttribute("data-has-on-nodes-change", "true");
  expect(flow).toHaveAttribute("data-has-on-viewport-change", "true");
  expect(flow).toHaveAttribute("data-zoom-on-double-click", "true");
  expect(flow).toHaveAttribute("data-zoom-on-pinch", "true");
  expect(flow).toHaveAttribute("data-zoom-on-scroll", "true");
  expect(flow).toHaveAttribute("data-prevent-scrolling", "true");
  expect(flow).toHaveAttribute("data-fit-view-max-zoom", "1");
  expect(flow).toHaveAttribute("data-max-zoom", "1.8");
  expect(flow).toHaveAttribute("data-auto-pan-on-node-drag", "false");
  expect(flow).toHaveAttribute("data-connect-on-click", "false");
  expect(flow).toHaveAttribute("data-edges-focusable", "false");
  expect(flow).toHaveAttribute("data-elements-selectable", "false");
  expect(flow).toHaveAttribute("data-nodes-connectable", "false");
  expect(flow).toHaveAttribute("data-nodes-focusable", "false");
  expect(flow).toHaveAttribute("data-pan-on-drag", "false");
  expect(flow).toHaveAttribute("data-select-nodes-on-drag", "false");
}

function applyLatestSearchParamsUpdate(currentSearch: string) {
  const lastCall =
    setSearchParamsMock.mock.calls[setSearchParamsMock.mock.calls.length - 1];
  const updater = lastCall?.[0];

  if (typeof updater !== "function") {
    throw new Error(
      "Expected the latest search params update to use an updater function.",
    );
  }

  searchParamsMock = updater(new URLSearchParams(currentSearch));
}

describe("RunsDetailPage", () => {
  beforeEach(() => {
    createRunRerunMutateAsyncMock.mockReset();
    createRunForkMutateAsyncMock.mockReset();
    navigateMock.mockReset();
    searchParamsMock = new URLSearchParams();
    setSearchParamsMock.mockReset();
    useCreateRunForkMock.mockReset();
    useCreateRunForkMock.mockReturnValue({
      isPending: false,
      mutateAsync: createRunForkMutateAsyncMock,
    });
    useCreateRunRerunMock.mockReset();
    useCreateRunRerunMock.mockReturnValue({
      isPending: false,
      mutateAsync: createRunRerunMutateAsyncMock,
    });
    useRunForkDraftMock.mockReset();
    useRunForkDraftMock.mockReturnValue(forkDraftQueryResult());
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 1024,
    });
    useRunRerunDraftMock.mockReset();
    useRunRerunDraftMock.mockReturnValue(draftQueryResult<RunRerunDraftRead>());
    useRunMock.mockReset();
  });

  it("renders all run inspection sections in one stacked workspace without the page tab console", () => {
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          memoryArtifacts: [
            {
              createdAt: NOW,
              memoryId: "memory_safe",
              provenance: {
                agentKey: "portfolio_manager",
                agentVersion: 3,
                createdByType: "agent",
                runId: 42,
                slot: "decision",
                workflowKey: "market_review",
              },
              sourceGraphMetadata: null,
              status: "active",
              summary: "Compact safe memory",
            },
          ],
          memoryEvents: [
            buildMemoryEvent({ id: 9101, eventType: "retrieved" }),
            buildMemoryEvent({ id: 9102, eventType: "written" }),
            buildMemoryEvent({ id: 9103, eventType: "reviewed" }),
            buildMemoryEvent({ id: 9104, eventType: "failed" }),
          ],
          packageProvenance: buildPackageProvenance({
            resolvedModelConnections: [buildResolvedModelConnection({})],
          }),
        }),
      ),
    );

    render(<RunsDetailPage />);

    expect(screen.queryByTestId("runs-tab-console")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("tablist", { name: /run inspection tabs/i }),
    ).not.toBeInTheDocument();

    const stack = screen.getByTestId("runs-stacked-workspace");
    const expectedSections = [
      ["runs-detail-section-operational-overview", "Operational overview"],
      ["runs-detail-section-final-output", "Final output"],
      ["runs-detail-section-evidence-availability", "Evidence availability"],
      ["runs-detail-section-diagnostics", "Diagnostics"],
      ["runs-detail-section-execution-steps", "Execution steps"],
      ["runs-detail-section-run-input", "Run input"],
      ["runs-detail-section-input-provenance", "Input provenance"],
      ["runs-detail-section-output-provenance", "Output provenance"],
      ["runs-detail-section-memory", "Memory"],
      ["runs-memory-evidence", "Run memory evidence"],
      ["runs-memory-group-retrievedContext", "Retrieved context"],
      ["runs-memory-group-memoryWrites", "Memory written and reused"],
      ["runs-memory-group-reviewFollowUp", "Review and follow-up"],
      ["runs-memory-group-auditTrail", "Audit trail"],
      ["runs-detail-section-runtime-profile", "Runtime profile"],
      ["runs-detail-section-selected-strategies", "Selected strategies"],
      ["runs-detail-section-capability-matrix", "Capability matrix"],
      ["runs-detail-section-token-accounting", "Token accounting"],
      ["runs-detail-section-invocation-usage-rows", "Invocation usage rows"],
      ["runs-detail-section-lineage", "Lineage"],
      ["runs-memory-compact-artifacts", "Compact artifact slice"],
      ["runs-detail-section-metadata", "Metadata"],
    ];
    const sections = expectedSections.map(([sectionId, title]) => {
      const section = within(stack).getByTestId(sectionId);
      expect(section).toHaveTextContent(title);
      return section;
    });

    expect(sections).toHaveLength(expectedSections.length);
    sections.slice(1).forEach((section, index) => {
      expect(
        sections[index].compareDocumentPosition(section) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    });
    expect(within(stack).getByTestId("runs-overview-workspace")).toBeVisible();
    expect(within(stack).getByTestId("runs-execution-outline")).toBeVisible();
    expect(within(stack).getByTestId("runs-diagnostics-workspace"))
      .toBeVisible();
    expect(within(stack).getByTestId("runs-input-workspace")).toBeVisible();
    expect(within(stack).getByTestId("runs-output-workspace")).toBeVisible();
    expect(within(stack).getByTestId("runs-runtime-workspace")).toBeVisible();
    expect(within(stack).getByTestId("runs-memory-workspace")).toBeVisible();
    expect(within(stack).getByTestId("runs-lineage-workspace")).toBeVisible();
    expect(within(stack).getByTestId("runs-audit-table")).toBeVisible();
  });

  it("renders every stacked run detail block with shared iconized section chrome", () => {
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          memoryEvents: [buildMemoryEvent()],
          packageProvenance: buildPackageProvenance({
            resolvedModelConnections: [buildResolvedModelConnection({})],
          }),
        }),
      ),
    );

    render(<RunsDetailPage />);

    const stack = screen.getByTestId("runs-stacked-workspace");
    const expectedBlocks = [
      ["operational-overview", "Operational overview"],
      ["final-output", "Final output"],
      ["evidence-availability", "Evidence availability"],
      ["diagnostics", "Diagnostics"],
      ["execution-steps", "Execution steps"],
      ["run-input", "Run input"],
      ["input-provenance", "Input provenance"],
      ["output-provenance", "Output provenance"],
      ["memory", "Memory"],
      ["runtime-profile", "Runtime profile"],
      ["selected-strategies", "Selected strategies"],
      ["capability-matrix", "Capability matrix"],
      ["token-accounting", "Token accounting"],
      ["invocation-usage-rows", "Invocation usage rows"],
      ["lineage", "Lineage"],
      ["metadata", "Metadata"],
    ];

    expectedBlocks.forEach(([blockId, title]) => {
      const block = within(stack).getByTestId(`runs-detail-section-${blockId}`);
      expect(block).toHaveAttribute("data-run-detail-section-block", "true");
      expect(
        within(block).getByTestId(`runs-detail-section-icon-${blockId}`),
      ).toHaveAttribute("aria-hidden", "true");
      expect(
        within(block).getByTestId(`runs-detail-section-title-${blockId}`),
      ).toHaveTextContent(title);
      expect(
        within(block).getByTestId(`runs-detail-section-description-${blockId}`),
      ).toHaveClass("text-xs", "leading-5", "text-muted-foreground");
    });
  });

  it.each([
    ["succeeded", "outputs"],
    ["running", "execution"],
    ["queued", "summary"],
    ["failed", "execution"],
    ["canceled", "summary"],
  ])("defaults %s runs to %s mode", (status, expectedMode) => {
    useRunMock.mockReturnValue(
      queryResult(buildRun({ status: status as RunRead["status"] })),
    );

    const rendered = render(<RunsDetailPage />);

    expect(screen.queryByTestId("runs-tab-console")).not.toBeInTheDocument();
    expect(screen.getByTestId("runs-inspection-workspace")).toHaveAttribute(
      "data-run-mode",
      expectedMode,
    );
    expect(screen.getByTestId("runs-stacked-workspace")).toBeVisible();

    rendered.unmount();
  });

  it("defaults failed runs to execution and the first failing context", () => {
    const failedInvocation = buildInvocation({
      errorCode: "model_error",
      errorDetails: [{ type: "rate_limit" }],
      errorMessage: "Provider failed",
      id: 1002,
      position: 2,
      slot: "decision",
      status: "failed",
    });
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          error: "Run failed after decision.",
          finalOutput: null,
          status: "failed",
          steps: [
            buildStep({
              invocations: [buildInvocation(), failedInvocation],
              status: "failed",
            }),
          ],
        }),
      ),
    );

    const failedRender = render(<RunsDetailPage />);

    expect(screen.queryByTestId("runs-tab-console")).not.toBeInTheDocument();
    expect(screen.getByTestId("runs-inspection-workspace")).toHaveAttribute(
      "data-run-mode",
      "execution",
    );
    expect(screen.getByTestId("runs-invocation-1002-outline-entry"))
      .toHaveAttribute("data-state", "selected");
    expect(screen.getByTestId("runs-active-evidence-viewer")).toHaveTextContent(
      /provider failed/i,
    );
    expect(screen.getByTestId("runs-detail-state-summary")).toHaveTextContent(
      /decision agent invocation #1002/i,
    );

    failedRender.unmount();
    searchParamsMock = new URLSearchParams("mode=summary");
    setSearchParamsMock.mockReset();
    render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-inspection-workspace")).toHaveAttribute(
      "data-run-mode",
      "summary",
    );
    expect(screen.getByTestId("runs-overview-workspace")).toBeVisible();
    expect(screen.getByTestId("runs-execution-outline")).toBeVisible();
    expect(screen.queryByTestId("split-inspector-right-pane"))
      .not.toBeInTheDocument();
  });

  it("renders dedicated secondary modes with compact empty states", () => {
    const tokenlessRun = buildRun({
      executedTokens: 0,
      inheritedTokens: 0,
      totalTokens: 0,
      steps: [
        buildStep({
          invocations: [buildInvocation({ graphMetadata: null, tokens: 0 })],
        }),
      ],
    });

    useRunMock.mockReturnValue(queryResult(buildRun()));
    searchParamsMock = new URLSearchParams("mode=lineage");
    const lineageRender = render(<RunsDetailPage />);
    const lineageWorkspace = screen.getByTestId("runs-lineage-workspace");
    expect(lineageWorkspace).toBeVisible();
    expect(within(lineageWorkspace).getByTestId("runs-lineage-empty"))
      .toHaveTextContent(/no fork, snapshot replay, copied-step, or historical lineage/i);
    expect(screen.queryByTestId("runs-lineage-inspector-empty"))
      .not.toBeInTheDocument();
    lineageRender.unmount();

    searchParamsMock = new URLSearchParams("mode=memory");
    const memoryRender = render(<RunsDetailPage />);
    const memoryWorkspace = screen.getByTestId("runs-memory-workspace");
    expect(memoryWorkspace).toBeVisible();
    expect(within(memoryWorkspace).getByTestId("runs-memory-empty"))
      .toHaveTextContent(/no retrieval, write, review, audit, or compact memory artifact/i);
    expect(screen.queryByTestId("runs-memory-inspector-empty"))
      .not.toBeInTheDocument();
    memoryRender.unmount();

    useRunMock.mockReturnValue(queryResult(tokenlessRun));
    searchParamsMock = new URLSearchParams("mode=runtime");
    const tokensRender = render(<RunsDetailPage />);
    const tokensWorkspace = screen.getByTestId("runs-tokens-workspace");
    expect(tokensWorkspace).toBeVisible();
    expect(within(tokensWorkspace).getByTestId("runs-tokens-empty"))
      .toHaveTextContent(/no token accounting was reported/i);
    tokensRender.unmount();

    useRunMock.mockReturnValue(queryResult(buildRun()));
    searchParamsMock = new URLSearchParams("mode=diagnostics");
    render(<RunsDetailPage />);
    const diagnosticsWorkspace = screen.getByTestId("runs-diagnostics-workspace");
    expect(diagnosticsWorkspace).toBeVisible();
    expect(within(diagnosticsWorkspace).getByTestId("runs-diagnostics-empty"))
      .toHaveTextContent(/no run diagnostics, queue warnings, runtime capability warnings/i);
  });

  it("renders secondary lineage, memory, and token accounting evidence", () => {
    const copiedInvocation = buildInvocation({
      outputOrigin: "copied",
      resolvedInputOrigin: "copied",
      sourceInvocationId: 501,
      tokens: 21,
    });
    const executedInvocation = buildInvocation({
      graphMetadata: {
        modelGateway: {
          selectedStrategies: null,
          usage: { inputTokens: 18, outputTokens: 12, totalTokens: 30 },
        },
      },
      id: 1002,
      position: 2,
      slot: "decision",
      tokens: 30,
    });
    const run = buildRun({
      executedTokens: 30,
      inheritedTokens: 21,
      lineageRootRunId: 40,
      memoryArtifacts: [
        {
          memoryId: "memory_safe",
          summary: "Compact safe memory",
          status: "active",
          createdAt: NOW,
          provenance: {
            agentKey: "portfolio_manager",
            agentVersion: 3,
            createdByType: "agent",
            runId: 42,
            slot: "decision",
            workflowKey: "market_review",
          },
          sourceGraphMetadata: null,
        },
      ],
      memoryEvents: [
        buildMemoryEvent({ id: 9101, eventType: "retrieved" }),
        buildMemoryEvent({ id: 9102, eventType: "written", memoryId: "memory_safe" }),
      ],
      packageProvenance: buildPackageProvenance(),
      replayStepIndex: 1,
      resumeStepIndex: 2,
      sourceRunId: 41,
      steps: [
        buildStep({
          invocations: [copiedInvocation],
          origin: "copied",
          sourceRunId: 41,
          sourceRunStepId: 401,
          sourceStepIndex: 1,
        }),
        buildStep({
          id: 102,
          index: 2,
          invocations: [executedInvocation],
        }),
      ],
      totalTokens: 51,
    });

    useRunMock.mockReturnValue(queryResult(run));
    searchParamsMock = new URLSearchParams("mode=lineage");
    const lineageRender = render(<RunsDetailPage />);
    const lineageWorkspace = screen.getByTestId("runs-lineage-workspace");
    expect(lineageWorkspace).toHaveTextContent(/lineage boundaries/i);
    expect(lineageWorkspace).toHaveTextContent(/Run #41/i);
    expect(lineageWorkspace).toHaveTextContent(/1 copied · 1 planned/i);
    expect(within(lineageWorkspace).getByTestId("runs-lineage-summary"))
      .toBeVisible();
    lineageRender.unmount();

    searchParamsMock = new URLSearchParams("mode=memory");
    const memoryRender = render(<RunsDetailPage />);
    const memoryWorkspace = screen.getByTestId("runs-memory-workspace");
    expect(memoryWorkspace).toHaveTextContent(/retrieved context/i);
    expect(memoryWorkspace).toHaveTextContent(/memory written and reused/i);
    expect(screen.getByTestId("runs-memory-compact-artifacts"))
      .toHaveTextContent(/compact artifact slice/i);
    expect(screen.getByTestId("runs-memory-compact-artifact-memory_safe"))
      .toHaveTextContent(/Compact safe memory/i);
    memoryRender.unmount();

    searchParamsMock = new URLSearchParams("mode=runtime");
    render(<RunsDetailPage />);
    const tokensWorkspace = screen.getByTestId("runs-tokens-workspace");
    expect(tokensWorkspace).toHaveTextContent(/token accounting/i);
    expect(tokensWorkspace).toHaveTextContent(/51/);
    expect(tokensWorkspace).toHaveTextContent(/30/);
    expect(tokensWorkspace).toHaveTextContent(/21/);
    expect(screen.getByTestId("runs-token-row-2-1002")).toHaveTextContent(
      /Input tokens: 18/i,
    );
  });

  it("keeps warning-only diagnostics distinct from destructive failures", () => {
    const warningOnlyRun = buildRun({
      packageProvenance: buildPackageProvenance({
        currentPackage: {
          available: true,
          compiledHash: "compiled-hash-new",
          compiledHashMatchesSnapshot: false,
          manifestHash: "manifest-hash-abc",
          manifestHashMatchesSnapshot: true,
        },
        preflightSummary: {
          ready: true,
          blockingErrors: [],
          warnings: [
            {
              field: "extensions.signaldeck.finance",
              issue: "Finance extension was enabled at launch.",
            },
          ],
        },
        resolvedModelConnections: [
          buildResolvedModelConnection({
            capabilities: buildCapabilities({
              nativeToolCalls: buildCapabilityState(
                "unsupported",
                "Native tool calls are unavailable.",
                "2026-05-08T07:22:00Z",
              ),
            }),
          }),
        ],
      }),
    });
    useRunMock.mockReturnValue(queryResult(warningOnlyRun));
    searchParamsMock = new URLSearchParams("mode=diagnostics");
    const warningRender = render(<RunsDetailPage />);
    const warningDiagnostics = screen.getByTestId("runs-diagnostics-workspace");
    expect(warningDiagnostics).toHaveTextContent(/warnings/i);
    expect(screen.getByTestId("runs-diagnostic-preflight-warning-0"))
      .toHaveAttribute("data-severity", "warning");
    expect(screen.getByTestId("runs-diagnostic-compiled-hash-mismatch"))
      .toHaveAttribute("data-severity", "warning");
    expect(screen.getByTestId("runs-diagnostic-unsupported-primary_openai-nativeToolCalls"))
      .toHaveAttribute("data-severity", "warning");
    expect(warningDiagnostics.querySelector('[data-severity="error"]'))
      .not.toBeInTheDocument();
    expect(warningDiagnostics.querySelector('[data-slot="badge"].bg-destructive'))
      .not.toBeInTheDocument();
    warningRender.unmount();

    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          error: "Provider failed after retries.",
          status: "failed",
          steps: [
            buildStep({
              invocations: [
                buildInvocation({
                  errorCode: "model_error",
                  errorMessage: "Provider failed",
                  status: "failed",
                }),
              ],
              status: "failed",
            }),
          ],
        }),
      ),
    );
    searchParamsMock = new URLSearchParams("mode=diagnostics");
    render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-diagnostic-run-error"))
      .toHaveAttribute("data-severity", "error");
    expect(screen.getByTestId("runs-diagnostic-agent-1001-error"))
      .toHaveAttribute("data-severity", "error");
    expect(screen.getByTestId("runs-diagnostics-workspace").querySelector('[data-severity="error"]'))
      .toBeInTheDocument();
  });

  it("resolves legacy mode aliases to canonical inspection state", () => {
    useRunMock.mockReturnValue(queryResult(buildRun()));

    searchParamsMock = new URLSearchParams("mode=steps");
    const executionRender = render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-inspection-workspace")).toHaveAttribute(
      "data-run-mode",
      "execution",
    );
    executionRender.unmount();

    searchParamsMock = new URLSearchParams("mode=tokens");
    const runtimeRender = render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-inspection-workspace")).toHaveAttribute(
      "data-run-mode",
      "runtime",
    );
    runtimeRender.unmount();

    searchParamsMock = new URLSearchParams("mode=audit");
    render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-inspection-workspace")).toHaveAttribute(
      "data-run-mode",
      "metadata",
    );
  });

  it("renders selected execution and metadata evidence inline without an inspector pane", () => {
    const run = buildRun({
      memoryArtifacts: [
        {
          memoryId: "memory_701",
          summary: "AAPL decision memory",
          status: "pending",
          createdAt: NOW,
          provenance: {
            agentKey: "portfolio_manager",
            agentVersion: 3,
            createdByType: "agent",
            runId: 42,
            slot: "decision",
            workflowKey: "market_review",
          },
          sourceGraphMetadata: null,
        },
      ],
    });
    useRunMock.mockReturnValue(queryResult(run));

    searchParamsMock = new URLSearchParams("mode=execution");
    const executionRender = render(<RunsDetailPage />);
    fireEvent.click(
      within(screen.getByTestId("runs-step-1")).getByRole("button", {
        name: /step 1/i,
      }),
    );
    applyLatestSearchParamsUpdate("mode=execution");
    expect(searchParamsMock.get("mode")).toBe("execution");
    executionRender.unmount();

    const selectedStepRender = render(<RunsDetailPage />);
    expect(screen.queryByTestId("split-inspector-right-pane"))
      .not.toBeInTheDocument();
    expect(screen.getByTestId("runs-step-1-inline-evidence")).toHaveTextContent(
      /step evidence/i,
    );
    selectedStepRender.unmount();

    searchParamsMock = new URLSearchParams("mode=execution");
    const invocationRender = render(<RunsDetailPage />);
    fireEvent.click(
      within(screen.getByTestId("runs-invocation-1001-outline-entry")).getByRole(
        "button",
        { name: /analysis agent/i },
      ),
    );
    applyLatestSearchParamsUpdate("mode=execution");
    invocationRender.unmount();

    const selectedInvocationRender = render(<RunsDetailPage />);
    expect(
      screen.getByTestId("runs-invocation-1001-inline-evidence"),
    ).toHaveTextContent(/output/i);
    selectedInvocationRender.unmount();

    searchParamsMock = new URLSearchParams("mode=metadata");
    const metadataRender = render(<RunsDetailPage />);
    fireEvent.click(
      within(screen.getByTestId("runs-audit-row-payload-input")).getByRole(
        "button",
        { name: /run input/i },
      ),
    );
    applyLatestSearchParamsUpdate("mode=metadata");
    expect(searchParamsMock.get("mode")).toBe("metadata");
    metadataRender.unmount();

    const selectedMetadataRender = render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-metadata-collapsible")).toHaveAttribute(
      "data-slot",
      "collapsible",
    );
    expect(
      screen.getByTestId("runs-audit-row-payload-input-inline-evidence"),
    ).toHaveTextContent(/AAPL/i);
    selectedMetadataRender.unmount();

    searchParamsMock = new URLSearchParams("mode=metadata");
    const traceRender = render(<RunsDetailPage />);
    fireEvent.click(
      within(screen.getByTestId("runs-audit-row-trace-agent-1001")).getByRole(
        "button",
        { name: /agent invocation #1001/i },
      ),
    );
    applyLatestSearchParamsUpdate("mode=metadata");
    traceRender.unmount();

    const selectedTraceRender = render(<RunsDetailPage />);
    const traceInlineEvidence = screen.getByTestId(
      "runs-audit-row-trace-agent-1001-inline-evidence",
    );
    expect(traceInlineEvidence).toHaveTextContent(/analysis/i);
    fireEvent.click(
      within(traceInlineEvidence).getByRole("button", { name: /run input/i }),
    );
    applyLatestSearchParamsUpdate(
      "mode=metadata&inspect=invocation%3A1001&pane=output",
    );
    expect(searchParamsMock.get("mode")).toBe("metadata");
    selectedTraceRender.unmount();

    const tracePaneRender = render(<RunsDetailPage />);
    expect(
      screen.getByTestId("runs-audit-row-trace-agent-1001-inline-evidence"),
    ).toHaveTextContent(/AAPL/i);
    tracePaneRender.unmount();

    searchParamsMock = new URLSearchParams("mode=metadata");
    const artifactRender = render(<RunsDetailPage />);
    fireEvent.click(
      within(screen.getByTestId("runs-audit-row-artifact-memory_701")).getByRole(
        "button",
        { name: /AAPL decision memory/i },
      ),
    );
    applyLatestSearchParamsUpdate("mode=metadata");
    artifactRender.unmount();

    const selectedArtifactRender = render(<RunsDetailPage />);
    const artifactInlineEvidence = screen.getByTestId(
      "runs-audit-row-artifact-memory_701-inline-evidence",
    );
    expect(artifactInlineEvidence).toHaveTextContent(/portfolio_manager@3/i);
    fireEvent.click(
      within(artifactInlineEvidence).getByRole("button", { name: /provenance/i }),
    );
    applyLatestSearchParamsUpdate(
      "mode=metadata&inspect=memory%3Amemory_701&pane=details",
    );
    expect(searchParamsMock.get("mode")).toBe("metadata");
    selectedArtifactRender.unmount();

    render(<RunsDetailPage />);
    expect(
      screen.getByTestId("runs-audit-row-artifact-memory_701-inline-evidence"),
    ).toHaveTextContent(/Provenance/i);
  });

  it("updates inspection URL state without clearing modal state", () => {
    useRunMock.mockReturnValue(queryResult(buildRun()));

    render(<RunsDetailPage />);

    const stepOneButton = within(
      screen.getByTestId("runs-step-1"),
    ).getAllByRole("button", { name: /step 1/i })[0];
    fireEvent.click(stepOneButton);
    const updater = setSearchParamsMock.mock.calls.at(-1)?.[0] as (
      current: URLSearchParams,
    ) => URLSearchParams;
    const nextParams = updater(new URLSearchParams("rerun=1"));

    expect(nextParams.get("inspect")).toBe("step:1");
    expect(nextParams.has("pane")).toBe(false);
    expect(nextParams.get("rerun")).toBe("1");

    const forkParams = updater(
      new URLSearchParams("fork=1&resumeStepIndex=1&invocationId=1001"),
    );
    expect(forkParams.get("inspect")).toBe("step:1");
    expect(forkParams.get("fork")).toBe("1");
    expect(forkParams.get("resumeStepIndex")).toBe("1");
    expect(forkParams.get("invocationId")).toBe("1001");
  });

  it("renders normalized lineage, step origins, invocation origins, and trace summaries", () => {
    const copiedInvocation = buildInvocation({
      id: 1001,
      outputOrigin: "copied",
      resolvedInputOrigin: "copied",
      sourceInvocationId: 501,
      traceSpanId: "span-1",
    });
    const failedInvocation = buildInvocation({
      agentRef: {
        scope: "packageLocal",
        localId: 12,
        key: "consumer_agent",
        version: 2,
      },
      agentKey: "consumer_agent",
      agentVersion: 2,
      durationMs: 12,
      errorCode: "model_error",
      errorDetails: [{ type: "rate_limit" }],
      errorMessage: "Provider failed",
      graphMetadata: {
        modelGateway: {
          selectedStrategies: {
            outputStrategy: "json_object_validation",
            parallelToolCalls: false,
            reasoningEffort: "low",
            reasoningStrategy: "disabled_by_policy",
            streamingStrategy: "disabled",
            toolCallStrategy: "native_tool_calls",
          },
          usage: {
            inputTokens: 18,
            outputTokens: 12,
            totalTokens: 30,
          },
        },
      },
      id: 1002,
      output: null,
      outputOrigin: null,
      position: 2,
      resolvedInput: { analysis: { summary: "analysis" } },
      runStepId: 102,
      slot: "decision",
      status: "failed",
      stepIndex: 2,
      tokens: 30,
      traceSpanId: "span-2",
    });
    const run = buildRun({
      executedTokens: 30,
      finalOutput: { summary: "All clear", source: "normalized" },
      replayStepIndex: 1,
      inheritedTokens: 21,
      lineageRootRunId: 40,
      resumeStepIndex: 2,
      sourceRunId: 41,
      targetId: 7,
      targetKey: "market_review_package",
      targetKind: "workflowPackage",
      packageProvenance: {
        workflowPackageId: 7,
        workflowPackageKey: "market_review_package",
        workflowPackageName: "Market Review Package",
        workflowPackageDescription: "Snapshot package for market reviews.",
        workflowPackageStatus: "active",
        workflowPackageManifestHash: "manifest-hash-abc",
        workflowPackageCompiledHash: "compiled-hash-abc",
        workflowKey: "market_review",
        workflowName: "Market review",
        workflowDescription: "Review market context.",
        manifestSource: "apiVersion: signaldeck.workflowPackage/v1",
        packageDefinition: { package: { key: "market_review_package" } },
        compiledPlan: { workflow: { key: "market_review" } },
        launchSnapshot: {
          workflowKey: "market_review",
          workflowName: "Market review",
          workflowDescription: "Review market context.",
          inputSchema: { type: "object" },
          parameters: { ticker: "AAPL" },
        },
        extensionDependencies: [],
        localResourceRefs: {
          agents: ["research_agent"],
          outputSchemas: [],
          capabilityProfiles: [],
          mcpServers: [],
          workflows: ["market_review"],
        },
        preflightSummary: { ready: true, blockingErrors: [], warnings: [] },
        currentPackage: {
          available: true,
          manifestHash: "manifest-hash-abc",
          compiledHash: "compiled-hash-abc",
          manifestHashMatchesSnapshot: true,
          compiledHashMatchesSnapshot: true,
        },
        resolvedModelConnections: [
          buildResolvedModelConnection({
            capabilities: buildCapabilities({
              nativeToolCalls: buildCapabilityState(
                "unsupported",
                "Native tool calls are required by this run but were unavailable.",
                "2026-05-08T07:22:00Z",
              ),
              parallelToolCalls: buildCapabilityState(
                "unsupported",
                "Parallel tool calls were serialized for compatibility.",
                "2026-05-08T07:23:00Z",
              ),
              responsesApi: buildCapabilityState(
                "supported",
                "Responses API support was recorded for the frozen run profile.",
                "2026-05-08T07:24:00Z",
              ),
            }),
          }),
          buildResolvedModelConnection({
            apiStyle: "chat_completions",
            baseUrl: "https://signaldeck-deterministic-model.local/v1",
            capabilities: buildCapabilities({
              chatCompletions: buildCapabilityState(
                "supported",
                "Chat completions support is available on the smoke profile.",
                "2026-05-08T07:31:00Z",
              ),
              jsonObjectOutput: buildCapabilityState(
                "notApplicable",
                "JSON object output is not exercised on the smoke profile.",
                "2026-05-08T07:32:00Z",
              ),
              nativeToolCalls: buildCapabilityState(
                "unsupported",
                "Native tool calls are not available on the smoke profile.",
                "2026-05-08T07:34:00Z",
              ),
              parallelToolCalls: buildCapabilityState(
                "unsupported",
                "Parallel tool calls are not available on the smoke profile.",
                "2026-05-08T07:35:00Z",
              ),
              reasoningHints: buildCapabilityState(
                "notApplicable",
                "Reasoning hints are not exercised on the smoke profile.",
                "2026-05-08T07:36:00Z",
              ),
              responsesApi: buildCapabilityState(
                "notApplicable",
                "Responses API is not exercised on the smoke profile.",
                "2026-05-08T07:37:00Z",
              ),
              streaming: buildCapabilityState(
                "unsupported",
                "Streaming is disabled for the smoke profile.",
                "2026-05-08T07:38:00Z",
              ),
              strictJsonSchemaOutput: buildCapabilityState(
                "supported",
                "Strict JSON schema output is available on the smoke profile.",
                "2026-05-08T07:39:00Z",
              ),
              systemMessages: buildCapabilityState(
                "supported",
                "System messages are accepted on the smoke profile.",
                "2026-05-08T07:40:00Z",
              ),
              textGeneration: buildCapabilityState(
                "supported",
                "Text generation is available on the smoke profile.",
                "2026-05-08T07:41:00Z",
              ),
              usageReporting: buildCapabilityState(
                "supported",
                "Usage metadata was emitted by the smoke profile probe.",
                "2026-05-08T07:42:00Z",
              ),
            }),
            connectionKind: "deterministic_smoke",
            hasApiKey: false,
            key: "smoke_model",
            modelId: "signaldeck-smoke",
            name: "Smoke Model",
            outputStrategyPolicy: "allow_plain_text",
            parallelToolCallsPolicy: "forbid",
            probeCacheTtlSeconds: 300,
            protocolProfile: "openai_chat_completions",
            reasoningEffort: null,
            reasoningPolicy: "forbid",
            streamingPolicy: "forbid",
            timeoutSeconds: 5,
          }),
        ],
      },
      steps: [
        buildStep({
          invocations: [copiedInvocation],
          origin: "copied",
          sourceRunId: 41,
          sourceRunStepId: 401,
          sourceStepIndex: 1,
        }),
        buildStep({
          id: 102,
          index: 2,
          invocations: [failedInvocation],
          origin: "planned",
          status: "failed",
        }),
      ],
    });
    useRunMock.mockReturnValue(queryResult(run));

    const defaultRender = render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-detail-page")).toBeInTheDocument();
    expect(screen.getByTestId("runs-detail-page")).toHaveClass(
      "min-w-0",
      "overflow-hidden",
    );
    expect(screen.queryByRole("main")).not.toBeInTheDocument();
    expect(screen.getByTestId("workspace-page-shell-context")).toContainElement(
      screen.getByTestId("runs-detail-header"),
    );
    expect(screen.queryByTestId("workspace-page-shell-left-rail"))
      .not.toBeInTheDocument();
    expect(screen.queryByTestId("runs-tab-console")).not.toBeInTheDocument();
    expect(screen.getByTestId("runs-mode-workspace")).toHaveAttribute(
      "data-run-mode",
      "outputs",
    );
    expect(screen.queryByTestId("runs-inspection-split-layout"))
      .not.toBeInTheDocument();
    expect(screen.queryByTestId("split-inspector-right-pane"))
      .not.toBeInTheDocument();
    expect(
      screen.getAllByRole("heading", { name: /final output/i })[0],
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: /output provenance/i }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: /operational overview/i }),
    ).toBeVisible();
    expect(screen.getByTestId("runs-detail-context-frame")).toHaveClass(
      "min-h-0",
      "overflow-y-auto",
      "overscroll-contain",
      "flex-col",
    );
    expect(screen.getByTestId("runs-detail-context-frame")).toBeVisible();
    expect(screen.getByTestId("runs-inspection-workspace")).toBeInTheDocument();
    expect(screen.getByTestId("runs-inspection-workspace")).toHaveClass(
      "basis-0",
      "flex-1",
      "min-h-0",
      "min-w-0",
    );
    expect(screen.getByTestId("runs-inspection-workspace")).not.toHaveAttribute(
      "data-console-layout",
    );
    expect(screen.queryByTestId("runs-evidence-viewer"))
      .not.toBeInTheDocument();
    expect(screen.getByTestId("runs-detail-header")).toHaveTextContent(
      /succeeded/i,
    );
    expect(screen.getByTestId("runs-detail-header")).toHaveTextContent(
      /workflow package/i,
    );
    expect(screen.getByTestId("runs-detail-summary-line")).toHaveTextContent(
      /run #42/i,
    );
    expect(screen.getByTestId("runs-detail-summary-line")).toHaveTextContent(
      /captured/i,
    );
    expect(screen.getByTestId("runs-detail-summary-line")).toHaveTextContent(
      /51 tokens/i,
    );
    expect(screen.getByTestId("runs-detail-summary-line")).not.toHaveTextContent(
      /100%/i,
    );
    expect(screen.getByTestId("runs-detail-header")).not.toHaveTextContent(
      /output captured/i,
    );
    expect(screen.getByTestId("runs-detail-state-summary")).toHaveTextContent(
      /failure: step 2/i,
    );
    expect(screen.getByTestId("runs-detail-identity-line")).toHaveTextContent(
      /market review package/i,
    );
    expect(screen.getByTestId("runs-detail-metadata-line")).toHaveTextContent(
      /lineage from run #41/i,
    );
    expect(screen.getByTestId("runs-detail-target-identity")).toHaveTextContent(
      /market_review_package/i,
    );
    expect(screen.queryByText(/captured package id/i)).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /open current package/i }),
    ).toHaveAttribute("href", "/workflow-packages/7");
    expect(screen.getByTestId("runs-detail-actions")).toHaveClass(
      "flex",
      "min-w-0",
      "flex-wrap",
      "items-center",
    );
    expect(screen.getByTestId("runs-detail-rerun")).toHaveTextContent(
      /run snapshot again/i,
    );
    expect(screen.getByTestId("runs-detail-rerun")).toHaveClass(
      "bg-primary",
      "text-primary-foreground",
      "cursor-pointer",
    );
    const finalOutputCard = screen.getByTestId("runs-detail-final-output-card");
    const finalOutput = within(finalOutputCard).getByTestId(
      "runs-detail-final-output",
    );
    expect(finalOutputCard).toHaveAttribute("data-slot", "card");
    expect(
      finalOutputCard.querySelector("[data-slot='card-content']"),
    ).toHaveClass("space-y-5", "pt-6");
    expect(finalOutput).toHaveTextContent(/normalized/i);
    expect(finalOutput).toHaveClass(
      "flex",
      "flex-col",
      "data-[orientation=vertical]:items-stretch",
      "min-w-0",
      "gap-3",
    );
    expect(finalOutput).not.toHaveClass("overflow-hidden", "text-xs");
    expect(finalOutput.querySelector("pre")).toBeNull();
    expect(
      within(finalOutputCard).getAllByRole("heading", { name: /final output/i })[1],
    ).toHaveClass("text-base", "font-medium", "leading-none");
    expect(screen.queryByTestId("runs-evidence-pane-nav"))
      .not.toBeInTheDocument();
    defaultRender.unmount();
    searchParamsMock = new URLSearchParams("mode=execution");
    const stepsModeRender = render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-inspection-workspace")).toHaveAttribute(
      "data-run-mode",
      "execution",
    );
    expect(screen.getByTestId("runs-step-1-trace-summary")).toHaveTextContent(
      /analysis\/span-1/i,
    );
    expect(screen.getByTestId("runs-step-2-trace-summary")).toHaveTextContent(
      /decision\/span-2/i,
    );
    expect(
      screen.getByTestId("runs-step-1-completed-indicator"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("runs-step-2-completed-indicator"),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("runs-inspection-split-layout"))
      .not.toBeInTheDocument();
    expect(screen.queryByTestId("split-inspector-resize-handle"))
      .not.toBeInTheDocument();
    expect(screen.getByTestId("runs-execution-collapsible")).toHaveAttribute(
      "data-slot",
      "collapsible",
    );
    expect(screen.getByTestId("runs-step-1")).toHaveTextContent(
      /copied origin/i,
    );
    expect(screen.getByTestId("runs-step-1")).toHaveTextContent(
      /1 agent invocation/i,
    );
    expect(screen.getByTestId("runs-step-2")).toHaveTextContent(
      /1 agent invocation/i,
    );
    expect(
      screen.queryByTestId("runs-step-1-slot-analysis"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("runs-step-2-slot-decision"),
    ).not.toBeInTheDocument();

    stepsModeRender.unmount();
    searchParamsMock = new URLSearchParams("mode=summary");
    const overviewRender = render(<RunsDetailPage />);
    const overview = screen.getByTestId("runs-overview-workspace");
    expect(overview).toHaveClass("grid", "gap-3");
    expect(
      within(overview).getByRole("heading", { name: /operational overview/i }),
    ).toBeVisible();
    const evidenceAvailability = screen.getByTestId(
      "runs-detail-section-evidence-availability",
    );
    expect(
      within(evidenceAvailability).getByRole("heading", {
        name: /evidence availability/i,
      }),
    ).toBeVisible();
    expect(screen.getByTestId("runs-summary-execution-row")).toHaveTextContent(
      /2 of 2 invocation\(s\) terminal/i,
    );
    expect(screen.getByTestId("runs-summary-progress-row")).toHaveTextContent(
      /100%/i,
    );
    expect(evidenceAvailability).toHaveTextContent(/30 executed tokens/i);
    expect(evidenceAvailability).toHaveTextContent(/21 inherited tokens/i);

    overviewRender.unmount();
    searchParamsMock = new URLSearchParams("mode=runtime");
    const runtimeModeRender = render(<RunsDetailPage />);
    const runtimeProfile = screen.getByTestId("runs-runtime-profile");
    expect(runtimeProfile).toBeVisible();
    expect(runtimeProfile).toHaveTextContent(/runtime profile/i);
    expect(runtimeProfile).not.toHaveTextContent(/runtime snapshot summary/i);
    expect(runtimeProfile).not.toHaveTextContent(/frozen run provenance/i);
    const primaryProfile = screen.getByTestId(
      "runs-runtime-profile-connection-primary_openai",
    );
    expect(primaryProfile).toHaveTextContent(/Primary OpenAI/i);
    expect(primaryProfile).toHaveTextContent(/primary_openai/i);
    expect(primaryProfile).toHaveTextContent(/Responses-compatible/i);
    expect(primaryProfile).toHaveTextContent(/Credential present/i);
    expect(primaryProfile).toHaveTextContent(
      /9 supported · 2 unsupported · 0 unknown · 0 not applicable/i,
    );
    expect(primaryProfile).not.toHaveTextContent(/Snapshot key/i);
    expect(primaryProfile).not.toHaveTextContent(/Selected strategies/i);
    expect(primaryProfile).not.toHaveTextContent(/Last probed/i);
    const smokeProfile = screen.getByTestId(
      "runs-runtime-profile-connection-smoke_model",
    );
    expect(smokeProfile).toHaveTextContent(/Smoke Model/i);
    expect(smokeProfile).toHaveTextContent(/Chat Completions-compatible/i);
    expect(smokeProfile).toHaveTextContent(/No credential/i);
    expect(smokeProfile).toHaveTextContent(
      /5 supported · 3 unsupported · 0 unknown · 3 not applicable/i,
    );
    expect(screen.getByRole("heading", { name: /selected strategies/i })).toBeVisible();
    const decisionStrategy = screen.getByTestId("runs-runtime-strategy-2-1002");
    expect(decisionStrategy).toBeVisible();
    expect(decisionStrategy).toHaveTextContent(/consumer_agent@2/i);
    expect(decisionStrategy).toHaveTextContent(/json object validation/i);
    expect(decisionStrategy).toHaveTextContent(/native tool calls/i);
    expect(decisionStrategy).toHaveTextContent(/Disabled/i);
    expect(decisionStrategy).toHaveTextContent(/disabled by policy/i);
    expect(decisionStrategy).toHaveTextContent(/Input tokens/i);
    expect(decisionStrategy).toHaveTextContent(/30/i);
    expect(screen.queryByText(/total cost/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/inherited cost/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/executed cost/i)).not.toBeInTheDocument();

    runtimeModeRender.unmount();
    searchParamsMock = new URLSearchParams("mode=metadata");
    const auditModeRender = render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-audit-table")).toBeVisible();
    expect(screen.queryByTestId("runs-audit-row-trace-root"))
      .not.toBeInTheDocument();
    expect(screen.getByTestId("runs-audit-row-payload-output"))
      .toHaveTextContent(/final output captured/i);
    expect(
      screen.getByTestId("runs-audit-row-trace-agent-1002"),
    ).toHaveTextContent(/decision\/span-2/i);

    auditModeRender.unmount();
    searchParamsMock = new URLSearchParams("mode=execution");
    const stepSelectionRender = render(<RunsDetailPage />);
    const stepOneButton = within(
      screen.getByTestId("runs-step-1"),
    ).getAllByRole("button", { name: /step 1/i })[0];
    fireEvent.click(stepOneButton);
    expect(
      within(screen.getByTestId("runs-step-1")).queryByRole("link", {
        name: /step 1/i,
      }),
    ).not.toBeInTheDocument();
    const stepSelectUpdater = setSearchParamsMock.mock.calls.at(-1)?.[0] as (
      current: URLSearchParams,
    ) => URLSearchParams;
    const selectedStepParams = stepSelectUpdater(new URLSearchParams());
    expect(selectedStepParams.get("inspect")).toBe("step:1");
    expect(selectedStepParams.has("pane")).toBe(false);

    stepSelectionRender.unmount();
    searchParamsMock = new URLSearchParams("inspect=run&pane=input");
    const runInputRender = render(<RunsDetailPage />);
    const runInput = screen.getByTestId("runs-detail-input");
    expect(runInput).toHaveTextContent(/AAPL/i);
    expect(runInput).toHaveClass("flex", "flex-col", "min-w-0", "gap-3");
    expect(runInput).not.toHaveClass("overflow-hidden", "text-xs");
    expect(screen.getAllByRole("heading", { name: /^run input$/i })[1]).toHaveClass(
      "text-base",
      "font-medium",
      "leading-none",
    );
    expect(screen.queryByTestId("runs-active-evidence-viewer"))
      .not.toBeInTheDocument();
    expect(screen.queryByTestId("runs-evidence-pane-nav"))
      .not.toBeInTheDocument();

    runInputRender.unmount();
    searchParamsMock = new URLSearchParams("inspect=step:1");
    const stepSummaryRender = render(<RunsDetailPage />);
    expect(screen.queryByTestId("runs-inspection-split-layout"))
      .not.toBeInTheDocument();
    expect(screen.queryByTestId("runs-evidence-viewer"))
      .not.toBeInTheDocument();
    const stepInlineEvidence = screen.getByTestId("runs-step-1-inline-evidence");
    expect(stepInlineEvidence).toHaveTextContent(/step evidence/i);
    expect(within(stepInlineEvidence).getByTestId("runs-evidence-pane-nav"))
      .toBeVisible();
    expect(
      within(stepInlineEvidence).getByRole("button", { name: "Details" }),
    ).toBeVisible();
    const stepSummary = screen.getByTestId("runs-step-1-summary");
    const metadataHeading = within(stepSummary).getByRole("heading", {
      name: /step metadata/i,
    });
    const outputHeading = within(stepSummary).getByRole("heading", {
      name: /aggregated output/i,
    });
    expect(metadataHeading).toBeVisible();
    expect(metadataHeading).toHaveClass("text-base");
    expect(outputHeading).toBeVisible();
    expect(outputHeading).toHaveClass("text-base");
    expect(
      within(stepSummary).queryByRole("heading", { name: /step summary/i }),
    ).not.toBeInTheDocument();
    expect(
      within(stepSummary).queryByText(
        /step metadata and readonly aggregated output/i,
      ),
    ).not.toBeInTheDocument();
    expect(
      within(stepSummary).queryByText(/readonly step output/i),
    ).not.toBeInTheDocument();
    expect(
      stepSummary.querySelectorAll("[data-slot='card-content'] > section"),
    ).toHaveLength(2);
    const metadata = screen.getByTestId("runs-step-1-metadata");
    expect(metadata.tagName).toBe("DL");
    expect(metadata.querySelectorAll("dt")).toHaveLength(9);
    expect(
      screen.getByTestId("runs-step-1-aggregated-output"),
    ).toHaveTextContent(/analysis/i);
    expect(
      screen.getByTestId("runs-step-1-aggregated-output"),
    ).toHaveTextContent(/research_agent/i);

    stepSummaryRender.unmount();
    searchParamsMock = new URLSearchParams("inspect=step:1&pane=lineage");
    const stepLineageRender = render(<RunsDetailPage />);
    const stepLineage = screen.getByTestId("runs-step-1-lineage-summary");
    const stepLineageDiagram = within(stepLineage).getByTestId(
      "runs-step-1-lineage-diagram",
    );
    expect(stepLineageDiagram).toBeInTheDocument();
    expect(stepLineageDiagram).toHaveClass("h-80");
    expectDraggableZoomableLineageContract(
      within(stepLineageDiagram).getByTestId("mock-react-flow"),
    );
    expect(
      within(stepLineage).getByTestId("runs-step-1-lineage-node-source"),
    ).toHaveTextContent(/source run/i);
    expect(
      within(stepLineage).getByTestId("runs-step-1-lineage-node-source"),
    ).toHaveTextContent(/source step row/i);
    const stepLineageSourceNode = within(stepLineage).getByTestId(
      "runs-step-1-lineage-node-source",
    );
    expect(
      within(stepLineageSourceNode).getByRole("link", { name: /^run #41$/i }),
    ).toHaveAttribute("href", "/runs/41");
    expect(
      within(stepLineageSourceNode).getByRole("link", {
        name: /run #41 step 1/i,
      }),
    ).toHaveAttribute("href", "/runs/41#step-1");
    expect(
      within(stepLineage).getByTestId("runs-step-1-lineage-node-current"),
    ).toHaveTextContent(/origin/i);
    expect(
      within(stepLineage).getByTestId("runs-step-1-lineage-node-current"),
    ).toHaveTextContent(/copied/i);
    expect(
      within(stepLineageDiagram).getByTestId(
        "mock-react-flow-edge-source-current",
      ),
    ).toHaveTextContent(/provenance/i);

    stepLineageRender.unmount();
    searchParamsMock = new URLSearchParams("pane=provenance");
    const invalidRunPaneRender = render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-detail-final-output")).toHaveTextContent(
      /normalized/i,
    );
    expect(
      screen.getAllByRole("heading", { name: /final output/i })[0],
    ).toBeVisible();

    invalidRunPaneRender.unmount();
    searchParamsMock = new URLSearchParams("inspect=step:1&pane=request");
    const invalidStepPaneRender = render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-step-1-summary")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("runs-step-1-inline-evidence")).queryByRole(
        "button",
        { name: /trace/i },
      ),
    ).not.toBeInTheDocument();

    invalidStepPaneRender.unmount();
    searchParamsMock = new URLSearchParams("pane=lineage");
    const lineageRender = render(<RunsDetailPage />);
    const lineage = screen.getByTestId("runs-lineage-summary");
    const runLineageDiagram = within(lineage).getByTestId(
      "runs-lineage-diagram",
    );
    expect(runLineageDiagram).toBeInTheDocument();
    expect(runLineageDiagram).toHaveClass("h-80");
    const runLineageFlow =
      within(runLineageDiagram).getByTestId("mock-react-flow");
    expectDraggableZoomableLineageContract(runLineageFlow);
    fireEvent.click(
      within(runLineageFlow).getByTestId("mock-react-flow-drag-first-node"),
    );
    expect(
      within(lineage).getByTestId("runs-lineage-node-root"),
    ).toHaveAttribute("data-node-x", "123");
    expect(
      within(lineage).getByTestId("runs-lineage-node-root"),
    ).toHaveAttribute("data-node-y", "45");
    fireEvent.click(
      within(runLineageFlow).getByTestId("mock-react-flow-zoom-viewport"),
    );
    expect(runLineageFlow).toHaveAttribute("data-viewport-zoom", "1.25");
    expect(
      within(lineage).getByTestId("runs-lineage-node-root"),
    ).toHaveTextContent(/lineage root/i);
    expect(
      within(lineage).getByTestId("runs-lineage-node-root"),
    ).toHaveTextContent(/run #40/i);
    expect(
      within(lineage).getByRole("link", { name: /run #41/i }),
    ).toHaveAttribute("href", "/runs/41");
    expect(
      within(lineage).getByTestId("runs-lineage-node-source"),
    ).toHaveTextContent(/source run/i);
    expect(
      within(lineage).getByTestId("runs-historical-lineage"),
    ).toHaveTextContent(/read-only audit lineage/i);
    expect(
      within(lineage).getByTestId("runs-lineage-node-source"),
    ).toHaveTextContent(/historical lineage step/i);
    expect(
      within(lineage).getByTestId("runs-lineage-node-source"),
    ).toHaveTextContent(/step 1/i);
    expect(
      within(lineage).getByTestId("runs-lineage-node-current"),
    ).toHaveTextContent(/resume boundary/i);
    expect(
      within(lineage).getByTestId("runs-lineage-node-current"),
    ).toHaveTextContent(/step 2/i);
    expect(
      within(lineage).getByTestId("runs-lineage-node-current"),
    ).toHaveTextContent(/1 copied · 1 planned/i);
    expect(
      within(lineage).getByTestId("runs-lineage-node-current"),
    ).toHaveTextContent(/1 copied · 1 planned\/executed/i);
    expect(
      within(runLineageDiagram).getByTestId("mock-react-flow-edge-root-source"),
    ).toHaveTextContent(/lineage root/i);
    expect(
      within(runLineageDiagram).getByTestId(
        "mock-react-flow-edge-source-current",
      ),
    ).toHaveTextContent(/historical lineage \/ resume/i);

    lineageRender.unmount();
    searchParamsMock = new URLSearchParams(
      "inspect=invocation:1002&pane=error",
    );
    render(<RunsDetailPage />);
    const activeEvidence = within(
      screen.getByTestId("runs-invocation-1002-inline-evidence"),
    ).getByTestId("runs-active-evidence-viewer");
    expect(within(activeEvidence).getByText("model_error")).toBeVisible();
    expect(within(activeEvidence).getByText("Provider failed")).toBeVisible();
    expect(within(activeEvidence).getByText(/rate_limit/i)).toBeVisible();
  });

  it("renders missing usage metadata without hiding selected strategies", () => {
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          executedTokens: 0,
          finalOutput: { summary: "usage omitted" },
          steps: [
            buildStep({
              invocations: [
                buildInvocation({
                  graphMetadata: {
                    modelGateway: {
                      selectedStrategies: {
                        outputStrategy: "strictJsonSchema",
                        parallelToolCalls: false,
                        reasoningEffort: "medium",
                        reasoningStrategy: "enabled",
                        streamingStrategy: "disabled",
                        toolCallStrategy: "none",
                      },
                      usage: null,
                    },
                  },
                }),
              ],
            }),
          ],
          packageProvenance: buildPackageProvenance({
            resolvedModelConnections: [
              buildResolvedModelConnection({
                capabilities: buildCapabilities({
                  usageReporting: buildCapabilityState(
                    "unsupported",
                    "Usage metadata was not reported by the fake provider.",
                    "2026-05-08T07:50:00Z",
                  ),
                }),
              }),
            ],
          }),
        }),
      ),
    );

    const defaultRender = render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-runtime-profile")).toBeVisible();
    expect(screen.getByTestId("runs-runtime-strategy-1-1001")).toBeVisible();

    defaultRender.unmount();
    searchParamsMock = new URLSearchParams("mode=runtime");
    render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-runtime-profile")).toHaveTextContent(
      /usage reporting/i,
    );
    expect(screen.getByTestId("runs-runtime-profile")).toHaveTextContent(
      /unsupported/i,
    );

    expect(
      screen.getByTestId("runs-runtime-strategy-1-1001"),
    ).toBeVisible();
    expect(
      screen.getByTestId("runs-runtime-strategy-1-1001"),
    ).toHaveTextContent(/strictJsonSchema/i);
    expect(
      screen.getByTestId("runs-runtime-strategy-1-1001"),
    ).toHaveTextContent(/enabled/i);
    expect(
      within(screen.getByTestId("runs-runtime-strategy-1-1001")).queryByText(
        /^Input tokens$/i,
      ),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("runs-runtime-strategy-1-1001")).toHaveTextContent(
      /Usage not recorded/i,
    );
  });

  it("keeps raw payloads scrollable on mobile without a sheet inspector", () => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 390,
    });
    useRunMock.mockReturnValue(
      queryResult(buildRun({ finalOutput: { payload: "x".repeat(240) } })),
    );

    render(<RunsDetailPage />);

    const workspace = screen.getByTestId("runs-inspection-workspace");
    expect(workspace).not.toHaveAttribute("data-console-layout");
    expect(workspace).toHaveClass("min-w-0");
    expect(screen.queryByTestId("runs-inspection-sheet-layout"))
      .not.toBeInTheDocument();
    expect(screen.queryByTestId("runs-inspection-split-layout"))
      .not.toBeInTheDocument();
    expect(screen.queryByTestId("runs-mobile-inspector-trigger"))
      .not.toBeInTheDocument();
    expect(screen.queryByTestId("runs-evidence-viewer"))
      .not.toBeInTheDocument();

    const finalOutput = screen.getByTestId("runs-detail-final-output");
    fireEvent.mouseDown(within(finalOutput).getByRole("tab", { name: "Raw" }), {
      button: 0,
    });

    expect(
      screen.getByTestId("runs-detail-final-output-tab-scroll"),
    ).toHaveClass("max-w-full", "overflow-x-auto");
    expect(screen.getByTestId("runs-detail-final-output-raw")).toHaveAttribute(
      "data-wide-payload",
      "scroll",
    );
    expect(screen.getByTestId("runs-detail-final-output-raw")).toHaveClass(
      "max-w-full",
      "overflow-x-auto",
      "whitespace-pre",
    );
    expect(screen.queryByTestId("split-inspector-right-pane"))
      .not.toBeInTheDocument();
  });

  it("groups graph metadata and renders compact memory artifact audit links", () => {
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          packageProvenance: buildPackageProvenance(),
          memoryArtifacts: [
            {
              memoryId: "memory_701",
              summary: "AAPL decision memory",
              status: "pending",
              createdAt: NOW,
              provenance: {
                agentKey: "portfolio_manager",
                agentVersion: 3,
                createdByType: "agent",
                runId: 42,
                slot: "decision",
                workflowKey: "market_review",
                workflowVersion: 2,
              },
              sourceGraphMetadata: {
                nodeId: "decision",
                nodeKind: "step",
                loopId: "review_loop",
                loopIteration: 2,
              },
              auditLinks: {
                report: {
                  slug: "memory_aapl_decision",
                  name: "AAPL decision memory report",
                  url: "/reports/memory_aapl_decision",
                  downloadUrl: "/api/v1/reports/memory_aapl_decision/download",
                },
              },
            },
          ],
          steps: [
            buildStep({
              graphMetadata: {
                nodeKind: "fanout",
                fanoutId: "analyst_fanout",
                sourceRefs: { branches: [] },
              },
              invocations: [
                buildInvocation({
                  graphMetadata: {
                    nodeId: "market_analysis",
                    nodeKind: "step",
                    fanoutId: "analyst_fanout",
                    branchId: "market",
                  },
                  slot: "market",
                }),
                buildInvocation({
                  graphMetadata: {
                    nodeId: "news_analysis",
                    nodeKind: "step",
                    fanoutId: "analyst_fanout",
                    branchId: "news",
                  },
                  id: 1002,
                  position: 2,
                  slot: "news",
                }),
              ],
            }),
            buildStep({
              id: 102,
              index: 2,
              invocations: [
                buildInvocation({
                  graphMetadata: {
                    nodeId: "risk_review",
                    nodeKind: "step",
                    loopId: "review_loop",
                    loopIteration: 1,
                  },
                  id: 1003,
                  runStepId: 102,
                  slot: "risk",
                  stepIndex: 2,
                }),
              ],
            }),
          ],
        }),
      ),
    );

    searchParamsMock = new URLSearchParams("mode=execution");
    const defaultRender = render(<RunsDetailPage />);

    expect(screen.queryByTestId("runs-graph-summary")).not.toBeInTheDocument();
    expect(screen.getByTestId("runs-step-1")).toHaveTextContent(
      /2 agent invocation/i,
    );
    expect(
      screen.queryByTestId("runs-step-1-slot-market"),
    ).not.toBeInTheDocument();

    defaultRender.unmount();
    searchParamsMock = new URLSearchParams(
      "mode=metadata&inspect=memory:memory_701&pane=details",
    );
    render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-memory-artifacts")).toBeInTheDocument();
    const artifact = screen.getByTestId("runs-memory-artifact-memory_701");
    expect(artifact).toHaveTextContent("AAPL decision memory");
    expect(artifact).toHaveTextContent(/pending/i);
    expect(artifact).toHaveTextContent(/portfolio_manager@3/i);
    expect(artifact).toHaveTextContent(/workflow market_review/i);
    expect(artifact).toHaveTextContent(/slot decision/i);
    expect(artifact).toHaveTextContent(/run #42/i);
    expect(artifact).toHaveTextContent(/loop review_loop.*iteration 2/i);
    expect(
      within(artifact).getByRole("link", { name: /open canonical memory/i }),
    ).toHaveAttribute(
      "href",
      "/memory?memoryId=memory_701&packageKey=market_review_package&runId=42&workflowKey=market_review&agentKey=portfolio_manager",
    );
    expect(
      within(artifact).getByRole("link", { name: /open report/i }),
    ).toHaveAttribute("href", "/reports/memory_aapl_decision");
    expect(
      within(artifact).getByRole("link", { name: /download/i }),
    ).toHaveAttribute("download");
    expect(
      within(artifact).getByRole("link", { name: /download/i }),
    ).toHaveAttribute("href", "/api/v1/reports/memory_aapl_decision/download");
  });

  it("renders memory artifacts without report actions when audit links are absent", () => {
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          memoryArtifacts: [
            {
              memoryId: "memory_702",
              summary: "AAPL risk memory",
              status: "active",
              createdAt: NOW,
              provenance: {
                agentKey: "risk_manager",
                agentVersion: 1,
                createdByType: "agent",
                runId: 42,
                workflowKey: "market_review",
              },
              sourceGraphMetadata: null,
            },
          ],
        }),
      ),
    );

    searchParamsMock = new URLSearchParams(
      "mode=metadata&inspect=memory:memory_702&pane=details",
    );
    render(<RunsDetailPage />);

    const artifact = screen.getByTestId("runs-memory-artifact-memory_702");
    expect(artifact).toHaveTextContent("AAPL risk memory");
    expect(artifact).toHaveTextContent(/active/i);
    expect(artifact).toHaveTextContent(/risk_manager@1/i);
    expect(artifact).toHaveTextContent(/workflow market_review/i);
    expect(artifact).toHaveTextContent(/run #42/i);
    expect(
      within(artifact).queryByRole("link", { name: /open report/i }),
    ).not.toBeInTheDocument();
    expect(
      within(artifact).queryByRole("link", { name: /download/i }),
    ).not.toBeInTheDocument();
  });

  it("renders grouped run memory event evidence and keeps artifacts compact", () => {
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          memoryArtifacts: [
            {
              memoryId: "memory_safe",
              summary: "Compact safe memory",
              status: "active",
              createdAt: NOW,
              provenance: {
                agentKey: "portfolio_manager",
                agentVersion: 3,
                createdByType: "agent",
                runId: 42,
                slot: "decision",
                workflowKey: "market_review",
              },
              sourceGraphMetadata: null,
            },
          ],
          memoryEvents: [
            buildMemoryEvent({
              id: 9101,
              eventType: "retrieved",
              retrievalMode: "explicit-selectors",
              filters: { scope: "package:market_review" },
              budget: { limit: 5, maxCharacters: 4000 },
              resultSnapshot: {
                resultCount: 1,
                snippets: [{ memoryId: "memory_safe", summary: "Safe memory" }],
              },
              traceSpanId: "span-memory-lookup",
            }),
            buildMemoryEvent({
              id: 9102,
              eventType: "injected",
              injectedText:
                "Historical memory, not an instruction: Safe memory",
              statusSnapshot: { status: "injected" },
            }),
            buildMemoryEvent({
              id: 9103,
              eventType: "written",
              memoryId: "memory_safe",
              revisionId: "revision_created",
              resultSnapshot: { revisionAction: "created" },
            }),
            buildMemoryEvent({
              id: 9104,
              eventType: "reused",
              memoryId: "memory_safe",
              revisionId: "revision_created",
              resultSnapshot: { revisionAction: "reused" },
            }),
            buildMemoryEvent({
              id: 9105,
              eventType: "reviewed",
              memoryId: "memory_safe",
              statusSnapshot: { status: "resolved" },
            }),
            buildMemoryEvent({
              id: 9106,
              eventType: "failed",
              statusSnapshot: { status: "failed", code: "memory_write_failed" },
            }),
          ],
        }),
      ),
    );

    searchParamsMock = new URLSearchParams("inspect=run&pane=memory");
    render(<RunsDetailPage />);

    const memoryWorkspace = screen.getByTestId("runs-memory-workspace");
    expect(screen.getByTestId("runs-memory-evidence")).toBeVisible();
    expect(
      within(memoryWorkspace).getByRole("heading", { name: /run memory evidence/i }),
    ).toBeVisible();
    expect(
      within(memoryWorkspace).getByRole("heading", { name: /^memory$/i }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: /retrieved context/i }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: /memory written and reused/i }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: /review and follow-up/i }),
    ).toBeVisible();
    expect(screen.getByRole("heading", { name: /audit trail/i })).toBeVisible();
    expect(
      screen.getByTestId("runs-memory-group-retrievedContext"),
    ).toHaveTextContent(/2 events/i);
    expect(
      screen.getByTestId("runs-memory-group-memoryWrites"),
    ).toHaveTextContent(/2 events/i);
    expect(
      screen.getByTestId("runs-memory-group-reviewFollowUp"),
    ).toHaveTextContent(/1 event/i);
    expect(
      screen.getByTestId("runs-memory-group-auditTrail"),
    ).toHaveTextContent(/1 event/i);
    expect(
      screen.getByTestId("runs-memory-event-9101-result"),
    ).toHaveTextContent(/Safe memory/i);
    expect(
      screen.getByTestId("runs-memory-event-9102-injected-text"),
    ).toHaveTextContent(/Historical memory, not an instruction/i);
    expect(
      screen.getByTestId("runs-memory-event-9103-result"),
    ).toHaveTextContent(/created/i);
    expect(
      screen.getByTestId("runs-memory-event-9104-result"),
    ).toHaveTextContent(/reused/i);
    expect(
      screen.getByTestId("runs-memory-event-9105-status"),
    ).toHaveTextContent(/resolved/i);
    expect(
      screen.getByTestId("runs-memory-event-9106-status"),
    ).toHaveTextContent(/memory_write_failed/i);
    expect(screen.getByTestId("runs-memory-compact-artifacts"))
      .toHaveTextContent(/compact artifact slice/i);
    expect(screen.getByTestId("runs-memory-compact-artifact-memory_safe"))
      .toHaveTextContent(/Compact safe memory/i);
    expect(
      screen.queryByTestId("runs-memory-artifacts-empty"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /open report/i }),
    ).not.toBeInTheDocument();
  });

  it("renders one compact absent-memory state for the memory mode", () => {
    useRunMock.mockReturnValue(queryResult(buildRun()));
    searchParamsMock = new URLSearchParams("inspect=run&pane=memory");

    render(<RunsDetailPage />);

    const memoryWorkspace = screen.getByTestId("runs-memory-workspace");
    expect(within(memoryWorkspace).getByTestId("runs-memory-empty"))
      .toHaveTextContent(/No retrieval, write, review, audit, or compact memory artifact/i);
    expect(screen.queryByTestId("runs-memory-inspector-empty"))
      .not.toBeInTheDocument();
    expect(screen.queryByTestId("runs-memory-artifacts-empty"))
      .not.toBeInTheDocument();
    expect(screen.queryByText(/No memory artifacts were created by this run/i))
      .not.toBeInTheDocument();
  });

  it("omits graph grouping and memory artifact cards when metadata is absent", () => {
    useRunMock.mockReturnValue(queryResult(buildRun()));

    render(<RunsDetailPage />);

    expect(screen.queryByTestId("runs-graph-summary")).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("runs-memory-artifacts"),
    ).not.toBeInTheDocument();
  });

  it("renders a single-node step lineage diagram when no upstream source exists", () => {
    useRunMock.mockReturnValue(queryResult(buildRun()));
    searchParamsMock = new URLSearchParams("inspect=step:1&pane=lineage");

    render(<RunsDetailPage />);

    const stepLineage = screen.getByTestId("runs-step-1-lineage-summary");
    const stepLineageDiagram = within(stepLineage).getByTestId(
      "runs-step-1-lineage-diagram",
    );
    expect(stepLineageDiagram).toHaveClass("h-80");
    expectDraggableZoomableLineageContract(
      within(stepLineageDiagram).getByTestId("mock-react-flow"),
    );
    expect(
      within(stepLineage).getByTestId("runs-step-1-lineage-node-current"),
    ).toHaveTextContent(/origin/i);
    expect(
      within(stepLineage).getByTestId("runs-step-1-lineage-node-current"),
    ).toHaveTextContent(/planned/i);
    expect(
      within(stepLineage).getByTestId("runs-step-1-lineage-node-current"),
    ).toHaveTextContent(/source run/i);
    expect(
      within(stepLineage).getByTestId("runs-step-1-lineage-node-current"),
    ).toHaveTextContent(/source step/i);
    expect(
      within(stepLineage).getByTestId("runs-step-1-lineage-node-current"),
    ).toHaveTextContent(/source step row/i);
    expect(
      within(stepLineage).getByTestId("runs-step-1-lineage-node-current"),
    ).toHaveTextContent(/not recorded/i);
    expect(
      within(stepLineage).queryByTestId("runs-step-1-lineage-node-source"),
    ).not.toBeInTheDocument();
    expect(
      within(stepLineageDiagram).queryByTestId(
        "mock-react-flow-edge-source-current",
      ),
    ).not.toBeInTheDocument();
  });

  it("renders package target identity and span-only outline trace summary", () => {
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          finalOutput: { summary: "Macro complete" },
          id: 43,
          input: { topic: "macro" },
          steps: [
            buildStep({
              id: 201,
              invocations: [
                buildInvocation({
                  agentRef: {
                    scope: "packageLocal",
                    localId: 20,
                    key: "macro_agent",
                    version: 9,
                  },
                  agentKey: "macro_agent",
                  agentVersion: 9,
                  id: 2001,
                  output: { summary: "Macro complete" },
                  outputSchemaRef: {
                    scope: "packageLocal",
                    localId: 31,
                    version: 1,
                  },
                  outputSchemaVersion: 1,
                  resolvedInput: { topic: "macro" },
                  runId: 43,
                  runStepId: 201,
                  slot: "result",
                  stepIndex: 1,
                  tokens: 18,
                  traceSpanId: "span-agent-1",
                }),
              ],
              runId: 43,
            }),
          ],
          targetId: 12,
          targetKey: "macro_package",
          targetKind: "workflowPackage",
          totalTokens: 18,
          traceId: null,
        }),
      ),
    );

    searchParamsMock = new URLSearchParams("mode=execution");
    render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-execution-table")).toHaveClass(
      "border-transparent",
      "bg-transparent",
    );
    expect(screen.getByTestId("runs-detail-header")).toHaveTextContent(
      /workflow package/i,
    );
    expect(screen.getByTestId("runs-detail-target-identity")).toHaveTextContent(
      /macro_package/i,
    );
    expect(
      screen.queryByText(/captured package id: 12/i),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("runs-step-1-trace-summary")).toHaveTextContent(
      /result\/span-agent-1/i,
    );
    expect(
      screen.getByTestId("runs-step-1-completed-indicator"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/captured through invocation spans/i),
    ).not.toBeInTheDocument();
  });

  it("renders structured final and aggregated output for nested payloads", () => {
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          finalOutput: { second: {}, first: [null, 3, "ready"], done: false },
          steps: [
            buildStep({
              invocations: [
                buildInvocation({
                  output: {
                    agentSecond: false,
                    agentFirst: [null, 3, "ready"],
                  },
                }),
              ],
            }),
          ],
        }),
      ),
    );

    const defaultRender = render(<RunsDetailPage />);
    const finalOutput = screen.getByTestId("runs-detail-final-output");
    const finalText = finalOutput.textContent ?? "";

    expect(finalOutput.querySelector("pre")).toBeNull();
    expect(finalOutput).toHaveTextContent("object");
    expect(finalOutput).toHaveTextContent("array");
    expect(finalOutput).toHaveTextContent("false");
    expect(finalOutput).toHaveTextContent("null");
    expect(finalOutput).toHaveTextContent("3");
    expect(finalOutput).toHaveTextContent('"ready"');
    expect(finalOutput).toHaveTextContent("Empty object");
    expect(finalText.indexOf("second")).toBeLessThan(
      finalText.indexOf("first"),
    );

    defaultRender.unmount();
    searchParamsMock = new URLSearchParams("inspect=step:1");
    render(<RunsDetailPage />);

    const aggregatedOutput = screen.getByTestId(
      "runs-step-1-aggregated-output",
    );
    const aggregatedText = aggregatedOutput.textContent ?? "";

    expect(aggregatedOutput.querySelector("pre")).toBeNull();
    expect(aggregatedText.indexOf("stepIndex")).toBeLessThan(
      aggregatedText.indexOf("agentInvocations"),
    );
    expect(aggregatedText.indexOf("agentSecond")).toBeLessThan(
      aggregatedText.indexOf("agentFirst"),
    );
  });

  it("enables multiline string views through runs payload wrappers", () => {
    const markdownTable = "| Symbol | Rating |\n| --- | --- |\n| AAPL | Buy |";
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          finalOutput: { summary: "Line one\nLine two", report: markdownTable },
          steps: [
            buildStep({
              invocations: [
                buildInvocation({
                  output: { report: markdownTable },
                }),
              ],
            }),
          ],
        }),
      ),
    );

    const defaultRender = render(<RunsDetailPage />);
    const finalOutput = screen.getByTestId("runs-detail-final-output");

    expect(
      within(finalOutput).getAllByRole("tab", { name: "Raw JSON" })[0],
    ).toHaveAttribute("data-state", "active");
    expect(
      within(finalOutput).getAllByRole("tab", { name: "Markdown" }),
    ).toHaveLength(2);

    fireEvent.mouseDown(
      within(finalOutput).getAllByRole("tab", { name: "Plain text" })[0],
      { button: 0 },
    );
    expect(
      finalOutput.querySelector('[data-structured-string-view="plain-text"]')
        ?.textContent,
    ).toBe("Line one\nLine two");

    fireEvent.mouseDown(
      within(finalOutput).getAllByRole("tab", { name: "Markdown" })[1],
      { button: 0 },
    );
    expect(finalOutput.querySelector("table")).toBeInTheDocument();

    defaultRender.unmount();
    searchParamsMock = new URLSearchParams("inspect=step:1");
    render(<RunsDetailPage />);

    const aggregatedOutput = screen.getByTestId(
      "runs-step-1-aggregated-output",
    );
    fireEvent.mouseDown(
      within(aggregatedOutput).getByRole("tab", { name: "Markdown" }),
      { button: 0 },
    );

    expect(aggregatedOutput.querySelector("table")).toBeInTheDocument();
  });

  it("renders terminal null final output instead of the pending-state copy", () => {
    useRunMock.mockReturnValue(
      queryResult(buildRun({ finalOutput: null, status: "succeeded" })),
    );

    const succeededRender = render(<RunsDetailPage />);

    const succeededFinalOutput = screen.getByTestId("runs-detail-final-output");

    expect(succeededFinalOutput).toHaveTextContent("null");
    expect(
      succeededFinalOutput.querySelector("[data-structured-string-view]"),
    ).toBeNull();
    expect(succeededFinalOutput).not.toHaveTextContent(
      "Final output is not available yet.",
    );
    succeededRender.unmount();

    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          error: "Provider failed before final output.",
          finalOutput: null,
          status: "failed",
          steps: [buildStep({ status: "failed" })],
        }),
      ),
    );

    searchParamsMock = new URLSearchParams("mode=outputs");
    render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-detail-state-summary")).toHaveTextContent(
      /failure/i,
    );
    expect(screen.getAllByText("Not produced").length).toBeGreaterThan(0);
    expect(screen.getByTestId("runs-detail-final-output")).toHaveTextContent(
      /run failed before final output was produced/i,
    );
    expect(screen.queryByTestId("runs-active-evidence-viewer"))
      .not.toBeInTheDocument();
    expect(screen.queryByText("Final output is not available yet."))
      .not.toBeInTheDocument();
  });

  it("handles empty, running, skipped, and invalid pane URL state", () => {
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          finalOutput: null,
          progress: {
            unit: "invocation",
            terminalCount: 3,
            totalCount: 5,
            percent: 64,
          },
          status: "running",
          steps: [
            buildStep({
              finishedAt: null,
              invocations: [],
              persistedAt: null,
              status: "running",
            }),
            buildStep({
              id: 102,
              index: 2,
              invocations: [],
              origin: "copied",
              sourceRunId: 41,
              sourceRunStepId: 402,
              sourceStepIndex: 2,
              status: "skipped",
            }),
          ],
          traceId: null,
        }),
      ),
    );

    searchParamsMock = new URLSearchParams("pane=request");
    const stepsRender = render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-inspection-workspace")).toHaveAttribute(
      "data-run-mode",
      "execution",
    );
    expect(screen.getByTestId("runs-step-1")).toHaveTextContent(/running/i);
    expect(
      screen.getByTestId("runs-step-1-executing-indicator"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("runs-step-2")).toHaveTextContent(/skipped/i);
    expect(
      screen.queryByTestId("runs-step-2-completed-indicator"),
    ).not.toBeInTheDocument();

    stepsRender.unmount();
    searchParamsMock = new URLSearchParams("mode=summary&pane=request");
    const overviewRender = render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-summary-execution-row")).toHaveTextContent(
      /0 of 0 invocation\(s\) terminal/i,
    );
    expect(screen.getByTestId("runs-summary-progress-row")).toHaveTextContent(
      /64%/i,
    );

    overviewRender.unmount();
    searchParamsMock = new URLSearchParams("mode=outputs&pane=request");
    const outputRender = render(<RunsDetailPage />);
    const pendingFinalOutputCard = screen.getByTestId(
      "runs-detail-final-output-card",
    );
    const pendingFinalOutput = within(pendingFinalOutputCard).getByTestId(
      "runs-detail-final-output",
    );
    expect(pendingFinalOutputCard).toHaveAttribute("data-slot", "card");
    expect(
      pendingFinalOutputCard.querySelector("[data-slot='card-content']"),
    ).toHaveClass("space-y-5", "pt-6");
    expect(pendingFinalOutput).toHaveTextContent(
      "Final output is not available yet.",
    );
    expect(pendingFinalOutput).toHaveClass(
      "rounded-md",
      "border",
      "bg-muted/20",
      "p-3",
      "text-sm",
      "text-muted-foreground",
    );
    expect(
      within(pendingFinalOutputCard).getAllByRole("heading", {
        name: /final output/i,
      })[1],
    ).toBeVisible();
    expect(
      screen.queryByText(/no invocation trace spans captured/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("runs-evidence-pane-nav"))
      .not.toBeInTheDocument();
    expect(
      screen.queryByText(/no invocations have been planned or persisted/i),
    ).not.toBeInTheDocument();
    outputRender.unmount();
  });

  it("renders an explicit empty state when no steps exist", () => {
    useRunMock.mockReturnValue(
      queryResult(buildRun({ steps: [], traceId: null })),
    );
    searchParamsMock = new URLSearchParams("mode=execution");

    render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-empty-steps")).toHaveTextContent(
      /no steps have been planned/i,
    );
  });

  it("shows backend-owned queued reasons with zero progress", () => {
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          finishedAt: null,
          progress: {
            unit: "invocation",
            terminalCount: 0,
            totalCount: 0,
            percent: 0,
          },
          queue: {
            blockingRunId: 41,
            message:
              "Backend queue read model: source package run #41 is still active.",
            reason: "blocked-by-package-serial-policy",
            state: "blocked",
          },
          startedAt: null,
          status: "queued",
          steps: [],
          traceId: null,
        }),
      ),
    );

    const queuedReasonRender = render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-detail-status")).toHaveTextContent(
      /queued/i,
    );
    expect(screen.getByTestId("runs-detail-queue-reason")).toHaveTextContent(
      /blocked by package serial policy/i,
    );
    expect(screen.getByTestId("runs-detail-queue-reason")).toHaveTextContent(
      /backend queue read model: source package run #41 is still active/i,
    );
    expect(screen.getByTestId("runs-detail-queue-reason")).toHaveTextContent(
      /blocking run: #41/i,
    );
    expect(screen.getByTestId("runs-summary-progress-row")).toHaveTextContent(
      /0%/i,
    );
    expect(screen.queryByText(/awaiting execution/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/still running/i)).not.toBeInTheDocument();

    queuedReasonRender.unmount();
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          finishedAt: null,
          progress: {
            unit: "invocation",
            terminalCount: 0,
            totalCount: 0,
            percent: 0,
          },
          queue: null,
          startedAt: null,
          status: "queued",
          steps: [],
          traceId: null,
        }),
      ),
    );
    render(<RunsDetailPage />);

    expect(
      screen.queryByTestId("runs-detail-queue-reason"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/awaiting worker capacity/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/blocked by package serial policy/i),
    ).not.toBeInTheDocument();
  });

  it("submits a full rerun with changed root parameters and navigates to the created run", async () => {
    searchParamsMock = new URLSearchParams("rerun=1");
    createRunRerunMutateAsyncMock.mockResolvedValue({ id: 98 });
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunRerunDraftMock.mockReturnValue(draftQueryResult(buildRerunDraft()));

    render(<RunsDetailPage />);

    expect(
      screen.getByRole("dialog", { name: /run snapshot again/i }),
    ).toBeVisible();
    expect(
      screen.getByText(/create a new run from this captured snapshot/i),
    ).toBeVisible();
    expect(useRunRerunDraftMock).toHaveBeenLastCalledWith("42", {
      enabled: true,
    });
    fireEvent.change(await screen.findByLabelText("Root run parameters JSON"), {
      target: { value: JSON.stringify({ ticker: "MSFT" }, null, 2) },
    });
    expect(
      screen.queryByLabelText("Target invocation input JSON"),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("run-rerun-submit"));

    await waitFor(() =>
      expect(createRunRerunMutateAsyncMock).toHaveBeenCalledWith({
        runId: "42",
        payload: { parameters: { ticker: "MSFT" } },
      }),
    );
    expect(navigateMock).toHaveBeenCalledWith("/runs/98");
  });

  it("shows current rerun readiness blockers from top-level draft fields", async () => {
    searchParamsMock = new URLSearchParams("rerun=1");
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunRerunDraftMock.mockReturnValue(
      draftQueryResult(
        buildRerunDraft({
          blockingErrors: [
            {
              field: "modelConnections.primary_openai",
              issue: "Current model connection is missing.",
            },
          ],
          packageProvenance: buildPackageProvenance({
            preflightSummary: { ready: true, blockingErrors: [], warnings: [] },
          }),
          ready: false,
          warnings: [
            {
              field: "extensions.signaldeck.finance",
              issue: "Historical package used Finance Workspace tools.",
            },
          ],
        }),
      ),
    );

    render(<RunsDetailPage />);

    const readiness = await screen.findByTestId("run-rerun-readiness");
    expect(readiness).toHaveTextContent(/current snapshot readiness blocked/i);
    expect(readiness).toHaveTextContent(/current model connection is missing/i);
    expect(readiness).toHaveTextContent(
      /historical package used finance workspace tools/i,
    );
    expect(screen.getByTestId("run-rerun-submit")).toBeDisabled();
    fireEvent.click(screen.getByTestId("run-rerun-submit"));
    expect(createRunRerunMutateAsyncMock).not.toHaveBeenCalled();
  });

  it("does not treat historical rerun provenance preflight as current readiness", async () => {
    searchParamsMock = new URLSearchParams("rerun=1");
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunRerunDraftMock.mockReturnValue(
      draftQueryResult(
        buildRerunDraft({
          packageProvenance: buildPackageProvenance({
            preflightSummary: {
              blockingErrors: [
                {
                  field: "modelConnections.old",
                  issue: "Historical model connection was missing.",
                },
              ],
              ready: false,
              warnings: [],
            },
          }),
          ready: true,
        }),
      ),
    );

    render(<RunsDetailPage />);

    const readiness = await screen.findByTestId("run-rerun-readiness");
    expect(readiness).toHaveTextContent(/current snapshot readiness passed/i);
    expect(readiness).not.toHaveTextContent(
      /historical model connection was missing/i,
    );
    expect(screen.getByTestId("run-rerun-submit")).toBeEnabled();
  });

  it("opens the fork dialog from invocation URL params and fetches the invocation draft", async () => {
    searchParamsMock = new URLSearchParams(
      "fork=1&resumeStepIndex=1&invocationId=1001",
    );
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunForkDraftMock.mockReturnValue(forkDraftQueryResult(buildForkDraft()));

    render(<RunsDetailPage />);

    const forkDialog = screen.getByRole("dialog", {
      name: /fork from analysis invocation/i,
    });
    expect(forkDialog).toBeVisible();
    expect(useRunForkDraftMock).toHaveBeenLastCalledWith("42", 1001, {
      enabled: true,
    });
    expect(within(forkDialog).getByText(/resume at step 1/i)).toBeVisible();
    expect(within(forkDialog).getByText(/^invocation #1001$/i)).toBeVisible();
    expect(
      await screen.findByLabelText("Target invocation input JSON"),
    ).toHaveValue(JSON.stringify({ ticker: "AAPL" }, null, 2));
    expect(
      screen.queryByLabelText("Root run parameters JSON"),
    ).not.toBeInTheDocument();
  });

  it("shows current fork readiness blockers from top-level draft fields", async () => {
    searchParamsMock = new URLSearchParams(
      "fork=1&resumeStepIndex=1&invocationId=1001",
    );
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunForkDraftMock.mockReturnValue(
      forkDraftQueryResult(
        buildForkDraft({
          blockingErrors: [
            {
              field: "modelConnections.primary_openai",
              issue: "Current model connection is missing for fork.",
            },
          ],
          packageProvenance: buildPackageProvenance({
            preflightSummary: { ready: true, blockingErrors: [], warnings: [] },
          }),
          ready: false,
          warnings: [
            {
              field: "extensions.signaldeck.finance",
              issue: "Current extension state changed since source run.",
            },
          ],
        }),
      ),
    );

    render(<RunsDetailPage />);

    const readiness = await screen.findByTestId("run-fork-readiness");
    expect(readiness).toHaveTextContent(/current fork readiness blocked/i);
    expect(readiness).toHaveTextContent(
      /current model connection is missing for fork/i,
    );
    expect(readiness).toHaveTextContent(
      /current extension state changed since source run/i,
    );
    expect(screen.getByTestId("run-fork-submit")).toBeDisabled();
    fireEvent.click(screen.getByTestId("run-fork-submit"));
    expect(createRunForkMutateAsyncMock).not.toHaveBeenCalled();
  });

  it("does not treat historical fork provenance preflight as current readiness", async () => {
    searchParamsMock = new URLSearchParams(
      "fork=1&resumeStepIndex=1&invocationId=1001",
    );
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunForkDraftMock.mockReturnValue(
      forkDraftQueryResult(
        buildForkDraft({
          packageProvenance: buildPackageProvenance({
            preflightSummary: {
              blockingErrors: [
                {
                  field: "modelConnections.old",
                  issue: "Historical model connection was missing.",
                },
              ],
              ready: false,
              warnings: [],
            },
          }),
          ready: true,
        }),
      ),
    );

    render(<RunsDetailPage />);

    const readiness = await screen.findByTestId("run-fork-readiness");
    expect(readiness).toHaveTextContent(/current fork readiness passed/i);
    expect(readiness).not.toHaveTextContent(
      /historical model connection was missing/i,
    );
    expect(screen.getByTestId("run-fork-submit")).toBeEnabled();
  });

  it("keeps the last fork presentation while Cancel closes the dialog", async () => {
    searchParamsMock = new URLSearchParams(
      "fork=1&resumeStepIndex=1&invocationId=1001",
    );
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunForkDraftMock.mockReturnValue(forkDraftQueryResult(buildForkDraft()));

    const { rerender } = render(<RunsDetailPage />);

    fireEvent.change(
      await screen.findByLabelText("Target invocation input JSON"),
      {
        target: { value: JSON.stringify({ ticker: "MSFT" }, null, 2) },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    applyLatestSearchParamsUpdate("fork=1&resumeStepIndex=1&invocationId=1001");
    rerender(<RunsDetailPage />);

    expect(useRunForkDraftMock).toHaveBeenLastCalledWith("42", 1001, {
      enabled: false,
    });
    expect(
      screen.queryByTestId("run-fork-invalid-target"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/fork unavailable/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/invocation #undefined/i),
    ).not.toBeInTheDocument();
  });

  it("resets canceled fork edits after the close animation completes and the dialog reopens", async () => {
    searchParamsMock = new URLSearchParams(
      "fork=1&resumeStepIndex=1&invocationId=1001",
    );
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunForkDraftMock.mockReturnValue(forkDraftQueryResult(buildForkDraft()));

    const { rerender } = render(<RunsDetailPage />);

    fireEvent.change(
      await screen.findByLabelText("Target invocation input JSON"),
      {
        target: { value: JSON.stringify({ ticker: "MSFT" }, null, 2) },
      },
    );

    vi.useFakeTimers();
    try {
      fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
      applyLatestSearchParamsUpdate(
        "fork=1&resumeStepIndex=1&invocationId=1001",
      );
      rerender(<RunsDetailPage />);
      expect(useRunForkDraftMock).toHaveBeenLastCalledWith("42", 1001, {
        enabled: false,
      });

      act(() => {
        vi.advanceTimersByTime(200);
      });

      searchParamsMock = new URLSearchParams(
        "fork=1&resumeStepIndex=1&invocationId=1001",
      );
      rerender(<RunsDetailPage />);

      expect(screen.getByLabelText("Target invocation input JSON")).toHaveValue(
        JSON.stringify({ ticker: "AAPL" }, null, 2),
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("updates URL params when the selected invocation fork action is clicked", () => {
    searchParamsMock = new URLSearchParams("inspect=invocation:1001");
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));

    render(<RunsDetailPage />);

    expect(
      screen.queryByTestId("runs-step-1-replay-entry"),
    ).not.toBeInTheDocument();
    expect(
      within(
        screen.getByTestId("runs-invocation-1001-outline-entry"),
      ).queryByRole("button", { name: /fork from this invocation/i }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("runs-invocation-1001-fork-entry"));

    expect(setSearchParamsMock).toHaveBeenCalledTimes(1);
    const updater = setSearchParamsMock.mock.calls[0][0] as (
      current: URLSearchParams,
    ) => URLSearchParams;
    const nextParams = updater(
      new URLSearchParams("panel=legacy&stepReplay=1&stepIndex=1"),
    );
    expect(nextParams.get("panel")).toBe("legacy");
    expect(nextParams.get("fork")).toBe("1");
    expect(nextParams.get("resumeStepIndex")).toBe("1");
    expect(nextParams.get("invocationId")).toBe("1001");
    expect(nextParams.has("stepReplay")).toBe(false);
    expect(nextParams.has("stepIndex")).toBe(false);
  });

  it("uses selected invocation fork actions and no ambiguous step shortcut for mixed or multi-invocation steps", () => {
    searchParamsMock = new URLSearchParams("inspect=invocation:1001");
    useRunMock.mockReturnValue(
      queryResult(
        buildReplayableWorkflowRun({
          steps: [
            buildStep({
              invocations: [
                buildInvocation({ id: 1001, position: 1, slot: "analysis" }),
                buildInvocation({ id: 1003, position: 2, slot: "risk" }),
              ],
              operationInvocations: [
                {
                  createdAt: NOW,
                  durationMs: 3,
                  errorCode: null,
                  errorDetails: [],
                  errorMessage: null,
                  finishedAt: "2026-04-20T10:00:03Z",
                  graphMetadata: null,
                  id: 2001,
                  method: "POST",
                  operationKey: "notify",
                  operationKind: "http",
                  optional: false,
                  output: { ok: true },
                  outputOrigin: "executed",
                  outputSchemaRef: {
                    scope: "packageLocal",
                    localId: 31,
                    version: 1,
                  },
                  outputSchemaVersion: 1,
                  persistedAt: "2026-04-20T10:00:03Z",
                  position: 3,
                  requestMetadata: {},
                  responseMetadata: {},
                  runId: 42,
                  runStepId: 101,
                  slot: "notify",
                  sourceOperationInvocationId: null,
                  sourceRunId: null,
                  sourceRunStepId: null,
                  sourceStepIndex: null,
                  startedAt: NOW,
                  status: "succeeded",
                  stepIndex: 1,
                  timeoutSeconds: 10,
                  traceSpanId: null,
                  updatedAt: "2026-04-20T10:00:03Z",
                },
              ],
            }),
          ],
        }),
      ),
    );

    const { rerender } = render(<RunsDetailPage />);

    expect(
      screen.queryByTestId("runs-step-1-replay-entry"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId("runs-invocation-1001-fork-entry"),
    ).toHaveTextContent(/fork from this invocation/i);
    expect(
      screen.queryByTestId("runs-invocation-1003-fork-entry"),
    ).not.toBeInTheDocument();
    expect(
      within(
        screen.getByTestId("runs-invocation-1001-outline-entry"),
      ).queryByRole("button", { name: /fork from this invocation/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId("runs-operation-2001-outline-entry"),
    ).toHaveTextContent(/operation forks are not supported/i);
    expect(
      within(
        screen.getByTestId("runs-operation-2001-outline-entry"),
      ).queryByRole("button", { name: /fork from this invocation/i }),
    ).not.toBeInTheDocument();

    searchParamsMock = new URLSearchParams("inspect=invocation:1003");
    rerender(<RunsDetailPage />);

    expect(
      screen.queryByTestId("runs-invocation-1001-fork-entry"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId("runs-invocation-1003-fork-entry"),
    ).toHaveTextContent(/fork from this invocation/i);
  });

  it("does not expose fork actions for non-succeeded steps", () => {
    searchParamsMock = new URLSearchParams("inspect=invocation:1001");
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          targetKind: "workflowPackage",
          steps: [
            buildStep({ status: "pending" }),
            buildStep({ id: 102, index: 2, status: "failed" }),
            buildStep({ id: 103, index: 3, status: "skipped" }),
          ],
        }),
      ),
    );

    render(<RunsDetailPage />);

    expect(
      screen.queryByRole("button", { name: /fork from this invocation/i }),
    ).not.toBeInTheDocument();
  });

  it("submits changed target invocation input and navigates to the created run", async () => {
    searchParamsMock = new URLSearchParams(
      "fork=1&resumeStepIndex=1&invocationId=1001",
    );
    createRunForkMutateAsyncMock.mockResolvedValue({ id: 99 });
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunForkDraftMock.mockReturnValue(forkDraftQueryResult(buildForkDraft()));

    render(<RunsDetailPage />);

    fireEvent.change(
      await screen.findByLabelText("Target invocation input JSON"),
      {
        target: { value: JSON.stringify({ ticker: "MSFT" }, null, 2) },
      },
    );
    fireEvent.click(screen.getByTestId("run-fork-submit"));

    await waitFor(() =>
      expect(createRunForkMutateAsyncMock).toHaveBeenCalledWith({
        runId: "42",
        payload: {
          invocationInput: { ticker: "MSFT" },
          sourceInvocationId: 1001,
        },
      }),
    );
    expect(navigateMock).toHaveBeenCalledWith("/runs/99");
  });

  it("blocks fork submit and shows precise JSON parse errors", async () => {
    searchParamsMock = new URLSearchParams(
      "fork=1&resumeStepIndex=1&invocationId=1001",
    );
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunForkDraftMock.mockReturnValue(forkDraftQueryResult(buildForkDraft()));

    render(<RunsDetailPage />);

    fireEvent.change(
      await screen.findByLabelText("Target invocation input JSON"),
      {
        target: { value: "{not-json" },
      },
    );

    expect(
      await screen.findByText(
        /target invocation input json must be valid json/i,
      ),
    ).toBeVisible();
    expect(screen.getByTestId("run-fork-submit")).toBeDisabled();
    fireEvent.click(screen.getByTestId("run-fork-submit"));
    expect(createRunForkMutateAsyncMock).not.toHaveBeenCalled();
  });

  it("shows invalid URL fork state without fetching a draft", () => {
    searchParamsMock = new URLSearchParams(
      "fork=1&resumeStepIndex=3&invocationId=1001",
    );
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));

    render(<RunsDetailPage />);

    expect(screen.getByTestId("run-fork-invalid-target")).toHaveTextContent(
      /step 3 is not available/i,
    );
    expect(useRunForkDraftMock).toHaveBeenLastCalledWith("42", 1001, {
      enabled: false,
    });
  });
});
