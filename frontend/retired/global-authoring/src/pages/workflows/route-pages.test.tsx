import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WorkflowDetailPage } from "./detail";
import { WorkflowLaunchPage } from "./launch";

const navigateMock = vi.fn();
const paramsMock: { workflowId?: string } = { workflowId: "88" };
const createRunRerunMutateAsyncMock = vi.fn();
const createWorkflowLaunchMock = vi.fn();
const useCreateRunRerunMock = vi.fn();
const useRunRerunDraftMock = vi.fn();
const useWorkflowMock = vi.fn();
const useWorkflowLaunchMock = vi.fn();
const useWorkflowVersionsMock = vi.fn();
const useRunsMock = vi.fn();
const toastErrorMock = vi.fn();
const toastSuccessMock = vi.fn();

const workflow = {
  id: 88,
  aggregateBudgetUsd: "1.25000000",
  createdAt: "2026-04-20T10:00:00Z",
  description: "Reviews market context.",
  inputSchema: {},
  key: "market_review",
  manifestApiVersion: "ledger.workflow/v1",
  manifestSource: "apiVersion: ledger.workflow/v1",
  name: "Market Review",
  outputSpec: {
    agentId: 1,
    agentKey: "research_agent",
    agentVersion: 3,
    kind: "slot",
    outputSchemaId: 11,
    outputSchemaVersion: 1,
    slot: "decision",
    stepIndex: 1,
  },
  status: "published",
  steps: [{ agents: [], index: 1 }],
  updatedAt: "2026-04-20T10:00:00Z",
  version: 2,
};

const workflowRun = {
  id: 904,
  finishedAt: null,
  queuedAt: "2026-04-29T10:00:00Z",
  startedAt: null,
  status: "queued",
  targetId: 88,
  targetKey: "market_review",
  targetKind: "workflow",
  targetVersion: 2,
  totalTokens: 0,
  traceId: null,
};

const launchMetadata = {
  workflowId: 88,
  description: "Reviews market context.",
  inputSchema: {
    additionalProperties: false,
    properties: {
      limit: { description: "Optional cap.", title: "Risk Limit", type: "number" },
      symbol: { description: "Portfolio symbol.", title: "Portfolio Symbol", type: "string" },
    },
    required: ["symbol"],
    type: "object",
  },
  key: "market_review",
  name: "Market Review",
  version: 2,
};

vi.mock("react-router", () => ({
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
  useNavigate: () => navigateMock,
  useParams: () => paramsMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => toastErrorMock(...args),
    success: (...args: unknown[]) => toastSuccessMock(...args),
  },
}));

vi.mock("@/hooks/use-runs", () => ({
  useCreateRunRerun: () => useCreateRunRerunMock(),
  useRunRerunDraft: (...args: unknown[]) => useRunRerunDraftMock(...args),
  useRuns: (...args: unknown[]) => useRunsMock(...args),
}));

vi.mock("@/hooks/use-workflows", () => ({
  useCreateWorkflowLaunch: () => ({ isPending: false, mutateAsync: createWorkflowLaunchMock }),
  useWorkflow: (...args: unknown[]) => useWorkflowMock(...args),
  useWorkflowLaunch: (...args: unknown[]) => useWorkflowLaunchMock(...args),
  useWorkflowVersions: (...args: unknown[]) => useWorkflowVersionsMock(...args),
}));

describe("workflow route pages", () => {
  beforeEach(() => {
    paramsMock.workflowId = "88";
    createRunRerunMutateAsyncMock.mockReset();
    navigateMock.mockReset();
    createWorkflowLaunchMock.mockReset();
    useCreateRunRerunMock.mockReset();
    useCreateRunRerunMock.mockReturnValue({ isPending: false, mutateAsync: createRunRerunMutateAsyncMock });
    useRunRerunDraftMock.mockReset();
    useRunRerunDraftMock.mockReturnValue({
      data: { parameters: { symbol: "AAPL" }, sourceRunId: 904, targetId: 88, targetKey: "market_review", targetKind: "workflow", targetVersion: 2 },
      error: null,
      isError: false,
      isPending: false,
    });
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    useWorkflowMock.mockReturnValue({ data: workflow, error: null, isError: false, isPending: false });
    useRunsMock.mockReturnValue({
      data: { items: [workflowRun] },
      error: null,
      isError: false,
      isFetching: false,
      isPending: false,
      refetch: vi.fn(),
    });
    useWorkflowVersionsMock.mockReturnValue({
      data: { items: [{ ...workflow, inputSchema: launchMetadata.inputSchema }] },
      error: null,
      isError: false,
      isPending: false,
    });
    useWorkflowLaunchMock.mockReturnValue({
      data: launchMetadata,
      error: null,
      isError: false,
      isFetching: false,
      isPending: false,
    });
  });

  it("renders workflow metadata and scoped run history", () => {
    render(<WorkflowDetailPage />);

    expect(screen.getByTestId("workflow-detail-page")).toHaveTextContent("Market Review");
    expect(screen.getByTestId("workflow-run-history")).toHaveTextContent("Run #904");
    expect(screen.getByTestId("workflow-run-history-row-904")).toHaveTextContent("queued");
    expect(screen.getByTestId("workflow-run-history-row-904")).toHaveTextContent(/total tokens: 0/i);
    expect(screen.queryByText(/total cost/i)).not.toBeInTheDocument();
    expect(useRunsMock).toHaveBeenCalledWith(
      { limit: 20, targetId: 88, targetKind: "workflow" },
      { refetchInterval: 2000 },
    );

    expect(screen.getByTestId("workflow-run-history-rerun-904")).toHaveTextContent(/rerun/i);

    fireEvent.click(screen.getByTestId("workflow-detail-run"));
    expect(navigateMock).toHaveBeenCalledWith("/workflows/88/run");
  });

  it("opens workflow history rerun and creates a distinct run", async () => {
    createRunRerunMutateAsyncMock.mockResolvedValue({ id: 905, status: "queued" });

    render(<WorkflowDetailPage />);

    fireEvent.click(screen.getByTestId("workflow-run-history-rerun-904"));
    expect(screen.getByRole("dialog", { name: /rerun draft/i })).toBeVisible();
    fireEvent.change(await screen.findByLabelText("Rerun parameters JSON"), {
      target: { value: JSON.stringify({ symbol: "MSFT" }, null, 2) },
    });
    fireEvent.click(screen.getByTestId("run-rerun-submit"));

    await waitFor(() =>
      expect(createRunRerunMutateAsyncMock).toHaveBeenCalledWith({
        runId: "904",
        payload: { parameters: { symbol: "MSFT" } },
      }),
    );
    expect(navigateMock).toHaveBeenCalledWith("/runs/905");
    expect(screen.queryByText(/fork/i)).not.toBeInTheDocument();
  });

  it("submits workflow launch parameters and navigates to run detail", async () => {
    createWorkflowLaunchMock.mockResolvedValue({ id: 904, status: "queued" });

    render(<WorkflowLaunchPage />);

    await waitFor(() => expect(screen.getByTestId("workflow-launch-page")).toBeVisible());
    expect(screen.getByRole("heading", { name: /run market review/i })).toBeVisible();
    expect(screen.getByTestId("workflow-launch-back")).toHaveTextContent(/workflow detail/i);
    expect(screen.getByTestId("workflow-launch-version-select")).toHaveTextContent("v2");
    expect(screen.queryByText(/fork/i)).not.toBeInTheDocument();
    const rawParameters = screen.getByLabelText("Exact raw workflow launch parameters JSON") as HTMLTextAreaElement;
    await waitFor(() => expect(rawParameters).toHaveValue(JSON.stringify({ symbol: "example" }, null, 2)));
    expect(screen.getByLabelText("Portfolio Symbol")).toHaveValue("example");
    expect(screen.getByText("Portfolio symbol.")).toBeVisible();
    expect(screen.getByText("Optional cap.")).toBeVisible();
    expect(screen.getByRole("button", { name: /add field/i })).toBeVisible();

    fireEvent.click(screen.getByTestId("workflow-launch-submit"));

    await waitFor(() => expect(createWorkflowLaunchMock).toHaveBeenCalledTimes(1));
    expect(createWorkflowLaunchMock).toHaveBeenCalledWith({
      payload: { parameters: { symbol: "example" }, version: 2 },
      workflowId: "88",
    });
    expect(toastSuccessMock).toHaveBeenCalledWith("Workflow run queued");
    expect(navigateMock).toHaveBeenCalledWith("/runs/904");
  });
});
