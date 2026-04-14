import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OrchestrationRolesListPage } from "./list";

const {
  navigateMock,
  deleteMutateMock,
  toastSuccessMock,
  toastErrorMock,
} = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  deleteMutateMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  toastErrorMock: vi.fn(),
}));

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}));

vi.mock("@/hooks/use-studio", () => {
  throw new Error("Studio hooks must not be imported by orchestration role pages.");
});

vi.mock("@/hooks/use-runtime", () => {
  throw new Error("Runtime hooks must not be imported by orchestration role pages.");
});

vi.mock("@/lib/api/studio", () => {
  throw new Error("Studio API must not be imported by orchestration role pages.");
});

vi.mock("@/hooks/use-orchestration", () => ({
  useOrchestrationRoles: () => ({
    data: [
      {
        id: 1,
        handle: "librarian",
        name: "Librarian",
        systemPrompt: "Research and summarize.",
        createdAt: "2026-04-01T10:00:00Z",
        updatedAt: "2026-04-01T10:00:00Z",
      },
    ],
    isPending: false,
    isError: false,
  }),
  useDeleteOrchestrationRole: () => ({
    isPending: false,
    mutate: deleteMutateMock,
  }),
}));

describe("OrchestrationRolesListPage", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    deleteMutateMock.mockReset();
    toastSuccessMock.mockReset();
    toastErrorMock.mockReset();
  });

  it("shows the role catalog and a create role action", () => {
    render(<OrchestrationRolesListPage />);

    expect(screen.getByText(/librarian/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create role/i })).toBeInTheDocument();
    expect(screen.getByText(/shared system prompts/i)).toBeInTheDocument();
    expect(screen.queryByText(/studio/i)).not.toBeInTheDocument();
  });

  it("routes to the role editor and deletes a role from the list", async () => {
    deleteMutateMock.mockImplementation((_roleId: number, options?: { onSuccess?: () => void }) => {
      options?.onSuccess?.();
    });

    render(<OrchestrationRolesListPage />);

    fireEvent.click(screen.getByRole("button", { name: /edit librarian/i }));
    expect(navigateMock).toHaveBeenCalledWith("/orchestration/roles/1/edit");

    fireEvent.click(screen.getByRole("button", { name: /delete librarian/i }));

    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));

    await waitFor(() => {
      expect(deleteMutateMock).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          onError: expect.any(Function),
          onSuccess: expect.any(Function),
        }),
      );
    });
    expect(toastSuccessMock).toHaveBeenCalledWith("Role deleted");
  });
});
