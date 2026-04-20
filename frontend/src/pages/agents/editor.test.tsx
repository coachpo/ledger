import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AgentsEditorPage } from "./editor";

const navigateMock = vi.fn();
const paramsMock: { agentId?: string } = {};
const searchParamsMock = new URLSearchParams();
const createAgentMock = vi.fn();
const updateAgentMock = vi.fn();
const archiveAgentMock = vi.fn();
const resolveTestPanelMock = vi.fn();
const toastErrorMock = vi.fn();
const toastSuccessMock = vi.fn();

const existingAgent = {
  id: 12,
  budgetUsd: "2.50",
  description: "Tracks macro context.",
  inputSchema: { ticker: "AAPL" },
  key: "macro_agent",
  maxToolRounds: 4,
  mcpServers: [{ id: 8, key: "quotes_mcp", version: 2 }],
  model: "gpt-5.4",
  name: "Macro Agent",
  outputSchema: { id: 4, key: "summary_schema", version: 5 },
  skills: [{ id: 7, key: "summarize_skill", version: 3 }],
  status: "draft",
  streaming: true,
  systemPrompt: "Summarize clearly.",
  temperature: 0.2,
  version: 9,
};

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
  useParams: () => paramsMock,
  useSearchParams: () => [searchParamsMock, vi.fn()],
}));

vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => toastErrorMock(...args),
    success: (...args: unknown[]) => toastSuccessMock(...args),
  },
}));

vi.mock("@/hooks/use-agents", () => ({
  useAgent: (agentId?: string) =>
    agentId
      ? { data: existingAgent, error: null, isError: false, isPending: false }
      : { data: undefined, error: null, isError: false, isPending: false },
  useCreateAgent: () => ({ isPending: false, mutateAsync: createAgentMock }),
  useUpdateAgent: () => ({ isPending: false, mutateAsync: updateAgentMock }),
  useArchiveAgent: () => ({ isPending: false, mutateAsync: archiveAgentMock }),
  useResolveAgentTestPanel: () => ({ isPending: false, mutateAsync: resolveTestPanelMock }),
}));

vi.mock("@/hooks/use-output-schemas", () => ({
  useOutputSchemas: () => ({
    data: { items: [{ id: 4, key: "summary_schema", name: "Summary Schema", version: 5 }] },
  }),
}));

vi.mock("@/hooks/use-skills", () => ({
  useSkills: () => ({ data: { items: [{ id: 7, key: "summarize_skill", name: "Summarize", version: 3 }] } }),
}));

vi.mock("@/hooks/use-mcp-servers", () => ({
  useMcpServers: () => ({ data: { items: [{ id: 8, key: "quotes_mcp", name: "Quotes", version: 2 }] } }),
}));

describe("AgentsEditorPage", () => {
  beforeEach(() => {
    paramsMock.agentId = undefined;
    searchParamsMock.delete("duplicateFrom");
    navigateMock.mockReset();
    createAgentMock.mockReset();
    updateAgentMock.mockReset();
    archiveAgentMock.mockReset();
    resolveTestPanelMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
  });

  it("shows a deterministic invalid-save error on create", async () => {
    render(<AgentsEditorPage />);

    fireEvent.click(screen.getByRole("button", { name: /save agent/i }));

    await waitFor(() => expect(toastErrorMock).toHaveBeenCalledWith("Key is required."));
    expect(createAgentMock).not.toHaveBeenCalled();
  });

  it("hydrates duplicate mode from an existing agent", () => {
    searchParamsMock.set("duplicateFrom", "12");

    render(<AgentsEditorPage />);

    expect(screen.getByRole("heading", { name: /duplicate agent/i })).toBeVisible();
    expect(screen.getByLabelText(/name/i)).toHaveValue("Macro Agent Copy");
    expect(screen.getByLabelText(/key/i)).toHaveValue("");
  });

  it("hydrates edit state and saves through the update hook", async () => {
    paramsMock.agentId = "12";
    updateAgentMock.mockResolvedValue({ id: 12 });

    render(<AgentsEditorPage />);

    expect(screen.getByLabelText(/key/i)).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "Macro Agent Updated" } });
    fireEvent.click(screen.getByRole("button", { name: /save agent/i }));

    await waitFor(() => expect(updateAgentMock).toHaveBeenCalledTimes(1));
    expect(updateAgentMock).toHaveBeenCalledWith({
      agentId: "12",
      payload: {
        budgetUsd: "2.50",
        description: "Tracks macro context.",
        inputSchema: { ticker: "AAPL" },
        maxToolRounds: 4,
        mcpServers: [{ mcpServerKey: "quotes_mcp", mcpServerVersion: 2 }],
        model: "gpt-5.4",
        name: "Macro Agent Updated",
        outputSchemaKey: "summary_schema",
        outputSchemaVersion: 5,
        skills: [{ skillKey: "summarize_skill", skillVersion: 3 }],
        streaming: true,
        systemPrompt: "Summarize clearly.",
        temperature: 0.2,
      },
    });
  });

  it("archives an existing agent", async () => {
    paramsMock.agentId = "12";
    archiveAgentMock.mockResolvedValue({ id: 12 });

    render(<AgentsEditorPage />);
    fireEvent.click(screen.getByTestId("agents-archive"));

    await waitFor(() => expect(archiveAgentMock).toHaveBeenCalledWith("12"));
    expect(navigateMock).toHaveBeenCalledWith("/agents");
  });

  it("runs the test panel and renders the resolved payload", async () => {
    paramsMock.agentId = "12";
    resolveTestPanelMock.mockResolvedValue({
      agent: existingAgent,
      sampleInput: { ticker: "AAPL" },
    });

    render(<AgentsEditorPage />);
    fireEvent.click(screen.getByRole("tab", { name: /test panel/i }));
    fireEvent.click(screen.getByTestId("agent-test-panel-run"));

    await waitFor(() => expect(resolveTestPanelMock).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId("agent-test-panel-result")).toBeVisible();
    expect(screen.getByText(/test panel ready/i)).toBeVisible();
  });
});
