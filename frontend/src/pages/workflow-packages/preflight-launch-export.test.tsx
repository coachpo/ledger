import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError } from "@/lib/api-client";
import type { WorkflowPackageLaunchRead, WorkflowPackageManifestRead, WorkflowPackageRead } from "@/lib/types/workflow-package";

import { WorkflowPackageEditorPage } from "./editor";

const {
  createLaunchMock,
  importPackageMock,
  navigateMock,
  preflightPackageMock,
  updatePackageMock,
  useCreateLaunchMock,
  useCreatePackageMock,
  useImportPackageMock,
  useModelConnectionsMock,
  usePreflightPackageMock,
  useToolsMock,
  useUpdatePackageMock,
  useValidatePackageMock,
  useWorkflowPackageLaunchMock,
  useWorkflowPackageManifestMock,
  useWorkflowPackageMock,
  useWorkflowPackageVersionsMock,
  validatePackageMock,
} = vi.hoisted(() => ({
  createLaunchMock: vi.fn(),
  importPackageMock: vi.fn(),
  navigateMock: vi.fn(),
  preflightPackageMock: vi.fn(),
  updatePackageMock: vi.fn(),
  useCreateLaunchMock: vi.fn(),
  useCreatePackageMock: vi.fn(),
  useImportPackageMock: vi.fn(),
  useModelConnectionsMock: vi.fn(),
  usePreflightPackageMock: vi.fn(),
  useToolsMock: vi.fn(),
  useUpdatePackageMock: vi.fn(),
  useValidatePackageMock: vi.fn(),
  useWorkflowPackageLaunchMock: vi.fn(),
  useWorkflowPackageManifestMock: vi.fn(),
  useWorkflowPackageMock: vi.fn(),
  useWorkflowPackageVersionsMock: vi.fn(),
  validatePackageMock: vi.fn(),
}));

vi.mock("react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router")>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("@/hooks/use-model-connections", () => ({
  useModelConnections: (...args: unknown[]) => useModelConnectionsMock(...args),
}));

vi.mock("@/hooks/use-workflow-packages", () => ({
  useCreateWorkflowPackage: () => useCreatePackageMock(),
  useCreateWorkflowPackageLaunch: () => useCreateLaunchMock(),
  useDeleteWorkflowPackageSecretBinding: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useImportWorkflowPackage: () => useImportPackageMock(),
  usePreflightWorkflowPackage: () => usePreflightPackageMock(),
  useTools: () => useToolsMock(),
  useUpdateWorkflowPackage: () => useUpdatePackageMock(),
  useUpsertWorkflowPackageSecretBinding: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useValidateWorkflowPackageManifest: () => useValidatePackageMock(),
  useWorkflowPackage: (...args: unknown[]) => useWorkflowPackageMock(...args),
  useWorkflowPackageLaunch: (...args: unknown[]) => useWorkflowPackageLaunchMock(...args),
  useWorkflowPackageManifest: (...args: unknown[]) => useWorkflowPackageManifestMock(...args),
  useWorkflowPackageSecretBindings: () => ({ data: { items: [] }, error: null, isError: false, isPending: false }),
  useWorkflowPackageVersions: (...args: unknown[]) => useWorkflowPackageVersionsMock(...args),
}));

const packageRead: WorkflowPackageRead = {
  compiledHash: "compiled-hash-123",
  createdAt: "2026-05-01T10:00:00Z",
  description: "Package for neutral research workflows.",
  id: 42,
  key: "market_review_package",
  latestVersion: 7,
  latestVersionId: 70,
  manifestHash: "manifest-hash-123",
  name: "Market Review Package",
  status: "active",
  updatedAt: "2026-05-05T10:00:00Z",
  warnings: [],
};

const manifestRead: WorkflowPackageManifestRead = {
  compiledHash: "compiled-hash-123",
  manifestHash: "manifest-hash-123",
  manifestSource: `apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: hydrated_market_review
  name: Hydrated Market Review
  description: Manifest source description
spec:
  inputs:
    type: object
`,
  packageDefinition: {},
  packageId: 42,
  packageKey: "market_review_package",
  version: 7,
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
  packageVersion: 7,
  ready: true,
  warnings: [],
  workflowKey: "market_review",
};

function editorElement(initialEntry = "/workflow-packages/42") {
  return (
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/workflow-packages/:packageId" element={<WorkflowPackageEditorPage />} />
        <Route path="/workflow-packages/:packageId/run" element={<WorkflowPackageEditorPage />} />
      </Routes>
    </MemoryRouter>
  );
}

function renderEditor(initialEntry = "/workflow-packages/42") {
  return render(editorElement(initialEntry));
}

function clickTab(name: string) {
  fireEvent.click(screen.getByRole("tab", { name: `${name} tab` }));
}

async function choosePackageVersion(name: RegExp) {
  const versionSelect = screen.getByLabelText("Package version");
  versionSelect.focus();
  fireEvent.keyDown(versionSelect, { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name }));
}

describe("WorkflowPackageEditorPage preflight, launch, and export flows", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    updatePackageMock.mockReset();
    validatePackageMock.mockReset();
    preflightPackageMock.mockReset();
    createLaunchMock.mockReset();
    importPackageMock.mockReset();
    preflightPackageMock.mockResolvedValue(launchRead);
    createLaunchMock.mockResolvedValue({ createdAt: "2026-05-08T10:00:00Z", id: 99, status: "queued", workflowKey: "market_review", workflowPackageId: 42, workflowPackageKey: "market_review_package", workflowPackageVersion: 7 });
    importPackageMock.mockResolvedValue({ ...packageRead, warnings: [{ field: "spec.agents[0].modelConnection", issue: "Missing model connection primary_model" }] });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve("apiVersion: signaldeck.workflowPackage/v1\nkind: WorkflowPackage\nmetadata:\n  key: market_review_package\nspec:\n  mcpServers:\n    - key: market_stdio\n      transport: stdio\n      command: market-mcp\n      env:\n        MARKET_DATA_API_KEY: sk-live-env-secret\n    - key: market_http\n      transport: http-sse\n      url: https://example.com/mcp\n      headers:\n        Authorization: Bearer sk-live-header-secret\n      query:\n        apiKey: sk-live-query-secret\n"),
    }) as unknown as typeof fetch;
    global.fetch = fetchMock;
    window.fetch = fetchMock;
    useWorkflowPackageMock.mockReturnValue({ data: packageRead, error: null, isError: false, isPending: false, refetch: vi.fn() });
    useWorkflowPackageManifestMock.mockReturnValue({ data: manifestRead, error: null, isError: false, isFetching: false, isPending: false, refetch: vi.fn() });
    useWorkflowPackageVersionsMock.mockReturnValue({ data: { items: [{ compiledHash: "compiled", createdAt: "2026-05-05T10:00:00Z", id: 70, launchedAt: null, manifestHash: "manifest", packageId: 42, validationSummary: {}, version: 7, warnings: [] }] }, error: null, isError: false, isPending: false });
    useWorkflowPackageLaunchMock.mockReturnValue({ data: launchRead, error: null, isError: false, isPending: false });
    useCreatePackageMock.mockReturnValue({ isPending: false, mutateAsync: vi.fn() });
    useUpdatePackageMock.mockReturnValue({ isPending: false, mutateAsync: updatePackageMock });
    useValidatePackageMock.mockReturnValue({ isPending: false, mutateAsync: validatePackageMock });
    usePreflightPackageMock.mockReturnValue({ isPending: false, mutateAsync: preflightPackageMock });
    useCreateLaunchMock.mockReturnValue({ isPending: false, mutateAsync: createLaunchMock });
    useImportPackageMock.mockReturnValue({ isPending: false, mutateAsync: importPackageMock });
    useModelConnectionsMock.mockReturnValue({ data: { items: [] }, error: null, isError: false, isPending: false });
    useToolsMock.mockReturnValue({ data: { items: [] }, error: null, isError: false, isPending: false });
  });

  it("deep-links blocking preflight diagnostics into package-local editor fields", async () => {
    const blockedRead: WorkflowPackageLaunchRead = {
      ...launchRead,
      blockingErrors: [{ field: "spec.agents[0].modelConnection", issue: "Missing model connection primary_model" }],
      ready: false,
      warnings: [
        { field: "spec.agents[0].modelConnection", issue: "Deterministic smoke connection will run offline", connectionKind: "deterministic_smoke" },
        { field: "spec.capabilityProfiles[0].toolKeys[0]", issue: "Unknown tool key" },
      ],
    };
    preflightPackageMock.mockResolvedValueOnce(blockedRead);
    useWorkflowPackageLaunchMock.mockReturnValue({ data: blockedRead, error: null, isError: false, isPending: false });
    renderEditor();

    clickTab("Preflight");
    const preflightTab = screen.getByTestId("workflow-package-preflight-tab");
    expect(within(preflightTab).queryByText("Version")).not.toBeInTheDocument();
    expect(within(preflightTab).queryByText("Warnings")).not.toBeInTheDocument();
    expect(await screen.findByText(/needs attention/i)).toBeInTheDocument();
    expect(screen.getByText(/missing model connection/i)).toBeVisible();
    expect(within(preflightTab).getAllByText(/deterministic smoke/i).length).toBeGreaterThan(0);
    expect(within(preflightTab).getAllByText(/will run offline/i).length).toBeGreaterThan(1);
    fireEvent.click(within(preflightTab).getByRole("button", { name: /^run preflight$/i }));

    expect(await screen.findByRole("tab", { name: "Agents tab" })).toHaveAttribute("aria-selected", "true");
  });
  it("launches package run after preflight and navigates to run detail", async () => {
    renderEditor("/workflow-packages/42/run");

    const launchTab = await screen.findByTestId("workflow-package-launch-tab");
    expect(launchTab).toBeVisible();
    expect(within(launchTab).queryByText("Readiness")).not.toBeInTheDocument();
    expect(within(launchTab).queryByText("Workflow")).not.toBeInTheDocument();
    expect(within(launchTab).getByText("Provider-backed")).toBeVisible();
    expect(within(launchTab).getByText(/saved model connections are provider-backed/i)).toBeVisible();
    expect(screen.queryByRole("textbox", { name: "Ticker" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Runtime inputs JSON"), { target: { value: '{"ticker":"AAPL"}' } });
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    await waitFor(() => expect(preflightPackageMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: { parameters: {}, version: null, workflowKey: "market_review" },
    }));
    expect(createLaunchMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: { parameters: { ticker: "AAPL" }, version: null, workflowKey: "market_review" },
    });
    expect(navigateMock).toHaveBeenCalledWith("/runs/99");
  });

  it("submits raw launch parameters from the schema-derived template", async () => {
    const typedLaunchRead: WorkflowPackageLaunchRead = {
      ...launchRead,
      inputSchema: {
        properties: {
          includeNews: { title: "Include News", type: "boolean" },
          horizonDays: { title: "Horizon Days", type: "integer" },
          filters: {
            properties: {
              sector: { title: "Sector", type: "string" },
            },
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
    };
    useWorkflowPackageLaunchMock.mockReturnValue({ data: typedLaunchRead, error: null, isError: false, isPending: false });
    renderEditor("/workflow-packages/42/run");

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
        version: null,
        workflowKey: "market_review",
      },
    }));
  });

  it("resets raw JSON launch state when workflow key, selected version, or schema identity changes", async () => {
    const resetLaunchRead: WorkflowPackageLaunchRead = {
      ...launchRead,
      inputSchema: {
        properties: {
          ticker: { title: "Ticker", type: "string" },
        },
        required: ["ticker"],
        type: "object",
      },
      workflowKey: "reset_workflow",
    };
    useWorkflowPackageLaunchMock.mockReturnValue({ data: resetLaunchRead, error: null, isError: false, isPending: false });
    useWorkflowPackageVersionsMock.mockReturnValue({
      data: {
        items: [
          { compiledHash: "compiled", createdAt: "2026-05-05T10:00:00Z", id: 70, launchedAt: null, manifestHash: "manifest", packageId: 42, validationSummary: {}, version: 7, warnings: [] },
          { compiledHash: "compiled-6", createdAt: "2026-05-04T10:00:00Z", id: 60, launchedAt: null, manifestHash: "manifest-6", packageId: 42, validationSummary: {}, version: 6, warnings: [] },
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });
    const view = renderEditor("/workflow-packages/42/run");

    const runtimeJson = (await screen.findByLabelText("Runtime inputs JSON")) as HTMLTextAreaElement;
    expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "" }, null, 2));
    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"AAPL"}' } });
    expect(runtimeJson.value).toBe('{"ticker":"AAPL"}');

    fireEvent.click(screen.getByRole("button", { name: "Reset to template" }));
    expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "" }, null, 2));
    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"MSFT"}' } });

    fireEvent.change(screen.getByLabelText("Workflow key"), { target: { value: "alternate_workflow" } });
    await waitFor(() => expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "" }, null, 2)));
    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"NVDA"}' } });

    await choosePackageVersion(/^v6$/);
    await waitFor(() => expect(runtimeJson.value).toBe(JSON.stringify({ ticker: "" }, null, 2)));
    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"META"}' } });

    useWorkflowPackageLaunchMock.mockReturnValue({
      data: {
        ...resetLaunchRead,
        inputSchema: {
          properties: {
            symbol: { title: "Symbol", type: "string" },
          },
          required: ["symbol"],
          type: "object",
        },
      },
      error: null,
      isError: false,
      isPending: false,
    });
    view.rerender(editorElement("/workflow-packages/42/run"));

    await waitFor(() => expect(runtimeJson.value).toBe(JSON.stringify({ symbol: "" }, null, 2)));
  });

  it("rejects non-object raw JSON locally", async () => {
    renderEditor("/workflow-packages/42/run");

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
    renderEditor("/workflow-packages/42/run");

    fireEvent.change(await screen.findByLabelText("Runtime inputs JSON"), { target: { value: '{"ticker":"AAPL","extra":true}' } });
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    const feedback = await screen.findByTestId("runtime-input-validation-feedback");
    expect(feedback).toHaveTextContent("parameters.extra");
    expect(feedback).toHaveTextContent("Unknown field");
  });

  it.each([
    {
      expectedKeyword: /additionalProperties/i,
      inputSchema: {
        additionalProperties: true,
        properties: { ticker: { title: "Ticker", type: "string" } },
        required: ["ticker"],
        type: "object",
      },
      name: "removed-additional-properties-keyword",
    },
    {
      expectedKeyword: /patternProperties/i,
      inputSchema: {
        patternProperties: { "^x-": { type: "string" } },
        properties: {},
        type: "object",
      },
      name: "unsupported",
    },
  ])("keeps one raw JSON editor when $name templates start empty", async ({ expectedKeyword, inputSchema }) => {
    useWorkflowPackageLaunchMock.mockReturnValue({
      data: { ...launchRead, inputSchema },
      error: null,
      isError: false,
      isPending: false,
    });
    renderEditor("/workflow-packages/42/run");

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
        version: null,
        workflowKey: "market_review",
      },
    }));
  });

  it("auto-loads export preview and imports package YAML with inline private MCP values", async () => {
    renderEditor();
    clickTab("Import / Export");

    expect(screen.queryByRole("button", { name: /preview export/i })).not.toBeInTheDocument();
    expect(screen.getByText(/package-private mcp inline values remain visible in the manifest/i)).toBeVisible();
    const preview = await screen.findByLabelText("Package YAML preview");
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    await waitFor(() => expect((preview as HTMLTextAreaElement).value).toContain("sk-live-env-secret"));
    expect((preview as HTMLTextAreaElement).value).toContain("Authorization: Bearer sk-live-header-secret");
    expect((preview as HTMLTextAreaElement).value).toContain("apiKey: sk-live-query-secret");
    fireEvent.click(screen.getByRole("button", { name: "Import workflow package manifest" }));
    expect(screen.getByText(/package-private mcp inline values are imported exactly as shown/i)).toBeVisible();
    fireEvent.change(screen.getByLabelText("Import package YAML"), {
      target: { value: "metadata:\n  key: imported\nspec:\n  mcpServers:\n    - headers:\n        Authorization: Bearer sk-import-secret\n" },
    });
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /import package/i }));

    await waitFor(() => expect(importPackageMock).toHaveBeenCalledWith({
      manifestSource: expect.stringContaining("sk-import-secret"),
      mode: "create",
    }));
    expect(await screen.findByText(/missing model connection primary_model/i)).toBeVisible();
  });

  it("keeps import input as pasted for inline private MCP values", async () => {
    renderEditor();
    clickTab("Import / Export");

    fireEvent.click(screen.getByRole("button", { name: "Import workflow package manifest" }));
    fireEvent.change(screen.getByLabelText("Import package YAML"), {
      target: { value: "metadata:\n  key: imported\nspec:\n  mcpServers:\n    - headers:\n        Authorization: Bearer sk-import-secret\n" },
    });

    const importEditor = screen.getByLabelText("Import package YAML") as HTMLTextAreaElement;
    expect(importEditor.value).toContain("sk-import-secret");
    expect(importEditor.value).toContain("Authorization: Bearer sk-import-secret");

    const preview = await screen.findByLabelText("Package YAML preview");
    expect((preview as HTMLTextAreaElement).value).toContain("sk-live-env-secret");
    expect((preview as HTMLTextAreaElement).value).toContain("Authorization: Bearer sk-live-header-secret");
    expect((preview as HTMLTextAreaElement).value).toContain("apiKey: sk-live-query-secret");
  });
});
