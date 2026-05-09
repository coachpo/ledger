import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkflowPackageLaunchRead, WorkflowPackageRead } from "@/lib/types/workflow-package";

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
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve("apiVersion: ledger.workflowPackage/v1\nmetadata:\n  key: market_review_package\nsecretPayload: sk-live-secret\n"),
    }) as unknown as typeof fetch;
    useWorkflowPackageMock.mockReturnValue({ data: packageRead, error: null, isError: false, isPending: false });
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
    expect(await screen.findByText(/needs attention/i)).toBeInTheDocument();
    expect(screen.getByText(/missing model connection/i)).toBeVisible();
    fireEvent.click(within(screen.getByTestId("workflow-package-preflight-tab")).getByRole("button", { name: /^run preflight$/i }));

    expect(await screen.findByRole("tab", { name: "Agents tab" })).toHaveAttribute("aria-selected", "true");
  });
  it("launches package run after preflight and navigates to run detail", async () => {
    renderEditor("/workflow-packages/42/run");

    expect(await screen.findByTestId("workflow-package-launch-tab")).toBeVisible();
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

  it("auto-loads export preview and imports sanitized YAML without rendering secret-like strings", async () => {
    renderEditor();
    clickTab("Import / Export");

    expect(screen.queryByRole("button", { name: /preview export/i })).not.toBeInTheDocument();
    const preview = await screen.findByLabelText("Sanitized package YAML preview");
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    await waitFor(() => expect((preview as HTMLTextAreaElement).value).toContain("[redacted]"));
    expect((preview as HTMLTextAreaElement).value).not.toContain("sk-live-secret");
    fireEvent.click(screen.getByRole("button", { name: "Import workflow package manifest" }));
    fireEvent.change(screen.getByLabelText("Import package YAML"), {
      target: { value: "metadata:\n  key: imported\npassword: sk-import-secret\n" },
    });
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /import package/i }));

    await waitFor(() => expect(importPackageMock).toHaveBeenCalledWith({
      manifestSource: expect.not.stringContaining("sk-import-secret"),
      mode: "create",
    }));
    expect(await screen.findByText(/missing model connection primary_model/i)).toBeVisible();
    expect(screen.queryByText(/sk-import-secret/i)).not.toBeInTheDocument();
  });
});
