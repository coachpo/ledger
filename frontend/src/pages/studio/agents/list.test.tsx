import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StudioAgentsListPage } from "./list";

const navigateMock = vi.fn();

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
}));

vi.mock("@/hooks/use-studio", () => ({
  useStudioAgentSpecs: () => ({
    data: {
      items: [
        {
          id: 1,
          key: "managed_agent",
          version: 2,
          origin: "managed",
          status: "DRAFT",
          name: "Managed Agent",
          instructions: "Managed instructions.",
          modelPolicy: {},
          finalOutputContract: null,
          defaultCapabilityBundleKeys: [],
          defaultPersonaProfileKeys: [],
          createdAt: "2026-04-14T10:00:00Z",
          updatedAt: "2026-04-14T10:00:00Z",
        },
        {
          id: 2,
          key: "seeded_agent",
          version: 1,
          origin: "seeded",
          status: "ACTIVE",
          name: "Seeded Agent",
          instructions: "Seeded instructions.",
          modelPolicy: {},
          finalOutputContract: null,
          defaultCapabilityBundleKeys: [],
          defaultPersonaProfileKeys: [],
          createdAt: "2026-04-14T10:00:00Z",
          updatedAt: "2026-04-14T10:00:00Z",
        },
      ],
    },
    isError: false,
    isPending: false,
  }),
}));

describe("StudioAgentsListPage", () => {
  beforeEach(() => {
    navigateMock.mockReset();
  });

  it("shows managed and seeded agents with editability treatment", () => {
    render(<StudioAgentsListPage />);

    expect(screen.getByTestId("studio-agents-list")).toBeInTheDocument();
    expect(screen.getByTestId("studio-agents-row-managed_agent")).toBeInTheDocument();
    expect(screen.getByTestId("studio-agents-row-seeded_agent")).toBeInTheDocument();
    expect(screen.getAllByText(/editable/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/read-only/i).length).toBeGreaterThan(0);
  });

  it("navigates to the key-based Studio editor routes", () => {
    render(<StudioAgentsListPage />);

    fireEvent.click(screen.getByTestId("studio-agents-new"));
    expect(navigateMock).toHaveBeenCalledWith("/studio/agents/new");

    fireEvent.click(screen.getByTestId("studio-agents-open-managed_agent"));
    expect(navigateMock).toHaveBeenCalledWith("/studio/agents/managed_agent/edit");
  });
});
