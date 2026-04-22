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

const existingInputSchema = {
  additionalProperties: false,
  properties: {
    ticker: { type: "string" },
  },
  required: ["ticker"],
  type: "object",
};

const existingAgent = {
  id: 12,
  budgetUsd: "2.50",
  description: "Tracks macro context.",
  inputSchema: existingInputSchema,
  key: "macro_agent",
  maxToolRounds: 4,
  mcpServers: [
    {
      boundary: { readOnly: false },
      description: "Quotes feed",
      enabled: true,
      id: 8,
      key: "quotes_mcp",
      name: "Quotes",
      status: "active",
      transport: "stdio",
      version: 2,
    },
  ],
  model: "gpt-5.4",
  name: "Macro Agent",
  outputSchema: {
    description: "Summary schema",
    id: 4,
    jsonSchema: { type: "object" },
    key: "summary_schema",
    kind: "standalone",
    name: "Summary Schema",
    status: "published",
    version: 5,
  },
  skills: [
    {
      description: "Summaries",
      id: 7,
      key: "summarize_skill",
      name: "Summarize",
      status: "published",
      version: 3,
    },
  ],
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
    data: {
      items: [
        {
          description: "Summary schema",
          id: 4,
          key: "summary_schema",
          name: "Summary Schema",
          status: "published",
          version: 5,
        },
      ],
    },
  }),
}));

vi.mock("@/hooks/use-skills", () => ({
  useSkills: () => ({
    data: {
      items: [
        {
          description: "Summaries",
          id: 7,
          key: "summarize_skill",
          name: "Summarize",
          status: "published",
          version: 3,
        },
      ],
    },
  }),
}));

vi.mock("@/hooks/use-mcp-servers", () => ({
  useMcpServers: () => ({
    data: {
      items: [
        {
          description: "Quotes feed",
          id: 8,
          key: "quotes_mcp",
          name: "Quotes",
          status: "active",
          version: 2,
        },
      ],
    },
  }),
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

  it("removes raw JSON and free-text authoring surfaces on create", async () => {
    render(<AgentsEditorPage />);

    expect(screen.queryByLabelText(/input schema json/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/sample input json/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^skills$/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^mcp servers$/i)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /output schema binding/i })).toBeVisible();
    expect(screen.getByRole("heading", { name: /skill bindings/i })).toBeVisible();
    expect(screen.getByRole("heading", { name: /mcp server bindings/i })).toBeVisible();
    expect(screen.getByRole("heading", { name: /^Input schema$/i })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: /save agent/i }));

    await waitFor(() => expect(toastErrorMock).toHaveBeenCalledWith("Key is required."));
    expect(createAgentMock).not.toHaveBeenCalled();
  });

  it("hydrates duplicate mode from an existing agent with structured bindings", () => {
    searchParamsMock.set("duplicateFrom", "12");

    render(<AgentsEditorPage />);

    expect(screen.getByRole("heading", { name: /duplicate agent/i })).toBeVisible();
    expect(screen.getByLabelText(/^Name$/i)).toHaveValue("Macro Agent Copy");
    expect(screen.getByLabelText(/^Key$/i)).toHaveValue("");
    expect(screen.queryByLabelText(/input schema json/i)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /output schema binding/i })).toBeVisible();
  });

  it("hydrates edit state and saves through the update hook with structured payloads", async () => {
    paramsMock.agentId = "12";
    updateAgentMock.mockResolvedValue({ id: 12 });

    render(<AgentsEditorPage />);

    expect(screen.getByLabelText(/^Key$/i)).toBeDisabled();
    expect(screen.queryByLabelText(/input schema json/i)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/^Name$/i), { target: { value: "Macro Agent Updated" } });
    fireEvent.click(screen.getByRole("button", { name: /save agent/i }));

    await waitFor(() => expect(updateAgentMock).toHaveBeenCalledTimes(1));
    expect(updateAgentMock).toHaveBeenCalledWith({
      agentId: "12",
      payload: {
        budgetUsd: "2.50",
        description: "Tracks macro context.",
        inputSchema: existingInputSchema,
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

  it("runs the test panel from the structured sample input form", async () => {
    paramsMock.agentId = "12";
    resolveTestPanelMock.mockResolvedValue({
      agent: existingAgent,
      sampleInput: { ticker: "AAPL" },
    });

    render(<AgentsEditorPage />);
    fireEvent.click(screen.getByRole("tab", { name: /test panel/i }));

    expect(screen.queryByLabelText(/sample input json/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("agent-test-panel-run"));

    await waitFor(() =>
      expect(resolveTestPanelMock).toHaveBeenCalledWith({ sampleInput: { ticker: "AAPL" } }),
    );
    expect(screen.getByTestId("agent-test-panel-result")).toBeVisible();
    expect(screen.getByText(/test panel ready/i)).toBeVisible();
  });
});
