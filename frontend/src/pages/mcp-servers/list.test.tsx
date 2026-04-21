import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { McpServersListPage } from "./list";

const {
  archiveMcpServerMock,
  navigateMock,
  toastErrorMock,
  toastSuccessMock,
  useMcpServersMock,
} = vi.hoisted(() => ({
  archiveMcpServerMock: vi.fn(),
  navigateMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  useMcpServersMock: vi.fn(),
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

vi.mock("@/hooks/use-mcp-servers", () => ({
  useArchiveMcpServer: () => ({ isPending: false, mutateAsync: archiveMcpServerMock }),
  useMcpServers: () => useMcpServersMock(),
}));

describe("McpServersListPage", () => {
  beforeEach(() => {
    archiveMcpServerMock.mockReset();
    navigateMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    useMcpServersMock.mockReturnValue({
      data: {
        items: [
          {
            id: 4,
            key: "quotes_mcp",
            name: "Quotes MCP",
            description: "Serves quotes.",
            transport: "stdio",
            enabled: true,
            status: "draft",
            version: 6,
          },
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });
  });

  it("renders rows, archives, and navigates to create/edit routes", async () => {
    archiveMcpServerMock.mockResolvedValue({ id: 4 });

    render(<McpServersListPage />);

    expect(screen.getByTestId("mcp-servers-row-quotes_mcp")).toBeVisible();
    expect(screen.getByText(/configured for stdio command \+ args transport\./i)).toBeVisible();

    fireEvent.click(screen.getByTestId("mcp-servers-archive-quotes_mcp"));
    await waitFor(() => expect(archiveMcpServerMock).toHaveBeenCalledWith(4));
    expect(toastSuccessMock).toHaveBeenCalledWith("MCP server archived");

    fireEvent.click(screen.getByTestId("mcp-servers-new"));
    expect(navigateMock).toHaveBeenCalledWith("/mcp-servers/new");

    fireEvent.click(screen.getByTestId("mcp-servers-open-quotes_mcp"));
    expect(navigateMock).toHaveBeenCalledWith("/mcp-servers/4/edit");
  });

  it("archives an MCP server from the list", async () => {
    archiveMcpServerMock.mockResolvedValue({ id: 4 });

    render(<McpServersListPage />);

    fireEvent.click(screen.getByTestId("mcp-servers-archive-quotes_mcp"));

    await waitFor(() => expect(archiveMcpServerMock).toHaveBeenCalledWith(4));
    expect(toastSuccessMock).toHaveBeenCalledWith("MCP server archived");
  });
});
