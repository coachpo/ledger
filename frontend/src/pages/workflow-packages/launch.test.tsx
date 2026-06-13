import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError } from "@/lib/api-client";
import type {
  WorkflowPackageLaunchRead,
  WorkflowPackageManifestRead,
  WorkflowPackageRead,
  WorkflowPackageRuntimeInputEntryRead,
} from "@/lib/types/workflow-package";

import { WorkflowPackageLaunchPage } from "./launch";

const {
  createLaunchMock,
  createRuntimeInputPresetEntryMock,
  deleteRuntimeInputPresetEntryMock,
  navigateMock,
  preflightPackageMock,
  toastErrorMock,
  toastSuccessMock,
  toastWarningMock,
  updateRuntimeInputPresetEntryMock,
  useCreateLaunchMock,
  useCreateRuntimeInputPresetEntryMock,
  useDeleteRuntimeInputPresetEntryMock,
  usePreflightPackageMock,
  useUpdateRuntimeInputPresetEntryMock,
  useWorkflowPackageLaunchMock,
  useWorkflowPackageManifestMock,
  useWorkflowPackageMock,
  useWorkflowPackageRuntimeInputRegistryMock,
} = vi.hoisted(() => ({
  createLaunchMock: vi.fn(),
  createRuntimeInputPresetEntryMock: vi.fn(),
  deleteRuntimeInputPresetEntryMock: vi.fn(),
  navigateMock: vi.fn(),
  preflightPackageMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  toastWarningMock: vi.fn(),
  updateRuntimeInputPresetEntryMock: vi.fn(),
  useCreateLaunchMock: vi.fn(),
  useCreateRuntimeInputPresetEntryMock: vi.fn(),
  useDeleteRuntimeInputPresetEntryMock: vi.fn(),
  usePreflightPackageMock: vi.fn(),
  useUpdateRuntimeInputPresetEntryMock: vi.fn(),
  useWorkflowPackageLaunchMock: vi.fn(),
  useWorkflowPackageManifestMock: vi.fn(),
  useWorkflowPackageMock: vi.fn(),
  useWorkflowPackageRuntimeInputRegistryMock: vi.fn(),
}));

vi.mock("react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router")>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
    warning: toastWarningMock,
  },
}));

vi.mock("@/hooks/use-workflow-packages", () => ({
  useCreateWorkflowPackageLaunch: () => useCreateLaunchMock(),
  useCreateWorkflowPackageRuntimeInputPresetEntry: () => useCreateRuntimeInputPresetEntryMock(),
  useDeleteWorkflowPackageRuntimeInputPresetEntry: () => useDeleteRuntimeInputPresetEntryMock(),
  usePreflightWorkflowPackage: () => usePreflightPackageMock(),
  useUpdateWorkflowPackageRuntimeInputPresetEntry: () => useUpdateRuntimeInputPresetEntryMock(),
  useWorkflowPackage: (...args: unknown[]) => useWorkflowPackageMock(...args),
  useWorkflowPackageLaunch: (...args: unknown[]) => useWorkflowPackageLaunchMock(...args),
  useWorkflowPackageManifest: (...args: unknown[]) => useWorkflowPackageManifestMock(...args),
  useWorkflowPackageRuntimeInputRegistry: (...args: unknown[]) => useWorkflowPackageRuntimeInputRegistryMock(...args),
}));

const packageRead: WorkflowPackageRead = {
  compiledHash: "compiled-hash-123",
  createdAt: "2026-05-01T10:00:00Z",
  description: "Package for neutral research workflows.",
  id: 42,
  key: "market_review_package",
  manifestHash: "manifest-hash-123",
  name: "Market Review Package",
  updatedAt: "2026-05-05T10:00:00Z",
};

function manifestRead(
  workflows: Array<{
    description?: string;
    inputSchema?: Record<string, unknown>;
    key: string;
    label?: string;
    name?: string;
  }>,
): WorkflowPackageManifestRead {
  return {
    compiledHash: "compiled-hash-123",
    manifestHash: "manifest-hash-123",
    manifestSource: "apiVersion: signaldeck.workflowPackage/v1",
    packageDefinition: {
      spec: {
        workflows,
      },
    },
    packageId: 42,
    packageKey: "market_review_package",
  };
}

const singleWorkflowManifestRead = manifestRead([
  {
    description: "Run market review",
    inputSchema: {
      properties: {
        ticker: { description: "Ticker symbol", title: "Ticker", type: "string" },
      },
      required: ["ticker"],
      type: "object",
    },
    key: "market_review",
    name: "Market Review",
  },
]);

const launchRead: WorkflowPackageLaunchRead = {
  blockingErrors: [],
  description: "Run market review",
  inputSchema: {
    properties: {
      ticker: { description: "Ticker symbol", title: "Ticker", type: "string" },
    },
    required: ["ticker"],
    type: "object",
  },
  manifestHash: "manifest-hash-123",
  name: "Market Review",
  packageId: 42,
  packageKey: "market_review_package",
  ready: true,
  warnings: [],
  workflowKey: "market_review",
};

function runtimeInputEntry(
  overrides: Partial<WorkflowPackageRuntimeInputEntryRead> & Pick<WorkflowPackageRuntimeInputEntryRead, "id" | "slot">,
): WorkflowPackageRuntimeInputEntryRead {
  const entry: WorkflowPackageRuntimeInputEntryRead = {
    compiledHash: "compiled-hash-123",
    createdAt: "2026-05-08T10:00:00Z",
    id: overrides.id,
    inputSchemaSnapshot: null,
    manifestHash: "manifest-hash-123",
    name: null,
    packageId: 42,
    payload: { ticker: "AAPL" },
    schemaFingerprint: "schema-fingerprint-123",
    slot: overrides.slot,
    sourceKind: overrides.slot,
    sourceRunId: null,
    stale: { reasons: [], stale: false },
    updatedAt: "2026-05-08T10:00:00Z",
    workflowKey: "market_review",
  };
  return { ...entry, ...overrides };
}

function runtimeInputRegistry(overrides: {
  history?: WorkflowPackageRuntimeInputEntryRead[];
  isError?: boolean;
  isFetching?: boolean;
  isPending?: boolean;
  presets?: WorkflowPackageRuntimeInputEntryRead[];
} = {}) {
  return {
    data: {
      currentMetadata: null,
      history: overrides.history ?? [],
      packageId: 42,
      packageKey: "market_review_package",
      presets: overrides.presets ?? [],
      workflowKey: "market_review",
    },
    error: overrides.isError ? new Error("Saved inputs failed") : null,
    isError: overrides.isError ?? false,
    isFetching: overrides.isFetching ?? false,
    isPending: overrides.isPending ?? false,
  };
}

function renderLaunchPage(initialEntry = "/workflow-packages/42/run") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/workflow-packages/:packageId/run" element={<WorkflowPackageLaunchPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function workflowSelector() {
  return screen.getByRole("combobox", { name: /workflow/i });
}

async function chooseWorkflow(optionName: string | RegExp) {
  const selector = workflowSelector();
  selector.focus();
  fireEvent.keyDown(selector, { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name: optionName }));
}

async function selectSingleWorkflow() {
  await chooseWorkflow(/^Market Review$/);
  await waitFor(() => expect(workflowSelector()).toHaveTextContent("Market Review"));
}

function switchToJsonMode() {
  fireEvent.click(screen.getByRole("radio", { name: "JSON" }));
}

async function completeReadyPreflight() {
  fireEvent.click(screen.getByRole("button", { name: /run preflight/i }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: /launch run/i })).not.toBeDisabled(),
  );
}

describe("WorkflowPackageLaunchPage", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    preflightPackageMock.mockReset();
    createLaunchMock.mockReset();
    createRuntimeInputPresetEntryMock.mockReset();
    deleteRuntimeInputPresetEntryMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    toastWarningMock.mockReset();
    updateRuntimeInputPresetEntryMock.mockReset();
    useWorkflowPackageMock.mockReset();
    useWorkflowPackageLaunchMock.mockReset();
    useWorkflowPackageManifestMock.mockReset();
    useWorkflowPackageRuntimeInputRegistryMock.mockReset();
    preflightPackageMock.mockResolvedValue(launchRead);
    createLaunchMock.mockResolvedValue({ createdAt: "2026-05-08T10:00:00Z", id: 99, status: "queued", workflowKey: "market_review", workflowPackageId: 42, workflowPackageKey: "market_review_package" });
    createRuntimeInputPresetEntryMock.mockResolvedValue(runtimeInputEntry({ id: 30, name: "Saved preset", slot: "preset" }));
    updateRuntimeInputPresetEntryMock.mockResolvedValue(runtimeInputEntry({ id: 7, name: "Updated preset", slot: "preset" }));
    deleteRuntimeInputPresetEntryMock.mockResolvedValue(undefined);
    useWorkflowPackageMock.mockReturnValue({ data: packageRead, error: null, isError: false, isPending: false });
    useWorkflowPackageManifestMock.mockReturnValue({ data: singleWorkflowManifestRead, error: null, isError: false, isPending: false });
    useWorkflowPackageLaunchMock.mockReturnValue({ data: launchRead, error: null, isError: false, isPending: false });
    usePreflightPackageMock.mockReturnValue({ isPending: false, mutateAsync: preflightPackageMock });
    useCreateLaunchMock.mockReturnValue({ isPending: false, mutateAsync: createLaunchMock });
    useCreateRuntimeInputPresetEntryMock.mockReturnValue({ isPending: false, mutateAsync: createRuntimeInputPresetEntryMock });
    useUpdateRuntimeInputPresetEntryMock.mockReturnValue({ isPending: false, mutateAsync: updateRuntimeInputPresetEntryMock });
    useDeleteRuntimeInputPresetEntryMock.mockReturnValue({ isPending: false, mutateAsync: deleteRuntimeInputPresetEntryMock });
    useWorkflowPackageRuntimeInputRegistryMock.mockReturnValue(runtimeInputRegistry());
  });

  it("renders a compact launch page with collapsed package details and sticky actions", async () => {
    renderLaunchPage();

    expect(screen.getByTestId("workflow-package-launch-page")).toBeVisible();
    expect(screen.getByTestId("workflow-package-launch-page")).toHaveClass("min-w-0", "overflow-hidden");
    expect(screen.getByTestId("workspace-page-shell-context")).toHaveClass("sticky", "top-0");
    expect(screen.getByRole("heading", { name: "Launch Workflow Package" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Open Editor" })).toHaveAttribute("href", "/workflow-packages/42");
    const identity = screen.getByTestId("workflow-package-launch-identity");
    expect(identity).toHaveTextContent("Package #42");
    expect(identity).toHaveTextContent("market_review_package");
    expect(identity).toHaveTextContent(/Updated/i);
    expect(screen.queryByText("manifest-hash-123")).not.toBeInTheDocument();
    fireEvent.click(within(identity).getByRole("button", { name: "Details" }));
    expect(screen.getByTestId("workflow-package-launch-details")).toHaveTextContent("Market Review Package");
    expect(screen.getByTestId("workflow-package-launch-details")).toHaveTextContent("manifest-hash-123");
    expect(screen.getByTestId("workflow-package-launch-next-step")).toHaveTextContent(
      "Choose a workflow to continue.",
    );
    expect(workflowSelector()).toHaveTextContent("Choose a workflow");
    const readiness = screen.getByTestId("workflow-package-preflight-status");
    expect(readiness).toHaveTextContent("Metadata missing");
    expect(readiness).toHaveTextContent("Preflight pending");
    expect(readiness).toHaveTextContent("Workflow");
    expect(readiness).toHaveTextContent("Workflow selection required");
    expect(readiness).toHaveTextContent("Manifest not recorded");
    expect(readiness).toHaveTextContent("Input schema unavailable");
    expect(readiness).not.toHaveTextContent("Blocking");
    expect(readiness).not.toHaveTextContent("Warnings");
    const runConfig = screen.getByTestId("workflow-package-run-config");
    expect(screen.getByTestId("workflow-package-launch-tab")).toContainElement(runConfig);
    expect(runConfig).toHaveTextContent("Runtime inputs");
    expect(screen.getByTestId("runtime-input-console-grid")).toHaveClass("grid", "min-w-0");
    expect(screen.getByTestId("runtime-input-json-panel")).toHaveClass("min-w-0");
    expect(screen.getByLabelText("Runtime inputs JSON")).toHaveClass("max-w-full", "overflow-x-auto", "whitespace-pre");
    const actionBar = screen.getByTestId("workflow-package-run-actions");
    expect(actionBar).toHaveClass("sticky", "flex", "min-w-0", "flex-col", "sm:flex-row");
    expect(actionBar).not.toHaveClass(
      "backdrop-blur",
      "supports-[backdrop-filter]:bg-background/85",
    );
    const preflightButton = within(actionBar).getByRole("button", {
      name: /run preflight/i,
    });
    expect(preflightButton).toBeVisible();
    expect(preflightButton).toBeDisabled();
    const launchButton = within(actionBar).getByRole("button", { name: /launch run/i });
    expect(launchButton).toBeDisabled();
    expect(launchButton).toHaveAccessibleDescription("Choose a workflow to continue.");
    expect(screen.getByLabelText("Runtime inputs JSON")).toBeDisabled();
    expect(screen.getByRole("tablist")).toBeVisible();
    expect(screen.getByRole("tab", { name: /presets/i })).toBeDisabled();
    expect(screen.getByRole("tab", { name: /history/i })).toBeDisabled();
    expect(screen.queryByTestId("workflow-package-launch-context")).not.toBeInTheDocument();
    expect(screen.queryByTestId("workflow-package-constraint-inspector")).not.toBeInTheDocument();
    expect(screen.queryByTestId("workflow-package-editor-shell")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /workflow/i })).not.toBeInTheDocument();
    expect(useWorkflowPackageMock).toHaveBeenCalledWith("42");
    expect(useWorkflowPackageManifestMock).toHaveBeenCalledWith("42");
    await waitFor(() =>
      expect(useWorkflowPackageLaunchMock).toHaveBeenLastCalledWith(
        "42",
        undefined,
      ),
    );
  });

  it("separates capability blockers from warnings before run creation", async () => {
    const strictJsonSchemaWarning =
      "spec.outputSchemas.risk_debate_transition.jsonSchema: This workflow requires structured JSON output, but strict JSON-schema output has not been proven yet.";

    useWorkflowPackageLaunchMock.mockReturnValue({
      data: {
        ...launchRead,
        blockingErrors: [
          {
            field: "spec.agents[0].modelConnection",
            issue: "This workflow requires native tool calls",
            severity: "error",
          },
        ],
        ready: false,
        warnings: [
          {
            field: "spec.outputSchemas.risk_debate_transition.jsonSchema",
            issue:
              "This workflow requires structured JSON output, but strict JSON-schema output has not been proven yet.",
            severity: "warning",
          },
          {
            field: "spec.agents[2].modelConnection",
            issue: "This model connection omits usage metadata, so run usage totals will be derived from the response body.",
            severity: "warning",
          },
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });
    renderLaunchPage();

    await selectSingleWorkflow();
    const readiness = screen.getByTestId("workflow-package-preflight-status");
    expect(readiness).toHaveTextContent("Blocking");
    expect(readiness).toHaveTextContent("Warnings");
    expect(readiness).toHaveTextContent("1");
    expect(readiness).toHaveTextContent("2");
    const blockers = screen.getByTestId("workflow-package-launch-blockers");
    const warnings = screen.getByTestId("workflow-package-launch-warnings");
    expect(blockers).toHaveTextContent(/Blocking diagnostics/i);
    expect(blockers).toHaveTextContent(/This workflow requires native tool calls/i);
    expect(warnings).toHaveTextContent(/Warnings/i);
    expect(warnings).toHaveTextContent(strictJsonSchemaWarning);
    expect(warnings).toHaveTextContent(/omits usage metadata/i);
    expect(within(warnings).getByRole("list")).toBeVisible();
    expect(within(warnings).getAllByRole("listitem")).toHaveLength(2);
    expect(within(warnings).getAllByText("Warning").length).toBeGreaterThan(0);
  });

  it("renders launch-specific invalid and not-found states", () => {
    const invalidView = renderLaunchPage("/workflow-packages/new/run");
    expect(screen.getByText("Invalid workflow package launch route")).toBeVisible();
    expect(screen.getByText(/persisted numeric workflow package id/i)).toBeVisible();
    invalidView.unmount();

    useWorkflowPackageMock.mockReturnValue({
      data: undefined,
      error: new ApiRequestError({ code: "not_found", message: "No package", status: 404 }),
      isError: true,
      isPending: false,
    });
    renderLaunchPage();
    expect(screen.getByText("Workflow package not found")).toBeVisible();
    expect(screen.queryByTestId("workflow-package-launch-tab")).not.toBeInTheDocument();
  });

  it("shows launch metadata missing, loading, and load-error states", async () => {
    useWorkflowPackageLaunchMock.mockReturnValue({ data: undefined, error: null, isError: false, isPending: false });
    const missingView = renderLaunchPage();
    expect(screen.getByTestId("workflow-package-launch-next-step")).toHaveTextContent(
      "Choose a workflow to continue.",
    );
    const missingReadiness = screen.getByTestId("workflow-package-preflight-status");
    expect(missingReadiness).toHaveTextContent("Metadata missing");
    expect(missingReadiness).toHaveTextContent("Preflight pending");
    expect(missingReadiness).toHaveTextContent("Workflow selection required");
    expect(missingReadiness).toHaveTextContent("Manifest not recorded");
    expect(missingReadiness).toHaveTextContent("Input schema unavailable");
    missingView.unmount();

    useWorkflowPackageLaunchMock.mockReturnValue({ data: undefined, error: null, isError: false, isPending: true });
    const loadingView = renderLaunchPage();
    await selectSingleWorkflow();
    expect(screen.getByText("Loading launch metadata...")).toBeVisible();
    expect(screen.getByTestId("workflow-package-preflight-status")).toHaveTextContent("Metadata loading");
    loadingView.unmount();

    useWorkflowPackageLaunchMock.mockReturnValue({ data: undefined, error: new Error("Launch metadata failed"), isError: true, isPending: false });
    const errorView = renderLaunchPage();
    await selectSingleWorkflow();
    expect(screen.getAllByText("Launch metadata unavailable").length).toBeGreaterThan(0);
    expect(screen.getByTestId("workflow-package-preflight-status")).toHaveTextContent("Launch metadata unavailable");
    expect(screen.getByTestId("workflow-package-launch-metadata-error")).toHaveTextContent("Launch metadata failed");
    const errorLaunchButton = screen.getByRole("button", { name: /launch run/i });
    expect(errorLaunchButton).toBeDisabled();
    expect(errorLaunchButton).toHaveAccessibleDescription("Launch disabled until launch metadata is available.");
    errorView.unmount();
  });

  it("requires explicit workflow selection for multi-workflow packages before preflight or saved-input actions", async () => {
    const advisorySchema = {
      properties: {
        ticker: { title: "Ticker", type: "string" },
      },
      required: ["ticker"],
      type: "object",
    };
    const newsSchema = {
      properties: {
        query: { title: "Query", type: "string" },
      },
      required: ["query"],
      type: "object",
    };
    useWorkflowPackageManifestMock.mockReturnValue({
      data: manifestRead([
        { description: "Advisory workflow", inputSchema: advisorySchema, key: "advisory_research", name: "Advisory Research" },
        { description: "News workflow", inputSchema: newsSchema, key: "news_research", name: "News Research" },
      ]),
      error: null,
      isError: false,
      isPending: false,
    });
    useWorkflowPackageLaunchMock.mockImplementation((_packageId, workflowKey) => ({
      data: workflowKey === "news_research"
        ? { ...launchRead, description: "News workflow", inputSchema: newsSchema, name: "News Research", workflowKey: "news_research" }
        : { ...launchRead, description: "Advisory workflow", inputSchema: advisorySchema, name: "Advisory Research", workflowKey: "advisory_research" },
      error: null,
      isError: false,
      isPending: false,
    }));

    renderLaunchPage();

    expect(workflowSelector()).toHaveTextContent("Choose a workflow");
    expect(screen.getByTestId("workflow-package-launch-next-step")).toHaveTextContent("Choose a workflow to continue");
    expect(screen.getByRole("button", { name: /run preflight/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /launch run/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save current JSON" })).toBeDisabled();
    expect(screen.getByLabelText("Runtime inputs JSON")).toBeDisabled();
    expect(screen.getByLabelText("Saved runtime input preset name")).toBeDisabled();
    const pendingHelper = screen.getByTestId("runtime-input-saved-inputs-helper");
    expect(pendingHelper).toHaveTextContent("workflow pending");
    expect(pendingHelper).not.toHaveTextContent(/loading saved inputs for this workflow/i);
    expect(pendingHelper).not.toHaveTextContent("No saved runtime input presets for this workflow.");
    expect(pendingHelper).not.toHaveTextContent("No launch history yet.");
    expect(within(pendingHelper).getAllByText("0/20")).toHaveLength(2);

    await chooseWorkflow(/^News Research$/);

    await waitFor(() => expect(workflowSelector()).toHaveTextContent("News Research"));
    expect(screen.getByTestId("workflow-package-launch-next-step")).toHaveTextContent("Run preflight to load launch metadata and validate this package before launch.");
    expect(screen.getByRole("button", { name: /run preflight/i })).not.toBeDisabled();
    expect(screen.getByRole("tab", { name: /presets/i })).not.toBeDisabled();
    expect(screen.getByRole("tab", { name: /history/i })).not.toBeDisabled();
    expect(screen.getByLabelText("Runtime inputs JSON")).not.toBeDisabled();
    expect(screen.getByLabelText("Saved runtime input preset name")).not.toBeDisabled();
    expect(screen.getByText("No saved runtime input presets for this workflow.")).toBeVisible();
    fireEvent.mouseDown(screen.getByRole("tab", { name: /history/i }), { button: 0 });
    expect(screen.getByText("No launch history yet.")).toBeVisible();
    fireEvent.mouseDown(screen.getByRole("tab", { name: /presets/i }), { button: 0 });
    expect((screen.getByLabelText("Runtime inputs JSON") as HTMLTextAreaElement).value).toBe(
      JSON.stringify({ query: "" }, null, 2),
    );
  });

  it("keeps a stale selected workflow visible instead of remapping to the only current manifest workflow", async () => {
    const retiredSchema = {
      properties: {
        symbol: { title: "Symbol", type: "string" },
      },
      required: ["symbol"],
      type: "object",
    };
    useWorkflowPackageManifestMock.mockReturnValue({
      data: manifestRead([
        {
          description: "Retired workflow",
          inputSchema: retiredSchema,
          key: "retired_workflow",
          name: "Retired Workflow",
        },
      ]),
      error: null,
      isError: false,
      isPending: false,
    });
    useWorkflowPackageLaunchMock.mockImplementation((_packageId, workflowKey) => ({
      data:
        workflowKey === "retired_workflow"
          ? {
              ...launchRead,
              description: "Retired workflow",
              inputSchema: retiredSchema,
              name: "Retired Workflow",
              workflowKey: "retired_workflow",
            }
          : launchRead,
      error: null,
      isError: false,
      isPending: false,
    }));

    const view = renderLaunchPage();

    expect(workflowSelector()).toHaveTextContent("Choose a workflow");
    await chooseWorkflow(/^Retired Workflow$/);
    await waitFor(() => expect(workflowSelector()).toHaveTextContent("Retired Workflow"));
    expect(screen.getByRole("button", { name: /run preflight/i })).not.toBeDisabled();
    expect(screen.getByTestId("runtime-input-saved-inputs-helper")).toHaveTextContent(
      "retired_workflow",
    );

    useWorkflowPackageManifestMock.mockReturnValue({
      data: singleWorkflowManifestRead,
      error: null,
      isError: false,
      isPending: false,
    });
    view.rerender(
      <MemoryRouter initialEntries={["/workflow-packages/42/run"]}>
        <Routes>
          <Route path="/workflow-packages/:packageId/run" element={<WorkflowPackageLaunchPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(workflowSelector()).toHaveTextContent(
        "Unknown workflow: retired_workflow",
      ),
    );
    expect(screen.getByTestId("workflow-package-launch-next-step")).toHaveTextContent(
      "Selected workflow is no longer present in the current manifest. Choose a workflow to continue.",
    );
    expect(screen.getByRole("button", { name: /run preflight/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /launch run/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save current JSON" })).toBeDisabled();
    expect(screen.getByTestId("runtime-input-saved-inputs-helper")).toHaveTextContent(
      "workflow pending",
    );
    expect(workflowSelector()).not.toHaveTextContent("Market Review");
    await waitFor(() =>
      expect(useWorkflowPackageLaunchMock).toHaveBeenLastCalledWith(
        "42",
        undefined,
      ),
    );
    expect(useWorkflowPackageRuntimeInputRegistryMock).toHaveBeenLastCalledWith(
      "42",
      "",
    );
  });

  it("shows explicit manifest-empty and manifest-error workflow selector states", () => {
    useWorkflowPackageManifestMock.mockReturnValue({
      data: manifestRead([]),
      error: null,
      isError: false,
      isPending: false,
    });
    const emptyView = renderLaunchPage();

    expect(screen.getByTestId("workflow-package-launch-next-step")).toHaveTextContent("This package manifest does not declare any workflows.");
    expect(screen.getByRole("button", { name: /run preflight/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /launch run/i })).toBeDisabled();
    emptyView.unmount();

    useWorkflowPackageManifestMock.mockReturnValue({
      data: undefined,
      error: new Error("Manifest fetch failed"),
      isError: true,
      isPending: false,
    });
    renderLaunchPage();

    expect(screen.getByTestId("workflow-package-launch-next-step")).toHaveTextContent("Workflow selector unavailable until the package manifest loads.");
    expect(screen.getByText("Manifest fetch failed")).toBeVisible();
    expect(screen.getByRole("button", { name: /run preflight/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /launch run/i })).toBeDisabled();
  });

  it("launches a package run after preflight and navigates to run detail", async () => {
    renderLaunchPage();

    await selectSingleWorkflow();
    const launchPanel = await screen.findByTestId("workflow-package-launch-tab");
    expect(within(launchPanel).getByRole("combobox", { name: /workflow/i })).toBeVisible();
    expect(screen.getByTestId("runtime-input-schema-form")).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Ticker" })).toBeVisible();
    fireEvent.change(screen.getByLabelText("Runtime inputs JSON"), { target: { value: '{"ticker":"AAPL"}' } });
    await completeReadyPreflight();
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    await waitFor(() => expect(preflightPackageMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: { parameters: { ticker: "AAPL" }, workflowKey: "market_review" },
    }));
    expect(createLaunchMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: { parameters: { ticker: "AAPL" }, workflowKey: "market_review" },
    });
    expect(navigateMock).toHaveBeenCalledWith("/runs/99");
  });

  it("blocks create-launch when launch preflight returns blocking diagnostics", async () => {
    preflightPackageMock.mockResolvedValueOnce({
      ...launchRead,
      blockingErrors: [{ field: "spec.agents[0].modelConnection", issue: "Missing model connection primary_model" }],
      ready: false,
    });
    renderLaunchPage();

    await selectSingleWorkflow();
    fireEvent.change(screen.getByLabelText("Runtime inputs JSON"), { target: { value: '{"ticker":"AAPL"}' } });
    fireEvent.click(screen.getByRole("button", { name: /run preflight/i }));

    expect(await screen.findByText(/Missing model connection primary_model/i)).toBeVisible();
    const launchButton = screen.getByRole("button", { name: /launch run/i });
    expect(launchButton).toBeDisabled();
    expect(launchButton).toHaveAccessibleDescription("Launch disabled until blocking diagnostics are resolved.");
    expect(createLaunchMock).not.toHaveBeenCalled();
  });

  it("manages saved runtime input presets and load-only history without replacing the raw editor", async () => {
    const preset = runtimeInputEntry({
      id: 7,
      name: "Baseline preset",
      payload: { ticker: "MSFT" },
      slot: "preset",
      stale: {
        reasons: [{ current: "manifest-hash-123", field: "manifestHash", issue: "Manifest changed", stored: "old-manifest" }],
        stale: true,
      },
      updatedAt: "2026-05-08T09:00:00Z",
    });
    const olderHistory = runtimeInputEntry({ createdAt: "2026-05-08T08:00:00Z", id: 10, payload: { ticker: "TSLA" }, slot: "history", sourceRunId: 88 });
    const newerHistory = runtimeInputEntry({ createdAt: "2026-05-08T11:00:00Z", id: 11, payload: { ticker: "NVDA" }, slot: "history", sourceRunId: 99 });
    useWorkflowPackageRuntimeInputRegistryMock.mockReturnValue(runtimeInputRegistry({ history: [olderHistory, newerHistory], presets: [preset] }));
    renderLaunchPage();

    await selectSingleWorkflow();
    const helper = await screen.findByTestId("runtime-input-saved-inputs-helper");
    expect(within(helper).getByText("Saved inputs")).toBeVisible();
    expect(within(helper).getByText("1/20")).toBeVisible();
    expect(within(helper).getByText("2/20")).toBeVisible();
    expect(within(screen.getByTestId("saved-input-preset-7")).getByText("Stale")).toBeVisible();
    expect(within(screen.getByTestId("saved-input-preset-7")).getByText(/manifestHash: Manifest changed/i)).toBeVisible();

    const runtimeJson = (await screen.findByLabelText("Runtime inputs JSON")) as HTMLTextAreaElement;
    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"AAPL"}' } });
    fireEvent.change(screen.getByLabelText("Saved runtime input preset name"), { target: { value: "Morning preset" } });
    fireEvent.click(screen.getByRole("button", { name: "Save current JSON" }));

    await waitFor(() => expect(createRuntimeInputPresetEntryMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: { name: "Morning preset", payload: { ticker: "AAPL" } },
      workflowKey: "market_review",
    }));

    fireEvent.click(screen.getByRole("button", { name: "Load saved runtime input preset Baseline preset" }));
    expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "MSFT" }, null, 2));
    expect(createLaunchMock).not.toHaveBeenCalled();

    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"GOOG"}' } });
    fireEvent.click(screen.getByRole("button", { name: "Overwrite saved runtime input preset Baseline preset" }));
    await waitFor(() => expect(updateRuntimeInputPresetEntryMock).toHaveBeenCalledWith({
      entryId: 7,
      packageId: "42",
      payload: { name: "Baseline preset", payload: { ticker: "GOOG" } },
      workflowKey: "market_review",
    }));

    fireEvent.click(screen.getByRole("button", { name: "Delete saved runtime input preset Baseline preset" }));
    await waitFor(() => expect(deleteRuntimeInputPresetEntryMock).toHaveBeenCalledWith({ entryId: 7, packageId: "42", workflowKey: "market_review" }));

    fireEvent.mouseDown(screen.getByRole("tab", { name: /history/i }), {
      button: 0,
    });
    expect(screen.getByTestId("saved-input-history-11").compareDocumentPosition(screen.getByTestId("saved-input-history-10")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const newestHistoryRow = screen.getByTestId("saved-input-history-11");
    expect(within(newestHistoryRow).queryByRole("button", { name: /overwrite/i })).not.toBeInTheDocument();
    expect(within(newestHistoryRow).queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load history input Run #99" }));
    expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "NVDA" }, null, 2));
    expect(preflightPackageMock).not.toHaveBeenCalled();
    expect(createLaunchMock).not.toHaveBeenCalled();
  });

  it("keeps stale extra saved inputs in advanced JSON with local validation details", async () => {
    const preset = runtimeInputEntry({
      id: 7,
      name: "Baseline preset",
      payload: { legacyWindow: "pre-upgrade", ticker: "MSFT" },
      slot: "preset",
      stale: {
        reasons: [{ current: "compiled-hash-123", field: "compiledHash", issue: "Compiled package changed", stored: "old-compiled" }],
        stale: true,
      },
    });
    useWorkflowPackageRuntimeInputRegistryMock.mockReturnValue(
      runtimeInputRegistry({ presets: [preset] }),
    );
    renderLaunchPage();

    await selectSingleWorkflow();
    fireEvent.click(screen.getByRole("button", { name: "Load saved runtime input preset Baseline preset" }));

    const feedback = await screen.findByTestId("runtime-input-validation-feedback");
    expect(feedback).toHaveTextContent("parameters.legacyWindow");
    expect(feedback).toHaveTextContent("Extra inputs are not permitted.");
    expect(screen.queryByTestId("runtime-input-primary-form")).not.toBeInTheDocument();
    expect(screen.getByTestId("runtime-input-json-mode-notice")).toBeVisible();
    expect((screen.getByLabelText("Runtime inputs JSON") as HTMLTextAreaElement).value).toBe(
      JSON.stringify({ legacyWindow: "pre-upgrade", ticker: "MSFT" }, null, 2),
    );
    fireEvent.click(screen.getByRole("button", { name: /run preflight/i }));
    expect(preflightPackageMock).not.toHaveBeenCalled();
  });

  it("resets launch form to required and defaulted inputs", async () => {
    useWorkflowPackageLaunchMock.mockReturnValue({
      data: {
        ...launchRead,
        inputSchema: {
          properties: {
            includeNews: { default: true, title: "Include News", type: "boolean" },
            lookbackDays: { default: 14, title: "Lookback Days", type: "integer" },
            notes: { title: "Notes", type: "string" },
            ticker: { title: "Ticker", type: "string" },
          },
          required: ["ticker"],
          type: "object",
        },
      },
      error: null,
      isError: false,
      isPending: false,
    });
    renderLaunchPage();

    await selectSingleWorkflow();
    const schemaForm = await screen.findByTestId("runtime-input-schema-form");
    fireEvent.change(within(schemaForm).getByRole("textbox", { name: "Ticker" }), {
      target: { value: "AAPL" },
    });
    fireEvent.click(within(schemaForm).getByRole("button", { name: "Add Field" }));
    fireEvent.change(within(schemaForm).getByRole("textbox", { name: "Notes" }), {
      target: { value: "Loaded from a stale preset" },
    });
    switchToJsonMode();
    fireEvent.change(screen.getByLabelText("Runtime inputs JSON"), {
      target: { value: '{"ticker":null}' },
    });
    fireEvent.click(screen.getByRole("button", { name: /run preflight/i }));
    expect(await screen.findByTestId("runtime-input-validation-feedback")).toHaveTextContent("Null is only allowed");

    fireEvent.click(screen.getByRole("button", { name: "Reset to template" }));

    const resetForm = screen.getByTestId("runtime-input-schema-form");
    expect(screen.getByTestId("runtime-input-primary-form")).toBeVisible();
    expect(within(resetForm).getByRole("textbox", { name: "Ticker" })).toHaveValue("");
    expect(within(resetForm).getByRole("spinbutton", { name: "Lookback Days" })).toHaveValue(14);
    expect(within(resetForm).getByRole("switch", { name: "Include News" })).toBeChecked();
    expect(within(resetForm).queryByRole("textbox", { name: "Notes" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("runtime-input-validation-feedback")).not.toBeInTheDocument();
    expect((screen.getByLabelText("Runtime inputs JSON") as HTMLTextAreaElement).value).toBe(JSON.stringify({
      includeNews: true,
      lookbackDays: 14,
      ticker: "",
    }, null, 2));
  });

  it("saves the canonical form payload for saved runtime input presets", async () => {
    useWorkflowPackageLaunchMock.mockReturnValue({
      data: {
        ...launchRead,
        inputSchema: {
          properties: {
            includeNews: { default: false, title: "Include News", type: "boolean" },
            notes: { title: "Notes", type: "string" },
            ticker: { title: "Ticker", type: "string" },
          },
          required: ["ticker"],
          type: "object",
        },
      },
      error: null,
      isError: false,
      isPending: false,
    });
    renderLaunchPage();

    await selectSingleWorkflow();
    const schemaForm = await screen.findByTestId("runtime-input-schema-form");
    fireEvent.change(within(schemaForm).getByRole("textbox", { name: "Ticker" }), {
      target: { value: "NVDA" },
    });
    fireEvent.change(screen.getByLabelText("Saved runtime input preset name"), {
      target: { value: "Canonical preset" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save current JSON" }));

    await waitFor(() => expect(createRuntimeInputPresetEntryMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: {
        name: "Canonical preset",
        payload: { includeNews: false, ticker: "NVDA" },
      },
      workflowKey: "market_review",
    }));
    await waitFor(() => expect(toastSuccessMock).toHaveBeenCalledWith("Saved runtime input preset"));
  });

  it("overwrites saved runtime input presets from validated advanced JSON payloads", async () => {
    const preset = runtimeInputEntry({
      id: 7,
      name: "Baseline preset",
      payload: { ticker: "MSFT" },
      slot: "preset",
    });
    useWorkflowPackageRuntimeInputRegistryMock.mockReturnValue(
      runtimeInputRegistry({ presets: [preset] }),
    );
    renderLaunchPage();

    await selectSingleWorkflow();
    switchToJsonMode();
    fireEvent.change(screen.getByLabelText("Runtime inputs JSON"), {
      target: { value: '{"ticker":"GOOG"}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Overwrite saved runtime input preset Baseline preset" }));

    await waitFor(() => expect(updateRuntimeInputPresetEntryMock).toHaveBeenCalledWith({
      entryId: 7,
      packageId: "42",
      payload: {
        name: "Baseline preset",
        payload: { ticker: "GOOG" },
      },
      workflowKey: "market_review",
    }));
  });

  it("keeps invalid stale saved inputs in advanced JSON with local validation details", async () => {
    const preset = runtimeInputEntry({
      id: 7,
      name: "Old nullable preset",
      payload: { legacyField: "visible", ticker: null },
      slot: "preset",
      stale: {
        reasons: [{ current: "schema-fingerprint-123", field: "schemaFingerprint", issue: "Schema changed", stored: "old-schema" }],
        stale: true,
      },
    });
    useWorkflowPackageRuntimeInputRegistryMock.mockReturnValue(
      runtimeInputRegistry({ presets: [preset] }),
    );
    renderLaunchPage();

    await selectSingleWorkflow();
    fireEvent.click(screen.getByRole("button", { name: "Load saved runtime input preset Old nullable preset" }));

    const feedback = await screen.findByTestId("runtime-input-validation-feedback");
    expect(feedback).toHaveTextContent("parameters.legacyField");
    expect(feedback).toHaveTextContent("Extra inputs are not permitted.");
    expect(feedback).toHaveTextContent("parameters.ticker");
    expect(feedback).toHaveTextContent("Null is only allowed for nullable runtime input fields.");
    expect(screen.getByTestId("runtime-input-json-mode-notice")).toBeVisible();
    expect((screen.getByLabelText("Runtime inputs JSON") as HTMLTextAreaElement).value).toBe(
      JSON.stringify({ legacyField: "visible", ticker: null }, null, 2),
    );
    fireEvent.change(screen.getByLabelText("Saved runtime input preset name"), {
      target: { value: "Still invalid" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save current JSON" }));
    expect(createRuntimeInputPresetEntryMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("radio", { name: "Form" }));
    expect(screen.getByTestId("runtime-input-json-mode-notice")).toBeVisible();
  });

  it("reloads nullable saved nulls and submits them when the current schema still allows null", async () => {
    useWorkflowPackageLaunchMock.mockReturnValue({
      data: {
        ...launchRead,
        inputSchema: {
          properties: {
            ticker: { title: "Ticker", type: ["string", "null"] },
          },
          required: ["ticker"],
          type: "object",
        },
      },
      error: null,
      isError: false,
      isPending: false,
    });
    const preset = runtimeInputEntry({
      id: 7,
      name: "Nullable preset",
      payload: { ticker: null },
      slot: "preset",
    });
    useWorkflowPackageRuntimeInputRegistryMock.mockReturnValue(
      runtimeInputRegistry({ presets: [preset] }),
    );
    renderLaunchPage();

    await selectSingleWorkflow();
    fireEvent.click(screen.getByRole("button", { name: "Load saved runtime input preset Nullable preset" }));

    expect(await screen.findByTestId("runtime-input-primary-form")).toBeVisible();
    expect((screen.getByLabelText("Runtime inputs JSON") as HTMLTextAreaElement).value).toBe(
      JSON.stringify({ ticker: null }, null, 2),
    );
    await completeReadyPreflight();
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    await waitFor(() => expect(createLaunchMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: { parameters: { ticker: null }, workflowKey: "market_review" },
    }));
  });

  it("shows workflow-scoped loading and saved runtime input preset cap messaging in the saved inputs helper", async () => {
    const presetEntries = Array.from({ length: 20 }, (_, index) => runtimeInputEntry({
      id: index + 1,
      name: `Preset ${index + 1}`,
      slot: "preset",
      updatedAt: `2026-05-08T10:${String(index).padStart(2, "0")}:00Z`,
    }));
    useWorkflowPackageRuntimeInputRegistryMock.mockReturnValue(runtimeInputRegistry({ isFetching: true, presets: presetEntries }));
    renderLaunchPage();

    await selectSingleWorkflow();
    const helper = await screen.findByTestId("runtime-input-saved-inputs-helper");
    expect(within(helper).getByText(/loading saved inputs for market_review/i)).toBeVisible();
    expect(within(helper).getByText("20/20")).toBeVisible();
    expect(within(helper).getByText(/saved runtime input presets are capped at 20 per workflow/i)).toBeVisible();
    fireEvent.change(screen.getByLabelText("Saved runtime input preset name"), { target: { value: "Overflow preset" } });
    expect(screen.getByRole("button", { name: "Save current JSON" })).toBeDisabled();
  });

  it("keeps saved runtime input presets isolated by workflow key when switching workflows", async () => {
    const advisorySchema = {
      properties: {
        ticker: { title: "Ticker", type: "string" },
      },
      required: ["ticker"],
      type: "object",
    };
    const newsSchema = {
      properties: {
        lookbackDays: { title: "Lookback Days", type: "integer" },
        query: { title: "Query", type: "string" },
      },
      required: ["query"],
      type: "object",
    };
    useWorkflowPackageManifestMock.mockReturnValue({
      data: manifestRead([
        { description: "Advisory workflow", inputSchema: advisorySchema, key: "advisory_research", name: "Advisory Research" },
        { description: "News workflow", inputSchema: newsSchema, key: "news_research", name: "News Research" },
      ]),
      error: null,
      isError: false,
      isPending: false,
    });
    useWorkflowPackageLaunchMock.mockImplementation((_packageId, workflowKey) => ({
      data: workflowKey === "news_research"
        ? { ...launchRead, description: "News workflow", inputSchema: newsSchema, name: "News Research", workflowKey: "news_research" }
        : { ...launchRead, description: "Advisory workflow", inputSchema: advisorySchema, name: "Advisory Research", workflowKey: "advisory_research" },
      error: null,
      isError: false,
      isPending: false,
    }));
    useWorkflowPackageRuntimeInputRegistryMock.mockImplementation((_packageId, workflowKey) => {
      if (workflowKey === "news_research") {
        return runtimeInputRegistry({
          presets: [
            runtimeInputEntry({
              id: 19,
              name: "Breaking News",
              payload: { lookbackDays: 7, query: "AI earnings" },
              slot: "preset",
              workflowKey: "news_research",
            }),
          ],
        });
      }
      if (workflowKey === "advisory_research") {
        return runtimeInputRegistry({
          presets: [
            runtimeInputEntry({
              id: 7,
              name: "Baseline preset",
              payload: { ticker: "MSFT" },
              slot: "preset",
              workflowKey: "advisory_research",
            }),
          ],
        });
      }
      return runtimeInputRegistry();
    });

    renderLaunchPage();

    await chooseWorkflow(/^Advisory Research$/);
    const runtimeJson = (await screen.findByLabelText("Runtime inputs JSON")) as HTMLTextAreaElement;
    await waitFor(() => expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "" }, null, 2)));
    expect(screen.getByRole("button", { name: "Load saved runtime input preset Baseline preset" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Load saved runtime input preset Baseline preset" }));
    expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "MSFT" }, null, 2));

    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"AAPL"}' } });
    await chooseWorkflow(/^News Research$/);

    await waitFor(() => expect(runtimeJson.value).toBe(JSON.stringify({ query: "" }, null, 2)));
    expect(screen.getByTestId("runtime-input-saved-inputs-helper")).toHaveTextContent("news_research");
    expect(screen.queryByRole("button", { name: "Load saved runtime input preset Baseline preset" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load saved runtime input preset Breaking News" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Load saved runtime input preset Breaking News" }));
    expect(runtimeJson.value).toBe(JSON.stringify({ lookbackDays: 7, query: "AI earnings" }, null, 2));

    await chooseWorkflow(/^Advisory Research$/);

    await waitFor(() => expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "" }, null, 2)));
    expect(screen.getByTestId("runtime-input-saved-inputs-helper")).toHaveTextContent("advisory_research");
    expect(screen.getByRole("button", { name: "Load saved runtime input preset Baseline preset" })).toBeVisible();
  });

  it("blocks launch when advanced JSON is invalid", async () => {
    const preset = runtimeInputEntry({
      id: 7,
      name: "Baseline preset",
      slot: "preset",
    });
    useWorkflowPackageRuntimeInputRegistryMock.mockReturnValue(
      runtimeInputRegistry({ presets: [preset] }),
    );
    renderLaunchPage();

    await selectSingleWorkflow();
    await completeReadyPreflight();
    preflightPackageMock.mockClear();
    switchToJsonMode();
    const runtimeJson = screen.getByLabelText(
      "Runtime inputs JSON",
    ) as HTMLTextAreaElement;
    fireEvent.change(runtimeJson, { target: { value: '{"ticker":' } });
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    const feedback = await screen.findByTestId(
      "runtime-input-validation-feedback",
    );
    expect(feedback).toHaveTextContent("Runtime inputs JSON");
    expect(preflightPackageMock).not.toHaveBeenCalled();
    expect(createLaunchMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /run preflight/i }));
    expect(preflightPackageMock).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Saved runtime input preset name"), {
      target: { value: "Broken preset" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save current JSON" }));
    expect(createRuntimeInputPresetEntryMock).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", {
        name: "Overwrite saved runtime input preset Baseline preset",
      }),
    );
    expect(updateRuntimeInputPresetEntryMock).not.toHaveBeenCalled();
  });

  it("rejects non-nullable advanced JSON null before preflight or launch API calls", async () => {
    renderLaunchPage();

    await selectSingleWorkflow();
    await completeReadyPreflight();
    preflightPackageMock.mockClear();
    switchToJsonMode();
    fireEvent.change(screen.getByLabelText("Runtime inputs JSON"), {
      target: { value: '{"ticker":null}' },
    });
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    const feedback = await screen.findByTestId("runtime-input-validation-feedback");
    expect(feedback).toHaveTextContent("parameters.ticker");
    expect(feedback).toHaveTextContent("Null is only allowed for nullable runtime input fields.");
    expect(preflightPackageMock).not.toHaveBeenCalled();
    expect(createLaunchMock).not.toHaveBeenCalled();
  });

  it("applies valid advanced JSON to the launch form", async () => {
    renderLaunchPage();

    await selectSingleWorkflow();
    switchToJsonMode();
    const runtimeJson = screen.getByLabelText(
      "Runtime inputs JSON",
    ) as HTMLTextAreaElement;
    expect(runtimeJson).not.toHaveAttribute("readonly");
    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"NVDA"}' } });
    fireEvent.click(screen.getByRole("button", { name: "Apply JSON to form" }));

    const tickerInput = await screen.findByRole("textbox", { name: "Ticker" });
    expect(tickerInput).toHaveValue("NVDA");
    expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "NVDA" }, null, 2));
    expect(screen.getByTestId("runtime-input-primary-form")).toBeVisible();
  });

  it("renders schema form as the primary launch input surface", async () => {
    renderLaunchPage();

    await selectSingleWorkflow();
    const schemaForm = await screen.findByTestId("runtime-input-schema-form");
    expect(schemaForm).toBeVisible();
    const tickerInput = screen.getByRole("textbox", { name: "Ticker" });
    fireEvent.change(tickerInput, { target: { value: "AAPL" } });

    expect((screen.getByLabelText("Runtime inputs JSON") as HTMLTextAreaElement).value).toBe(
      JSON.stringify({ ticker: "AAPL" }, null, 2),
    );
    await completeReadyPreflight();
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    await waitFor(() => expect(createLaunchMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: { parameters: { ticker: "AAPL" }, workflowKey: "market_review" },
    }));
  });

  it("renders every declared workflow input as visible or addable", async () => {
    useWorkflowPackageLaunchMock.mockReturnValue({
      data: {
        ...launchRead,
        inputSchema: {
          properties: {
            includeNews: { title: "Include News", type: "boolean" },
            lookbackDays: { default: 5, title: "Lookback Days", type: "integer" },
            notes: {
              description: "Optional memo for this launch.",
              title: "Notes",
              type: "string",
            },
            ticker: { title: "Ticker", type: "string" },
          },
          required: ["ticker", "includeNews"],
          type: "object",
        },
      },
      error: null,
      isError: false,
      isPending: false,
    });
    renderLaunchPage();

    await selectSingleWorkflow();
    const primaryForm = await screen.findByTestId("runtime-input-primary-form");
    const schemaForm = screen.getByTestId("runtime-input-schema-form");
    expect(primaryForm).toHaveTextContent("Supported-schema input surface");
    expect(within(schemaForm).getByRole("textbox", { name: "Ticker" })).toBeVisible();
    expect(within(schemaForm).getByRole("switch", { name: "Include News" })).toBeVisible();
    expect(within(schemaForm).getByRole("spinbutton", { name: "Lookback Days" })).toHaveValue(5);
    expect(within(schemaForm).getByText("Notes")).toBeVisible();
    expect(within(schemaForm).getByText("Optional memo for this launch.")).toBeVisible();
    expect(within(schemaForm).getByRole("button", { name: "Add Field" })).toBeVisible();
    expect(within(schemaForm).queryByRole("textbox", { name: "Notes" })).not.toBeInTheDocument();
    const runtimeJson = screen.getByLabelText("Runtime inputs JSON") as HTMLTextAreaElement;
    expect(screen.getByTestId("runtime-input-advanced-json")).toHaveTextContent("Advanced JSON preview");
    expect(runtimeJson).toHaveAttribute("readonly");
    expect(runtimeJson.value).toBe(JSON.stringify({
      includeNews: false,
      lookbackDays: 5,
      ticker: "",
    }, null, 2));

    fireEvent.change(within(schemaForm).getByRole("textbox", { name: "Ticker" }), {
      target: { value: "AAPL" },
    });
    await completeReadyPreflight();
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));
    await waitFor(() => expect(createLaunchMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: {
        parameters: {
          includeNews: false,
          lookbackDays: 5,
          ticker: "AAPL",
        },
        workflowKey: "market_review",
      },
    }));

    fireEvent.click(within(schemaForm).getByRole("button", { name: "Add Field" }));
    expect(within(schemaForm).getByRole("textbox", { name: "Notes" })).toBeVisible();
  });

  it("removes optional no-default inputs from the submitted launch payload", async () => {
    useWorkflowPackageLaunchMock.mockReturnValue({
      data: {
        ...launchRead,
        inputSchema: {
          properties: {
            notes: { title: "Notes", type: "string" },
            ticker: { title: "Ticker", type: "string" },
          },
          required: ["ticker"],
          type: "object",
        },
      },
      error: null,
      isError: false,
      isPending: false,
    });
    renderLaunchPage();

    await selectSingleWorkflow();
    const schemaForm = await screen.findByTestId("runtime-input-schema-form");
    fireEvent.change(within(schemaForm).getByRole("textbox", { name: "Ticker" }), {
      target: { value: "AAPL" },
    });
    expect((screen.getByLabelText("Runtime inputs JSON") as HTMLTextAreaElement).value).toBe(
      JSON.stringify({ ticker: "AAPL" }, null, 2),
    );

    fireEvent.click(within(schemaForm).getByRole("button", { name: "Add Field" }));
    fireEvent.change(within(schemaForm).getByRole("textbox", { name: "Notes" }), {
      target: { value: "Include memo in this run" },
    });
    expect((screen.getByLabelText("Runtime inputs JSON") as HTMLTextAreaElement).value).toBe(
      JSON.stringify({ notes: "Include memo in this run", ticker: "AAPL" }, null, 2),
    );

    fireEvent.click(within(schemaForm).getByRole("button", { name: /remove optional field/i }));
    expect(within(schemaForm).queryByRole("textbox", { name: "Notes" })).not.toBeInTheDocument();
    expect((screen.getByLabelText("Runtime inputs JSON") as HTMLTextAreaElement).value).toBe(
      JSON.stringify({ ticker: "AAPL" }, null, 2),
    );
    await completeReadyPreflight();
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    await waitFor(() => expect(createLaunchMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: { parameters: { ticker: "AAPL" }, workflowKey: "market_review" },
    }));
  });

  it("renders optional inputs with defaults as active prefilled fields", async () => {
    useWorkflowPackageLaunchMock.mockReturnValue({
      data: {
        ...launchRead,
        inputSchema: {
          properties: {
            includeNews: { default: true, title: "Include News", type: "boolean" },
            lookbackDays: { default: 14, title: "Lookback Days", type: "integer" },
            notes: { title: "Notes", type: "string" },
            strategy: { default: "balanced", title: "Strategy", type: "string" },
            ticker: { title: "Ticker", type: "string" },
          },
          required: ["ticker"],
          type: "object",
        },
      },
      error: null,
      isError: false,
      isPending: false,
    });
    renderLaunchPage();

    await selectSingleWorkflow();
    const schemaForm = await screen.findByTestId("runtime-input-schema-form");
    expect(within(schemaForm).getByRole("spinbutton", { name: "Lookback Days" })).toHaveValue(14);
    expect(within(schemaForm).getByRole("textbox", { name: "Strategy" })).toHaveValue("balanced");
    expect(within(schemaForm).getByRole("switch", { name: "Include News" })).toBeChecked();
    expect(within(schemaForm).getByText("Notes")).toBeVisible();
    expect(within(schemaForm).queryByRole("textbox", { name: "Notes" })).not.toBeInTheDocument();
    expect((screen.getByLabelText("Runtime inputs JSON") as HTMLTextAreaElement).value).toBe(JSON.stringify({
      includeNews: true,
      lookbackDays: 14,
      strategy: "balanced",
      ticker: "",
    }, null, 2));

    fireEvent.change(within(schemaForm).getByRole("textbox", { name: "Ticker" }), {
      target: { value: "MSFT" },
    });
    await completeReadyPreflight();
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    await waitFor(() => expect(createLaunchMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: {
        parameters: {
          includeNews: true,
          lookbackDays: 14,
          strategy: "balanced",
          ticker: "MSFT",
        },
        workflowKey: "market_review",
      },
    }));
  });

  it("submits launch parameters from the schema-derived template", async () => {
    useWorkflowPackageLaunchMock.mockReturnValue({
      data: {
        ...launchRead,
        inputSchema: {
          properties: {
            includeNews: { title: "Include News", type: "boolean" },
            horizonDays: { title: "Horizon Days", type: "integer" },
            filters: {
              properties: { sector: { title: "Sector", type: "string" } },
              required: ["sector"],
              title: "Filters",
              type: "object",
            },
            comment: { title: "Comment", type: "string" },
            defaultLimit: { default: 10, title: "Default Limit", type: "integer" },
            emptyOverride: { default: "preset", title: "Empty Override", type: "string" },
          },
          required: ["includeNews", "horizonDays", "filters"],
          type: "object",
        },
      },
      error: null,
      isError: false,
      isPending: false,
    });
    renderLaunchPage();
    await selectSingleWorkflow();
    const runtimeJson = (await screen.findByLabelText("Runtime inputs JSON")) as HTMLTextAreaElement;
    expect(runtimeJson.value).toBe(JSON.stringify({
      defaultLimit: 10,
      emptyOverride: "preset",
      filters: { sector: "" },
      horizonDays: 0,
      includeNews: false,
    }, null, 2));
    expect(screen.queryByRole("textbox", { name: "Comment" })).not.toBeInTheDocument();

    fireEvent.change(runtimeJson, { target: { value: JSON.stringify({
      defaultLimit: 10,
      emptyOverride: "",
      filters: { sector: "technology" },
      horizonDays: 14,
      includeNews: true,
    }) } });
    await completeReadyPreflight();
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    await waitFor(() => expect(createLaunchMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: {
        parameters: {
          defaultLimit: 10,
          emptyOverride: "",
          filters: { sector: "technology" },
          horizonDays: 14,
          includeNews: true,
        },
        workflowKey: "market_review",
      },
    }));
  });

  it("resets raw JSON launch state when workflow selection or schema identity changes", async () => {
    const sharedSchema = {
      properties: { ticker: { title: "Ticker", type: "string" } },
      required: ["ticker"],
      type: "object",
    };
    useWorkflowPackageManifestMock.mockReturnValue({
      data: manifestRead([
        { description: "Reset workflow", inputSchema: sharedSchema, key: "reset_workflow", name: "Reset Workflow" },
        { description: "Alternate workflow", inputSchema: sharedSchema, key: "alternate_workflow", name: "Alternate Workflow" },
      ]),
      error: null,
      isError: false,
      isPending: false,
    });
    useWorkflowPackageLaunchMock.mockImplementation((_packageId, workflowKey) => ({
      data: {
        ...launchRead,
        inputSchema: sharedSchema,
        name: workflowKey === "alternate_workflow" ? "Alternate Workflow" : "Reset Workflow",
        workflowKey: workflowKey === "alternate_workflow" ? "alternate_workflow" : "reset_workflow",
      },
      error: null,
      isError: false,
      isPending: false,
    }));
    const view = renderLaunchPage();

    await chooseWorkflow(/^Reset Workflow$/);
    const runtimeJson = (await screen.findByLabelText("Runtime inputs JSON")) as HTMLTextAreaElement;
    await waitFor(() => expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "" }, null, 2)));
    switchToJsonMode();
    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"AAPL"}' } });
    expect(runtimeJson.value).toBe('{"ticker":"AAPL"}');

    fireEvent.click(screen.getByRole("button", { name: "Reset to template" }));
    expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "" }, null, 2));
    switchToJsonMode();
    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"MSFT"}' } });

    await chooseWorkflow(/^Alternate Workflow$/);
    await waitFor(() => expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "" }, null, 2)));
    useWorkflowPackageLaunchMock.mockReturnValue({
      data: {
        ...launchRead,
        inputSchema: { properties: { symbol: { title: "Symbol", type: "string" } }, required: ["symbol"], type: "object" },
        name: "Alternate Workflow",
        workflowKey: "alternate_workflow",
      },
      error: null,
      isError: false,
      isPending: false,
    });
    view.rerender(
      <MemoryRouter initialEntries={["/workflow-packages/42/run"]}>
        <Routes><Route path="/workflow-packages/:packageId/run" element={<WorkflowPackageLaunchPage />} /></Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(runtimeJson.value).toBe(JSON.stringify({ symbol: "" }, null, 2)));
  });

  it("preserves user-entered runtime JSON when workflow metadata rebinds after selector changes", async () => {
    const sharedSchema = {
      properties: { ticker: { title: "Ticker", type: "string" } },
      required: ["ticker"],
      type: "object",
    };
    useWorkflowPackageManifestMock.mockReturnValue({
      data: manifestRead([
        { description: "Reset workflow", inputSchema: sharedSchema, key: "reset_workflow", name: "Reset Workflow" },
        { description: "Alternate workflow", inputSchema: sharedSchema, key: "alternate_workflow", name: "Alternate Workflow" },
      ]),
      error: null,
      isError: false,
      isPending: false,
    });
    useWorkflowPackageLaunchMock.mockImplementation((_packageId, workflowKey) => ({
      data: {
        ...launchRead,
        inputSchema: sharedSchema,
        name: workflowKey === "alternate_workflow" ? "Alternate Workflow" : "Reset Workflow",
        workflowKey: workflowKey === "alternate_workflow" ? "alternate_workflow" : "reset_workflow",
      },
      error: null,
      isError: false,
      isPending: false,
    }));
    const view = renderLaunchPage();

    await chooseWorkflow(/^Reset Workflow$/);
    const runtimeJson = (await screen.findByLabelText("Runtime inputs JSON")) as HTMLTextAreaElement;
    await chooseWorkflow(/^Alternate Workflow$/);
    switchToJsonMode();
    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"AAPL"}' } });
    useWorkflowPackageLaunchMock.mockReturnValue({
      data: {
        ...launchRead,
        inputSchema: sharedSchema,
        name: "Alternate Workflow",
        workflowKey: "alternate_workflow",
      },
      error: null,
      isError: false,
      isPending: false,
    });
    view.rerender(
      <MemoryRouter initialEntries={["/workflow-packages/42/run"]}>
        <Routes><Route path="/workflow-packages/:packageId/run" element={<WorkflowPackageLaunchPage />} /></Routes>
      </MemoryRouter>,
    );

    expect(runtimeJson.value).toBe('{"ticker":"AAPL"}');
    await completeReadyPreflight();
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    await waitFor(() => expect(createLaunchMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: { parameters: { ticker: "AAPL" }, workflowKey: "alternate_workflow" },
    }));
  });

  it("rejects non-object raw JSON locally", async () => {
    useWorkflowPackageLaunchMock.mockReturnValue({
      data: {
        ...launchRead,
        inputSchema: { additionalProperties: true, properties: { ticker: { title: "Ticker", type: "string" } }, required: ["ticker"], type: "object" },
      },
      error: null,
      isError: false,
      isPending: false,
    });
    renderLaunchPage();

    await selectSingleWorkflow();
    await completeReadyPreflight();
    preflightPackageMock.mockClear();
    fireEvent.change(await screen.findByLabelText("Runtime inputs JSON"), { target: { value: "[]" } });
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    expect(await screen.findByTestId("runtime-input-validation-feedback")).toHaveTextContent("Runtime inputs JSON must be a valid object.");
    expect(preflightPackageMock).not.toHaveBeenCalled();
    expect(createLaunchMock).not.toHaveBeenCalled();
  });

  it("shows backend path-specific launch validation details inline", async () => {
    createLaunchMock.mockRejectedValueOnce(new ApiRequestError({
      code: "validation_error",
      details: [{ field: "parameters.ticker", issue: "Ticker blocked" }],
      message: "Validation failed",
      status: 422,
    }));
    renderLaunchPage();

    await selectSingleWorkflow();
    fireEvent.change(await screen.findByRole("textbox", { name: "Ticker" }), { target: { value: "AAPL" } });
    await completeReadyPreflight();
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    const feedback = await screen.findByTestId("runtime-input-validation-feedback");
    expect(feedback).toHaveTextContent("parameters.ticker");
    expect(feedback).toHaveTextContent("Ticker blocked");
  });

  it.each([
    {
      expectedKeyword: /additionalProperties/i,
      inputSchema: { additionalProperties: true, properties: { ticker: { title: "Ticker", type: "string" } }, required: ["ticker"], type: "object" },
    },
    {
      expectedKeyword: /patternProperties/i,
      inputSchema: { patternProperties: { "^x-": { type: "string" } }, properties: {}, type: "object" },
    },
  ])("keeps raw JSON fallback for unsupported workflow input schemas", async ({ expectedKeyword, inputSchema }) => {
    useWorkflowPackageLaunchMock.mockReturnValue({
      data: { ...launchRead, inputSchema },
      error: null,
      isError: false,
      isPending: false,
    });
    renderLaunchPage();

    await selectSingleWorkflow();
    const schemaWarning = await screen.findByTestId("runtime-input-schema-template-warning");
    expect(within(schemaWarning).getByText("Schema template started empty")).toBeVisible();
    fireEvent.click(within(schemaWarning).getByRole("button", { name: "Details" }));
    expect(within(schemaWarning).getByText(expectedKeyword)).toBeVisible();
    expect(screen.queryByRole("textbox", { name: "Ticker" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Runtime inputs JSON"), {
      target: { value: '{"enabled":true,"limit":3,"filters":{"sector":"energy"}}' },
    });
    await completeReadyPreflight();
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    await waitFor(() => expect(createLaunchMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: {
        parameters: { enabled: true, filters: { sector: "energy" }, limit: 3 },
        workflowKey: "market_review",
      },
    }));
  });
});
