import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkflowPackageRead } from "@/lib/types/workflow-package";

import { WorkflowPackageEditorPage } from "./editor";

const { navigateMock, useWorkflowPackageMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
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
    useWorkflowPackageMock.mockReturnValue({
      data: packageRead,
      error: null,
      isError: false,
      isPending: false,
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

  it("opens the same shell with Launch active for the run route", () => {
    renderEditor("/workflow-packages/42/run", "/workflow-packages/:packageId/run");

    const launchTab = screen.getByRole("tab", { name: "Launch tab" });
    expect(launchTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Launch route")).toBeVisible();
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Launch package run");
  });

  it("renders the new package shell without loading package detail", () => {
    useWorkflowPackageMock.mockReturnValue({
      data: undefined,
      error: null,
      isError: false,
      isPending: false,
    });

    renderEditor("/workflow-packages/new", "/workflow-packages/new");

    expect(useWorkflowPackageMock).toHaveBeenCalledWith(undefined);
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

  it("surfaces package load errors without hiding tabs", () => {
    useWorkflowPackageMock.mockReturnValue({
      data: undefined,
      error: new Error("Package missing"),
      isError: true,
      isPending: false,
    });

    renderEditor("/workflow-packages/42", "/workflow-packages/:packageId");

    expect(screen.getByRole("alert")).toHaveTextContent("Package missing");
    expect(within(screen.getByRole("tablist")).getByRole("tab", { name: "Overview tab" })).toBeVisible();
  });
});
