import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError } from "@/lib/api-client";
import type {
  WorkflowPackageLaunchRead,
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
    useWorkflowPackageRuntimeInputRegistryMock.mockReset();
    preflightPackageMock.mockResolvedValue(launchRead);
    createLaunchMock.mockResolvedValue({ createdAt: "2026-05-08T10:00:00Z", id: 99, status: "queued", workflowKey: "market_review", workflowPackageId: 42, workflowPackageKey: "market_review_package" });
    createRuntimeInputPersonalEntryMock.mockResolvedValue(runtimeInputEntry({ id: 30, name: "Saved preset", slot: "personal" }));
    updateRuntimeInputPersonalEntryMock.mockResolvedValue(runtimeInputEntry({ id: 7, name: "Updated preset", slot: "personal" }));
    deleteRuntimeInputPersonalEntryMock.mockResolvedValue(undefined);
    useWorkflowPackageMock.mockReturnValue({ data: packageRead, error: null, isError: false, isPending: false });
    useWorkflowPackageLaunchMock.mockReturnValue({ data: launchRead, error: null, isError: false, isPending: false });
    usePreflightPackageMock.mockReturnValue({ isPending: false, mutateAsync: preflightPackageMock });
    useCreateLaunchMock.mockReturnValue({ isPending: false, mutateAsync: createLaunchMock });
    useCreateRuntimeInputPersonalEntryMock.mockReturnValue({ isPending: false, mutateAsync: createRuntimeInputPersonalEntryMock });
    useUpdateRuntimeInputPersonalEntryMock.mockReturnValue({ isPending: false, mutateAsync: updateRuntimeInputPersonalEntryMock });
    useDeleteRuntimeInputPersonalEntryMock.mockReturnValue({ isPending: false, mutateAsync: deleteRuntimeInputPersonalEntryMock });
    useWorkflowPackageRuntimeInputRegistryMock.mockReturnValue(runtimeInputRegistry());
  });

  it("renders a dedicated launch page with read-only saved package context", async () => {
    renderLaunchPage();

    expect(screen.getByTestId("workflow-package-launch-page")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Launch Workflow Package" })).toBeVisible();
    expect(screen.getByText("Saved package launch")).toBeVisible();
    expect(screen.getByText("Market Review Package")).toBeVisible();
    expect(screen.getAllByText("market_review_package").length).toBeGreaterThan(0);
    expect(screen.getByText(/Launch uses persisted package state/i)).toBeVisible();
    expect(screen.getByRole("link", { name: "Open authoring editor" })).toHaveAttribute("href", "/workflow-packages/42");
    expect(screen.queryByTestId("workflow-package-editor-shell")).not.toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(useWorkflowPackageMock).toHaveBeenCalledWith("42");
    await waitFor(() => expect(useWorkflowPackageLaunchMock).toHaveBeenLastCalledWith("42", "market_review"));
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

  it("shows launch metadata loading and load-error states", () => {
    useWorkflowPackageLaunchMock.mockReturnValue({ data: undefined, error: null, isError: false, isPending: true });
    const loadingView = renderLaunchPage();
    expect(screen.getByText("Loading launch metadata...")).toBeVisible();
    loadingView.unmount();

    useWorkflowPackageLaunchMock.mockReturnValue({ data: undefined, error: new Error("Launch metadata failed"), isError: true, isPending: false });
    const errorView = renderLaunchPage();
    expect(screen.getByTestId("workflow-package-launch-metadata-error")).toHaveTextContent("Launch metadata failed");
    errorView.unmount();
  });

  it("launches a package run after preflight and navigates to run detail", async () => {
    renderLaunchPage();

    await waitFor(() => expect(screen.getByLabelText("Workflow key")).toHaveValue("market_review"));
    const launchPanel = await screen.findByTestId("workflow-package-launch-tab");
    expect(within(launchPanel).queryByText("Workflow")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Ticker" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Runtime inputs JSON"), { target: { value: '{"ticker":"AAPL"}' } });
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

    await waitFor(() => expect(screen.getByLabelText("Workflow key")).toHaveValue("market_review"));
    fireEvent.change(screen.getByLabelText("Runtime inputs JSON"), { target: { value: '{"ticker":"AAPL"}' } });
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    expect(await screen.findByText(/Missing model connection primary_model/i)).toBeVisible();
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

    const helper = await screen.findByTestId("runtime-input-saved-inputs-helper");
    expect(within(helper).getByText("Saved Inputs")).toBeVisible();
    expect(within(helper).getByText("1/20")).toBeVisible();
    expect(within(helper).getByText("2/20")).toBeVisible();
    expect(within(screen.getByTestId("saved-input-personal-7")).getByText("Stale")).toBeVisible();
    expect(within(screen.getByTestId("saved-input-personal-7")).getByText(/manifestHash: Manifest changed/i)).toBeVisible();
    expect(screen.getByTestId("saved-input-history-11").compareDocumentPosition(screen.getByTestId("saved-input-history-10")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

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

    const helper = await screen.findByTestId("runtime-input-saved-inputs-helper");
    expect(within(helper).getByText(/loading saved inputs for market_review/i)).toBeVisible();
    expect(within(helper).getByText("20/20")).toBeVisible();
    expect(within(helper).getByText(/personal presets are capped at 20 per workflow/i)).toBeVisible();
    fireEvent.change(screen.getByLabelText("Personal preset name"), { target: { value: "Overflow preset" } });
    expect(screen.getByRole("button", { name: "Save current JSON" })).toBeDisabled();
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

  it("resets raw JSON launch state when workflow key or schema identity changes", async () => {
    const resetLaunchRead: WorkflowPackageLaunchRead = {
      ...launchRead,
      inputSchema: { properties: { ticker: { title: "Ticker", type: "string" } }, required: ["ticker"], type: "object" },
      workflowKey: "reset_workflow",
    };
    useWorkflowPackageLaunchMock.mockReturnValue({ data: resetLaunchRead, error: null, isError: false, isPending: false });
    const view = renderLaunchPage();

    const runtimeJson = (await screen.findByLabelText("Runtime inputs JSON")) as HTMLTextAreaElement;
    expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "" }, null, 2));
    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"AAPL"}' } });
    expect(runtimeJson.value).toBe('{"ticker":"AAPL"}');

    fireEvent.click(screen.getByRole("button", { name: "Reset to template" }));
    expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "" }, null, 2));
    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"MSFT"}' } });

    fireEvent.change(screen.getByLabelText("Workflow key"), { target: { value: "alternate_workflow" } });
    await waitFor(() => expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "" }, null, 2)));
    useWorkflowPackageLaunchMock.mockReturnValue({
      data: { ...resetLaunchRead, inputSchema: { properties: { symbol: { title: "Symbol", type: "string" } }, required: ["symbol"], type: "object" } },
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

  it("preserves user-entered runtime JSON when workflow metadata rebinds after key change", async () => {
    const initialLaunchRead: WorkflowPackageLaunchRead = {
      ...launchRead,
      inputSchema: { properties: { ticker: { title: "Ticker", type: "string" } }, required: ["ticker"], type: "object" },
      workflowKey: "reset_workflow",
    };
    useWorkflowPackageLaunchMock.mockReturnValue({ data: initialLaunchRead, error: null, isError: false, isPending: false });
    const view = renderLaunchPage();

    await waitFor(() => expect(screen.getByLabelText("Workflow key")).toHaveValue("reset_workflow"));
    const runtimeJson = (await screen.findByLabelText("Runtime inputs JSON")) as HTMLTextAreaElement;
    fireEvent.change(screen.getByLabelText("Workflow key"), { target: { value: "alternate_workflow" } });
    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"AAPL"}' } });
    useWorkflowPackageLaunchMock.mockReturnValue({
      data: { ...initialLaunchRead, workflowKey: "alternate_workflow" },
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
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    await waitFor(() => expect(createLaunchMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: { parameters: { ticker: "AAPL" }, workflowKey: "alternate_workflow" },
    }));
  });

  it("rejects non-object raw JSON locally", async () => {
    renderLaunchPage();

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

    fireEvent.change(await screen.findByLabelText("Runtime inputs JSON"), { target: { value: '{"ticker":"AAPL","extra":true}' } });
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

    expect(await screen.findByText("Schema template started empty")).toBeVisible();
    expect(screen.getByText(expectedKeyword)).toBeVisible();
    expect(screen.queryByRole("textbox", { name: "Ticker" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Runtime inputs JSON"), {
      target: { value: '{"enabled":true,"limit":3,"filters":{"sector":"energy"}}' },
    });
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
