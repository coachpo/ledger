import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { McpServersEditorPage } from "./editor";

const navigateMock = vi.fn();
const paramsMock: { serverId?: string } = {};
const createServerMock = vi.fn();
const updateServerMock = vi.fn();
const activateServerMock = vi.fn();
const testConnectionMock = vi.fn();
const toastErrorMock = vi.fn();
const toastSuccessMock = vi.fn();

const existingServer = {
  id: 4,
  key: "quotes_mcp",
  version: 6,
  status: "draft",
  name: "Quotes MCP",
  description: "Serves quotes.",
  enabled: true,
  transport: "stdio",
  command: "quotesd",
  args: ["--mode", "stdio"],
  env: { TOKEN: "abc" },
  createdAt: "2026-04-21T12:00:00Z",
  updatedAt: "2026-04-21T12:30:00Z",
};

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
  useParams: () => paramsMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => toastErrorMock(...args),
    success: (...args: unknown[]) => toastSuccessMock(...args),
  },
}));

vi.mock("@/hooks/use-mcp-servers", () => ({
  useMcpServer: () =>
    paramsMock.serverId
      ? { data: existingServer, error: null, isError: false, isPending: false }
      : { data: undefined, error: null, isError: false, isPending: false },
  useCreateMcpServer: () => ({ isPending: false, mutateAsync: createServerMock }),
  useUpdateMcpServer: () => ({ isPending: false, mutateAsync: updateServerMock }),
  useActivateMcpServer: () => ({ isPending: false, mutateAsync: activateServerMock }),
  useTestMcpServerConnection: () => ({ isPending: false, mutateAsync: testConnectionMock }),
}));

describe("McpServersEditorPage", () => {
  beforeEach(() => {
    paramsMock.serverId = undefined;
    navigateMock.mockReset();
    createServerMock.mockReset();
    updateServerMock.mockReset();
    activateServerMock.mockReset();
    testConnectionMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
  });

  it("submits a flat create body with key", async () => {
    createServerMock.mockResolvedValue({ id: 9 });
    render(<McpServersEditorPage />);

    fireEvent.change(screen.getByLabelText(/key/i), { target: { value: "market_data" } });
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "Market Data MCP" } });
    fireEvent.change(screen.getByLabelText(/args json/i), {
      target: { value: '["-m", "app.agents.mcp.stock_analysis_reference_server"]' },
    });
    fireEvent.click(screen.getByRole("button", { name: /save mcp server/i }));

    await waitFor(() => expect(createServerMock).toHaveBeenCalledTimes(1));
    expect(createServerMock).toHaveBeenCalledWith({
      args: ["-m", "app.agents.mcp.stock_analysis_reference_server"],
      command: "python3",
      description: "",
      enabled: true,
      env: {},
      key: "market_data",
      name: "Market Data MCP",
      transport: "stdio",
    });
    expect(navigateMock).toHaveBeenCalledWith("/mcp-servers/9/edit");
  });

  it("loads flat detail fields and submits a flat patch body without key", async () => {
    paramsMock.serverId = "4";
    updateServerMock.mockResolvedValue({ id: 10 });
    render(<McpServersEditorPage />);

    expect(screen.getByLabelText(/name/i)).toHaveValue("Quotes MCP");
    expect(screen.getByLabelText(/args json/i)).toHaveValue(JSON.stringify(["--mode", "stdio"], null, 2));
    expect(screen.getByLabelText(/key/i)).toHaveValue("quotes_mcp");
    expect(screen.getByLabelText(/key/i)).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "Updated Quotes MCP" } });
    fireEvent.click(screen.getByRole("button", { name: /save mcp server/i }));

    await waitFor(() => expect(updateServerMock).toHaveBeenCalledTimes(1));
    expect(updateServerMock).toHaveBeenCalledWith({
      payload: {
        args: ["--mode", "stdio"],
        command: "quotesd",
        description: "Serves quotes.",
        enabled: true,
        env: { TOKEN: "abc" },
        name: "Updated Quotes MCP",
        transport: "stdio",
      },
      serverId: "4",
    });
    expect(navigateMock).toHaveBeenCalledWith("/mcp-servers/10/edit");
  });

  it("activates a draft MCP server", async () => {
    paramsMock.serverId = "4";
    activateServerMock.mockResolvedValue({ id: 4 });

    render(<McpServersEditorPage />);
    fireEvent.click(screen.getByTestId("mcp-server-activate"));

    await waitFor(() => expect(activateServerMock).toHaveBeenCalledWith("4"));
    expect(toastSuccessMock).toHaveBeenCalledWith("MCP server activated");
  });

  it("surfaces successful connection feedback inline", async () => {
    paramsMock.serverId = "4";
    testConnectionMock.mockResolvedValue({ ok: true, message: "Connection OK" });

    render(<McpServersEditorPage />);
    fireEvent.click(screen.getByTestId("mcp-server-test-connection"));

    await waitFor(() => expect(screen.getByTestId("mcp-server-connection-feedback")).toBeVisible());
    expect(screen.getByText(/connection succeeded/i)).toBeVisible();
    expect(screen.getByText(/connection ok/i)).toBeVisible();
  });

  it("surfaces failed connection feedback inline", async () => {
    paramsMock.serverId = "4";
    testConnectionMock.mockRejectedValue(new Error("Connection refused"));

    render(<McpServersEditorPage />);
    fireEvent.click(screen.getByTestId("mcp-server-test-connection"));

    await waitFor(() => expect(screen.getByTestId("mcp-server-connection-feedback")).toBeVisible());
    expect(screen.getByText(/connection test failed/i)).toBeVisible();
    expect(screen.getByText(/connection refused/i)).toBeVisible();
  });
});
