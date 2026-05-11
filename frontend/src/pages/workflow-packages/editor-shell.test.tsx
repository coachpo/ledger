import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkflowPackageManifestRead, WorkflowPackageRead } from "@/lib/types/workflow-package";

import { WorkflowPackageEditorPage } from "./editor";

const { navigateMock, useWorkflowPackageManifestMock, useWorkflowPackageMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  useWorkflowPackageManifestMock: vi.fn(),
  useWorkflowPackageMock: vi.fn(),
}));

vi.mock("react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router")>();
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock("@/hooks/use-model-connections", () => ({
  useModelConnections: () => ({ data: { items: [] }, error: null, isError: false, isPending: false }),
}));

vi.mock("@/hooks/use-workflow-packages", () => ({
  useCreateWorkflowPackage: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useCreateWorkflowPackageLaunch: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useImportWorkflowPackage: () => ({ isPending: false, mutateAsync: vi.fn() }),
  usePreflightWorkflowPackage: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useTools: () => ({ data: { items: [] }, error: null, isError: false, isPending: false }),
  useUpdateWorkflowPackage: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useValidateWorkflowPackageManifest: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useWorkflowPackage: (...args: unknown[]) => useWorkflowPackageMock(...args),
  useWorkflowPackageLaunch: () => ({ data: undefined, error: null, isError: false, isPending: false }),
  useWorkflowPackageManifest: (...args: unknown[]) => useWorkflowPackageManifestMock(...args),
  useWorkflowPackageVersions: () => ({ data: { items: [] }, error: null, isError: false, isPending: false }),
}));

const packageRead: WorkflowPackageRead = {
  compiledHash: "compiled-hash-123",
  createdAt: "2026-05-01T10:00:00Z",
  description: "Private package for multi-agent market review.",
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

function renderEditor(initialEntry: string, routePath: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path={routePath} element={<WorkflowPackageEditorPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("WorkflowPackageEditorPage", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    useWorkflowPackageMock.mockReset();
    useWorkflowPackageManifestMock.mockReset();
    useWorkflowPackageMock.mockReturnValue({
      data: packageRead,
      error: null,
      isError: false,
      isPending: false,
      refetch: vi.fn(),
    });
    useWorkflowPackageManifestMock.mockReturnValue({
      data: manifestRead,
      error: null,
      isError: false,
      isFetching: false,
      isPending: false,
      refetch: vi.fn(),
    });
  });

  it("renders the editor shell with all package-local tabs and accessible action labels", () => {
    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    expect(screen.getByTestId("workflow-package-editor-shell")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Market Review Package" })).toBeVisible();
    expect(screen.getByText("market_review_package · v7")).toBeVisible();
    expect(screen.getAllByText("Private package for multi-agent market review.")[0]).toBeVisible();

    for (const tabName of [
      "Overview",
      "Agents",
      "Output Schemas",
      "Capability Profiles",
      "Private MCP",
      "Preflight",
      "Launch",
      "Import / Export",
    ]) {
      expect(screen.getByRole("tab", { name: `${tabName} tab` })).toBeVisible();
    }

    expect(screen.getByRole("button", { name: "Save package draft" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Run package preflight" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Launch workflow package" })).toBeEnabled();

    const overviewTab = screen.getByRole("tab", { name: "Overview tab" });
    expect(overviewTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Package overview");
  });

  it("hydrates existing package draft fields from manifestSource instead of summary metadata", () => {
    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    expect(screen.getByLabelText("Package key")).toHaveValue("hydrated_market_review");
    expect(screen.getByLabelText("Package name")).toHaveValue("Hydrated Market Review");
    expect(screen.getByLabelText("Package description")).toHaveValue("Manifest source description");
  });

  it("keeps historical versions launch/export-only while hydration stays pinned to the latest draft", () => {
    renderEditor("/workflow-packages/42?version=7", "/workflow-packages/:packageId");

    expect(screen.getByLabelText("Package key")).toHaveValue("hydrated_market_review");
    expect(screen.getByLabelText("Package name")).toHaveValue("Hydrated Market Review");
    expect(screen.getByLabelText("Package description")).toHaveValue("Manifest source description");
    expect(screen.getByRole("button", { name: "Save package draft" })).toBeEnabled();
  });

  it("surfaces package load errors in a blocking retry state", () => {
    useWorkflowPackageMock.mockReturnValue({
      data: undefined,
      error: new Error("Package missing"),
      isError: true,
      isPending: false,
      refetch: vi.fn(),
    });

    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    expect(screen.getByTestId("workflow-package-manifest-blocker")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("Package missing");
    expect(screen.queryByRole("tablist")).toBeNull();
    expect(screen.getByRole("button", { name: "Save package draft" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Run package preflight" })).toBeDisabled();
  });

  it("opens the same shell with Launch active for the run route", () => {
    renderEditor("/workflow-packages/42/run", "/workflow-packages/:packageId/run");

    const launchTab = screen.getByRole("tab", { name: "Launch tab" });
    expect(launchTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Launch route")).toBeVisible();
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Launch package run");
  });

  it("renders the new package shell without loading package detail or manifest", () => {
    useWorkflowPackageMock.mockReturnValue({
      data: undefined,
      error: null,
      isError: false,
      isPending: false,
      refetch: vi.fn(),
    });

    renderEditor("/workflow-packages/new", "/workflow-packages/new");

    expect(useWorkflowPackageMock).toHaveBeenCalledWith(undefined);
    expect(useWorkflowPackageManifestMock).toHaveBeenCalledWith(undefined);
    expect(screen.getByRole("heading", { name: "New Workflow Package" })).toBeVisible();
    expect(screen.getByText("Draft manifest shell")).toBeVisible();
    expect(screen.getByRole("button", { name: "Launch workflow package" })).toBeDisabled();
  });

  it("switches tabs and routes launch button to the run shell", () => {
    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    fireEvent.click(screen.getByRole("tab", { name: "Private MCP tab" }));
    expect(screen.getByRole("tab", { name: "Private MCP tab" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Private MCP servers");

    fireEvent.click(screen.getByRole("button", { name: "Launch workflow package" }));
    expect(navigateMock).toHaveBeenCalledWith("/workflow-packages/42/run");
  });

  it("surfaces package load errors in a blocking retry state", () => {
    useWorkflowPackageMock.mockReturnValue({
      data: undefined,
      error: new Error("Package missing"),
      isError: true,
      isPending: false,
      refetch: vi.fn(),
    });

    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    expect(screen.getByTestId("workflow-package-manifest-blocker")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("Package missing");
    expect(screen.queryByRole("tablist")).toBeNull();
    expect(screen.getByRole("button", { name: "Save package draft" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Run package preflight" })).toBeDisabled();
  });

  it("surfaces manifest parse errors in a blocking retry state", () => {
    useWorkflowPackageManifestMock.mockReturnValue({
      data: {
        ...manifestRead,
        manifestSource: "apiVersion: ledger.workflowPackage/v1\nmetadata:\n  key: broken\n  name: Broken Package\n  description: [",
      },
      error: null,
      isError: false,
      isFetching: false,
      isPending: false,
      refetch: vi.fn(),
    });

    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    expect(screen.getByTestId("workflow-package-manifest-blocker")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("sufficiently indented");
    expect(screen.queryByRole("tablist")).toBeNull();
    expect(screen.getByRole("button", { name: "Save package draft" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Run package preflight" })).toBeDisabled();
  });
});
