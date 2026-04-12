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
  description: "Reviews public market context.",
  roleId: 3,
  roleKey: "macro_research_role",
  promptAppend: "Focus on public market data.",
  capabilityBundleKeys: ["research.context_bundle", "reports.latest_bundle"],
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
  useOrchestrationCharacter: () =>
    paramsMock.characterId
      ? {
          data: existingCharacter,
          isPending: false,
          isError: false,
          error: null,
        }
      : {
          data: undefined,
          isPending: false,
          isError: false,
          error: null,
        },
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

  it("creates bundle refs and resolves the selected role to roleId", async () => {
    paramsMock.characterId = undefined;
    createCharacterMock.mockResolvedValue({ id: 12 });

    render(<OrchestrationCharacterEditorPage />);

    fireEvent.change(screen.getByLabelText(/handle/i), {
      target: { value: "market_researcher" },
    });
    fireEvent.change(screen.getByLabelText(/name/i), {
      target: { value: "Market Researcher" },
    });
    fireEvent.change(screen.getByLabelText(/role/i), {
      target: { value: "3" },
    });
    fireEvent.change(screen.getByLabelText(/capability bundle refs/i), {
      target: { value: "research.context_bundle\nreports.latest_bundle" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save character/i }));

    await waitFor(() => expect(createCharacterMock).toHaveBeenCalledTimes(1));
    expect(createCharacterMock).toHaveBeenCalledWith({
      handle: "market_researcher",
      displayName: "Market Researcher",
      description: null,
      promptAppend: null,
      roleId: 3,
      capabilityBundleKeys: ["research.context_bundle", "reports.latest_bundle"],
      enabled: true,
    });
  });

  it("locks the handle, hydrates enabled, and persists the toggle through the update hook", async () => {
    updateCharacterMock.mockResolvedValue({ id: 7 });

    render(<OrchestrationCharacterEditorPage />);

    const enabledSwitch = screen.getByRole("switch", { name: /enabled/i });
    expect(screen.getByLabelText(/handle/i)).toBeDisabled();
    expect(screen.getByLabelText(/role/i)).toHaveValue("3");
    expect(screen.getByLabelText(/capability bundle refs/i)).toHaveValue(
      "research.context_bundle\nreports.latest_bundle",
    );
    expect(enabledSwitch).not.toBeChecked();

    fireEvent.click(enabledSwitch);
    fireEvent.click(screen.getByRole("button", { name: /save character/i }));

    await waitFor(() => expect(updateCharacterMock).toHaveBeenCalledTimes(1));
    expect(updateCharacterMock).toHaveBeenCalledWith({
      characterId: "7",
      payload: {
        displayName: "Market Researcher",
        description: "Reviews public market context.",
        promptAppend: "Focus on public market data.",
        roleId: 3,
        capabilityBundleKeys: ["research.context_bundle", "reports.latest_bundle"],
        enabled: true,
      },
    });
  });
});
