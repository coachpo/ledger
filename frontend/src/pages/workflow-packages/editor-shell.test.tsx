import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkflowPackageManifestRead, WorkflowPackageRead } from "@/lib/types/workflow-package";

import { WorkflowPackageEditorPage } from "./editor";

const { navigateMock, updatePackageMock, useWorkflowPackageManifestMock, useWorkflowPackageMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  updatePackageMock: vi.fn(),
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
  useDeleteWorkflowPackageSecretBinding: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useTools: () => ({ data: { items: [] }, error: null, isError: false, isPending: false }),
  useUpdateWorkflowPackage: () => ({ isPending: false, mutateAsync: updatePackageMock }),
  useUpsertWorkflowPackageSecretBinding: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useValidateWorkflowPackageManifest: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useWorkflowPackage: (...args: unknown[]) => useWorkflowPackageMock(...args),
  useWorkflowPackageManifest: (...args: unknown[]) => useWorkflowPackageManifestMock(...args),
  useWorkflowPackageSecretBindings: () => ({ data: { items: [] }, error: null, isError: false, isPending: false }),
}));

const packageRead: WorkflowPackageRead = {
  compiledHash: "compiled-hash-123",
  createdAt: "2026-05-01T10:00:00Z",
  description: "Private package for multi-agent market review.",
  id: 42,
  key: "market_review_package",
  manifestHash: "manifest-hash-123",
  name: "Market Review Package",
  updatedAt: "2026-05-05T10:00:00Z",
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
    updatePackageMock.mockReset();
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
    expect(screen.getByText("market_review_package")).toBeVisible();
    expect(screen.getAllByText("Private package for multi-agent market review.")[0]).toBeVisible();

    for (const tabName of [
      "Overview",
      "Agents",
      "Output Schemas",
      "Capability Profiles",
      "Private MCP",
      "Workflow YAML",
      "Secret Bindings",
      "Import / Export",
    ]) {
      expect(screen.getByRole("tab", { name: `${tabName} tab` })).toBeVisible();
    }

    expect(screen.queryByRole("tab", { name: "Preflight tab" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Launch tab" })).not.toBeInTheDocument();
    expect(screen.queryByText("Launch route")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save package" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Validate package" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Launch workflow package" })).toBeEnabled();

    const overviewTab = screen.getByRole("tab", { name: "Overview tab" });
    expect(overviewTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Package overview");
  });

  it("keeps one visible Workflow YAML field label while preserving the textarea accessible name", () => {
    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    fireEvent.click(screen.getByRole("tab", { name: "Workflow YAML tab" }));
    const tabpanel = screen.getByRole("tabpanel");

    expect(within(tabpanel).getAllByText("Workflow YAML")).toHaveLength(1);
    expect(screen.getByRole("textbox", { name: "Workflow YAML" })).toBeVisible();
  });

  it("renders package editor tabs as a vertical rail beside the active panel", () => {
    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    const tabList = screen.getByRole("tablist", { name: "Workflow package editor sections" });
    expect(tabList).toHaveAttribute("aria-orientation", "vertical");

    const tabsRoot = tabList.closest("[data-slot='tabs']");
    const tabRail = tabList.parentElement;
    const contentColumn = tabRail?.nextElementSibling;
    if (!tabsRoot || !tabRail || !contentColumn) {
      throw new Error("Expected the tab rail and tab panel column to share one tabs root");
    }

    expect(tabsRoot.children).toHaveLength(2);
    expect(tabRail.parentElement).toBe(tabsRoot);
    expect(contentColumn).toContainElement(screen.getByRole("tabpanel"));
  });

  it("hydrates existing package draft fields from manifestSource instead of summary metadata", () => {
    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    expect(screen.getByLabelText("Package key")).toHaveValue("hydrated_market_review");
    expect(screen.getByLabelText("Package name")).toHaveValue("Hydrated Market Review");
    expect(screen.getByLabelText("Package description")).toHaveValue("Manifest source description");
  });

  it("renders current-only authoring without historical affordances", () => {
    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    expect(screen.getByLabelText("Package key")).toHaveValue("hydrated_market_review");
    expect(screen.getByLabelText("Package name")).toHaveValue("Hydrated Market Review");
    expect(screen.getByLabelText("Package description")).toHaveValue("Manifest source description");
    expect(screen.getByRole("button", { name: "Save package" })).toBeEnabled();
    expect(screen.queryByText(new RegExp("Package vers" + "ion", "i"))).not.toBeInTheDocument();
    expect(screen.queryByText(/Latest/i)).not.toBeInTheDocument();
    expect(screen.queryByText(new RegExp("selected vers" + "ion", "i"))).not.toBeInTheDocument();
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
    expect(screen.getByRole("button", { name: "Save package" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Validate package" })).toBeDisabled();
  });

  it("does not turn the editor shell into a launch mode when mounted on the run-shaped path", () => {
    renderEditor("/workflow-packages/42/run", "/workflow-packages/:packageId/run");

    expect(screen.getByTestId("workflow-package-editor-shell")).toBeVisible();
    expect(screen.queryByRole("tab", { name: "Preflight tab" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Launch tab" })).not.toBeInTheDocument();
    expect(screen.queryByText("Launch route")).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Overview tab" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Package overview");
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

  it("switches tabs and routes clean launch button to the run shell", () => {
    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    fireEvent.click(screen.getByRole("tab", { name: "Private MCP tab" }));
    expect(screen.getByRole("tab", { name: "Private MCP tab" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Private MCP servers");

    fireEvent.click(screen.getByRole("button", { name: "Launch workflow package" }));
    expect(navigateMock).toHaveBeenCalledWith("/workflow-packages/42/run");
  });

  it("confirms dirty launch handoff without saving unsaved editor changes", () => {
    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    fireEvent.change(screen.getByLabelText("Package name"), {
      target: { value: "Unsaved Market Review" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Launch workflow package" }));

    expect(screen.getByRole("dialog")).toHaveTextContent("Unsaved editor changes are excluded until you save them.");
    expect(screen.getByRole("button", { name: "Cancel" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Launch saved package" })).toBeVisible();
    expect(updatePackageMock).not.toHaveBeenCalled();
    expect(navigateMock).not.toHaveBeenCalledWith("/workflow-packages/42/run");

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Launch workflow package" }));
    fireEvent.click(screen.getByRole("button", { name: "Launch saved package" }));

    expect(updatePackageMock).not.toHaveBeenCalled();
    expect(navigateMock).toHaveBeenCalledWith("/workflow-packages/42/run");
  });

  it("surfaces manifest parse errors in a blocking retry state", () => {
    useWorkflowPackageManifestMock.mockReturnValue({
      data: {
        ...manifestRead,
        manifestSource: "apiVersion: signaldeck.workflowPackage/v1\nmetadata:\n  key: broken\n  name: Broken Package\n  description: [",
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
    expect(screen.getByRole("button", { name: "Save package" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Validate package" })).toBeDisabled();
  });
});
