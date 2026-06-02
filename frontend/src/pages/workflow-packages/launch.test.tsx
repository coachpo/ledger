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
  createRuntimeInputPersonalEntryMock,
  deleteRuntimeInputPersonalEntryMock,
  navigateMock,
  preflightPackageMock,
  updateRuntimeInputPersonalEntryMock,
  useCreateLaunchMock,
  useCreateRuntimeInputPersonalEntryMock,
  useDeleteRuntimeInputPersonalEntryMock,
  usePreflightPackageMock,
  useUpdateRuntimeInputPersonalEntryMock,
  useWorkflowPackageLaunchMock,
  useWorkflowPackageManifestMock,
  useWorkflowPackageMock,
  useWorkflowPackageRuntimeInputRegistryMock,
} = vi.hoisted(() => ({
  createLaunchMock: vi.fn(),
  createRuntimeInputPersonalEntryMock: vi.fn(),
  deleteRuntimeInputPersonalEntryMock: vi.fn(),
  navigateMock: vi.fn(),
  preflightPackageMock: vi.fn(),
  updateRuntimeInputPersonalEntryMock: vi.fn(),
  useCreateLaunchMock: vi.fn(),
  useCreateRuntimeInputPersonalEntryMock: vi.fn(),
  useDeleteRuntimeInputPersonalEntryMock: vi.fn(),
  usePreflightPackageMock: vi.fn(),
  useUpdateRuntimeInputPersonalEntryMock: vi.fn(),
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
  toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

vi.mock("@/hooks/use-workflow-packages", () => ({
  useCreateWorkflowPackageLaunch: () => useCreateLaunchMock(),
  useCreateWorkflowPackageRuntimeInputPersonalEntry: () => useCreateRuntimeInputPersonalEntryMock(),
  useDeleteWorkflowPackageRuntimeInputPersonalEntry: () => useDeleteRuntimeInputPersonalEntryMock(),
  usePreflightWorkflowPackage: () => usePreflightPackageMock(),
  useUpdateWorkflowPackageRuntimeInputPersonalEntry: () => useUpdateRuntimeInputPersonalEntryMock(),
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
  personal?: WorkflowPackageRuntimeInputEntryRead[];
} = {}) {
  return {
    data: {
      currentMetadata: null,
      history: overrides.history ?? [],
      packageId: 42,
      packageKey: "market_review_package",
      personal: overrides.personal ?? [],
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
    createRuntimeInputPersonalEntryMock.mockReset();
    updateRuntimeInputPersonalEntryMock.mockReset();
    deleteRuntimeInputPersonalEntryMock.mockReset();
    useWorkflowPackageMock.mockReset();
    useWorkflowPackageLaunchMock.mockReset();
    useWorkflowPackageManifestMock.mockReset();
    useWorkflowPackageRuntimeInputRegistryMock.mockReset();
    preflightPackageMock.mockResolvedValue(launchRead);
    createLaunchMock.mockResolvedValue({ createdAt: "2026-05-08T10:00:00Z", id: 99, status: "queued", workflowKey: "market_review", workflowPackageId: 42, workflowPackageKey: "market_review_package" });
    createRuntimeInputPersonalEntryMock.mockResolvedValue(runtimeInputEntry({ id: 30, name: "Saved preset", slot: "personal" }));
    updateRuntimeInputPersonalEntryMock.mockResolvedValue(runtimeInputEntry({ id: 7, name: "Updated preset", slot: "personal" }));
    deleteRuntimeInputPersonalEntryMock.mockResolvedValue(undefined);
    useWorkflowPackageMock.mockReturnValue({ data: packageRead, error: null, isError: false, isPending: false });
    useWorkflowPackageManifestMock.mockReturnValue({ data: singleWorkflowManifestRead, error: null, isError: false, isPending: false });
    useWorkflowPackageLaunchMock.mockReturnValue({ data: launchRead, error: null, isError: false, isPending: false });
    usePreflightPackageMock.mockReturnValue({ isPending: false, mutateAsync: preflightPackageMock });
    useCreateLaunchMock.mockReturnValue({ isPending: false, mutateAsync: createLaunchMock });
    useCreateRuntimeInputPersonalEntryMock.mockReturnValue({ isPending: false, mutateAsync: createRuntimeInputPersonalEntryMock });
    useUpdateRuntimeInputPersonalEntryMock.mockReturnValue({ isPending: false, mutateAsync: updateRuntimeInputPersonalEntryMock });
    useDeleteRuntimeInputPersonalEntryMock.mockReturnValue({ isPending: false, mutateAsync: deleteRuntimeInputPersonalEntryMock });
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
            field: "spec.agents[1].modelConnection",
            issue: "This connection will degrade to plain text output",
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
    expect(warnings).toHaveTextContent(/This connection will degrade to plain text output/i);
    expect(warnings).toHaveTextContent(/omits usage metadata/i);
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
    expect(screen.getByLabelText("Personal preset name")).toBeDisabled();
    expect(screen.getByTestId("runtime-input-saved-inputs-helper")).toHaveTextContent("workflow pending");
    expect(screen.getByTestId("runtime-input-saved-inputs-helper")).not.toHaveTextContent(
      /loading saved inputs for this workflow/i,
    );

    await chooseWorkflow(/^News Research$/);

    await waitFor(() => expect(workflowSelector()).toHaveTextContent("News Research"));
    expect(screen.getByTestId("workflow-package-launch-next-step")).toHaveTextContent("Run preflight to load launch metadata and validate this package before launch.");
    expect(screen.getByRole("button", { name: /run preflight/i })).not.toBeDisabled();
    expect(screen.getByRole("tab", { name: /presets/i })).not.toBeDisabled();
    expect(screen.getByRole("tab", { name: /history/i })).not.toBeDisabled();
    expect(screen.getByLabelText("Runtime inputs JSON")).not.toBeDisabled();
    expect(screen.getByLabelText("Personal preset name")).not.toBeDisabled();
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
    expect(screen.queryByRole("textbox", { name: "Ticker" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Runtime inputs JSON"), { target: { value: '{"ticker":"AAPL"}' } });
    await completeReadyPreflight();
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    await waitFor(() => expect(preflightPackageMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: { parameters: {}, workflowKey: "market_review" },
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

  it("manages saved personal inputs and load-only history without replacing the raw editor", async () => {
    const personal = runtimeInputEntry({
      id: 7,
      name: "Baseline preset",
      payload: { ticker: "MSFT" },
      slot: "personal",
      stale: {
        reasons: [{ current: "manifest-hash-123", field: "manifestHash", issue: "Manifest changed", stored: "old-manifest" }],
        stale: true,
      },
      updatedAt: "2026-05-08T09:00:00Z",
    });
    const olderHistory = runtimeInputEntry({ createdAt: "2026-05-08T08:00:00Z", id: 10, payload: { ticker: "TSLA" }, slot: "history", sourceRunId: 88 });
    const newerHistory = runtimeInputEntry({ createdAt: "2026-05-08T11:00:00Z", id: 11, payload: { ticker: "NVDA" }, slot: "history", sourceRunId: 99 });
    useWorkflowPackageRuntimeInputRegistryMock.mockReturnValue(runtimeInputRegistry({ history: [olderHistory, newerHistory], personal: [personal] }));
    renderLaunchPage();

    await selectSingleWorkflow();
    const helper = await screen.findByTestId("runtime-input-saved-inputs-helper");
    expect(within(helper).getByText("Saved inputs")).toBeVisible();
    expect(within(helper).getByText("1/20")).toBeVisible();
    expect(within(helper).getByText("2/20")).toBeVisible();
    expect(within(screen.getByTestId("saved-input-personal-7")).getByText("Stale")).toBeVisible();
    expect(within(screen.getByTestId("saved-input-personal-7")).getByText(/manifestHash: Manifest changed/i)).toBeVisible();

    const runtimeJson = (await screen.findByLabelText("Runtime inputs JSON")) as HTMLTextAreaElement;
    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"AAPL"}' } });
    fireEvent.change(screen.getByLabelText("Personal preset name"), { target: { value: "Morning preset" } });
    fireEvent.click(screen.getByRole("button", { name: "Save current JSON" }));

    await waitFor(() => expect(createRuntimeInputPersonalEntryMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: { name: "Morning preset", payload: { ticker: "AAPL" } },
      workflowKey: "market_review",
    }));

    fireEvent.click(screen.getByRole("button", { name: "Load personal input Baseline preset" }));
    expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "MSFT" }, null, 2));
    expect(createLaunchMock).not.toHaveBeenCalled();

    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"GOOG"}' } });
    fireEvent.click(screen.getByRole("button", { name: "Overwrite personal input Baseline preset" }));
    await waitFor(() => expect(updateRuntimeInputPersonalEntryMock).toHaveBeenCalledWith({
      entryId: 7,
      packageId: "42",
      payload: { name: "Baseline preset", payload: { ticker: "GOOG" } },
      workflowKey: "market_review",
    }));

    fireEvent.click(screen.getByRole("button", { name: "Delete personal input Baseline preset" }));
    await waitFor(() => expect(deleteRuntimeInputPersonalEntryMock).toHaveBeenCalledWith({ entryId: 7, packageId: "42", workflowKey: "market_review" }));

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

  it("shows workflow-scoped loading and personal cap messaging in the saved inputs helper", async () => {
    const personalEntries = Array.from({ length: 20 }, (_, index) => runtimeInputEntry({
      id: index + 1,
      name: `Preset ${index + 1}`,
      slot: "personal",
      updatedAt: `2026-05-08T10:${String(index).padStart(2, "0")}:00Z`,
    }));
    useWorkflowPackageRuntimeInputRegistryMock.mockReturnValue(runtimeInputRegistry({ isFetching: true, personal: personalEntries }));
    renderLaunchPage();

    await selectSingleWorkflow();
    const helper = await screen.findByTestId("runtime-input-saved-inputs-helper");
    expect(within(helper).getByText(/loading saved inputs for market_review/i)).toBeVisible();
    expect(within(helper).getByText("20/20")).toBeVisible();
    expect(within(helper).getByText(/personal presets are capped at 20 per workflow/i)).toBeVisible();
    fireEvent.change(screen.getByLabelText("Personal preset name"), { target: { value: "Overflow preset" } });
    expect(screen.getByRole("button", { name: "Save current JSON" })).toBeDisabled();
  });

  it("keeps saved personal inputs isolated by workflow key when switching workflows", async () => {
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
          personal: [
            runtimeInputEntry({
              id: 19,
              name: "Breaking News",
              payload: { lookbackDays: 7, query: "AI earnings" },
              slot: "personal",
              workflowKey: "news_research",
            }),
          ],
        });
      }
      if (workflowKey === "advisory_research") {
        return runtimeInputRegistry({
          personal: [
            runtimeInputEntry({
              id: 7,
              name: "Baseline preset",
              payload: { ticker: "MSFT" },
              slot: "personal",
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
    expect(screen.getByRole("button", { name: "Load personal input Baseline preset" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Load personal input Baseline preset" }));
    expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "MSFT" }, null, 2));

    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"AAPL"}' } });
    await chooseWorkflow(/^News Research$/);

    await waitFor(() => expect(runtimeJson.value).toBe(JSON.stringify({ query: "" }, null, 2)));
    expect(screen.getByTestId("runtime-input-saved-inputs-helper")).toHaveTextContent("news_research");
    expect(screen.queryByRole("button", { name: "Load personal input Baseline preset" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load personal input Breaking News" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Load personal input Breaking News" }));
    expect(runtimeJson.value).toBe(JSON.stringify({ lookbackDays: 7, query: "AI earnings" }, null, 2));

    await chooseWorkflow(/^Advisory Research$/);

    await waitFor(() => expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "" }, null, 2)));
    expect(screen.getByTestId("runtime-input-saved-inputs-helper")).toHaveTextContent("advisory_research");
    expect(screen.getByRole("button", { name: "Load personal input Baseline preset" })).toBeVisible();
  });

  it("submits raw launch parameters from the schema-derived template", async () => {
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
    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"AAPL"}' } });
    expect(runtimeJson.value).toBe('{"ticker":"AAPL"}');

    fireEvent.click(screen.getByRole("button", { name: "Reset to template" }));
    expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "" }, null, 2));
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
      details: [{ field: "parameters.extra", issue: "Unknown field" }],
      message: "Validation failed",
      status: 422,
    }));
    renderLaunchPage();

    await selectSingleWorkflow();
    fireEvent.change(await screen.findByLabelText("Runtime inputs JSON"), { target: { value: '{"ticker":"AAPL","extra":true}' } });
    await completeReadyPreflight();
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    const feedback = await screen.findByTestId("runtime-input-validation-feedback");
    expect(feedback).toHaveTextContent("parameters.extra");
    expect(feedback).toHaveTextContent("Unknown field");
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
  ])("keeps one raw JSON editor when templates start empty", async ({ expectedKeyword, inputSchema }) => {
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
