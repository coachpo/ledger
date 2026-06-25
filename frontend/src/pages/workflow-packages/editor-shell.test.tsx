import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  WorkflowPackageManifestRead,
  WorkflowPackageRead,
} from "@/lib/types/workflow-package";

import { WorkflowPackageEditorPage } from "./editor";

const {
  navigateMock,
  updatePackageMock,
  useWorkflowPackageManifestMock,
  useWorkflowPackageMock,
} = vi.hoisted(() => ({
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
  useModelConnections: () => ({
    data: { items: [] },
    error: null,
    isError: false,
    isPending: false,
  }),
}));

vi.mock("@/hooks/use-workflow-packages", () => ({
  useCreateWorkflowPackage: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useDeleteWorkflowPackageSecretBinding: () => ({
    isPending: false,
    mutateAsync: vi.fn(),
  }),
  useTools: () => ({
    data: { items: [] },
    error: null,
    isError: false,
    isPending: false,
  }),
  useUpdateWorkflowPackage: () => ({
    isPending: false,
    mutateAsync: updatePackageMock,
  }),
  useUpsertWorkflowPackageSecretBinding: () => ({
    isPending: false,
    mutateAsync: vi.fn(),
  }),
  useValidateWorkflowPackageManifest: () => ({
    isPending: false,
    mutateAsync: vi.fn(),
  }),
  useWorkflowPackage: (...args: unknown[]) => useWorkflowPackageMock(...args),
  useWorkflowPackageManifest: (...args: unknown[]) =>
    useWorkflowPackageManifestMock(...args),
  useWorkflowPackageSecretBindings: () => ({
    data: { items: [] },
    error: null,
    isError: false,
    isPending: false,
  }),
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

    const shell = screen.getByTestId("workflow-package-editor-shell");
    expect(shell).toBeVisible();
    expect(shell).toHaveClass(
      "h-full",
      "min-h-0",
      "min-w-0",
      "overflow-hidden",
    );
    expect(screen.getByTestId("workspace-page-shell-context")).toHaveClass(
      "sticky",
      "top-0",
    );
    expect(screen.getByTestId("workspace-page-shell-body")).toHaveAttribute(
      "aria-label",
      "Workflow package authoring workspace",
    );
    expect(screen.queryByRole("main")).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Market Review Package" }),
    ).toBeVisible();

    const contextBar = screen.getByTestId("workflow-package-context-bar");
    const headerTopRow = screen.getByTestId(
      "workflow-package-editor-header-top-row",
    );
    expect(headerTopRow).toContainElement(
      screen.getByRole("heading", { name: "Market Review Package" }),
    );
    expect(within(headerTopRow).getByText("market_review_package")).toBeVisible();
    expect(within(headerTopRow).queryByRole("button")).not.toBeInTheDocument();

    const actionsRow = screen.getByTestId("workflow-package-editor-actions-row");
    expect(
      within(actionsRow).getByRole("button", { name: "Save package" }),
    ).toBeEnabled();
    expect(
      within(actionsRow).getByRole("button", { name: "Validate package" }),
    ).toBeEnabled();
    expect(
      within(actionsRow).getByRole("button", {
        name: "Launch workflow package",
      }),
    ).toBeEnabled();

    const headerMetaRow = screen.getByTestId(
      "workflow-package-editor-header-meta-row",
    );
    expect(headerMetaRow).toHaveTextContent(
      "Private package for multi-agent market review.",
    );
    expect(headerMetaRow).toHaveTextContent("Manifest manifest-has");
    expect(headerMetaRow).toHaveTextContent("Compiled compiled-has");
    expect(headerMetaRow).toHaveTextContent("Updated");

    expect(contextBar).toContainElement(headerTopRow);
    expect(contextBar).toContainElement(headerMetaRow);
    expect(contextBar).toContainElement(actionsRow);

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

    expect(screen.getByRole("button", { name: "Save package" })).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "Validate package" }),
    ).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "Launch workflow package" }),
    ).toBeEnabled();

    const overviewTab = screen.getByRole("tab", { name: "Overview tab" });
    expect(overviewTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Package overview");
  });

  it("keeps one visible Workflow YAML field label while preserving the textarea accessible name", () => {
    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    fireEvent.click(screen.getByRole("tab", { name: "Workflow YAML tab" }));
    const tabpanel = screen.getByRole("tabpanel");

    expect(within(tabpanel).getAllByText("Workflow YAML")).toHaveLength(1);
    expect(
      screen.getByRole("textbox", { name: "Workflow YAML" }),
    ).toBeVisible();
  });

  it("renders explicit sticky section navigation beside the active panel", () => {
    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    expect(screen.getByTestId("workspace-page-shell-context")).toHaveClass(
      "sticky",
      "top-0",
    );

    const sectionNav = screen.getByTestId("workflow-package-section-nav");
    expect(screen.getByTestId("workspace-page-shell-left-rail")).toHaveClass(
      "lg:sticky",
      "lg:top-3",
    );

    const tabList = screen.getByRole("tablist", {
      name: "Workflow package editor sections",
    });
    expect(sectionNav).toBe(tabList);
    expect(tabList).toHaveAttribute("aria-orientation", "vertical");
    expect(tabList).toHaveTextContent(
      "Package-private agent definitions stay local",
    );

    const tabsRoot = tabList.closest("[data-slot='tabs']");
    if (!tabsRoot) {
      throw new Error(
        "Expected the section navigation and panel to share one tabs root",
      );
    }

    const body = screen.getByTestId("workspace-page-shell-body");
    const rail = screen.getByTestId("workspace-page-shell-left-rail");
    expect(tabsRoot).toContainElement(sectionNav);
    expect(tabsRoot).toContainElement(screen.getByRole("tabpanel"));
    expect(rail).toContainElement(sectionNav);
    expect(body).toContainElement(screen.getByRole("tabpanel"));
    expect(rail).not.toContainElement(body);
  });

  it("hydrates existing package draft fields from manifestSource instead of summary metadata", () => {
    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    expect(screen.getByLabelText("Package key")).toHaveValue(
      "hydrated_market_review",
    );
    expect(screen.getByLabelText("Package name")).toHaveValue(
      "Hydrated Market Review",
    );
    expect(screen.getByLabelText("Package description")).toHaveValue(
      "Manifest source description",
    );
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

    expect(
      screen.getByTestId("workflow-package-manifest-blocker"),
    ).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("Package missing");
    expect(screen.queryByRole("tablist")).toBeNull();
    expect(screen.getByRole("button", { name: "Save package" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Validate package" }),
    ).toBeDisabled();
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
    expect(
      screen.getByRole("heading", { name: "New Workflow Package" }),
    ).toBeVisible();
    expect(screen.getByText("Draft manifest shell")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Launch workflow package" }),
    ).toBeDisabled();
  });

  it("applies selected-state visual classes to the active authoring tab", () => {
    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    const overviewTab = screen.getByRole("tab", { name: "Overview tab" });
    const agentsTab = screen.getByRole("tab", { name: "Agents tab" });

    expect(overviewTab).toHaveAttribute("data-state", "active");
    expect(agentsTab).toHaveAttribute("data-state", "inactive");
    expect(overviewTab).toHaveClass("data-[state=active]:bg-ui-surface-elevated");
    expect(overviewTab).toHaveClass("data-[state=active]:text-foreground");
    expect(overviewTab).toHaveClass("data-[state=active]:shadow-ui-xs");

    fireEvent.click(agentsTab);

    expect(agentsTab).toHaveAttribute("data-state", "active");
    expect(overviewTab).toHaveAttribute("data-state", "inactive");
    expect(screen.getByRole("tabpanel")).toHaveTextContent(
      "No package-local agents yet.",
    );
  });

  it("switches tabs and routes clean launch button to the run shell", () => {
    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    fireEvent.click(screen.getByRole("tab", { name: "Private MCP tab" }));
    expect(
      screen.getByRole("tab", { name: "Private MCP tab" }),
    ).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent(
      "Private MCP servers",
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Launch workflow package" }),
    );
    expect(navigateMock).toHaveBeenCalledWith("/workflow-packages/42/run");
  });

  it("confirms dirty launch handoff without saving unsaved editor changes", () => {
    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    fireEvent.change(screen.getByLabelText("Package name"), {
      target: { value: "Unsaved Market Review" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Launch workflow package" }),
    );

    expect(screen.getByRole("dialog")).toHaveTextContent(
      "Unsaved editor changes are excluded until you save them.",
    );
    expect(screen.getByRole("button", { name: "Cancel" })).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Launch saved package" }),
    ).toBeVisible();
    expect(updatePackageMock).not.toHaveBeenCalled();
    expect(navigateMock).not.toHaveBeenCalledWith("/workflow-packages/42/run");

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Launch workflow package" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Launch saved package" }),
    );

    expect(updatePackageMock).not.toHaveBeenCalled();
    expect(navigateMock).toHaveBeenCalledWith("/workflow-packages/42/run");
  });

  it("surfaces manifest parse errors in a blocking retry state", () => {
    useWorkflowPackageManifestMock.mockReturnValue({
      data: {
        ...manifestRead,
        manifestSource:
          "apiVersion: signaldeck.workflowPackage/v1\nmetadata:\n  key: broken\n  name: Broken Package\n  description: [",
      },
      error: null,
      isError: false,
      isFetching: false,
      isPending: false,
      refetch: vi.fn(),
    });

    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    expect(
      screen.getByTestId("workflow-package-manifest-blocker"),
    ).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "sufficiently indented",
    );
    expect(screen.queryByRole("tablist")).toBeNull();
    expect(screen.getByRole("button", { name: "Save package" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Validate package" }),
    ).toBeDisabled();
  });
});
