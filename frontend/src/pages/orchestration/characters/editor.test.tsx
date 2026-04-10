import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OrchestrationCharacterEditorPage } from "./editor";

const navigateMock = vi.fn();
const paramsMock: { characterId?: string } = { characterId: "7" };
const createCharacterMock = vi.fn();
const updateCharacterMock = vi.fn();
const existingCharacter = {
  id: 7,
  handle: "market_researcher",
  displayName: "Market Researcher",
  roleId: 3,
  roleKey: "macro_research_role",
  promptAppend: "Focus on public market data.",
  enabled: false,
  version: 2,
  createdAt: "2026-04-01T10:00:00Z",
  updatedAt: "2026-04-01T10:00:00Z",
};
const roleOptions = [
  {
    id: 3,
    key: "macro_research_role",
    name: "Macro Research Role",
    version: 1,
  },
];

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
  useParams: () => paramsMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/hooks/use-orchestration", () => ({
  useOrchestrationCharacter: () => ({
    data: existingCharacter,
    isPending: false,
    isError: false,
    error: null,
  }),
  useOrchestrationRoles: () => ({
    data: roleOptions,
    isPending: false,
    isError: false,
    error: null,
  }),
  useCreateOrchestrationCharacter: () => ({
    isPending: false,
    mutateAsync: createCharacterMock,
  }),
  useUpdateOrchestrationCharacter: () => ({
    isPending: false,
    mutateAsync: updateCharacterMock,
  }),
}));

describe("OrchestrationCharacterEditorPage", () => {
  beforeEach(() => {
    paramsMock.characterId = "7";
    navigateMock.mockReset();
    createCharacterMock.mockReset();
    updateCharacterMock.mockReset();
  });

  it("locks the handle, hydrates enabled, and persists the toggle through the update hook", async () => {
    updateCharacterMock.mockResolvedValue({ id: 7 });

    render(<OrchestrationCharacterEditorPage />);

    const enabledSwitch = screen.getByRole("switch", { name: /enabled/i });
    expect(screen.getByLabelText(/handle/i)).toBeDisabled();
    expect(screen.getByLabelText(/role/i)).toHaveValue("3");
    expect(enabledSwitch).not.toBeChecked();

    fireEvent.click(enabledSwitch);
    fireEvent.click(screen.getByRole("button", { name: /save character/i }));

    await waitFor(() => expect(updateCharacterMock).toHaveBeenCalledTimes(1));
    expect(updateCharacterMock).toHaveBeenCalledWith({
      characterId: "7",
      data: {
        displayName: "Market Researcher",
        description: null,
        promptAppend: "Focus on public market data.",
        roleId: 3,
        enabled: true,
      },
    });
  });
});
