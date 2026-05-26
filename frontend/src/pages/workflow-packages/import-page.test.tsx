import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError } from "@/lib/api-client";
import type { WorkflowPackageRead } from "@/lib/types/workflow-package";

import { WorkflowPackageImportPage } from "./import-page";

const {
  blockerProceedMock,
  blockerResetMock,
  blockerStateMock,
  importPackageMock,
  navigateMock,
  toastErrorMock,
  toastSuccessMock,
  useBeforeUnloadMock,
  useImportPackageMock,
} = vi.hoisted(() => ({
  blockerProceedMock: vi.fn(),
  blockerResetMock: vi.fn(),
  blockerStateMock: { blocked: false },
  importPackageMock: vi.fn(),
  navigateMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  useBeforeUnloadMock: vi.fn(),
  useImportPackageMock: vi.fn(),
}));

vi.mock("react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router")>();
  return {
    ...actual,
    useBeforeUnload: useBeforeUnloadMock,
    useBlocker: (shouldBlock: boolean | ((context: {
      currentLocation: { pathname: string };
      historyAction: string;
      nextLocation: { pathname: string };
    }) => boolean)) => {
      const shouldGuard = typeof shouldBlock === "function"
        ? shouldBlock({
            currentLocation: { pathname: "/workflow-packages/import" },
            historyAction: "PUSH",
            nextLocation: { pathname: "/workflow-packages" },
          })
        : shouldBlock;

      return {
        proceed: blockerProceedMock,
        reset: blockerResetMock,
        state: shouldGuard && blockerStateMock.blocked ? "blocked" : "unblocked",
      };
    },
    useNavigate: () => navigateMock,
  };
});

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}));

vi.mock("@/hooks/use-workflow-packages", () => ({
  useImportWorkflowPackage: () => useImportPackageMock(),
}));

function packageFixture(overrides: Partial<WorkflowPackageRead> = {}): WorkflowPackageRead {
  return {
    compiledHash: "compiled-hash",
    createdAt: "2026-05-01T10:00:00Z",
    description: "Imported package",
    id: 77,
    key: "imported_package",
    manifestHash: "manifest-hash",
    name: "Imported Package",
    updatedAt: "2026-05-03T10:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <WorkflowPackageImportPage />
    </MemoryRouter>,
  );
}

describe("WorkflowPackageImportPage", () => {
  beforeEach(() => {
    blockerProceedMock.mockReset();
    blockerResetMock.mockReset();
    blockerStateMock.blocked = false;
    importPackageMock.mockReset();
    navigateMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    useBeforeUnloadMock.mockReset();
    useImportPackageMock.mockReset();
    importPackageMock.mockResolvedValue(packageFixture());
    useImportPackageMock.mockReturnValue({
      isPending: false,
      mutateAsync: importPackageMock,
    });
  });

  it("renders a full-height YAML import workspace and returns to the package list on cancel", () => {
    renderPage();

    const shell = screen.getByTestId("workflow-package-import-page");
    expect(shell).toHaveClass("h-full", "min-h-0", "min-w-0", "overflow-hidden");
    expect(screen.getByTestId("workspace-page-shell-context")).toHaveClass("sticky", "top-0");
    expect(screen.getByTestId("workspace-page-shell-body")).toHaveAttribute("aria-label", "Workflow package import workspace");
    expect(screen.queryByRole("main")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Import workflow package YAML" })).toBeVisible();
    const editor = screen.getByRole("textbox", { name: "Import package YAML" });
    expect(editor).toHaveAttribute("id", "workflow-package-import-yaml");
    expect(editor).toHaveClass("h-full");
    expect(editor).toHaveAttribute(
      "placeholder",
      "apiVersion: signaldeck.workflowPackage/v1\nkind: WorkflowPackage\nmetadata:\n  key: imported_package\n  name: Imported Package\nspec:\n  agents: []",
    );
    const inspector = screen.getByRole("complementary", {
      name: "Import constraint inspector",
    });
    expect(inspector).toHaveTextContent("Import constraints");
    expect(inspector).toHaveTextContent("Blocked");
    expect(inspector).toHaveTextContent(
      "Paste a Workflow Package manifest before importing.",
    );
    expect(screen.getByTestId("workspace-page-shell-context")).toHaveTextContent("Backend-owned");
    expect(inspector).toHaveTextContent("apiVersion must be signaldeck.workflowPackage/v1.");
    expect(screen.getByRole("button", { name: "Import package" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Cancel import" }));
    expect(navigateMock).toHaveBeenCalledWith("/workflow-packages");
  });

  it("updates the constraint inspector when pasted YAML activates import guards", () => {
    renderPage();

    fireEvent.change(screen.getByRole("textbox", { name: "Import package YAML" }), {
      target: { value: "metadata:\n  key: imported\n" },
    });

    const context = screen.getByTestId("workspace-page-shell-context");
    expect(context).toHaveTextContent("Pasted YAML");
    expect(context).toHaveTextContent("Guards");
    expect(context).toHaveTextContent("Active");
    expect(screen.getByTestId("workflow-package-import-inspector")).toHaveTextContent("No blocking constraints.");
  });

  it("confirms before discarding pasted YAML from either cancel action", () => {
    const confirmMock = vi
      .spyOn(window, "confirm")
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);

    renderPage();

    fireEvent.change(screen.getByRole("textbox", { name: "Import package YAML" }), {
      target: { value: "metadata:\n  key: imported\n" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Cancel import" }));
    expect(confirmMock).toHaveBeenCalledWith(
      "You have pasted workflow package YAML. Discard it and leave this page?",
    );
    expect(navigateMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(navigateMock).toHaveBeenCalledWith("/workflow-packages");
    confirmMock.mockRestore();
  });

  it("blocks route-level navigation attempts when pasted YAML is present", async () => {
    const confirmMock = vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    blockerStateMock.blocked = true;

    renderPage();

    fireEvent.change(screen.getByRole("textbox", { name: "Import package YAML" }), {
      target: { value: "metadata:\n  key: imported\n" },
    });

    await waitFor(() =>
      expect(confirmMock).toHaveBeenCalledWith(
        "You have pasted workflow package YAML. Discard it and leave this page?",
      ),
    );
    expect(blockerResetMock).toHaveBeenCalled();
    expect(blockerProceedMock).not.toHaveBeenCalled();
    confirmMock.mockRestore();
  });

  it("disables cancel controls while an import is pending", () => {
    useImportPackageMock.mockReturnValue({
      isPending: true,
      mutateAsync: importPackageMock,
    });

    renderPage();

    expect(screen.getByRole("button", { name: "Cancel import" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  });

  it("submits pasted YAML unchanged, shows success, and opens the imported package", async () => {
    renderPage();

    const pastedYaml = "metadata:\n  key: imported\nspec:\n  mcpServers:\n    - env:\n        API_KEY: sk-import-secret\n";
    fireEvent.change(screen.getByRole("textbox", { name: "Import package YAML" }), {
      target: { value: pastedYaml },
    });
    fireEvent.click(screen.getByRole("button", { name: "Import package" }));

    await waitFor(() =>
      expect(importPackageMock).toHaveBeenCalledWith({ manifestSource: pastedYaml }),
    );
    expect(importPackageMock.mock.calls[0][0].manifestSource).toContain(
      "API_KEY: sk-import-secret",
    );
    expect(toastSuccessMock).toHaveBeenCalledWith("Imported workflow package");
    expect(navigateMock).toHaveBeenCalledWith("/workflow-packages/77");
  });

  it("keeps users on the import workspace and shows backend detail errors", async () => {
    importPackageMock.mockRejectedValueOnce(new ApiRequestError({
      code: "validation_error",
      details: [{ field: "spec.agents[0].modelConnection", issue: "Missing model connection" }],
      message: "Workflow package manifest is invalid",
      status: 422,
    }));
    renderPage();

    fireEvent.change(screen.getByRole("textbox", { name: "Import package YAML" }), {
      target: { value: "metadata:\n  key: broken\n" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Import package" }));

    const alert = await screen.findByTestId("workflow-package-import-error");
    expect(alert).toHaveTextContent("Workflow package manifest is invalid");
    expect(within(alert).getByText(/spec\.agents\[0]\.modelConnection/)).toBeVisible();
    expect(alert).toHaveTextContent("Missing model connection");
    expect(screen.getByTestId("workspace-page-shell-context")).toHaveTextContent("Rejected");
    const inspector = screen.getByTestId("workflow-package-import-inspector");
    expect(inspector).toHaveTextContent(
      "Backend rejection details are shown in this route and remain visible until the next import attempt.",
    );
    expect(toastErrorMock).toHaveBeenCalledWith("Workflow package manifest is invalid");
    expect(navigateMock).not.toHaveBeenCalledWith("/workflow-packages/77");
  });
});
