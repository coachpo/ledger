import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import type { RunAgentInvocationRead, RunRead, RunRerunDraftRead, RunStepRead, RunStepReplayDraftRead } from "@/lib/types/run";

import { RunsDetailPage } from "./detail";

const createRunRerunMutateAsyncMock = vi.fn();
const createRunStepReplayMutateAsyncMock = vi.fn();
const navigateMock = vi.fn();
const setSearchParamsMock = vi.fn();
const useCreateRunRerunMock = vi.fn();
const useCreateRunStepReplayMock = vi.fn();
const useRunRerunDraftMock = vi.fn();
const useRunStepReplayDraftMock = vi.fn();
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
  useCreateRunRerun: () => useCreateRunRerunMock(),
  useCreateRunStepReplay: () => useCreateRunStepReplayMock(),
  useRun: () => useRunMock(),
  useRunRerunDraft: (...args: unknown[]) => useRunRerunDraftMock(...args),
  useRunStepReplayDraft: (...args: unknown[]) => useRunStepReplayDraftMock(...args),
}));

vi.mock("@xyflow/react", () => ({
  Background: () => <div data-testid="mock-react-flow-background" />,
  BackgroundVariant: { Dots: "dots" },
  Handle: () => <span data-testid="mock-react-flow-handle" />,
  MarkerType: { ArrowClosed: "arrowclosed" },
  Position: { Left: "left", Right: "right" },
  ReactFlow: ({
    children,
    edges = [],
    elementsSelectable,
    nodes = [],
    nodesConnectable,
    nodesDraggable,
    panOnDrag,
    zoomOnScroll,
    ...props
  }: {
    "aria-label"?: string;
    children?: ReactNode;
    edges?: Array<{ id: string; label?: ReactNode }>;
    elementsSelectable?: boolean;
    nodes?: Array<{
      data: { details: Array<{ label: string; value: ReactNode }>; eyebrow: string; testId: string; title: ReactNode };
      id: string;
    }>;
    nodesConnectable?: boolean;
    nodesDraggable?: boolean;
    panOnDrag?: boolean;
    zoomOnScroll?: boolean;
  }) => (
    <div
      aria-label={props["aria-label"]}
      data-readonly={String(
        nodesDraggable === false
        && nodesConnectable === false
        && elementsSelectable === false
        && panOnDrag === false
        && zoomOnScroll === false,
      )}
      data-testid="mock-react-flow"
    >
      {nodes.map((node) => (
        <div data-testid={node.data.testId} key={node.id}>
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
    targetVersion: 2,
    totalTokens: 51,
    traceId: "trace-42",
    updatedAt: "2026-04-20T10:00:04Z",
    ...overrides,
  };
}

function buildReplayableWorkflowRun(overrides: Partial<RunRead> = {}): RunRead {
  return buildRun({
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
    targetVersion: 2,
    ...overrides,
  };
}

function buildStepReplayDraft(overrides: Partial<RunStepReplayDraftRead> = {}): RunStepReplayDraftRead {
  return {
    parameters: { ticker: "AAPL" },
    replayStepIndex: 1,
    sourceRunId: 42,
    targetId: 7,
    targetKey: "market_review",
    targetKind: "workflow",
    targetVersion: 2,
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

function stepReplayDraftQueryResult(data: RunStepReplayDraftRead | undefined = undefined) {
  return draftQueryResult(data);
}

describe("RunsDetailPage", () => {
  beforeEach(() => {
    createRunRerunMutateAsyncMock.mockReset();
    createRunStepReplayMutateAsyncMock.mockReset();
    navigateMock.mockReset();
    searchParamsMock = new URLSearchParams();
    setSearchParamsMock.mockReset();
    useCreateRunRerunMock.mockReset();
    useCreateRunRerunMock.mockReturnValue({
      isPending: false,
      mutateAsync: createRunRerunMutateAsyncMock,
    });
    useCreateRunStepReplayMock.mockReset();
    useCreateRunStepReplayMock.mockReturnValue({
      isPending: false,
      mutateAsync: createRunStepReplayMutateAsyncMock,
    });
    useRunRerunDraftMock.mockReset();
    useRunRerunDraftMock.mockReturnValue(draftQueryResult<RunRerunDraftRead>());
    useRunStepReplayDraftMock.mockReset();
    useRunStepReplayDraftMock.mockReturnValue(stepReplayDraftQueryResult());
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
      targetVersion: 2,
      packageProvenance: {
        availability: { available: true },
        launchSnapshot: null,
        localResourceRefs: {},
        preflightSummary: { ready: true },
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
        workflowKey: "market_review",
        workflowPackageCompiledHash: "compiled-hash-abc",
        workflowPackageId: 7,
        workflowPackageKey: "market_review_package",
        workflowPackageManifestHash: "manifest-hash-abc",
        workflowPackageVersion: 2,
        workflowPackageVersionId: 70,
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
    expect(screen.getByTestId("runs-inspection-workspace")).toBeInTheDocument();
    expect(screen.getByTestId("runs-evidence-viewer")).toBeInTheDocument();
    expect(screen.getByTestId("runs-detail-status")).toHaveTextContent(/succeeded/i);
    expect(screen.getByTestId("runs-detail-target-kind")).toHaveTextContent(/workflow package/i);
    expect(screen.getByTestId("runs-detail-target-identity")).toHaveTextContent(/market_review_package@2/i);
    expect(screen.getByRole("link", { name: /back to package/i })).toHaveAttribute("href", "/workflow-packages/7");
    expect(screen.queryByRole("link", { name: /back to workflow/i })).not.toBeInTheDocument();
    expect(screen.getByTestId("runs-detail-rerun")).toHaveTextContent(/rerun/i);
    const finalOutput = screen.getByTestId("runs-detail-final-output");
    expect(finalOutput).toHaveTextContent(/normalized/i);
    expect(finalOutput).toHaveClass("rounded-md", "border", "bg-muted/20", "p-3", "text-sm");
    expect(finalOutput).not.toHaveClass("overflow-hidden", "text-xs");
    expect(screen.getByRole("heading", { name: /final output/i })).toHaveClass("text-base", "font-medium", "leading-none");
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

    const stepOneButton = within(screen.getByTestId("runs-step-1")).getByRole("button", { name: /step 1/i });
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
    expect(runInput).toHaveClass("rounded-md", "border", "bg-muted/20", "p-3", "text-sm");
    expect(runInput).not.toHaveClass("overflow-hidden", "text-xs");
    expect(screen.getByRole("heading", { name: /^run input$/i })).toHaveClass("text-base", "font-medium", "leading-none");
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
    expect(within(stepLineageDiagram).getByTestId("mock-react-flow")).toHaveAttribute("data-readonly", "true");
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
    const provenanceRender = render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-package-provenance")).toHaveTextContent(/market_review_package@2/i);
    expect(screen.getByTestId("runs-package-provenance")).toHaveTextContent(/market_review/i);
    expect(screen.getByTestId("runs-package-provenance")).toHaveTextContent(/manifest-hash-abc/i);
    expect(screen.getByTestId("runs-package-provenance")).toHaveTextContent(/compiled-hash-abc/i);
    expect(screen.getByTestId("runs-resolved-model-connection-primary_openai")).toHaveTextContent(/provider-backed/i);
    expect(screen.getByTestId("runs-resolved-model-connection-primary_openai")).toHaveTextContent(/provider credentials configured/i);
    expect(screen.getByTestId("runs-resolved-model-connection-smoke_model")).toHaveTextContent(/deterministic smoke/i);
    expect(screen.getByTestId("runs-resolved-model-connection-smoke_model")).toHaveTextContent(/offline deterministic smoke path/i);

    provenanceRender.unmount();
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
    expect(within(runLineageDiagram).getByTestId("mock-react-flow")).toHaveAttribute("data-readonly", "true");
    expect(within(lineage).getByTestId("runs-lineage-node-root")).toHaveTextContent(/lineage root/i);
    expect(within(lineage).getByTestId("runs-lineage-node-root")).toHaveTextContent(/run #40/i);
    expect(within(lineage).getByRole("link", { name: /run #41/i })).toHaveAttribute("href", "/runs/41");
    expect(within(lineage).getByTestId("runs-lineage-node-source")).toHaveTextContent(/source run/i);
    expect(within(lineage).getByTestId("runs-lineage-node-source")).toHaveTextContent(/replay step/i);
    expect(within(lineage).getByTestId("runs-lineage-node-source")).toHaveTextContent(/step 1/i);
    expect(within(lineage).getByTestId("runs-lineage-node-current")).toHaveTextContent(/resume step/i);
    expect(within(lineage).getByTestId("runs-lineage-node-current")).toHaveTextContent(/step 2/i);
    expect(within(lineage).getByTestId("runs-lineage-node-current")).toHaveTextContent(/1 copied · 1 planned/i);
    expect(within(lineage).getByTestId("runs-lineage-node-current")).toHaveTextContent(/1 copied · 1 planned\/executed/i);
    expect(within(runLineageDiagram).getByTestId("mock-react-flow-edge-root-source")).toHaveTextContent(/lineage root/i);
    expect(within(runLineageDiagram).getByTestId("mock-react-flow-edge-source-current")).toHaveTextContent(/replay \/ resume/i);

    lineageRender.unmount();
    searchParamsMock = new URLSearchParams("inspect=invocation:1002&pane=error");
    render(<RunsDetailPage />);
    expect(screen.getByText("model_error")).toBeVisible();
    expect(screen.getByText("Provider failed")).toBeVisible();
    expect(screen.getByText(/rate_limit/i)).toBeVisible();
  });

  it("groups graph metadata and renders memory artifact audit report links", () => {
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          memoryArtifacts: [
            {
              memoryId: "mem_701",
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
    searchParamsMock = new URLSearchParams("inspect=memory:mem_701");
    render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-memory-artifacts")).toBeInTheDocument();
    const artifact = screen.getByTestId("runs-memory-artifact-mem_701");
    expect(artifact).toHaveTextContent("AAPL decision memory");
    expect(artifact).toHaveTextContent(/pending/i);
    expect(artifact).toHaveTextContent(/portfolio_manager@3/i);
    expect(artifact).toHaveTextContent(/workflow market_review@2/i);
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
              memoryId: "mem_702",
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

    searchParamsMock = new URLSearchParams("inspect=memory:mem_702");
    render(<RunsDetailPage />);

    const artifact = screen.getByTestId("runs-memory-artifact-mem_702");
    expect(artifact).toHaveTextContent("AAPL risk memory");
    expect(artifact).toHaveTextContent(/active/i);
    expect(artifact).toHaveTextContent(/risk_manager@1/i);
    expect(artifact).toHaveTextContent(/workflow market_review/i);
    expect(artifact).toHaveTextContent(/run #42/i);
    expect(within(artifact).queryByRole("link", { name: /open report/i })).not.toBeInTheDocument();
    expect(within(artifact).queryByRole("link", { name: /download/i })).not.toBeInTheDocument();
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
    expect(within(stepLineageDiagram).getByTestId("mock-react-flow")).toHaveAttribute("data-readonly", "true");
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
          targetVersion: 9,
          totalTokens: 18,
          traceId: null,
        }),
      ),
    );

    render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-detail-target-kind")).toHaveTextContent(/agent/i);
    expect(screen.getByTestId("runs-detail-target-identity")).toHaveTextContent(/macro_agent@9/i);
    expect(screen.getByText(/target id: 12/i)).toBeVisible();
    expect(screen.getByText(/standalone agent execution/i)).toBeVisible();
    expect(screen.getByTestId("runs-step-1-trace-summary")).toHaveTextContent(/result\/span-agent-1/i);
    expect(screen.getByTestId("runs-step-1-completed-indicator")).toBeInTheDocument();
    expect(screen.queryByText(/captured through invocation spans/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /back to workflow/i })).not.toBeInTheDocument();
    expect(screen.queryByTestId("runs-detail-rerun")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /replay step/i })).not.toBeInTheDocument();
  });

  it("shows agent-run URL replay state as unavailable without fetching a draft", () => {
    searchParamsMock = new URLSearchParams("stepReplay=1&stepIndex=1");
    useRunMock.mockReturnValue(queryResult(buildRun({ targetKind: "agent" })));

    render(<RunsDetailPage />);

    expect(screen.queryByRole("button", { name: /replay step/i })).not.toBeInTheDocument();
    expect(screen.getByTestId("run-step-replay-invalid-step")).toHaveTextContent(/only available for workflow runs/i);
    expect(useRunStepReplayDraftMock).toHaveBeenLastCalledWith("42", 1, { enabled: false });
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
    expect(screen.getByTestId("runs-detail-final-output")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /final output/i })).toBeVisible();
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

  it("submits a full rerun with changed parameters and navigates to the created run", async () => {
    searchParamsMock = new URLSearchParams("rerun=1");
    createRunRerunMutateAsyncMock.mockResolvedValue({ id: 98 });
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunRerunDraftMock.mockReturnValue(draftQueryResult(buildRerunDraft()));

    render(<RunsDetailPage />);

    expect(screen.getByRole("dialog", { name: /rerun draft/i })).toBeVisible();
    expect(useRunRerunDraftMock).toHaveBeenLastCalledWith("42", { enabled: true });
    fireEvent.change(await screen.findByLabelText("Rerun parameters JSON"), {
      target: { value: JSON.stringify({ ticker: "MSFT" }, null, 2) },
    });
    fireEvent.click(screen.getByTestId("run-rerun-submit"));

    await waitFor(() =>
      expect(createRunRerunMutateAsyncMock).toHaveBeenCalledWith({
        runId: "42",
        payload: { parameters: { ticker: "MSFT" } },
      }),
    );
    expect(navigateMock).toHaveBeenCalledWith("/runs/98");
    expect(screen.queryByText(/fork/i)).not.toBeInTheDocument();
  });

  it("opens the step replay dialog from URL params and fetches the draft for a succeeded workflow step", async () => {
    searchParamsMock = new URLSearchParams("stepReplay=1&stepIndex=1");
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunStepReplayDraftMock.mockReturnValue(stepReplayDraftQueryResult(buildStepReplayDraft()));

    render(<RunsDetailPage />);

    expect(screen.getByRole("dialog", { name: /step replay draft/i })).toBeVisible();
    expect(useRunStepReplayDraftMock).toHaveBeenLastCalledWith("42", 1, { enabled: true });
    expect(await screen.findByLabelText("Step replay parameters JSON")).toHaveValue(JSON.stringify({ ticker: "AAPL" }, null, 2));
  });

  it("updates URL params when a succeeded workflow step replay action is clicked", () => {
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));

    render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-step-2-replay-entry")).toBeVisible();
    fireEvent.click(within(screen.getByTestId("runs-step-1-replay-entry")).getByRole("button", { name: /replay step/i }));

    expect(setSearchParamsMock).toHaveBeenCalledTimes(1);
    const updater = setSearchParamsMock.mock.calls[0][0] as (current: URLSearchParams) => URLSearchParams;
    const nextParams = updater(new URLSearchParams("panel=legacy"));
    expect(nextParams.get("panel")).toBe("legacy");
    expect(nextParams.get("stepReplay")).toBe("1");
    expect(nextParams.get("stepIndex")).toBe("1");
  });

  it("does not expose step replay actions for non-succeeded steps", () => {
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          steps: [
            buildStep({ status: "pending" }),
            buildStep({ id: 102, index: 2, status: "failed" }),
            buildStep({ id: 103, index: 3, status: "skipped" }),
          ],
        }),
      ),
    );

    render(<RunsDetailPage />);

    expect(screen.queryByRole("button", { name: /replay step/i })).not.toBeInTheDocument();
  });

  it("submits changed replay parameters and navigates to the created run", async () => {
    searchParamsMock = new URLSearchParams("stepReplay=1&stepIndex=1");
    createRunStepReplayMutateAsyncMock.mockResolvedValue({ id: 99 });
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunStepReplayDraftMock.mockReturnValue(stepReplayDraftQueryResult(buildStepReplayDraft()));

    render(<RunsDetailPage />);

    fireEvent.change(await screen.findByLabelText("Step replay parameters JSON"), {
      target: { value: JSON.stringify({ ticker: "MSFT" }, null, 2) },
    });
    fireEvent.click(screen.getByTestId("run-step-replay-submit"));

    await waitFor(() =>
      expect(createRunStepReplayMutateAsyncMock).toHaveBeenCalledWith({
        runId: "42",
        payload: {
          parameters: { ticker: "MSFT" },
          replayStepIndex: 1,
        },
      }),
    );
    expect(navigateMock).toHaveBeenCalledWith("/runs/99");
    expect(screen.queryByText(/fork/i)).not.toBeInTheDocument();
  });

  it("blocks submit and shows precise JSON parse errors", async () => {
    searchParamsMock = new URLSearchParams("stepReplay=1&stepIndex=1");
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));
    useRunStepReplayDraftMock.mockReturnValue(stepReplayDraftQueryResult(buildStepReplayDraft()));

    render(<RunsDetailPage />);

    fireEvent.change(await screen.findByLabelText("Step replay parameters JSON"), {
      target: { value: "{not-json" },
    });

    expect(await screen.findByText(/replay parameters json must be valid json/i)).toBeVisible();
    expect(screen.getByTestId("run-step-replay-submit")).toBeDisabled();
    fireEvent.click(screen.getByTestId("run-step-replay-submit"));
    expect(createRunStepReplayMutateAsyncMock).not.toHaveBeenCalled();
  });

  it("shows invalid URL step replay state without fetching a draft", () => {
    searchParamsMock = new URLSearchParams("stepReplay=1&stepIndex=3");
    useRunMock.mockReturnValue(queryResult(buildReplayableWorkflowRun()));

    render(<RunsDetailPage />);

    expect(screen.getByTestId("run-step-replay-invalid-step")).toHaveTextContent(/step 3 is not available/i);
    expect(useRunStepReplayDraftMock).toHaveBeenLastCalledWith("42", 3, { enabled: false });
  });
});
