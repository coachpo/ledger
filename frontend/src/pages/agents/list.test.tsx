import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AgentsListPage } from "./list";

const navigateMock = vi.fn();
const archiveAgentMock = vi.fn();
const useAgentsMock = vi.fn();
const toastSuccessMock = vi.fn();

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: (...args: unknown[]) => toastSuccessMock(...args),
  },
}));

vi.mock("@/hooks/use-agents", () => ({
  useAgents: () => useAgentsMock(),
  useArchiveAgent: () => ({ isPending: false, mutateAsync: archiveAgentMock }),
}));

describe("AgentsListPage", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    archiveAgentMock.mockReset();
    toastSuccessMock.mockReset();
    useAgentsMock.mockReturnValue({
      data: {
        items: [
          {
            id: 11,
            key: "macro_agent",
            name: "Macro Agent",
            description: "Summarizes macro context.",
            modelConnection: { modelId: "gpt-5.4" },
            outputSchema: { key: "summary_schema" },
            skills: [{ id: 1 }],
            mcpServers: [{ id: 2 }],
            status: "draft",
            streaming: true,
            version: 3,
          },
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });
  });

  it("renders rows and navigates to create edit and duplicate routes", () => {
    render(<AgentsListPage />);

    expect(screen.getByTestId("agents-row-macro_agent")).toBeVisible();

    fireEvent.click(screen.getByTestId("agents-new"));
    expect(navigateMock).toHaveBeenCalledWith("/agents/new");

    fireEvent.click(screen.getByTestId("agents-open-macro_agent"));
    expect(navigateMock).toHaveBeenCalledWith("/agents/11/edit");

    fireEvent.click(screen.getByTestId("agents-duplicate-macro_agent"));
    expect(navigateMock).toHaveBeenCalledWith("/agents/new?duplicateFrom=11");
  });

  it("archives an agent from the list", async () => {
    archiveAgentMock.mockResolvedValue({ id: 11 });

    render(<AgentsListPage />);
    fireEvent.click(screen.getByTestId("agents-archive-macro_agent"));

    await waitFor(() => expect(archiveAgentMock).toHaveBeenCalledWith(11));
    expect(toastSuccessMock).toHaveBeenCalledWith("Agent archived");
  });
});
