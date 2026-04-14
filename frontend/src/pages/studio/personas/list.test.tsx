import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StudioPersonasListPage } from "./list";

const navigateMock = vi.fn();

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
}));

vi.mock("@/hooks/use-studio", () => ({
  useStudioPersonas: () => ({
    data: {
      items: [
        {
          id: 5,
          key: "managed.persona.alpha",
          version: 2,
          origin: "managed",
          status: "DRAFT",
          kind: "managed_persona",
          displayName: "Managed Persona Alpha",
          enabled: true,
          handle: null,
          canonicalTargetId: "persona:managed.persona.alpha",
          parentProfileKey: null,
          parentProfileVersion: null,
          legacySourceVersion: null,
          systemPromptFragment: "System instructions.",
          promptAppendFragment: "Append instructions.",
          defaultCapabilityBundleKeys: [],
          createdAt: "2026-04-14T10:00:00Z",
          updatedAt: "2026-04-14T10:00:00Z",
        },
        {
          id: 11,
          key: "imported.character.analyst",
          version: 4,
          origin: "imported",
          status: "ACTIVE",
          kind: "character_profile",
          displayName: "Analyst",
          enabled: true,
          handle: "analyst",
          canonicalTargetId: "character:analyst",
          parentProfileKey: null,
          parentProfileVersion: null,
          legacySourceVersion: 3,
          systemPromptFragment: "System instructions.",
          promptAppendFragment: "Append instructions.",
          defaultCapabilityBundleKeys: [],
          createdAt: "2026-04-14T10:00:00Z",
          updatedAt: "2026-04-14T10:00:00Z",
        },
      ],
    },
    isError: false,
    isPending: false,
  }),
}));

describe("StudioPersonasListPage", () => {
  beforeEach(() => {
    navigateMock.mockReset();
  });

  it("renders managed and imported personas with matching edit vs inspect affordances", () => {
    render(<StudioPersonasListPage />);

    const managedRow = screen.getByTestId("studio-personas-row-managed.persona.alpha");
    const importedRow = screen.getByTestId("studio-personas-row-imported.character.analyst");

    expect(screen.getByTestId("studio-personas-list")).toBeInTheDocument();
    expect(managedRow).toBeInTheDocument();
    expect(importedRow).toBeInTheDocument();
    expect(within(managedRow).queryByText(/read-only/i)).not.toBeInTheDocument();
    expect(within(importedRow).getByText(/read-only/i)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("studio-personas-open-managed.persona.alpha"));
    fireEvent.click(screen.getByTestId("studio-personas-open-imported.character.analyst"));

    expect(navigateMock).toHaveBeenNthCalledWith(1, "/studio/personas/managed.persona.alpha/edit");
    expect(navigateMock).toHaveBeenNthCalledWith(2, "/studio/personas/imported.character.analyst/edit");
    expect(screen.getByText("Edit")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /inspect analyst/i })).toBeInTheDocument();
  });
});
