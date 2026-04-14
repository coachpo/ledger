import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OrchestrationCharactersListPage } from "./list";

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
  throw new Error("Studio hooks must not be imported by orchestration character pages.");
});

vi.mock("@/hooks/use-runtime", () => {
  throw new Error("Runtime hooks must not be imported by orchestration character pages.");
});

vi.mock("@/lib/api/studio", () => {
  throw new Error("Studio API must not be imported by orchestration character pages.");
});

vi.mock("@/hooks/use-orchestration", () => ({
  useOrchestrationCharacters: () => ({
    data: [
      {
        id: 7,
        handle: "market_researcher",
        name: "Market Researcher",
        roleKey: "macro_research_role",
        createdAt: "2026-04-01T10:00:00Z",
        updatedAt: "2026-04-01T10:00:00Z",
      },
    ],
    isPending: false,
    isError: false,
  }),
  useDeleteOrchestrationCharacter: () => ({
    isPending: false,
    mutate: deleteMutateMock,
  }),
}));

describe("OrchestrationCharactersListPage", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    deleteMutateMock.mockReset();
    toastSuccessMock.mockReset();
    toastErrorMock.mockReset();
  });

  it("shows character-to-role mappings and a create character action", () => {
    render(<OrchestrationCharactersListPage />);

    expect(screen.getByText(/market researcher/i)).toBeInTheDocument();
    expect(screen.getByText(/macro_research_role/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create character/i })).toBeInTheDocument();
    expect(screen.queryByText(/studio/i)).not.toBeInTheDocument();
  });

  it("routes to the character editor and deletes a character from the list", async () => {
    deleteMutateMock.mockImplementation(
      (_characterId: number, options?: { onSuccess?: () => void }) => {
        options?.onSuccess?.();
      },
    );

    render(<OrchestrationCharactersListPage />);

    fireEvent.click(screen.getByRole("button", { name: /edit market researcher/i }));
    expect(navigateMock).toHaveBeenCalledWith("/orchestration/characters/7/edit");

    fireEvent.click(screen.getByRole("button", { name: /delete market researcher/i }));

    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));

    await waitFor(() => {
      expect(deleteMutateMock).toHaveBeenCalledWith(
        7,
        expect.objectContaining({
          onError: expect.any(Function),
          onSuccess: expect.any(Function),
        }),
      );
    });
    expect(toastSuccessMock).toHaveBeenCalledWith("Character deleted");
  });
});
