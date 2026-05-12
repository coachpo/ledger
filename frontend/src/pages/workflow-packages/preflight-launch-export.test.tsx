import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
  useImportWorkflowPackage: () => useImportPackageMock(),
  usePreflightWorkflowPackage: () => usePreflightPackageMock(),
  useTools: () => useToolsMock(),
  useUpdateWorkflowPackage: () => useUpdatePackageMock(),
  useValidateWorkflowPackageManifest: () => useValidatePackageMock(),
  useWorkflowPackage: (...args: unknown[]) => useWorkflowPackageMock(...args),
  useWorkflowPackageLaunch: (...args: unknown[]) => useWorkflowPackageLaunchMock(...args),
  useWorkflowPackageManifest: (...args: unknown[]) => useWorkflowPackageManifestMock(...args),
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
  manifestSource: `apiVersion: ledger.workflowPackage/v1
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

function renderEditor(initialEntry = "/workflow-packages/42") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/workflow-packages/:packageId" element={<WorkflowPackageEditorPage />} />
        <Route path="/workflow-packages/:packageId/run" element={<WorkflowPackageEditorPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function clickTab(name: string) {
  fireEvent.click(screen.getByRole("tab", { name: `${name} tab` }));
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
      text: () => Promise.resolve("apiVersion: ledger.workflowPackage/v1\nkind: WorkflowPackage\nmetadata:\n  key: market_review_package\nspec:\n  mcpServers:\n    - key: market_stdio\n      transport: stdio\n      command: market-mcp\n      env:\n        MARKET_DATA_API_KEY: sk-live-env-secret\n    - key: market_http\n      transport: http-sse\n      url: https://example.com/mcp\n      headers:\n        Authorization: Bearer sk-live-header-secret\n      query:\n        apiKey: sk-live-query-secret\n"),
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
      warnings: [{ field: "spec.capabilityProfiles[0].toolKeys[0]", issue: "Unknown tool key" }],
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
    fireEvent.click(within(preflightTab).getByRole("button", { name: /^run preflight$/i }));

    expect(await screen.findByRole("tab", { name: "Agents tab" })).toHaveAttribute("aria-selected", "true");
  });
  it("launches package run after preflight and navigates to run detail", async () => {
    renderEditor("/workflow-packages/42/run");

    const launchTab = await screen.findByTestId("workflow-package-launch-tab");
    expect(launchTab).toBeVisible();
    expect(within(launchTab).queryByText("Readiness")).not.toBeInTheDocument();
    expect(within(launchTab).queryByText("Workflow")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Ticker"), { target: { value: "AAPL" } });
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
