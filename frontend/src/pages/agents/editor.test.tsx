import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { stringifyJson } from "@/lib/platform-authoring/common/serialization";
import { schemaBuilderToJsonSchema } from "@/lib/platform-authoring/schema/codec";
import type { AgentRead } from "@/lib/types/agent";
import type { ModelConnectionListItemRead } from "@/lib/types/model-connection";
import type { RunCreatedRead } from "@/lib/types/run";

import { AgentsEditorPage } from "./editor";

const navigateMock = vi.fn();
const paramsMock: { agentId?: string } = {};
const searchParamsMock = new URLSearchParams();
const createAgentMock = vi.fn();
const updateAgentMock = vi.fn();
const archiveAgentMock = vi.fn();
const createAgentRunMock = vi.fn();
const toastErrorMock = vi.fn();
const toastSuccessMock = vi.fn();
const useModelConnectionsMock = vi.fn();

const existingInputSchema = {
  additionalProperties: false,
  properties: {
    ticker: { type: "string" },
  },
  required: ["ticker"],
  type: "object",
};

const activeModelConnection: ModelConnectionListItemRead = {
  apiKeyLast4: "4242",
  baseUrl: "https://api.openai.com/v1",
  description: "Primary production connection",
  hasApiKey: true,
  id: 44,
  lastTestMessage: "Healthy",
  lastTestOk: true,
  lastTestedAt: "2026-04-22T08:00:00Z",
  modelId: "gpt-4.1",
  name: "Primary OpenAI",
  organization: "org_live",
  project: "proj_live",
  reasoningEffort: "high",
  status: "active",
  timeoutSeconds: 90,
};

const archivedModelConnection: ModelConnectionListItemRead = {
  apiKeyLast4: null,
  baseUrl: "https://archive.openai.com/v1",
  description: "Retired but still referenced",
  hasApiKey: false,
  id: 91,
  lastTestMessage: "Expired key",
  lastTestOk: false,
  lastTestedAt: "2026-04-21T08:00:00Z",
  modelId: "gpt-4o-mini",
  name: "Legacy Archive",
  organization: null,
  project: null,
  reasoningEffort: "low",
  status: "archived",
  timeoutSeconds: 45,
};

const existingAgent = {
  budgetUsd: "2.50",
  description: "Tracks macro context.",
  inputSchema: existingInputSchema,
  key: "macro_agent",
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
  modelConnection: activeModelConnection,
  modelConnectionId: activeModelConnection.id,
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
  systemPrompt: "Summarize clearly.",
  version: 9,
} as unknown as AgentRead;

const archivedAgent = {
  ...existingAgent,
  modelConnection: archivedModelConnection,
  modelConnectionId: archivedModelConnection.id,
} as unknown as AgentRead;

let currentAgent: AgentRead = existingAgent;

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
      ? { data: currentAgent, error: null, isError: false, isPending: false }
      : { data: undefined, error: null, isError: false, isPending: false },
  useArchiveAgent: () => ({ isPending: false, mutateAsync: archiveAgentMock }),
  useCreateAgent: () => ({ isPending: false, mutateAsync: createAgentMock }),
  useCreateAgentRun: () => ({ isPending: false, mutateAsync: createAgentRunMock }),
  useUpdateAgent: () => ({ isPending: false, mutateAsync: updateAgentMock }),
}));

vi.mock("@/hooks/use-model-connections", () => ({
  useModelConnections: (params?: unknown) => useModelConnectionsMock(params),
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

function renderAgentsEditorPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <AgentsEditorPage />
    </QueryClientProvider>,
  );
}

describe("AgentsEditorPage", () => {
  beforeEach(() => {
    archiveAgentMock.mockReset();
    createAgentMock.mockReset();
    createAgentRunMock.mockReset();
    currentAgent = existingAgent;
    navigateMock.mockReset();
    paramsMock.agentId = undefined;
    searchParamsMock.delete("duplicateFrom");
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    updateAgentMock.mockReset();
    useModelConnectionsMock.mockReset();
    useModelConnectionsMock.mockReturnValue({
      data: { items: [activeModelConnection] },
      error: null,
      isError: false,
      isPending: false,
    });
  });

  it("shows builder, exact raw schema JSON, and sample input raw JSON while still requiring a model connection on create", async () => {
    renderAgentsEditorPage();

    expect(useModelConnectionsMock).toHaveBeenCalledWith({ status: "active" });
    expect(screen.queryByLabelText(/^Model$/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Temperature$/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Max Tool Rounds$/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Streaming$/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/^Model Connection$/i)).toBeVisible();
    expect(screen.queryByLabelText(/^Input Schema JSON$/i)).not.toBeInTheDocument();
    expect(screen.getByTestId("agent-input-schema-raw-json")).toBeVisible();
    expect(screen.getByTestId("agent-input-schema-preview")).toBeVisible();
    expect(screen.queryByLabelText(/^skills$/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^mcp servers$/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("output-schema-add-field"));
    fireEvent.change(screen.getByDisplayValue("field_1"), { target: { value: "ticker" } });

    await waitFor(() => {
      expect(
        within(screen.getByTestId("agent-input-schema-preview")).getByRole("textbox", {
          name: /sample input/i,
        }),
      ).toHaveValue(stringifyJson({ ticker: "AAPL" }));
    });

    const rawJsonTextbox = within(screen.getByTestId("agent-input-schema-raw-json")).getByRole(
      "textbox",
      {
        name: /exact raw schema json/i,
      },
    );

    expect(rawJsonTextbox).toHaveValue(
      stringifyJson(
        schemaBuilderToJsonSchema({
          kind: "object",
          allowAdditionalProperties: false,
          fields: [{ name: "ticker", required: true, schema: { kind: "string" } }],
        }),
      ),
    );
    expect(rawJsonTextbox).toHaveAttribute("readonly");

    const sampleInputTextbox = within(screen.getByTestId("agent-input-schema-preview")).getByRole(
      "textbox",
      {
        name: /sample input/i,
      },
    );

    expect(sampleInputTextbox).toHaveValue(stringifyJson({ ticker: "AAPL" }));
    expect(sampleInputTextbox).toHaveAttribute("readonly");

    fireEvent.change(screen.getByLabelText(/^Key$/i), { target: { value: "macro_agent" } });
    fireEvent.change(screen.getByLabelText(/^Name$/i), { target: { value: "Macro Agent" } });
    fireEvent.click(screen.getByRole("button", { name: /save agent/i }));

    await waitFor(() => expect(toastErrorMock).toHaveBeenCalledWith("Model connection is required."));
    expect(createAgentMock).not.toHaveBeenCalled();
  });

  it("hydrates duplicate mode from an existing agent with structured bindings", () => {
    searchParamsMock.set("duplicateFrom", "12");

    renderAgentsEditorPage();

    expect(screen.getByRole("heading", { name: /duplicate agent/i })).toBeVisible();
    expect(screen.getByLabelText(/^Name$/i)).toHaveValue("Macro Agent Copy");
    expect(screen.getByLabelText(/^Key$/i)).toHaveValue("");
    expect(screen.queryByLabelText(/^Model$/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Temperature$/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Max Tool Rounds$/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Streaming$/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/^Model Connection$/i)).toHaveTextContent("Primary OpenAI · gpt-4.1");
  });

  it("hydrates edit state and saves through the update hook with modelConnectionId only", async () => {
    paramsMock.agentId = "12";
    updateAgentMock.mockResolvedValue({ id: 12 });

    renderAgentsEditorPage();

    expect(screen.getByLabelText(/^Key$/i)).toBeDisabled();
    expect(screen.queryByLabelText(/^Model$/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Temperature$/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Max Tool Rounds$/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Streaming$/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/^Model Connection$/i)).toHaveTextContent("Primary OpenAI · gpt-4.1");

    fireEvent.change(screen.getByLabelText(/^Name$/i), { target: { value: "Macro Agent Updated" } });
    fireEvent.click(screen.getByRole("button", { name: /save agent/i }));

    await waitFor(() => expect(updateAgentMock).toHaveBeenCalledTimes(1));
    expect(updateAgentMock).toHaveBeenCalledWith({
      agentId: "12",
      payload: {
        budgetUsd: "2.50",
        description: "Tracks macro context.",
        inputSchema: existingInputSchema,
        mcpServers: [{ mcpServerKey: "quotes_mcp", mcpServerVersion: 2 }],
        modelConnectionId: 44,
        name: "Macro Agent Updated",
        outputSchemaKey: "summary_schema",
        outputSchemaVersion: 5,
        skills: [{ skillKey: "summarize_skill", skillVersion: 3 }],
        systemPrompt: "Summarize clearly.",
      },
    });
  });

  it("renders an existing archived model connection on edit", () => {
    currentAgent = archivedAgent;
    paramsMock.agentId = "12";

    renderAgentsEditorPage();

    expect(screen.getByLabelText(/^Model Connection$/i)).toHaveTextContent("Legacy Archive · gpt-4o-mini");
    expect(screen.getByText(/archived model connection in use/i)).toBeVisible();
    expect(
      screen.getByText("https://archive.openai.com/v1 · low reasoning · archived"),
    ).toBeVisible();
  });

  it("archives an existing agent", async () => {
    paramsMock.agentId = "12";
    archiveAgentMock.mockResolvedValue({ id: 12 });

    renderAgentsEditorPage();
    fireEvent.click(screen.getByTestId("agents-archive"));

    await waitFor(() => expect(archiveAgentMock).toHaveBeenCalledWith("12"));
    expect(navigateMock).toHaveBeenCalledWith("/agents");
  });

  it("launches a real run from the structured input form and navigates to the run detail route", async () => {
    paramsMock.agentId = "12";
    createAgentRunMock.mockResolvedValue({
      createdAt: "2026-04-26T12:00:00Z",
      id: 321,
      status: "running",
      targetId: 12,
      targetKey: "macro_agent",
      targetKind: "agent",
      targetVersion: 9,
      traceId: null,
    } satisfies RunCreatedRead);

    renderAgentsEditorPage();
    expect(screen.queryByRole("tab", { name: /test panel/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /^run$/i }));

    expect(screen.queryByLabelText(/sample input json/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/exact raw result json/i)).not.toBeInTheDocument();
    expect(screen.getByTestId("agent-run-panel-input-form")).toBeVisible();
    expect(screen.getByTestId("agent-run-panel-input-raw-json")).toBeVisible();
    expect(screen.getByLabelText("Exact raw run-input JSON")).toHaveValue(
      stringifyJson({ ticker: "AAPL" }),
    );
    expect(screen.getByLabelText("Exact raw run-input JSON")).toHaveAttribute("readonly");
    fireEvent.click(screen.getByTestId("agent-run-panel-launch"));

    await waitFor(() =>
      expect(createAgentRunMock).toHaveBeenCalledWith({
        agentId: "12",
        payload: { ticker: "AAPL" },
        version: 9,
      }),
    );
    expect(toastSuccessMock).toHaveBeenCalledWith("Agent run started");
    expect(navigateMock).toHaveBeenCalledWith("/runs/321");
  });
});
