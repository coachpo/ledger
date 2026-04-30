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

const savedWorkflow: WorkflowRead = {
  id: 88,
  aggregateBudgetUsd: "1.25000000",
  createdAt: "2026-04-20T10:00:00Z",
  description: "Reviews market context.",
  inputSchema: {},
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
    validateWorkflowManifestMock.mockResolvedValue({
      compiledPayload,
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

  it("opens command snippets and inserts YAML text at the cursor", async () => {
    render(<WorkflowsEditorPage />);

    const editor = screen.getByTestId("workflow-yaml-editor") as HTMLTextAreaElement;
    fireEvent.click(screen.getByTestId("workflow-open-snippets"));
    fireEvent.click(screen.getByText("Input property"));

    await waitFor(() => expect(editor.value).toContain("newField:"));
    expect(editor.value).toContain("description: Describe this workflow input.");
  });
});
