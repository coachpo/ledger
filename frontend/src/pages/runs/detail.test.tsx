import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import type { RunAgentInvocationRead, RunForkDraftRead, RunRead, RunStepRead } from "@/lib/types/run";

import { RunsDetailPage } from "./detail";

const createRunForkMutateAsyncMock = vi.fn();
const navigateMock = vi.fn();
const setSearchParamsMock = vi.fn();
const useCreateRunForkMock = vi.fn();
const useRunForkDraftMock = vi.fn();
const useRunMock = vi.fn();
let searchParamsMock = new URLSearchParams();

vi.mock("react-router", () => ({
  Link: ({ children, to }: { children: ReactNode; to: string }) => <a href={to}>{children}</a>,
  useNavigate: () => navigateMock,
  useParams: () => ({ runId: "42" }),
  useSearchParams: () => [searchParamsMock, setSearchParamsMock],
}));

vi.mock("@/hooks/use-runs", () => ({
  useCreateRunFork: () => useCreateRunForkMock(),
  useRun: () => useRunMock(),
  useRunForkDraft: (...args: unknown[]) => useRunForkDraftMock(...args),
}));

const NOW = "2026-04-20T10:00:00Z";

function buildInvocation(overrides: Partial<RunAgentInvocationRead> = {}): RunAgentInvocationRead {
  return {
    agentId: 11,
    agentKey: "research_agent",
    agentVersion: 3,
    costUsd: "0.02000000",
    createdAt: NOW,
    durationMs: 8,
    errorCode: null,
    errorDetails: [],
    errorMessage: null,
    finishedAt: "2026-04-20T10:00:03Z",
    id: 1001,
    inputMode: "wired",
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
    executedCostUsd: "0.05000000",
    executedTokens: 51,
    finalOutput: { summary: "All clear" },
    finishedAt: "2026-04-20T10:00:04Z",
    forkedFromStepIndex: null,
    id: 42,
    inheritedCostUsd: "0.00000000",
    inheritedTokens: 0,
    input: { ticker: "AAPL" },
    lineageRootRunId: null,
    resumeStepIndex: 1,
    sourceRunId: null,
    startedAt: NOW,
    status: "succeeded",
    steps: [buildStep()],
    targetId: 7,
    targetKey: "market_review",
    targetKind: "workflow",
    targetVersion: 2,
    totalCostUsd: "0.05000000",
    totalTokens: 51,
    traceId: "trace-42",
    updatedAt: "2026-04-20T10:00:04Z",
    ...overrides,
  };
}

function buildForkableWorkflowRun(overrides: Partial<RunRead> = {}): RunRead {
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

function buildForkDraft(overrides: Partial<RunForkDraftRead> = {}): RunForkDraftRead {
  return {
    forkStepIndex: 1,
    input: { ticker: "AAPL" },
    sourceRunId: 42,
    steps: [
      {
        index: 1,
        invocations: [
          {
            agentKey: "research_agent",
            output: { summary: "analysis" },
            resolvedInput: { ticker: "AAPL" },
            slot: "analysis",
            sourceInvocationId: 501,
            stepIndex: 1,
          },
        ],
        sourceRunStepId: 101,
      },
    ],
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

function forkDraftQueryResult(data: RunForkDraftRead | undefined = undefined) {
  return {
    data,
    error: null,
    isError: false,
    isPending: false,
  };
}

describe("RunsDetailPage", () => {
  beforeEach(() => {
    createRunForkMutateAsyncMock.mockReset();
    navigateMock.mockReset();
    searchParamsMock = new URLSearchParams();
    setSearchParamsMock.mockReset();
    useCreateRunForkMock.mockReset();
    useCreateRunForkMock.mockReturnValue({
      isPending: false,
      mutateAsync: createRunForkMutateAsyncMock,
    });
    useRunForkDraftMock.mockReset();
    useRunForkDraftMock.mockReturnValue(forkDraftQueryResult());
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
      costUsd: "0.03000000",
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
      executedCostUsd: "0.03000000",
      executedTokens: 30,
      finalOutput: { summary: "All clear", source: "normalized" },
      forkedFromStepIndex: 1,
      inheritedCostUsd: "0.02000000",
      inheritedTokens: 21,
      lineageRootRunId: 40,
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
    expect(screen.getByTestId("runs-detail-target-kind")).toHaveTextContent(/workflow/i);
    expect(screen.getByTestId("runs-detail-target-identity")).toHaveTextContent(/market_review@2/i);
    expect(screen.getByTestId("runs-detail-final-output")).toHaveTextContent(/normalized/i);
    expect(screen.getByTestId("runs-trace-linkage")).toHaveTextContent(/trace-42/i);
    expect(screen.getByTestId("runs-trace-path")).toHaveTextContent(
      /trace-42 -> step 1\/analysis\/span-1 -> step 2\/decision\/span-2/i,
    );

    const lineage = screen.getByTestId("runs-lineage-summary");
    expect(within(lineage).getByRole("link", { name: /run #41/i })).toHaveAttribute("href", "/runs/41");
    expect(lineage).toHaveTextContent(/lineage root/i);
    expect(lineage).toHaveTextContent(/run #40/i);
    expect(lineage).toHaveTextContent(/forked from step/i);
    expect(lineage).toHaveTextContent(/step 1/i);
    expect(lineage).toHaveTextContent(/resume step/i);
    expect(lineage).toHaveTextContent(/step 2/i);
    expect(lineage).toHaveTextContent(/1 copied · 1 planned/i);
    expect(lineage).toHaveTextContent(/1 copied · 1 planned\/executed/i);

    expect(screen.getByTestId("runs-step-1")).toHaveTextContent(/copied origin/i);
    expect(screen.getByRole("link", { name: /run #41 step 1/i })).toHaveAttribute("href", "/runs/41#step-1");
    expect(screen.getByTestId("runs-step-1-slot-analysis")).toHaveTextContent(/output copied/i);
    expect(screen.getByRole("link", { name: /invocation #501/i })).toHaveAttribute("href", "/runs/41#invocation-501");

    expect(screen.getByTestId("runs-step-2-slot-decision")).toHaveTextContent(/input derived/i);
    expect(screen.getByTestId("runs-step-2-slot-decision")).toHaveTextContent(/output pending/i);
    expect(screen.getByText("model_error")).toBeVisible();
    expect(screen.getByText("Provider failed")).toBeVisible();
    expect(screen.getByText(/rate_limit/i)).toBeVisible();
    expect(screen.getByRole("link", { name: /trace link · span-2/i })).toBeVisible();
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
                  costUsd: "0.01500000",
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
          totalCostUsd: "0.01500000",
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
    expect(screen.queryByRole("button", { name: /fork step/i })).not.toBeInTheDocument();
  });

  it("shows agent-run URL fork state as unavailable without fetching a draft", () => {
    searchParamsMock = new URLSearchParams("fork=1&forkStepIndex=1");
    useRunMock.mockReturnValue(queryResult(buildRun({ targetKind: "agent" })));

    render(<RunsDetailPage />);

    expect(screen.queryByRole("button", { name: /fork step/i })).not.toBeInTheDocument();
    expect(screen.getByTestId("run-fork-invalid-step")).toHaveTextContent(/only available for workflow runs/i);
    expect(useRunForkDraftMock).toHaveBeenLastCalledWith("42", 1, { enabled: false });
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

  it("opens the fork dialog from URL params and fetches the draft for a succeeded mid-workflow step", async () => {
    searchParamsMock = new URLSearchParams("fork=1&forkStepIndex=1");
    useRunMock.mockReturnValue(queryResult(buildForkableWorkflowRun()));
    useRunForkDraftMock.mockReturnValue(forkDraftQueryResult(buildForkDraft()));

    render(<RunsDetailPage />);

    expect(screen.getByRole("dialog", { name: /fork run draft/i })).toBeVisible();
    expect(useRunForkDraftMock).toHaveBeenLastCalledWith("42", 1, { enabled: true });
    expect(await screen.findByLabelText("Fork draft run input JSON")).toHaveValue(JSON.stringify({ ticker: "AAPL" }, null, 2));
    expect(screen.getByTestId("run-fork-invocation-1-analysis")).toHaveTextContent(/copied from invocation #501/i);
  });

  it("updates URL params when a succeeded mid-workflow step fork action is clicked", () => {
    useRunMock.mockReturnValue(queryResult(buildForkableWorkflowRun()));

    render(<RunsDetailPage />);
    expect(screen.queryByTestId("runs-step-2-fork-entry")).not.toBeInTheDocument();
    fireEvent.click(within(screen.getByTestId("runs-step-1-fork-entry")).getByRole("button", { name: /fork step/i }));

    expect(setSearchParamsMock).toHaveBeenCalledTimes(1);
    const updater = setSearchParamsMock.mock.calls[0][0] as (current: URLSearchParams) => URLSearchParams;
    const nextParams = updater(new URLSearchParams("panel=trace"));
    expect(nextParams.get("panel")).toBe("trace");
    expect(nextParams.get("fork")).toBe("1");
    expect(nextParams.get("forkStepIndex")).toBe("1");
  });

  it("does not expose fork actions for non-succeeded steps", () => {
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

    expect(screen.queryByRole("button", { name: /fork step/i })).not.toBeInTheDocument();
  });

  it("submits only changed draft JSON and navigates to the created run", async () => {
    searchParamsMock = new URLSearchParams("fork=1&forkStepIndex=1");
    createRunForkMutateAsyncMock.mockResolvedValue({ id: 99 });
    useRunMock.mockReturnValue(queryResult(buildForkableWorkflowRun()));
    useRunForkDraftMock.mockReturnValue(forkDraftQueryResult(buildForkDraft()));

    render(<RunsDetailPage />);

    fireEvent.change(await screen.findByLabelText("Fork draft run input JSON"), {
      target: { value: JSON.stringify({ ticker: "MSFT" }, null, 2) },
    });
    fireEvent.change(screen.getByLabelText("Fork draft resolved input JSON"), {
      target: { value: JSON.stringify({ ticker: "MSFT" }, null, 2) },
    });
    fireEvent.change(screen.getByLabelText("Fork draft output JSON"), {
      target: { value: JSON.stringify({ summary: "updated analysis" }, null, 2) },
    });
    fireEvent.click(screen.getByTestId("run-fork-submit"));

    await waitFor(() =>
      expect(createRunForkMutateAsyncMock).toHaveBeenCalledWith({
        runId: "42",
        payload: {
          forkStepIndex: 1,
          input: { ticker: "MSFT" },
          invocationEdits: [
            {
              output: { summary: "updated analysis" },
              resolvedInput: { ticker: "MSFT" },
              slot: "analysis",
              stepIndex: 1,
            },
          ],
        },
      }),
    );
    expect(navigateMock).toHaveBeenCalledWith("/runs/99");
  });

  it("blocks submit and shows precise JSON parse errors", async () => {
    searchParamsMock = new URLSearchParams("fork=1&forkStepIndex=1");
    useRunMock.mockReturnValue(queryResult(buildForkableWorkflowRun()));
    useRunForkDraftMock.mockReturnValue(forkDraftQueryResult(buildForkDraft()));

    render(<RunsDetailPage />);

    fireEvent.change(await screen.findByLabelText("Fork draft run input JSON"), {
      target: { value: "{not-json" },
    });

    expect(await screen.findByText(/run input json must be valid json/i)).toBeVisible();
    expect(screen.getByTestId("run-fork-submit")).toBeDisabled();
    fireEvent.click(screen.getByTestId("run-fork-submit"));
    expect(createRunForkMutateAsyncMock).not.toHaveBeenCalled();
  });

  it("shows final-step URL fork state as unavailable without fetching a draft", () => {
    searchParamsMock = new URLSearchParams("fork=1&forkStepIndex=2");
    useRunMock.mockReturnValue(queryResult(buildForkableWorkflowRun()));

    render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-step-1-fork-entry")).toBeVisible();
    expect(screen.queryByTestId("runs-step-2-fork-entry")).not.toBeInTheDocument();
    expect(screen.getByTestId("run-fork-invalid-step")).toHaveTextContent(/final workflow steps cannot be forked/i);
    expect(useRunForkDraftMock).toHaveBeenLastCalledWith("42", 2, { enabled: false });
  });

  it("shows invalid URL fork state without fetching a draft", () => {
    searchParamsMock = new URLSearchParams("fork=1&forkStepIndex=3");
    useRunMock.mockReturnValue(queryResult(buildForkableWorkflowRun()));

    render(<RunsDetailPage />);

    expect(screen.getByTestId("run-fork-invalid-step")).toHaveTextContent(/step 3 is not available/i);
    expect(useRunForkDraftMock).toHaveBeenLastCalledWith("42", 3, { enabled: false });
  });
});
