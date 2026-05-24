import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  WorkflowPackageManifestRead,
  WorkflowPackageRead,
} from "@/lib/types/workflow-package";

import { WorkflowPackageEditorPage } from "./editor";

const {
  createPackageMock,
  navigateMock,
  updatePackageMock,
  validatePackageMock,
  useCreatePackageMock,
  useModelConnectionsMock,
  useToolsMock,
  useUpdatePackageMock,
  useValidatePackageMock,
  useWorkflowPackageManifestMock,
  useWorkflowPackageMock,
} = vi.hoisted(() => ({
  createPackageMock: vi.fn(),
  navigateMock: vi.fn(),
  updatePackageMock: vi.fn(),
  validatePackageMock: vi.fn(),
  useCreatePackageMock: vi.fn(),
  useModelConnectionsMock: vi.fn(),
  useToolsMock: vi.fn(),
  useUpdatePackageMock: vi.fn(),
  useValidatePackageMock: vi.fn(),
  useWorkflowPackageManifestMock: vi.fn(),
  useWorkflowPackageMock: vi.fn(),
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
  useDeleteWorkflowPackageSecretBinding: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useTools: () => useToolsMock(),
  useUpdateWorkflowPackage: () => useUpdatePackageMock(),
  useUpsertWorkflowPackageSecretBinding: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useValidateWorkflowPackageManifest: () => useValidatePackageMock(),
  useWorkflowPackage: (...args: unknown[]) => useWorkflowPackageMock(...args),
  useWorkflowPackageManifest: (...args: unknown[]) => useWorkflowPackageManifestMock(...args),
  useWorkflowPackageSecretBindings: () => ({ data: { items: [] }, error: null, isError: false, isPending: false }),
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

const manifestRead: WorkflowPackageManifestRead = {
  compiledHash: "compiled-hash-123",
  manifestHash: "manifest-hash-123",
  manifestSource: `apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: market_review_package
  name: Market Review Package
  description: Package for neutral research workflows
spec:
  inputs:
    type: object
`,
  packageDefinition: {},
  packageId: 42,
  packageKey: "market_review_package",
};

function renderEditor() {
  return render(
    <MemoryRouter initialEntries={["/workflow-packages/42"]}>
      <Routes>
        <Route path="/workflow-packages/:packageId" element={<WorkflowPackageEditorPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function clickTab(name: string) {
  fireEvent.click(screen.getByRole("tab", { name: `${name} tab` }));
}
describe("WorkflowPackageEditorPage import and export flows", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    createPackageMock.mockReset();
    updatePackageMock.mockReset();
    validatePackageMock.mockReset();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve("apiVersion: signaldeck.workflowPackage/v1\nkind: WorkflowPackage\nmetadata:\n  key: market_review_package\nspec:\n  mcpServers:\n    - key: market_stdio\n      transport: stdio\n      command: market-mcp\n      env:\n        MARKET_DATA_API_KEY: sk-live-env-secret\n    - key: market_http\n      transport: http-sse\n      url: https://example.com/mcp\n      headers:\n        Authorization: Bearer sk-live-header-secret\n      query:\n        apiKey: sk-live-query-secret\n"),
    }) as unknown as typeof fetch;
    global.fetch = fetchMock;
    window.fetch = fetchMock;
    useWorkflowPackageMock.mockReturnValue({ data: packageRead, error: null, isError: false, isPending: false, refetch: vi.fn() });
    useWorkflowPackageManifestMock.mockReturnValue({ data: manifestRead, error: null, isError: false, isFetching: false, isPending: false, refetch: vi.fn() });
    useCreatePackageMock.mockReturnValue({ isPending: false, mutateAsync: createPackageMock });
    useUpdatePackageMock.mockReturnValue({ isPending: false, mutateAsync: updatePackageMock });
    useValidatePackageMock.mockReturnValue({ isPending: false, mutateAsync: validatePackageMock });
    useModelConnectionsMock.mockReturnValue({ data: { items: [] }, error: null, isError: false, isPending: false });
    useToolsMock.mockReturnValue({ data: { items: [] }, error: null, isError: false, isPending: false });
  });

  it("auto-loads export preview and routes import to the workspace", async () => {
    renderEditor();
    clickTab("Import / Export");

    expect(screen.queryByRole("button", { name: /preview export/i })).not.toBeInTheDocument();
    expect(screen.getByTestId("workflow-package-exports-tab")).toBeVisible();
    const preview = await screen.findByLabelText("Package YAML preview");
    expect(preview).toHaveClass("min-h-96", "font-mono", "text-xs");
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    await waitFor(() => expect((preview as HTMLTextAreaElement).value).toContain("sk-live-env-secret"));
    expect((preview as HTMLTextAreaElement).value).toContain("Authorization: Bearer sk-live-header-secret");
    expect((preview as HTMLTextAreaElement).value).toContain("apiKey: sk-live-query-secret");

    fireEvent.click(screen.getByRole("button", { name: "Import Package" }));
    expect(navigateMock).toHaveBeenCalledWith("/workflow-packages/import");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("protects dirty package edits before routing to the import workspace", () => {
    const confirmMock = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderEditor();

    fireEvent.change(screen.getByLabelText("Package name"), {
      target: { value: "Unsaved Package Name" },
    });
    clickTab("Import / Export");
    fireEvent.click(screen.getByRole("button", { name: "Import Package" }));

    expect(confirmMock).toHaveBeenCalledWith(
      "You have unsaved changes. Discard them and open the import workspace?",
    );
    expect(navigateMock).not.toHaveBeenCalledWith("/workflow-packages/import");

    fireEvent.click(screen.getByRole("button", { name: "Import Package" }));
    expect(navigateMock).toHaveBeenCalledWith("/workflow-packages/import");
    confirmMock.mockRestore();
  });
});
