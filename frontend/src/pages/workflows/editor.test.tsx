import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WorkflowsEditorPage } from "./editor";

const navigateMock = vi.fn();
const paramsMock: { workflowId?: string } = {};
const createWorkflowMock = vi.fn();
const updateWorkflowMock = vi.fn();
const createWorkflowRunMock = vi.fn();
const toastErrorMock = vi.fn();
const toastSuccessMock = vi.fn();

const agents = [
  {
    id: 1,
    budgetUsd: "0.50000000",
    createdAt: "2026-04-20T10:00:00Z",
    description: "Researches a ticker.",
    inputSchema: {
      properties: { ticker: { type: "string" } },
      required: ["ticker"],
      type: "object",
    },
    key: "research_agent",
    maxToolRounds: 3,
    mcpServers: [],
    name: "Research Agent",
    outputSchema: {
      id: 11,
      jsonSchema: {
        additionalProperties: false,
        properties: { summary: { type: "string" } },
        required: ["summary"],
        type: "object",
      },
      key: "decision_schema",
      version: 1,
    },
    skills: [],
    status: "published",
    streaming: true,
    systemPrompt: "Research clearly.",
    updatedAt: "2026-04-20T10:00:00Z",
    version: 3,
  },
  {
    id: 2,
    budgetUsd: "0.75000000",
    createdAt: "2026-04-20T10:00:00Z",
    description: "Consumes prior analysis.",
    inputSchema: {
      properties: {
        analysis: {
          properties: { summary: { type: "string" } },
          required: ["summary"],
          type: "object",
        },
      },
      required: ["analysis"],
      type: "object",
    },
    key: "consumer_agent",
    maxToolRounds: 3,
    mcpServers: [],
    name: "Consumer Agent",
    outputSchema: {
      id: 11,
      jsonSchema: {
        additionalProperties: false,
        properties: { summary: { type: "string" } },
        required: ["summary"],
        type: "object",
      },
      key: "decision_schema",
      version: 1,
    },
    skills: [],
    status: "published",
    streaming: true,
    systemPrompt: "Consume clearly.",
    updatedAt: "2026-04-20T10:00:00Z",
    version: 2,
  },
];

const brokenWorkflow = {
  id: 77,
  aggregateBudgetUsd: "1.25000000",
  createdAt: "2026-04-20T10:00:00Z",
  description: "Broken workflow for validation.",
  inputSchema: {
    properties: { ticker: { type: "string" } },
    required: ["ticker"],
    type: "object",
  },
  key: "market_review",
  name: "Market Review",
  outputSpec: { agentId: 1, agentKey: "consumer_agent", agentVersion: 2, kind: "slot", outputSchemaId: 11, outputSchemaVersion: 1, slot: "decision", stepIndex: 2 },
  status: "published",
  steps: [
    {
      agents: [
        {
          agentId: 1,
          agentKey: "research_agent",
          agentVersion: 3,
          budgetUsd: "0.50000000",
          optional: false,
          outputSchemaId: 11,
          outputSchemaVersion: 1,
          slot: "analysis",
          wiring: { ticker: { from: "input", path: "ticker" } },
        },
      ],
      index: 1,
    },
    {
      agents: [
        {
          agentId: 2,
          agentKey: "consumer_agent",
          agentVersion: 2,
          budgetUsd: "0.75000000",
          optional: false,
          outputSchemaId: 11,
          outputSchemaVersion: 1,
          slot: "decision",
          wiring: { analysis: { from: "step", slot: "missing_slot", stepIndex: 1 } },
        },
      ],
      index: 2,
    },
  ],
  updatedAt: "2026-04-20T10:00:00Z",
  version: 2,
};

const validWorkflow = {
  ...brokenWorkflow,
  id: 88,
  steps: [
    brokenWorkflow.steps[0],
    {
      ...brokenWorkflow.steps[1],
      agents: [
        {
          ...brokenWorkflow.steps[1].agents[0],
          wiring: { analysis: { from: "step", slot: "analysis", stepIndex: 1 } },
        },
      ],
    },
  ],
};

vi.mock("react-router", () => ({
  useLocation: () => ({ hash: "" }),
  useNavigate: () => navigateMock,
  useParams: () => paramsMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => toastErrorMock(...args),
    success: (...args: unknown[]) => toastSuccessMock(...args),
  },
}));

vi.mock("@/hooks/use-agents", () => ({
  useAgents: () => ({ data: { items: agents }, isError: false, isPending: false }),
}));

vi.mock("@/hooks/use-workflows", () => ({
  useCreateWorkflow: () => ({ isPending: false, mutateAsync: createWorkflowMock }),
  useCreateWorkflowRun: () => ({ isPending: false, mutateAsync: createWorkflowRunMock }),
  useUpdateWorkflow: () => ({ isPending: false, mutateAsync: updateWorkflowMock }),
  useWorkflow: (workflowId?: string) => {
    if (!workflowId) {
      return { data: undefined, error: null, isError: false, isPending: false };
    }

    return {
      data: workflowId === "88" ? validWorkflow : brokenWorkflow,
      error: null,
      isError: false,
      isPending: false,
    };
  },
}));

describe("WorkflowsEditorPage", () => {
  beforeEach(() => {
    paramsMock.workflowId = undefined;
    navigateMock.mockReset();
    createWorkflowMock.mockReset();
    createWorkflowRunMock.mockReset();
    updateWorkflowMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
  });

  it("shows the shared schema builder in the input step and removes the input-schema JSON textarea", () => {
    render(<WorkflowsEditorPage />);

    expect(screen.getByRole("tab", { name: /input/i })).toBeVisible();
    expect(screen.getByRole("tab", { name: /steps/i })).toBeVisible();
    expect(screen.getByRole("tab", { name: /output/i })).toBeVisible();
    expect(screen.getByRole("tab", { name: /review/i })).toBeVisible();
    expect(screen.queryByLabelText("Input Schema JSON")).not.toBeInTheDocument();
    expect(screen.getByText("Workflow Input Schema")).toBeVisible();
    expect(screen.getByTestId("output-schema-add-field")).toBeVisible();

    fireEvent.change(screen.getByLabelText("Workflow Key"), { target: { value: "market_review" } });
    fireEvent.change(screen.getByLabelText("Workflow Name"), { target: { value: "Market Review" } });

    fireEvent.click(screen.getByTestId("workflow-wizard-next"));
    fireEvent.click(screen.getByTestId("workflow-wizard-next"));
    fireEvent.click(screen.getByTestId("workflow-wizard-next"));

    expect(screen.getAllByText(/run input/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/run now becomes available after the first save/i)).toBeVisible();
    expect(screen.queryByLabelText("Run Input JSON")).not.toBeInTheDocument();
    expect(screen.queryByTestId("workflow-review-payload")).not.toBeInTheDocument();
    expect(screen.getAllByText(/workflow summary/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/resolve validation issues to preview the workflow summary/i)).toBeVisible();
    expect(screen.getByText(/enter the run payload through the shared schema-driven form/i)).toBeVisible();
  });

  it("surfaces invalid slot wiring feedback and blocks save", async () => {
    paramsMock.workflowId = "77";

    render(<WorkflowsEditorPage />);
    fireEvent.click(screen.getByTestId("workflow-save"));

    expect(await screen.findByTestId("workflow-validation-feedback")).toHaveTextContent(
      "Slot 'missing_slot' was not found on step 1",
    );
    expect(updateWorkflowMock).not.toHaveBeenCalled();
  });

  it("renders the structured review summary and starts a run from the saved workflow detail", async () => {
    paramsMock.workflowId = "88";
    createWorkflowRunMock.mockResolvedValue({ id: 901 });

    render(<WorkflowsEditorPage />);

    expect(screen.getByTestId("workflow-review-summary")).toBeVisible();
    expect(screen.getByTestId("workflow-review-summary")).toHaveTextContent("market_review");
    expect(screen.queryByLabelText("Run Input JSON")).not.toBeInTheDocument();
    expect(screen.queryByTestId("workflow-review-payload")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("workflow-run-now"));

    await waitFor(() => expect(createWorkflowRunMock).toHaveBeenCalledTimes(1));
    expect(createWorkflowRunMock).toHaveBeenCalledWith({
      payload: { ticker: "AAPL" },
      version: 2,
      workflowId: 88,
    });
    expect(navigateMock).toHaveBeenCalledWith("/runs/901");
  });
});
