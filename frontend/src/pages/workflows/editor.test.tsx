import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createWorkflowManifestScaffold } from "@/lib/platform-authoring/workflows/manifest";
import type { WorkflowRead } from "@/lib/types/workflow";

import { WorkflowsEditorPage } from "./editor";

const navigateMock = vi.fn();
const paramsMock: { workflowId?: string } = {};
const createWorkflowMock = vi.fn();
const createWorkflowRunMock = vi.fn();
const updateWorkflowMock = vi.fn();
const validateWorkflowManifestMock = vi.fn();
const toastErrorMock = vi.fn();
const toastSuccessMock = vi.fn();

const savedManifest = createWorkflowManifestScaffold({
  agentSlot: "decision",
  agentUse: "research_agent@3",
  description: "Reviews market context.",
  key: "market_review",
  name: "Market Review",
  stepId: "review_market",
});

const workflowInputSchema = {
  additionalProperties: false,
  properties: {
    limit: {
      description: "Optional cap applied only when the workflow needs a guardrail.",
      title: "Risk Limit",
      type: "number",
    },
    symbol: {
      description: "Portfolio symbol supplied at launch time.",
      title: "Portfolio Symbol",
      type: "string",
    },
  },
  required: ["symbol"],
  type: "object",
};

const savedWorkflow: WorkflowRead = {
  id: 88,
  aggregateBudgetUsd: "1.25000000",
  createdAt: "2026-04-20T10:00:00Z",
  description: "Reviews market context.",
  inputSchema: workflowInputSchema,
  key: "market_review",
  manifestApiVersion: "ledger.workflow/v1",
  manifestSource: savedManifest,
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
  steps: [],
  updatedAt: "2026-04-20T10:00:00Z",
  version: 2,
};

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
  useParams: () => paramsMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => toastErrorMock(...args),
    success: (...args: unknown[]) => toastSuccessMock(...args),
  },
}));

Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
  configurable: true,
  value: vi.fn(),
});

vi.mock("@/hooks/use-workflows", () => ({
  useCreateWorkflow: () => ({ isPending: false, mutateAsync: createWorkflowMock }),
  useCreateWorkflowRun: () => ({ isPending: false, mutateAsync: createWorkflowRunMock }),
  useUpdateWorkflow: () => ({ isPending: false, mutateAsync: updateWorkflowMock }),
  useValidateWorkflowManifest: () => ({ isPending: false, mutateAsync: validateWorkflowManifestMock }),
  useWorkflow: (workflowId?: string) => {
    if (!workflowId) {
      return { data: undefined, error: null, isError: false, isPending: false };
    }

    return { data: savedWorkflow, error: null, isError: false, isPending: false };
  },
}));

describe("WorkflowsEditorPage", () => {
  beforeEach(() => {
    paramsMock.workflowId = undefined;
    navigateMock.mockReset();
    createWorkflowMock.mockReset();
    createWorkflowRunMock.mockReset();
    updateWorkflowMock.mockReset();
    validateWorkflowManifestMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
  });

  it("renders the YAML-first full-height editor shell without wizard tabs", () => {
    render(<WorkflowsEditorPage />);

    expect(screen.getByTestId("workflow-yaml-editor-shell")).toBeVisible();
    expect(screen.getByTestId("workflow-command-bar")).toBeVisible();
    expect(screen.getByTestId("workflow-outline-rail")).toBeVisible();
    expect(screen.getByTestId("workflow-yaml-editor")).toBeVisible();
    expect(screen.getByTestId("workflow-inspector-shell")).toBeVisible();
    const guide = within(screen.getByTestId("workflow-manifest-101"));
    expect(guide.getByText("Workflow Manifest 101")).toBeVisible();
    expect(guide.getByText("Describe the run input, ordered agent steps, and final output slot.")).toBeVisible();
    expect(guide.getByText("apiVersion + kind")).toBeVisible();
    expect(guide.getByText("Use ledger.workflow/v1 and kind: Workflow.")).toBeVisible();
    expect(guide.getByText("steps[].agents[].uses")).toBeVisible();
    expect(guide.getByText(/\$\{\{ inputs\.\* \}\} and \$\{\{ steps\.\*\.outputs\.\* \}\}/i)).toBeVisible();
    expect(guide.getByText("Validate before Save or Run.")).toBeVisible();
    expect(screen.queryByRole("tab", { name: /input/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /steps/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /output/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /review/i })).not.toBeInTheDocument();
    expect(screen.queryByTestId("workflow-wizard-next")).not.toBeInTheDocument();
  });

  it("scaffolds new workflows and saves manifestSource through create", async () => {
    createWorkflowMock.mockResolvedValue({ id: 123 });

    render(<WorkflowsEditorPage />);

    const editor = screen.getByTestId("workflow-yaml-editor");
    expect((editor as HTMLTextAreaElement).value).toContain("apiVersion: ledger.workflow/v1");
    expect((editor as HTMLTextAreaElement).value).toContain("key: new_workflow");

    fireEvent.click(screen.getByTestId("workflow-save"));

    await waitFor(() => expect(createWorkflowMock).toHaveBeenCalledTimes(1));
    expect(createWorkflowMock).toHaveBeenCalledWith({ manifestSource: expect.stringContaining("key: new_workflow") });
    expect(navigateMock).toHaveBeenCalledWith("/workflows/123/edit");
  });

  it("loads existing workflow manifestSource and saves through update", async () => {
    paramsMock.workflowId = "88";
    updateWorkflowMock.mockResolvedValue(savedWorkflow);

    render(<WorkflowsEditorPage />);

    expect(screen.getByTestId("workflow-yaml-editor")).toHaveValue(savedManifest);
    expect(screen.getAllByText("Market Review").length).toBeGreaterThan(0);
    expect(screen.getAllByText("market_review").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByTestId("workflow-save"));

    await waitFor(() => expect(updateWorkflowMock).toHaveBeenCalledTimes(1));
    expect(updateWorkflowMock).toHaveBeenCalledWith({
      payload: { manifestSource: savedManifest },
      workflowId: "88",
    });
  });

  it("surfaces local YAML diagnostics in the inspector shell", () => {
    render(<WorkflowsEditorPage />);

    fireEvent.change(screen.getByTestId("workflow-yaml-editor"), {
      target: { value: "apiVersion: ledger.workflow/v1\nkind: [" },
    });

    expect(screen.getByTestId("workflow-local-parse-status")).toHaveTextContent(
      "Local parse needs attention",
    );
    expect(within(screen.getByTestId("workflow-validation-feedback")).getByText(/malformed yaml/i)).toBeVisible();
  });

  it("runs backend manifest validation and renders diagnostics plus raw JSON previews", async () => {
    const compiledPayload = {
      key: "new_workflow",
      name: "New Workflow",
      inputSchema: { type: "object" },
      steps: [{ index: 1, agents: [{ agentKey: "research_agent", agentVersion: 1, slot: "analysis" }] }],
      outputSpec: { kind: "slot", stepIndex: 1, slot: "analysis" },
    };
    const runInputSchema = { type: "object", properties: { ticker: { type: "string" } } };
    const compiledGraph = {
      apiVersion: "ledger.workflow/v2",
      rootNodeId: "root_sequence",
      nodes: [
        { id: "root_sequence", nodeId: "root_sequence", kind: "sequence", childNodeIds: ["analyst_fanout", "review_loop", "decision"] },
        { id: "root_sequence.analyst_fanout", nodeId: "analyst_fanout", kind: "fanout", branchIds: ["market", "news"], mode: "concurrent" },
        { id: "root_sequence.analyst_fanout.market.market_analysis", nodeId: "market_analysis", kind: "step", stepIndex: 1, slot: "market", agentKey: "market_agent", agentVersion: 1, branchId: "market", refs: { ticker: { source: "inputs", path: "ticker" } } },
        { id: "root_sequence.review_loop", nodeId: "review_loop", kind: "loop", maxIterations: 2, sequenceNodeId: "review_sequence" },
        { id: "root_sequence.review_loop.iteration_1.review_sequence.risk_review", nodeId: "risk_review", kind: "step", stepIndex: 2, slot: "risk", agentKey: "risk_agent", agentVersion: 1, loopId: "review_loop", loopIteration: 1 },
        { id: "root_sequence.review_loop.iteration_2.review_sequence.risk_review", nodeId: "risk_review", kind: "step", stepIndex: 3, slot: "risk", agentKey: "risk_agent", agentVersion: 1, loopId: "review_loop", loopIteration: 2 },
        { id: "root_sequence.review_loop.iteration_10.review_sequence.risk_review", nodeId: "risk_review", kind: "step", stepIndex: 11, slot: "risk", agentKey: "risk_agent", agentVersion: 1, loopId: "review_loop", loopIteration: 10 },
      ],
      output: { source: "nodes", nodeId: "root_sequence", slot: "final", stepIndex: 3, compiledSlot: "final" },
      validation: { loopMaxIterations: 10, fanoutMaxBranches: 16 },
      postRunMemory: {
        enabled: true,
        sourceRefs: { ticker: { source: "inputs", path: "ticker" } },
      },
    };
    validateWorkflowManifestMock.mockResolvedValue({
      compiledPayload,
      compiledGraph,
      diagnostics: [
        {
          column: 9,
          line: 12,
          message: "Agent pin resolves with a warning",
          path: "steps[0].agents[0].uses",
          severity: "warning",
        },
      ],
      metadata: {
        apiVersion: "ledger.workflow/v1",
        description: "Describe what this workflow does.",
        key: "new_workflow",
        name: "New Workflow",
      },
      runInputSchema,
    });

    render(<WorkflowsEditorPage />);

    const manifestSource = (screen.getByTestId("workflow-yaml-editor") as HTMLTextAreaElement).value;
    fireEvent.click(screen.getByTestId("workflow-validate-manifest"));

    await waitFor(() => expect(validateWorkflowManifestMock).toHaveBeenCalledWith({ manifestSource }));
    expect(screen.getByTestId("workflow-backend-validation-status")).toHaveTextContent(
      "Backend validation has warnings",
    );
    expect(within(screen.getByTestId("workflow-backend-validation-feedback")).getByText("Agent pin resolves with a warning")).toBeVisible();
    expect(within(screen.getByTestId("workflow-backend-validation-feedback")).getByText("steps[0].agents[0].uses")).toBeVisible();
    expect(screen.getByTestId("workflow-compiled-graph-preview")).toHaveTextContent("analyst_fanout");
    expect(screen.getByTestId("workflow-compiled-graph-preview")).toHaveTextContent("review_loop");
    expect(screen.getByTestId("workflow-compiled-graph-preview")).toHaveTextContent("iteration 1");
    const graphPreviewText = screen.getByTestId("workflow-compiled-graph-preview").textContent ?? "";
    expect(graphPreviewText.indexOf("iteration 2")).toBeGreaterThan(graphPreviewText.indexOf("iteration 1"));
    expect(graphPreviewText.indexOf("iteration 10")).toBeGreaterThan(graphPreviewText.indexOf("iteration 2"));
    expect(screen.getByTestId("workflow-compiled-graph-preview")).toHaveTextContent("postRunMemory");
    expect(screen.getByLabelText("Exact raw compiled graph JSON")).toHaveValue(JSON.stringify(compiledGraph, null, 2));
    expect(screen.getByLabelText("Exact raw compiled workflow JSON")).toHaveValue(JSON.stringify(compiledPayload, null, 2));
    expect(screen.getByLabelText("Exact raw workflow run input schema JSON")).toHaveValue(JSON.stringify(runInputSchema, null, 2));
  });

  it("tracks dirty state, protects beforeunload, and clears after a successful save", async () => {
    createWorkflowMock.mockResolvedValue({ id: 123 });

    render(<WorkflowsEditorPage />);

    expect(screen.getByTestId("workflow-dirty-indicator")).toHaveTextContent("Saved baseline");
    fireEvent.change(screen.getByTestId("workflow-yaml-editor"), {
      target: { value: `${createWorkflowManifestScaffold()}\n# edited\n` },
    });

    expect(screen.getByTestId("workflow-dirty-indicator")).toHaveTextContent("Unsaved changes");
    await waitFor(() => {
      const beforeUnloadEvent = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(beforeUnloadEvent);
      expect(beforeUnloadEvent.defaultPrevented).toBe(true);
    });

    fireEvent.click(screen.getByTestId("workflow-save"));

    await waitFor(() => expect(createWorkflowMock).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId("workflow-dirty-indicator")).toHaveTextContent("Saved baseline");
  });

  it("launches a run with required inputs only and navigates to the run detail", async () => {
    paramsMock.workflowId = "88";
    createWorkflowRunMock.mockResolvedValue({ id: 904 });

    render(<WorkflowsEditorPage />);

    const rawInput = screen.getByLabelText("Exact raw workflow run-input JSON") as HTMLTextAreaElement;
    await waitFor(() => expect(rawInput).toHaveValue(JSON.stringify({ symbol: "example" }, null, 2)));
    expect(screen.getByLabelText("Portfolio Symbol")).toHaveValue("example");
    expect(screen.getByText("Portfolio symbol supplied at launch time.")).toBeVisible();
    expect(screen.getByText("Optional cap applied only when the workflow needs a guardrail.")).toBeVisible();
    expect(screen.getByRole("button", { name: /add field/i })).toBeVisible();
    expect(rawInput.value).not.toContain("Portfolio Symbol");
    expect(rawInput.value).not.toContain("limit");

    fireEvent.click(screen.getByTestId("workflow-run-now"));

    await waitFor(() => expect(createWorkflowRunMock).toHaveBeenCalledTimes(1));
    expect(createWorkflowRunMock).toHaveBeenCalledWith({
      payload: { symbol: "example" },
      version: 2,
      workflowId: "88",
    });
    expect(navigateMock).toHaveBeenCalledWith("/runs/904");
  });

  it("opens command snippets and inserts YAML text at the cursor", async () => {
    render(<WorkflowsEditorPage />);

    const editor = screen.getByTestId("workflow-yaml-editor") as HTMLTextAreaElement;
    fireEvent.click(screen.getByTestId("workflow-open-snippets"));
    fireEvent.click(screen.getByText("Input property"));

    await waitFor(() => expect(editor.value).toContain("newField:"));
    expect(editor.value).toContain("title: New field");
    expect(editor.value).toContain("description: Help text shown with this workflow input.");
  });
});
