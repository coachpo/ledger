import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import type { RunAgentInvocationRead, RunForkDraftRead, RunMemoryEventRead, RunRead, RunRerunDraftRead, RunStepRead } from "@/lib/types/run";

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
  Link: ({ children, to }: { children: ReactNode; to: string }) => <a href={to}>{children}</a>,
  useLocation: () => ({ hash: "", pathname: "/runs/42", search: searchParamsMock.toString() }),
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
    changes: Array<{ id: string; position?: { x: number; y: number }; type: string }>,
    nodes: Array<{ id: string; position?: { x: number; y: number } }>,
  ) => nodes.map((node) => {
    const positionChange = changes.find((change) => change.id === node.id && change.type === "position");
    return positionChange?.position ? { ...node, position: positionChange.position } : node;
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
      data: { details: Array<{ label: string; value: ReactNode }>; eyebrow: string; testId: string; title: ReactNode };
      id: string;
      position?: { x: number; y: number };
    }>;
    nodesConnectable?: boolean;
    nodesDraggable?: boolean;
    nodesFocusable?: boolean;
    onNodesChange?: (changes: Array<{ id: string; position?: { x: number; y: number }; type: string }>) => void;
    onViewportChange?: (viewport: { x: number; y: number; zoom: number }) => void;
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
      data-has-on-viewport-change={String(typeof onViewportChange === "function")}
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
            onNodesChange?.([{ id: firstNode.id, position: { x: 123, y: 45 }, type: "position" }]);
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
        <div data-node-x={String(node.position?.x)} data-node-y={String(node.position?.y)} data-testid={node.data.testId} key={node.id}>
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
        <p data-testid={`mock-react-flow-edge-${edge.id}`} key={edge.id}>{edge.label}</p>
      ))}
      {children}
    </div>
  ),
}));

const NOW = "2026-04-20T10:00:00Z";

function buildInvocation(overrides: Partial<RunAgentInvocationRead> = {}): RunAgentInvocationRead {
  return {
    agentRef: { scope: "global", id: 11, key: "research_agent", version: 3 },
    agentId: 11,
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
    outputSchemaId: 21,
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

function buildMemoryEvent(overrides: Partial<RunMemoryEventRead> = {}): RunMemoryEventRead {
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
    queuedAt: NOW,
    resumeStepIndex: 1,
    sourceRunId: null,
    startedAt: NOW,
    status: "succeeded",
    steps: [buildStep()],
    targetId: 7,
    targetKey: "market_review",
    targetKind: "workflow",
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

function buildRerunDraft(overrides: Partial<RunRerunDraftRead> = {}): RunRerunDraftRead {
  return {
    parameters: { ticker: "AAPL" },
    sourceRunId: 42,
    targetId: 7,
    targetKey: "market_review",
    targetKind: "workflow",
    packageProvenance: null,
    ...overrides,
  };
}

function buildForkDraft(overrides: Partial<RunForkDraftRead> = {}): RunForkDraftRead {
  return {
    invocationInput: { ticker: "AAPL" },
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
  const lastCall = setSearchParamsMock.mock.calls[setSearchParamsMock.mock.calls.length - 1];
  const updater = lastCall?.[0];

  if (typeof updater !== "function") {
    throw new Error("Expected the latest search params update to use an updater function.");
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
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1024 });
    useRunRerunDraftMock.mockReset();
    useRunRerunDraftMock.mockReturnValue(draftQueryResult<RunRerunDraftRead>());
    useRunMock.mockReset();
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
      agentId: 12,
      agentKey: "consumer_agent",
      agentVersion: 2,
      durationMs: 12,
      errorCode: "model_error",
      errorDetails: [{ type: "rate_limit" }],
      errorMessage: "Provider failed",
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
          {
            apiStyle: "responses",
            baseUrl: "https://api.openai.com/v1",
            connectionKind: "provider",
            hasApiKey: true,
            key: "primary_openai",
            modelId: "gpt-5.5",
            name: "Primary OpenAI",
            reasoningEffort: "medium",
            timeoutSeconds: 60,
          },
          {
            apiStyle: "responses",
            baseUrl: "https://signaldeck-deterministic-model.local/v1",
            connectionKind: "deterministic_smoke",
            hasApiKey: false,
            key: "smoke_model",
            modelId: "signaldeck-smoke",
            name: "Smoke Model",
            reasoningEffort: null,
            timeoutSeconds: 5,
          },
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
    expect(screen.getByTestId("runs-detail-page")).toHaveClass("min-w-0", "overflow-hidden");
    expect(screen.queryByRole("main")).not.toBeInTheDocument();
    expect(screen.getByTestId("runs-inspection-workspace")).toBeInTheDocument();
    expect(screen.getByTestId("runs-inspection-workspace")).toHaveAttribute("data-console-layout", "split");
    expect(screen.getByTestId("runs-evidence-viewer")).toBeInTheDocument();
    expect(screen.getByTestId("runs-detail-status")).toHaveTextContent(/succeeded/i);
    expect(screen.getByTestId("runs-detail-target-kind")).toHaveTextContent(/workflow package/i);
    expect(screen.getByTestId("runs-detail-target-identity")).toHaveTextContent(/snapshot: market_review_package/i);
    expect(screen.getByRole("link", { name: /open current package/i })).toHaveAttribute("href", "/workflow-packages/7");
    expect(screen.queryByRole("link", { name: /back to workflow/i })).not.toBeInTheDocument();
    expect(screen.getByTestId("runs-detail-actions")).toHaveClass("flex", "min-w-0", "flex-col", "sm:flex-row");
    expect(screen.getByTestId("runs-detail-rerun")).toHaveTextContent(/run snapshot again/i);
    expect(screen.getByTestId("runs-detail-rerun")).toHaveClass("bg-primary", "text-primary-foreground", "w-full", "sm:w-auto");
    const finalOutputCard = screen.getByTestId("runs-detail-final-output-card");
    const finalOutput = within(finalOutputCard).getByTestId("runs-detail-final-output");
    expect(finalOutputCard).toHaveAttribute("data-slot", "card");
    expect(finalOutputCard.querySelector("[data-slot='card-content']")).toHaveClass("space-y-5", "pt-6");
    expect(finalOutput).toHaveTextContent(/normalized/i);
    expect(finalOutput).toHaveClass("flex", "flex-col", "data-[orientation=vertical]:items-stretch", "min-w-0", "gap-3");
    expect(finalOutput).not.toHaveClass("overflow-hidden", "text-xs");
    expect(finalOutput.querySelector("pre")).toBeNull();
    expect(within(finalOutputCard).getByRole("heading", { name: /final output/i })).toHaveClass("text-base", "font-medium", "leading-none");
    expect(within(screen.getByTestId("runs-evidence-pane-nav")).queryByRole("button", { name: /trace/i })).not.toBeInTheDocument();
    expect(screen.getByTestId("runs-step-1-trace-summary")).toHaveTextContent(/analysis\/span-1/i);
    expect(screen.getByTestId("runs-step-2-trace-summary")).toHaveTextContent(/decision\/span-2/i);
    expect(screen.getByTestId("runs-step-1-completed-indicator")).toBeInTheDocument();
    expect(screen.queryByTestId("runs-step-2-completed-indicator")).not.toBeInTheDocument();
    expect(screen.getByTestId("runs-workspace-context")).toHaveAttribute("data-slot", "card");
    expect(within(screen.getByTestId("runs-workspace-context")).getAllByTestId(/runs-summary-.*-row/)).toHaveLength(3);
    expect(screen.getByTestId("runs-inspection-workspace")).toHaveAttribute("data-slot", "resizable-panel-group");
    expect(screen.getByTestId("runs-inspection-resize-handle")).toBeInTheDocument();
    expect(screen.getByText(/^Total tokens$/i).parentElement).toHaveTextContent(/51/i);
    expect(screen.getByText(/^Inherited tokens$/i).parentElement).toHaveTextContent(/21/i);
    expect(screen.getByText(/^Executed tokens$/i).parentElement).toHaveTextContent(/30/i);
    expect(screen.queryByText(/total cost/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/inherited cost/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/executed cost/i)).not.toBeInTheDocument();
    expect(screen.getByTestId("runs-step-1")).toHaveTextContent(/copied origin/i);
    expect(screen.getByTestId("runs-step-1")).toHaveTextContent(/1 agent invocation/i);
    expect(screen.getByTestId("runs-step-2")).toHaveTextContent(/1 agent invocation/i);
    expect(screen.queryByTestId("runs-step-1-slot-analysis")).not.toBeInTheDocument();
    expect(screen.queryByTestId("runs-step-2-slot-decision")).not.toBeInTheDocument();

    const stepOneButton = within(screen.getByTestId("runs-step-1")).getAllByRole("button", { name: /step 1/i })[0];
    fireEvent.click(stepOneButton);
    expect(within(screen.getByTestId("runs-step-1")).queryByRole("link", { name: /step 1/i })).not.toBeInTheDocument();
    const stepSelectUpdater = setSearchParamsMock.mock.calls.at(-1)?.[0] as (current: URLSearchParams) => URLSearchParams;
    const selectedStepParams = stepSelectUpdater(new URLSearchParams());
    expect(selectedStepParams.get("inspect")).toBe("step:1");
    expect(selectedStepParams.has("pane")).toBe(false);

    defaultRender.unmount();
    searchParamsMock = new URLSearchParams("inspect=run&pane=input");
    const runInputRender = render(<RunsDetailPage />);
    const runInput = screen.getByTestId("runs-detail-input");
    expect(runInput).toHaveTextContent(/AAPL/i);
    expect(runInput).toHaveClass("flex", "flex-col", "min-w-0", "gap-3");
    expect(runInput).not.toHaveClass("overflow-hidden", "text-xs");
    expect(screen.getByRole("heading", { name: /^run input$/i })).toHaveClass("text-base", "font-medium", "leading-none");
    expect(screen.queryByTestId("runs-detail-final-output-card")).not.toBeInTheDocument();
    expect(screen.queryByTestId("runs-detail-final-output")).not.toBeInTheDocument();

    runInputRender.unmount();
    searchParamsMock = new URLSearchParams("inspect=step:1");
    const stepSummaryRender = render(<RunsDetailPage />);
    const stepSummary = screen.getByTestId("runs-step-1-summary");
    const metadataHeading = within(stepSummary).getByRole("heading", { name: /step metadata/i });
    const outputHeading = within(stepSummary).getByRole("heading", { name: /aggregated output/i });
    expect(metadataHeading).toBeVisible();
    expect(metadataHeading).toHaveClass("text-base");
    expect(outputHeading).toBeVisible();
    expect(outputHeading).toHaveClass("text-base");
    expect(within(stepSummary).queryByRole("heading", { name: /step summary/i })).not.toBeInTheDocument();
    expect(within(stepSummary).queryByText(/step metadata and readonly aggregated output/i)).not.toBeInTheDocument();
    expect(within(stepSummary).queryByText(/readonly step output/i)).not.toBeInTheDocument();
    expect(stepSummary.querySelectorAll("[data-slot='card-content'] > section")).toHaveLength(2);
    const metadata = screen.getByTestId("runs-step-1-metadata");
    expect(metadata.tagName).toBe("DL");
    expect(metadata.querySelectorAll("dt")).toHaveLength(9);
    expect(screen.getByTestId("runs-step-1-aggregated-output")).toHaveTextContent(/analysis/i);
    expect(screen.getByTestId("runs-step-1-aggregated-output")).toHaveTextContent(/research_agent/i);

    stepSummaryRender.unmount();
    searchParamsMock = new URLSearchParams("inspect=step:1&pane=lineage");
    const stepLineageRender = render(<RunsDetailPage />);
    const stepLineage = screen.getByTestId("runs-step-1-lineage-summary");
    const stepLineageDiagram = within(stepLineage).getByTestId("runs-step-1-lineage-diagram");
    expect(stepLineageDiagram).toBeInTheDocument();
    expect(stepLineageDiagram).toHaveClass("h-80");
    expectDraggableZoomableLineageContract(within(stepLineageDiagram).getByTestId("mock-react-flow"));
    expect(within(stepLineage).getByTestId("runs-step-1-lineage-node-source")).toHaveTextContent(/source run/i);
    expect(within(stepLineage).getByTestId("runs-step-1-lineage-node-source")).toHaveTextContent(/source step row/i);
    const stepLineageSourceNode = within(stepLineage).getByTestId("runs-step-1-lineage-node-source");
    expect(within(stepLineageSourceNode).getByRole("link", { name: /^run #41$/i })).toHaveAttribute("href", "/runs/41");
    expect(within(stepLineageSourceNode).getByRole("link", { name: /run #41 step 1/i })).toHaveAttribute("href", "/runs/41#step-1");
    expect(within(stepLineage).getByTestId("runs-step-1-lineage-node-current")).toHaveTextContent(/origin/i);
    expect(within(stepLineage).getByTestId("runs-step-1-lineage-node-current")).toHaveTextContent(/copied/i);
    expect(within(stepLineageDiagram).getByTestId("mock-react-flow-edge-source-current")).toHaveTextContent(/provenance/i);

    stepLineageRender.unmount();
    searchParamsMock = new URLSearchParams("pane=provenance");
    const invalidRunPaneRender = render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-detail-final-output")).toHaveTextContent(/normalized/i);
    expect(screen.getByRole("heading", { name: /final output/i })).toBeVisible();

    invalidRunPaneRender.unmount();
    searchParamsMock = new URLSearchParams("inspect=step:1&pane=request");
    const invalidStepPaneRender = render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-step-1-summary")).toBeInTheDocument();
    expect(within(screen.getByTestId("runs-evidence-pane-nav")).queryByRole("button", { name: /trace/i })).not.toBeInTheDocument();

    invalidStepPaneRender.unmount();
    searchParamsMock = new URLSearchParams("pane=lineage");
    const lineageRender = render(<RunsDetailPage />);
    const lineage = screen.getByTestId("runs-lineage-summary");
    const runLineageDiagram = within(lineage).getByTestId("runs-lineage-diagram");
    expect(runLineageDiagram).toBeInTheDocument();
    expect(runLineageDiagram).toHaveClass("h-80");
    const runLineageFlow = within(runLineageDiagram).getByTestId("mock-react-flow");
    expectDraggableZoomableLineageContract(runLineageFlow);
    fireEvent.click(within(runLineageFlow).getByTestId("mock-react-flow-drag-first-node"));
    expect(within(lineage).getByTestId("runs-lineage-node-root")).toHaveAttribute("data-node-x", "123");
    expect(within(lineage).getByTestId("runs-lineage-node-root")).toHaveAttribute("data-node-y", "45");
    fireEvent.click(within(runLineageFlow).getByTestId("mock-react-flow-zoom-viewport"));
    expect(runLineageFlow).toHaveAttribute("data-viewport-zoom", "1.25");
    expect(within(lineage).getByTestId("runs-lineage-node-root")).toHaveTextContent(/lineage root/i);
    expect(within(lineage).getByTestId("runs-lineage-node-root")).toHaveTextContent(/run #40/i);
    expect(within(lineage).getByRole("link", { name: /run #41/i })).toHaveAttribute("href", "/runs/41");
    expect(within(lineage).getByTestId("runs-lineage-node-source")).toHaveTextContent(/source run/i);
    expect(within(lineage).getByTestId("runs-legacy-replay-lineage")).toHaveTextContent(/historical run was created by the old step replay flow/i);
    expect(within(lineage).getByTestId("runs-lineage-node-source")).toHaveTextContent(/legacy replay step/i);
    expect(within(lineage).getByTestId("runs-lineage-node-source")).toHaveTextContent(/step 1/i);
    expect(within(lineage).getByTestId("runs-lineage-node-current")).toHaveTextContent(/resume boundary/i);
    expect(within(lineage).getByTestId("runs-lineage-node-current")).toHaveTextContent(/step 2/i);
    expect(within(lineage).getByTestId("runs-lineage-node-current")).toHaveTextContent(/1 copied · 1 planned/i);
    expect(within(lineage).getByTestId("runs-lineage-node-current")).toHaveTextContent(/1 copied · 1 planned\/executed/i);
    expect(within(runLineageDiagram).getByTestId("mock-react-flow-edge-root-source")).toHaveTextContent(/lineage root/i);
    expect(within(runLineageDiagram).getByTestId("mock-react-flow-edge-source-current")).toHaveTextContent(/legacy replay \/ resume/i);

    lineageRender.unmount();
    searchParamsMock = new URLSearchParams("inspect=invocation:1002&pane=error");
    render(<RunsDetailPage />);
    expect(screen.getByText("model_error")).toBeVisible();
    expect(screen.getByText("Provider failed")).toBeVisible();
    expect(screen.getByText(/rate_limit/i)).toBeVisible();
  });

  it("stacks the inspection console and keeps raw payloads scrollable on mobile", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    useRunMock.mockReturnValue(queryResult(buildRun({ finalOutput: { payload: "x".repeat(240) } })));

    render(<RunsDetailPage />);

    const workspace = screen.getByTestId("runs-inspection-workspace");
    await waitFor(() => expect(workspace).toHaveAttribute("data-console-layout", "stacked"));
    expect(workspace).toHaveClass("min-w-0");
    expect(screen.getByTestId("runs-execution-outline")).toHaveClass("min-w-0");
    expect(screen.getByTestId("runs-evidence-viewer")).toHaveClass("min-w-0");
    expect(screen.getByTestId("runs-evidence-pane-nav")).toHaveClass("min-w-0", "flex-wrap");

    const finalOutput = screen.getByTestId("runs-detail-final-output");
    fireEvent.mouseDown(within(finalOutput).getByRole("tab", { name: "Raw" }), { button: 0 });

    expect(screen.getByTestId("runs-detail-final-output-tab-scroll")).toHaveClass("max-w-full", "overflow-x-auto");
    expect(screen.getByTestId("runs-detail-final-output-raw")).toHaveAttribute("data-wide-payload", "scroll");
    expect(screen.getByTestId("runs-detail-final-output-raw")).toHaveClass("max-w-full", "overflow-x-auto", "whitespace-pre");
  });

  it("groups graph metadata and renders compact memory artifact audit links", () => {
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
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
              sourceGraphMetadata: { nodeId: "decision", nodeKind: "step", loopId: "review_loop", loopIteration: 2 },
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
                  graphMetadata: { nodeId: "market_analysis", nodeKind: "step", fanoutId: "analyst_fanout", branchId: "market" },
                  slot: "market",
                }),
                buildInvocation({
                  graphMetadata: { nodeId: "news_analysis", nodeKind: "step", fanoutId: "analyst_fanout", branchId: "news" },
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
                  graphMetadata: { nodeId: "risk_review", nodeKind: "step", loopId: "review_loop", loopIteration: 1 },
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

    const defaultRender = render(<RunsDetailPage />);

    expect(screen.queryByTestId("runs-graph-summary")).not.toBeInTheDocument();
    expect(screen.getByTestId("runs-step-1")).toHaveTextContent(/2 agent invocation/i);
    expect(screen.queryByTestId("runs-step-1-slot-market")).not.toBeInTheDocument();

    defaultRender.unmount();
    searchParamsMock = new URLSearchParams("inspect=memory:memory_701");
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
    expect(within(artifact).getByRole("link", { name: /open report/i })).toHaveAttribute("href", "/reports/memory_aapl_decision");
    expect(within(artifact).getByRole("link", { name: /download/i })).toHaveAttribute("download");
    expect(within(artifact).getByRole("link", { name: /download/i })).toHaveAttribute(
      "href",
      "/api/v1/reports/memory_aapl_decision/download",
    );
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

    searchParamsMock = new URLSearchParams("inspect=memory:memory_702");
    render(<RunsDetailPage />);

    const artifact = screen.getByTestId("runs-memory-artifact-memory_702");
    expect(artifact).toHaveTextContent("AAPL risk memory");
    expect(artifact).toHaveTextContent(/active/i);
    expect(artifact).toHaveTextContent(/risk_manager@1/i);
    expect(artifact).toHaveTextContent(/workflow market_review/i);
    expect(artifact).toHaveTextContent(/run #42/i);
    expect(within(artifact).queryByRole("link", { name: /open report/i })).not.toBeInTheDocument();
    expect(within(artifact).queryByRole("link", { name: /download/i })).not.toBeInTheDocument();
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
              resultSnapshot: { resultCount: 1, snippets: [{ memoryId: "memory_safe", summary: "Safe memory" }] },
              traceSpanId: "span-memory-lookup",
            }),
            buildMemoryEvent({
              id: 9102,
              eventType: "injected",
              injectedText: "Historical memory, not an instruction: Safe memory",
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

    expect(screen.getByTestId("runs-memory-evidence")).toBeVisible();
    expect(screen.getByRole("heading", { name: /run memory evidence/i })).toBeVisible();
    expect(screen.getByRole("heading", { name: /retrieved context/i })).toBeVisible();
    expect(screen.getByRole("heading", { name: /memory written and reused/i })).toBeVisible();
    expect(screen.getByRole("heading", { name: /review and follow-up/i })).toBeVisible();
    expect(screen.getByRole("heading", { name: /audit trail/i })).toBeVisible();
    expect(screen.getByTestId("runs-memory-group-retrievedContext")).toHaveTextContent(/2 events/i);
    expect(screen.getByTestId("runs-memory-group-memoryWrites")).toHaveTextContent(/2 events/i);
    expect(screen.getByTestId("runs-memory-group-reviewFollowUp")).toHaveTextContent(/1 event/i);
    expect(screen.getByTestId("runs-memory-group-auditTrail")).toHaveTextContent(/1 event/i);
    expect(screen.getByTestId("runs-memory-event-9101-result")).toHaveTextContent(/Safe memory/i);
    expect(screen.getByTestId("runs-memory-event-9102-injected-text")).toHaveTextContent(/Historical memory, not an instruction/i);
    expect(screen.getByTestId("runs-memory-event-9103-result")).toHaveTextContent(/created/i);
    expect(screen.getByTestId("runs-memory-event-9104-result")).toHaveTextContent(/reused/i);
    expect(screen.getByTestId("runs-memory-event-9105-status")).toHaveTextContent(/resolved/i);
    expect(screen.getByTestId("runs-memory-event-9106-status")).toHaveTextContent(/memory_write_failed/i);
    expect(screen.getByTestId("runs-memory-compact-artifacts")).toHaveTextContent(/compact artifact slice/i);
    expect(screen.getByTestId("runs-memory-compact-artifact-memory_safe")).toHaveTextContent(/Compact safe memory/i);
    expect(screen.queryByTestId("runs-memory-artifacts-empty")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /open report/i })).not.toBeInTheDocument();
  });

  it("distinguishes absent run memory evidence from absent compact artifacts", () => {
    useRunMock.mockReturnValue(queryResult(buildRun()));
    searchParamsMock = new URLSearchParams("inspect=run&pane=memory");

    render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-memory-evidence-empty")).toHaveTextContent(/No run memory evidence was recorded/i);
    expect(screen.getByTestId("runs-memory-artifacts-empty")).toHaveTextContent(/No compact memory artifacts were written/i);
    expect(screen.queryByText(/No memory artifacts were created by this run/i)).not.toBeInTheDocument();
  });

  it("omits graph grouping and memory artifact cards when metadata is absent", () => {
    useRunMock.mockReturnValue(queryResult(buildRun()));

    render(<RunsDetailPage />);

    expect(screen.queryByTestId("runs-graph-summary")).not.toBeInTheDocument();
    expect(screen.queryByTestId("runs-memory-artifacts")).not.toBeInTheDocument();
  });

  it("renders a single-node step lineage diagram when no upstream source exists", () => {
    useRunMock.mockReturnValue(queryResult(buildRun()));
    searchParamsMock = new URLSearchParams("inspect=step:1&pane=lineage");

    render(<RunsDetailPage />);

    const stepLineage = screen.getByTestId("runs-step-1-lineage-summary");
    const stepLineageDiagram = within(stepLineage).getByTestId("runs-step-1-lineage-diagram");
    expect(stepLineageDiagram).toHaveClass("h-80");
    expectDraggableZoomableLineageContract(within(stepLineageDiagram).getByTestId("mock-react-flow"));
    expect(within(stepLineage).getByTestId("runs-step-1-lineage-node-current")).toHaveTextContent(/origin/i);
    expect(within(stepLineage).getByTestId("runs-step-1-lineage-node-current")).toHaveTextContent(/planned/i);
    expect(within(stepLineage).getByTestId("runs-step-1-lineage-node-current")).toHaveTextContent(/source run/i);
    expect(within(stepLineage).getByTestId("runs-step-1-lineage-node-current")).toHaveTextContent(/source step/i);
    expect(within(stepLineage).getByTestId("runs-step-1-lineage-node-current")).toHaveTextContent(/source step row/i);
    expect(within(stepLineage).getByTestId("runs-step-1-lineage-node-current")).toHaveTextContent(/not recorded/i);
    expect(within(stepLineage).queryByTestId("runs-step-1-lineage-node-source")).not.toBeInTheDocument();
    expect(within(stepLineageDiagram).queryByTestId("mock-react-flow-edge-source-current")).not.toBeInTheDocument();
  });

  it("renders standalone agent target identity and span-only outline trace summary", () => {
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
                  agentId: 20,
                  agentKey: "macro_agent",
                  agentVersion: 9,
                  id: 2001,
                  output: { summary: "Macro complete" },
                  outputSchemaId: 31,
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
          targetKey: "macro_agent",
          targetKind: "agent",
          totalTokens: 18,
          traceId: null,
        }),
      ),
    );

    render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-detail-target-kind")).toHaveTextContent(/agent/i);
    expect(screen.getByTestId("runs-detail-target-identity")).toHaveTextContent(/^macro_agent$/i);
    expect(screen.getByText(/target id: 12/i)).toBeVisible();
    expect(screen.getByText(/standalone agent execution/i)).toBeVisible();
    expect(screen.getByTestId("runs-step-1-trace-summary")).toHaveTextContent(/result\/span-agent-1/i);
    expect(screen.getByTestId("runs-step-1-completed-indicator")).toBeInTheDocument();
    expect(screen.queryByText(/captured through invocation spans/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /back to workflow/i })).not.toBeInTheDocument();
    expect(screen.queryByTestId("runs-detail-rerun")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /fork from this invocation/i })).not.toBeInTheDocument();
  });

  it("shows agent-run URL fork state as unavailable without fetching a draft", () => {
    searchParamsMock = new URLSearchParams("fork=1&resumeStepIndex=1&invocationId=1001");
    useRunMock.mockReturnValue(queryResult(buildRun({ targetKind: "agent" })));

    render(<RunsDetailPage />);

    expect(screen.queryByRole("button", { name: /fork from this invocation/i })).not.toBeInTheDocument();
    expect(screen.getByTestId("run-fork-invalid-target")).toHaveTextContent(/available for succeeded workflow package runs and succeeded agent invocations/i);
    expect(useRunForkDraftMock).toHaveBeenLastCalledWith("42", 1001, { enabled: false });
  });

  it("shows generic workflow URL fork state as unavailable without fetching a draft", () => {
    searchParamsMock = new URLSearchParams("fork=1&resumeStepIndex=1&invocationId=1001");
    useRunMock.mockReturnValue(queryResult(buildRun({ replayStepIndex: 1, targetKind: "workflow" })));

    render(<RunsDetailPage />);

    expect(screen.getByTestId("run-fork-invalid-target")).toHaveTextContent(/available for succeeded workflow package runs and succeeded agent invocations/i);
    expect(useRunForkDraftMock).toHaveBeenLastCalledWith("42", 1001, { enabled: false });
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
                  output: { agentSecond: false, agentFirst: [null, 3, "ready"] },
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
    expect(finalText.indexOf("second")).toBeLessThan(finalText.indexOf("first"));

    defaultRender.unmount();
    searchParamsMock = new URLSearchParams("inspect=step:1");
    render(<RunsDetailPage />);

    const aggregatedOutput = screen.getByTestId("runs-step-1-aggregated-output");
    const aggregatedText = aggregatedOutput.textContent ?? "";

    expect(aggregatedOutput.querySelector("pre")).toBeNull();
    expect(aggregatedText.indexOf("stepIndex")).toBeLessThan(aggregatedText.indexOf("agentInvocations"));
    expect(aggregatedText.indexOf("agentSecond")).toBeLessThan(aggregatedText.indexOf("agentFirst"));
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

  it("renders completed null final output instead of the pending-state copy", () => {
    useRunMock.mockReturnValue(queryResult(buildRun({ finalOutput: null, status: "succeeded" })));

    render(<RunsDetailPage />);

    const finalOutput = screen.getByTestId("runs-detail-final-output");

    expect(finalOutput).toHaveTextContent("null");
    expect(finalOutput.querySelector("[data-structured-string-view]")).toBeNull();
    expect(finalOutput).not.toHaveTextContent("Final output is not available yet.");
  });

  it("handles empty, running, skipped, and invalid pane URL state", () => {
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          finalOutput: null,
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
    render(<RunsDetailPage />);

    expect(screen.getByText(/0 of 0 invocation\(s\) terminal/i)).toBeVisible();
    const pendingFinalOutputCard = screen.getByTestId("runs-detail-final-output-card");
    const pendingFinalOutput = within(pendingFinalOutputCard).getByTestId("runs-detail-final-output");
    expect(pendingFinalOutputCard).toHaveAttribute("data-slot", "card");
    expect(pendingFinalOutputCard.querySelector("[data-slot='card-content']")).toHaveClass("space-y-5", "pt-6");
    expect(pendingFinalOutput).toHaveTextContent("Final output is not available yet.");
    expect(pendingFinalOutput).toHaveClass("rounded-md", "border", "bg-muted/20", "p-3", "text-sm", "text-muted-foreground");
    expect(within(pendingFinalOutputCard).getByRole("heading", { name: /final output/i })).toBeVisible();
    expect(screen.queryByText(/no invocation trace spans captured/i)).not.toBeInTheDocument();
    expect(within(screen.getByTestId("runs-evidence-pane-nav")).queryByRole("button", { name: /trace/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/no invocations have been planned or persisted/i)).not.toBeInTheDocument();
    expect(screen.getByTestId("runs-step-1")).toHaveTextContent(/running/i);
    expect(screen.getByTestId("runs-step-1-executing-indicator")).toBeInTheDocument();
    expect(screen.getByTestId("runs-step-2")).toHaveTextContent(/skipped/i);
    expect(screen.queryByTestId("runs-step-2-completed-indicator")).not.toBeInTheDocument();
  });

  it("renders an explicit empty state when no steps exist", () => {
    useRunMock.mockReturnValue(queryResult(buildRun({ steps: [], traceId: null })));

    render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-empty-steps")).toHaveTextContent(/no steps have been planned/i);
  });

  it("shows queued runs as awaiting execution with zero progress", () => {
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          finishedAt: null,
          startedAt: null,
          status: "queued",
          steps: [],
          traceId: null,
        }),
      ),
    );

    render(<RunsDetailPage />);

    expect(screen.getByText(/awaiting execution/i)).toBeVisible();
    expect(screen.getByText(/run progress/i).parentElement).toHaveTextContent(/0%/i);
    expect(screen.queryByText(/still running/i)).not.toBeInTheDocument();
  });

  it("submits a full rerun with changed root parameters and navigates to the created run", async () => {
    searchParamsMock = new URLSearchParams("rerun=1");
    createRunRerunMutateAsyncMock.mockResolvedValue({ id: 98 });
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunRerunDraftMock.mockReturnValue(draftQueryResult(buildRerunDraft()));

    render(<RunsDetailPage />);

    expect(screen.getByRole("dialog", { name: /run snapshot again/i })).toBeVisible();
    expect(screen.getByText(/edits only root run parameters/i)).toBeVisible();
    expect(useRunRerunDraftMock).toHaveBeenLastCalledWith("42", { enabled: true });
    fireEvent.change(await screen.findByLabelText("Root run parameters JSON"), {
      target: { value: JSON.stringify({ ticker: "MSFT" }, null, 2) },
    });
    expect(screen.queryByLabelText("Target invocation input JSON")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("run-rerun-submit"));

    await waitFor(() =>
      expect(createRunRerunMutateAsyncMock).toHaveBeenCalledWith({
        runId: "42",
        payload: { parameters: { ticker: "MSFT" } },
      }),
    );
    expect(navigateMock).toHaveBeenCalledWith("/runs/98");
  });

  it("opens the fork dialog from invocation URL params and fetches the invocation draft", async () => {
    searchParamsMock = new URLSearchParams("fork=1&resumeStepIndex=1&invocationId=1001");
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunForkDraftMock.mockReturnValue(forkDraftQueryResult(buildForkDraft()));

    render(<RunsDetailPage />);

    expect(screen.getByRole("dialog", { name: /fork from analysis invocation/i })).toBeVisible();
    expect(useRunForkDraftMock).toHaveBeenLastCalledWith("42", 1001, { enabled: true });
    expect(screen.getByText(/resume at step 1/i)).toBeVisible();
    expect(screen.getByText(/invocation #1001/i)).toBeVisible();
    expect(await screen.findByLabelText("Target invocation input JSON")).toHaveValue(JSON.stringify({ ticker: "AAPL" }, null, 2));
    expect(screen.queryByLabelText("Root run parameters JSON")).not.toBeInTheDocument();
  });

  it("keeps the last fork presentation while Cancel closes the dialog", async () => {
    searchParamsMock = new URLSearchParams("fork=1&resumeStepIndex=1&invocationId=1001");
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunForkDraftMock.mockReturnValue(forkDraftQueryResult(buildForkDraft()));

    const { rerender } = render(<RunsDetailPage />);

    fireEvent.change(await screen.findByLabelText("Target invocation input JSON"), {
      target: { value: JSON.stringify({ ticker: "MSFT" }, null, 2) },
    });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    applyLatestSearchParamsUpdate("fork=1&resumeStepIndex=1&invocationId=1001");
    rerender(<RunsDetailPage />);

    expect(useRunForkDraftMock).toHaveBeenLastCalledWith("42", 1001, { enabled: false });
    expect(screen.queryByTestId("run-fork-invalid-target")).not.toBeInTheDocument();
    expect(screen.queryByText(/fork unavailable/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/invocation #undefined/i)).not.toBeInTheDocument();
  });

  it("resets canceled fork edits after the close animation completes and the dialog reopens", async () => {
    searchParamsMock = new URLSearchParams("fork=1&resumeStepIndex=1&invocationId=1001");
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunForkDraftMock.mockReturnValue(forkDraftQueryResult(buildForkDraft()));

    const { rerender } = render(<RunsDetailPage />);

    fireEvent.change(await screen.findByLabelText("Target invocation input JSON"), {
      target: { value: JSON.stringify({ ticker: "MSFT" }, null, 2) },
    });

    vi.useFakeTimers();
    try {
      fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
      applyLatestSearchParamsUpdate("fork=1&resumeStepIndex=1&invocationId=1001");
      rerender(<RunsDetailPage />);
      expect(useRunForkDraftMock).toHaveBeenLastCalledWith("42", 1001, { enabled: false });

      act(() => {
        vi.advanceTimersByTime(200);
      });

      searchParamsMock = new URLSearchParams("fork=1&resumeStepIndex=1&invocationId=1001");
      rerender(<RunsDetailPage />);

      expect(screen.getByLabelText("Target invocation input JSON")).toHaveValue(JSON.stringify({ ticker: "AAPL" }, null, 2));
    } finally {
      vi.useRealTimers();
    }
  });

  it("updates URL params when an explicit invocation fork action is clicked", () => {
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));

    render(<RunsDetailPage />);

    expect(screen.queryByTestId("runs-step-1-replay-entry")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("runs-invocation-1001-fork-entry"));

    expect(setSearchParamsMock).toHaveBeenCalledTimes(1);
    const updater = setSearchParamsMock.mock.calls[0][0] as (current: URLSearchParams) => URLSearchParams;
    const nextParams = updater(new URLSearchParams("panel=legacy&stepReplay=1&stepIndex=1"));
    expect(nextParams.get("panel")).toBe("legacy");
    expect(nextParams.get("fork")).toBe("1");
    expect(nextParams.get("resumeStepIndex")).toBe("1");
    expect(nextParams.get("invocationId")).toBe("1001");
    expect(nextParams.has("stepReplay")).toBe(false);
    expect(nextParams.has("stepIndex")).toBe(false);
  });

  it("uses invocation-level fork actions and no ambiguous step shortcut for mixed or multi-invocation steps", () => {
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
                  outputSchemaRef: { scope: "packageLocal", localId: 31, version: 1 },
                  outputSchemaId: 31,
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

    render(<RunsDetailPage />);

    expect(screen.queryByTestId("runs-step-1-replay-entry")).not.toBeInTheDocument();
    expect(screen.getByTestId("runs-invocation-1001-fork-entry")).toHaveTextContent(/fork from this invocation/i);
    expect(screen.getByTestId("runs-invocation-1003-fork-entry")).toHaveTextContent(/fork from this invocation/i);
    expect(screen.getByTestId("runs-operation-2001-outline-entry")).toHaveTextContent(/operation forks are not supported/i);
    expect(within(screen.getByTestId("runs-operation-2001-outline-entry")).queryByRole("button", { name: /fork from this invocation/i })).not.toBeInTheDocument();
  });

  it("does not expose fork actions for non-succeeded steps", () => {
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

    expect(screen.queryByRole("button", { name: /fork from this invocation/i })).not.toBeInTheDocument();
  });

  it("submits changed target invocation input and navigates to the created run", async () => {
    searchParamsMock = new URLSearchParams("fork=1&resumeStepIndex=1&invocationId=1001");
    createRunForkMutateAsyncMock.mockResolvedValue({ id: 99 });
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunForkDraftMock.mockReturnValue(forkDraftQueryResult(buildForkDraft()));

    render(<RunsDetailPage />);

    fireEvent.change(await screen.findByLabelText("Target invocation input JSON"), {
      target: { value: JSON.stringify({ ticker: "MSFT" }, null, 2) },
    });
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
    searchParamsMock = new URLSearchParams("fork=1&resumeStepIndex=1&invocationId=1001");
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunForkDraftMock.mockReturnValue(forkDraftQueryResult(buildForkDraft()));

    render(<RunsDetailPage />);

    fireEvent.change(await screen.findByLabelText("Target invocation input JSON"), {
      target: { value: "{not-json" },
    });

    expect(await screen.findByText(/target invocation input json must be valid json/i)).toBeVisible();
    expect(screen.getByTestId("run-fork-submit")).toBeDisabled();
    fireEvent.click(screen.getByTestId("run-fork-submit"));
    expect(createRunForkMutateAsyncMock).not.toHaveBeenCalled();
  });

  it("shows invalid URL fork state without fetching a draft", () => {
    searchParamsMock = new URLSearchParams("fork=1&resumeStepIndex=3&invocationId=1001");
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));

    render(<RunsDetailPage />);

    expect(screen.getByTestId("run-fork-invalid-target")).toHaveTextContent(/step 3 is not available/i);
    expect(useRunForkDraftMock).toHaveBeenLastCalledWith("42", 1001, { enabled: false });
  });
});
