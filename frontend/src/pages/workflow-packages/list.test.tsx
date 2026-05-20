import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkflowPackageRead } from "@/lib/types/workflow-package";

import { WorkflowPackagesListPage } from "./list";

const {
  deletePackageMock,
  navigateMock,
  toastErrorMock,
  toastSuccessMock,
  useDeletePackageMock,
  useWorkflowPackagesMock,
} = vi.hoisted(() => ({
  deletePackageMock: vi.fn(),
  navigateMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  useDeletePackageMock: vi.fn(),
  useWorkflowPackagesMock: vi.fn(),
}));

vi.mock("react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router")>();
  return {
    ...actual,
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
  useDeleteWorkflowPackage: () => useDeletePackageMock(),
  useWorkflowPackages: () => useWorkflowPackagesMock(),
}));

function packageFixture(
  overrides: Partial<WorkflowPackageRead>,
): WorkflowPackageRead {
  return {
    compiledHash: "compiled-hash",
    createdAt: "2026-05-01T10:00:00Z",
    description: "Reusable package",
    id: 1,
    key: "alpha_package",
    manifestHash: "manifest-hash",
    name: "Alpha Package",
    updatedAt: "2026-05-03T10:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <WorkflowPackagesListPage />
    </MemoryRouter>,
  );
}

describe("WorkflowPackagesListPage", () => {
  beforeEach(() => {
    deletePackageMock.mockReset();
    navigateMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    useDeletePackageMock.mockReset();
    useWorkflowPackagesMock.mockReset();
    deletePackageMock.mockResolvedValue(undefined);
    useDeletePackageMock.mockReturnValue({
      isPending: false,
      mutateAsync: deletePackageMock,
    });
  });

  it("renders loading, error, and empty states", () => {
    useWorkflowPackagesMock.mockReturnValue({
      data: undefined,
      error: null,
      isError: false,
      isPending: true,
    });
    const { rerender } = renderPage();
    expect(
      screen.getByTestId("workflow-packages-list-page"),
    ).toBeInTheDocument();
    expect(document.querySelectorAll("[data-slot='skeleton']")).toHaveLength(4);

    useWorkflowPackagesMock.mockReturnValue({
      data: undefined,
      error: new Error("Package API unavailable"),
      isError: true,
      isPending: false,
    });
    rerender(
      <MemoryRouter>
        <WorkflowPackagesListPage />
      </MemoryRouter>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Package API unavailable",
    );

    useWorkflowPackagesMock.mockReturnValue({
      data: { items: [] },
      error: null,
      isError: false,
      isPending: false,
    });
    rerender(
      <MemoryRouter>
        <WorkflowPackagesListPage />
      </MemoryRouter>,
    );
    expect(screen.getByText("No workflow packages yet.")).toBeVisible();
  });

  it("renders package cards by default, search controls, and table columns after toggling", () => {
    useWorkflowPackagesMock.mockReturnValue({
      data: {
        items: [
          packageFixture({
            description: "Risk review workflow bundle",
            id: 9,
            key: "risk_review",
            name: "Risk Review",
                    updatedAt: "2026-05-04T10:00:00Z",
          }),
          packageFixture({
            description: "Draft allocation bundle",
            id: 4,
            key: "allocation_draft",
            name: "Allocation Draft",
            updatedAt: "2026-05-02T10:00:00Z",
          }),
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });
    renderPage();

    expect(
      screen.getByRole("heading", { name: "Workflow Packages" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Create new workflow package" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Import workflow package manifest" }),
    ).toBeVisible();
    expect(
      screen.getByRole("textbox", { name: "Search workflow packages" }),
    ).toHaveAttribute("placeholder", "Search packages by name, key, or hash...");
    expect(screen.queryByText("Package Inventory")).not.toBeInTheDocument();
    expect(screen.queryByText("Total Packages")).not.toBeInTheDocument();
    expect(screen.queryByText("Validation Warnings")).not.toBeInTheDocument();

    expect(screen.getByLabelText("Cards view")).toHaveAttribute(
      "data-state",
      "on",
    );
    expect(
      screen.queryByRole("columnheader", { name: "Name" }),
    ).not.toBeInTheDocument();

    const riskRow = screen.getByTestId("workflow-packages-row-risk_review");
    expect(riskRow).toHaveTextContent("Risk Review");
    expect(riskRow).toHaveTextContent("risk_review");
    expect(riskRow).toHaveTextContent("manifest-has");
    expect(riskRow).not.toHaveTextContent("Active");
    expect(riskRow).not.toHaveTextContent("Draft");
    expect(riskRow).toHaveTextContent("May 4, 2026");
    expect(
      within(riskRow).getByRole("button", { name: "Open package Risk Review" }),
    ).toBeVisible();
    expect(
      within(riskRow).getByRole("button", {
        name: "Launch package Risk Review",
      }),
    ).toBeVisible();
    expect(
      within(riskRow).getByRole("button", {
        name: "Delete package Risk Review",
      }),
    ).toBeVisible();

    const allocationRow = screen.getByTestId(
      "workflow-packages-row-allocation_draft",
    );
    expect(allocationRow).toHaveTextContent("Allocation Draft");
    expect(allocationRow).toHaveTextContent("allocation_draft");
    expect(allocationRow).not.toHaveTextContent("Active");
    expect(screen.queryByRole("columnheader", { name: "Status" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Table view"));
    expect(screen.getByLabelText("Table view")).toHaveAttribute(
      "data-state",
      "on",
    );

    for (const column of [
      "Name",
      "Key",
      "Manifest Hash",
      "Updated",
      "Actions",
    ]) {
      expect(screen.getByRole("columnheader", { name: column })).toBeVisible();
    }
    expect(screen.queryByRole("columnheader", { name: "Status" })).not.toBeInTheDocument();
  });

  it("filters packages through the command search and routes primary actions", () => {
    useWorkflowPackagesMock.mockReturnValue({
      data: {
        items: [
          packageFixture({ id: 9, key: "risk_review", name: "Risk Review" }),
          packageFixture({ id: 4, key: "macro_digest", name: "Macro Digest" }),
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });

    renderPage();

    fireEvent.change(
      screen.getByRole("textbox", { name: "Search workflow packages" }),
      {
        target: { value: "macro" },
      },
    );

    expect(
      screen.queryByTestId("workflow-packages-row-risk_review"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId("workflow-packages-row-macro_digest"),
    ).toBeVisible();

    fireEvent.click(
      screen.getByRole("button", { name: "Import workflow package manifest" }),
    );
    expect(navigateMock).toHaveBeenCalledWith("/workflow-packages/import");

    fireEvent.click(
      screen.getByRole("button", { name: "Create new workflow package" }),
    );
    expect(navigateMock).toHaveBeenCalledWith("/workflow-packages/new");

    fireEvent.click(
      screen.getByRole("button", { name: "Open package Macro Digest" }),
    );
    expect(navigateMock).toHaveBeenCalledWith("/workflow-packages/4");

    fireEvent.click(
      screen.getByRole("button", { name: "Launch package Macro Digest" }),
    );
    expect(navigateMock).toHaveBeenCalledWith("/workflow-packages/4/run");
  });

  it("permanently deletes packages and surfaces backend delete errors", async () => {
    useWorkflowPackagesMock.mockReturnValue({
      data: {
        items: [packageFixture({ id: 9, key: "risk_review", name: "Risk Review" })],
      },
      error: null,
      isError: false,
      isPending: false,
    });

    renderPage();

    fireEvent.click(
      screen.getByRole("button", { name: "Delete package Risk Review" }),
    );
    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      "Permanently delete Risk Review?",
    );
    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      "Historical run snapshots are preserved.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete package" }));

    await waitFor(() => expect(deletePackageMock).toHaveBeenCalledWith(9));
    expect(toastSuccessMock).toHaveBeenCalledWith(
      "Workflow package permanently deleted",
    );

    deletePackageMock.mockRejectedValueOnce(new Error("Package not found"));
    fireEvent.click(
      screen.getByRole("button", { name: "Delete package Risk Review" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete package" }));

    await waitFor(() =>
      expect(toastErrorMock).toHaveBeenCalledWith("Package not found"),
    );
  });
});
