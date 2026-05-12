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

const NOW = "2026-04-20T10:00:00Z";

function buildInvocation(overrides: Partial<RunAgentInvocationRead> = {}): RunAgentInvocationRead {
  return {
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

  it("renders normalized lineage, step origins, invocation origins, and trace linkage", () => {
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
            baseUrl: "https://ledger-deterministic-model.local/v1",
            connectionKind: "deterministic_smoke",
            hasApiKey: false,
            key: "smoke_model",
            modelId: "ledger-smoke",
            name: "Smoke Model",
            reasoningEffort: null,
            timeoutSeconds: 5,
          },
        ],
        workflowKey: "market_review",
        workflowPackageHash: "hash-abc",
        workflowPackageId: 7,
        workflowPackageKey: "market_review_package",
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

    render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-detail-page")).toBeInTheDocument();
    expect(screen.getByTestId("runs-detail-status")).toHaveTextContent(/succeeded/i);
    expect(screen.getByTestId("runs-detail-target-kind")).toHaveTextContent(/workflow package/i);
    expect(screen.getByTestId("runs-detail-target-identity")).toHaveTextContent(/market_review_package@2/i);
    expect(screen.getByRole("link", { name: /back to package/i })).toHaveAttribute("href", "/workflow-packages/7");
    expect(screen.getByTestId("runs-package-provenance")).toHaveTextContent(/market_review_package@2/i);
    expect(screen.getByTestId("runs-package-provenance")).toHaveTextContent(/market_review/i);
    expect(screen.getByTestId("runs-resolved-model-connection-primary_openai")).toHaveTextContent(/provider-backed/i);
    expect(screen.getByTestId("runs-resolved-model-connection-primary_openai")).toHaveTextContent(/provider credentials configured/i);
    expect(screen.getByTestId("runs-resolved-model-connection-smoke_model")).toHaveTextContent(/deterministic smoke/i);
    expect(screen.getByTestId("runs-resolved-model-connection-smoke_model")).toHaveTextContent(/offline deterministic smoke path/i);
    expect(screen.queryByRole("link", { name: /back to workflow/i })).not.toBeInTheDocument();
    expect(screen.getByTestId("runs-detail-rerun")).toHaveTextContent(/rerun/i);
    expect(screen.getByTestId("runs-detail-final-output")).toHaveTextContent(/normalized/i);
    expect(screen.getByTestId("runs-trace-linkage")).toHaveTextContent(/trace-42/i);
    expect(screen.getByTestId("runs-trace-path")).toHaveTextContent(
      /trace-42 -> step 1\/analysis\/span-1 -> step 2\/decision\/span-2/i,
    );
    expect(screen.getByText(/total tokens: 51/i)).toBeVisible();
    expect(screen.getByText(/inherited tokens: 21/i)).toBeVisible();
    expect(screen.getByText(/executed tokens: 30/i)).toBeVisible();
    expect(screen.queryByText(/total cost/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/inherited cost/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/executed cost/i)).not.toBeInTheDocument();

    const lineage = screen.getByTestId("runs-lineage-summary");
    expect(within(lineage).getByRole("link", { name: /run #41/i })).toHaveAttribute("href", "/runs/41");
    expect(lineage).toHaveTextContent(/lineage root/i);
    expect(lineage).toHaveTextContent(/run #40/i);
    expect(lineage).toHaveTextContent(/replay step/i);
    expect(lineage).toHaveTextContent(/step 1/i);
    expect(lineage).toHaveTextContent(/resume step/i);
    expect(lineage).toHaveTextContent(/step 2/i);
    expect(lineage).toHaveTextContent(/1 copied · 1 planned/i);
    expect(lineage).toHaveTextContent(/1 copied · 1 planned\/executed/i);

    expect(screen.getByTestId("runs-step-1")).toHaveTextContent(/copied origin/i);
    expect(screen.getByRole("link", { name: /run #41 step 1/i })).toHaveAttribute("href", "/runs/41#step-1");
    expect(screen.getByTestId("runs-step-1-slot-analysis")).toHaveTextContent(/output copied/i);
    expect(screen.getByRole("link", { name: /invocation #501/i })).toHaveAttribute("href", "/runs/41#invocation-501");

    const failedInvocationCard = screen.getByTestId("runs-step-2-slot-decision");
    expect(failedInvocationCard).toHaveTextContent(/input derived/i);
    expect(failedInvocationCard).toHaveTextContent(/output pending/i);
    expect(failedInvocationCard).toHaveTextContent(/tokens/i);
    expect(failedInvocationCard).toHaveTextContent(/30/i);
    expect(within(failedInvocationCard).queryByText(/^Cost$/i)).not.toBeInTheDocument();
    expect(screen.getByText("model_error")).toBeVisible();
    expect(screen.getByText("Provider failed")).toBeVisible();
    expect(screen.getByText(/rate_limit/i)).toBeVisible();
    expect(screen.getByRole("link", { name: /trace link · span-2/i })).toBeVisible();
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

    render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-graph-summary")).toHaveTextContent("Fanout analyst_fanout");
    expect(screen.getByTestId("runs-graph-summary")).toHaveTextContent("branch market");
    expect(screen.getByTestId("runs-graph-summary")).toHaveTextContent("Loop review_loop iteration 1");
    expect(screen.getByTestId("runs-step-1-slot-market")).toHaveTextContent("node market_analysis");
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

  it("keeps repeated fanouts separate across loop iterations", () => {
    useRunMock.mockReturnValue(
      queryResult(
        buildRun({
          steps: [
            buildStep({
              graphMetadata: { nodeKind: "fanout", fanoutId: "analyst_fanout", loopId: "review_loop", loopIteration: 1 },
              invocations: [
                buildInvocation({
                  graphMetadata: { nodeId: "market_analysis", nodeKind: "step", fanoutId: "analyst_fanout", branchId: "market", loopId: "review_loop", loopIteration: 1 },
                  slot: "market",
                }),
              ],
            }),
            buildStep({
              id: 102,
              index: 2,
              graphMetadata: { nodeKind: "fanout", fanoutId: "analyst_fanout", loopId: "review_loop", loopIteration: 2 },
              invocations: [
                buildInvocation({
                  graphMetadata: { nodeId: "market_analysis", nodeKind: "step", fanoutId: "analyst_fanout", branchId: "market", loopId: "review_loop", loopIteration: 2 },
                  id: 1002,
                  runStepId: 102,
                  slot: "market",
                  stepIndex: 2,
                }),
              ],
            }),
          ],
        }),
      ),
    );

    render(<RunsDetailPage />);

    const firstIterationGroup = screen.getByTestId("runs-graph-group-1");
    const secondIterationGroup = screen.getByTestId("runs-graph-group-2");
    expect(firstIterationGroup).toHaveTextContent("Fanout analyst_fanout · loop review_loop iteration 1");
    expect(firstIterationGroup).toHaveTextContent("Steps 1 · 1 invocation");
    expect(secondIterationGroup).toHaveTextContent("Fanout analyst_fanout · loop review_loop iteration 2");
    expect(secondIterationGroup).toHaveTextContent("Steps 2 · 1 invocation");
    expect(screen.queryByText(/Steps 1, 2 · 2 invocation/)).not.toBeInTheDocument();
  });

  it("omits graph grouping and memory artifact cards when metadata is absent", () => {
    useRunMock.mockReturnValue(queryResult(buildRun()));

    render(<RunsDetailPage />);

    expect(screen.queryByTestId("runs-graph-summary")).not.toBeInTheDocument();
    expect(screen.queryByTestId("runs-memory-artifacts")).not.toBeInTheDocument();
  });

  it("renders standalone agent target identity and span-only trace linkage", () => {
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
    expect(screen.getByTestId("runs-trace-path")).toHaveTextContent(/step 1\/result\/span-agent-1/i);
    expect(screen.getAllByText(/captured through invocation spans/i)).toHaveLength(2);
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

  it("handles empty, pending, skipped, and trace-less normalized state", () => {
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
              status: "pending",
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

    render(<RunsDetailPage />);

    expect(screen.getByText(/0 of 0 invocation\(s\) terminal/i)).toBeVisible();
    expect(screen.getByText(/no invocation trace spans captured/i)).toBeVisible();
    expect(screen.getAllByText(/no invocations have been planned or persisted/i)).toHaveLength(2);
    expect(screen.getByTestId("runs-step-1")).toHaveTextContent(/pending/i);
    expect(screen.getByTestId("runs-step-2")).toHaveTextContent(/skipped/i);
  });

  it("renders an explicit empty state when no steps exist", () => {
    useRunMock.mockReturnValue(queryResult(buildRun({ steps: [], traceId: null })));

    render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-empty-steps")).toHaveTextContent(/no steps have been planned/i);
    expect(screen.getByTestId("runs-trace-path")).toHaveTextContent(/span links: 0/i);
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
    const nextParams = updater(new URLSearchParams("panel=trace"));
    expect(nextParams.get("panel")).toBe("trace");
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
