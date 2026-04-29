import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createAgentManifestSource,
} from "@/lib/platform-authoring/agents/manifest";
import type { AgentRead } from "@/lib/types/agent";
import type { ModelConnectionListItemRead } from "@/lib/types/model-connection";

import { AgentsEditorPage } from "./editor";

const navigateMock = vi.fn();
const paramsMock: { agentId?: string } = {};
const searchParamsMock = new URLSearchParams();
const createAgentMock = vi.fn();
const createAgentRunMock = vi.fn();
const updateAgentMock = vi.fn();
const archiveAgentMock = vi.fn();
const validateAgentManifestMock = vi.fn();
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

const activeModelConnection: ModelConnectionListItemRead = {
  apiKeyLast4: "4242",
  baseUrl: "https://api.openai.com/v1",
  description: "Primary production connection",
  hasApiKey: true,
  id: 44,
  key: "primary_openai",
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

const savedManifest = createAgentManifestSource({
  budgetUsd: "2.50",
  description: "Tracks macro context.",
  inputSchema: existingInputSchema,
  key: "macro_agent",
  mcpServers: ["quotes_mcp@2"],
  modelConnection: "primary_openai",
  name: "Macro Agent",
  outputSchema: "summary_schema@5",
  skills: ["summarize_skill@3"],
  systemPrompt: "Summarize clearly.",
});

const existingAgent = {
  budgetUsd: "2.50",
  compilerVersion: "agent-manifest-compiler/1",
  createdAt: "2026-04-20T10:00:00Z",
  description: "Tracks macro context.",
  id: 12,
  inputSchema: existingInputSchema,
  key: "macro_agent",
  manifestApiVersion: "ledger.agent/v1",
  manifestHash: "sha256:macro",
  manifestSource: savedManifest,
  mcpServers: [
    {
      boundary: {
        command: ["quotes"],
        enabled: true,
        envKeys: [],
        headerNames: [],
        transport: "stdio",
        url: null,
      },
      description: "Quotes feed",
      enabled: true,
      id: 8,
      key: "quotes_mcp",
      name: "Quotes",
      status: "published",
      transport: "stdio",
      version: 2,
    },
  ],
  modelConnection: activeModelConnection,
  modelConnectionId: activeModelConnection.id,
  name: "Macro Agent",
  outputSchema: {
    builder: { kind: "object" },
    createdAt: "2026-04-20T10:00:00Z",
    description: "Summary schema",
    id: 4,
    jsonSchema: { type: "object" },
    key: "summary_schema",
    kind: "standalone",
    name: "Summary Schema",
    registryRefs: [],
    status: "published",
    updatedAt: "2026-04-20T10:00:00Z",
    version: 5,
  },
  skills: [
    {
      createdAt: "2026-04-20T10:00:00Z",
      description: "Summaries",
      id: 7,
      key: "summarize_skill",
      name: "Summarize",
      status: "published",
      toolDefinitions: [],
      updatedAt: "2026-04-20T10:00:00Z",
      version: 3,
    },
  ],
  status: "published",
  systemPrompt: "Summarize clearly.",
  updatedAt: "2026-04-20T10:00:00Z",
  version: 9,
} as AgentRead;

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

Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
  configurable: true,
  value: vi.fn(),
});

vi.mock("@/hooks/use-agents", () => ({
  useAgent: (agentId?: string) =>
    agentId
      ? { data: currentAgent, error: null, isError: false, isPending: false }
      : { data: undefined, error: null, isError: false, isPending: false },
  useArchiveAgent: () => ({ isPending: false, mutateAsync: archiveAgentMock }),
  useCreateAgent: () => ({ isPending: false, mutateAsync: createAgentMock }),
  useCreateAgentRun: () => ({ isPending: false, mutateAsync: createAgentRunMock }),
  useUpdateAgent: () => ({ isPending: false, mutateAsync: updateAgentMock }),
  useValidateAgentManifest: () => ({ isPending: false, mutateAsync: validateAgentManifestMock }),
}));

function renderAgentsEditorPage() {
  return render(<AgentsEditorPage />);
}

function expectLegacyStructuredAuthoringControlsAbsent() {
  expect(screen.queryByTestId("agents-editor-tabs")).not.toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: /configuration/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: /^run$/i })).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/^Key$/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/^Name$/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/^Description$/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/^Model Connection$/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/^System Prompt$/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/^Input Schema JSON$/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/^Sample Input JSON$/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/^Skills$/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/^MCP Servers$/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/output schema binding/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/schema builder/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/add skill binding/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/add mcp server binding/i)).not.toBeInTheDocument();
  expect(screen.queryByTestId("agent-input-schema-raw-json")).not.toBeInTheDocument();
  expect(screen.queryByTestId("output-schema-add-field")).not.toBeInTheDocument();
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
    validateAgentManifestMock.mockReset();
  });

  it("renders the YAML-only full-height editor shell without legacy structured controls", () => {
    renderAgentsEditorPage();

    expect(screen.getByTestId("agent-yaml-editor-shell")).toBeVisible();
    expect(screen.getByTestId("agent-command-bar")).toBeVisible();
    expect(screen.getByTestId("agent-outline-rail")).toBeVisible();
    expect(screen.getByTestId("agent-yaml-editor")).toBeVisible();
    expect(screen.getByTestId("agent-inspector-shell")).toBeVisible();
    expect(screen.getByTestId("agent-validation-panel")).toBeVisible();
    expect(screen.getByTestId("agent-compiled-panel")).toBeVisible();
    expect(screen.getByTestId("agent-run-input-panel")).toBeVisible();
    expect(screen.getByRole("button", { name: /format yaml/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /snippets/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /validate/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /save agent/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /duplicate agent/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /archive agent/i })).toBeVisible();
    expectLegacyStructuredAuthoringControlsAbsent();
    expect(screen.getByTestId("agent-run-panel-input-form")).toBeVisible();
  });

  it("renders edit routes with the same YAML-only shell and no structured controls", () => {
    paramsMock.agentId = "12";

    renderAgentsEditorPage();

    expect(screen.getByTestId("agent-yaml-editor-shell")).toBeVisible();
    expect(screen.getByTestId("agent-yaml-editor")).toHaveValue(savedManifest);
    expectLegacyStructuredAuthoringControlsAbsent();
  });

  it("scaffolds new agents and saves manifestSource through create", async () => {
    createAgentMock.mockResolvedValue({ id: 123 });

    renderAgentsEditorPage();

    const editor = screen.getByTestId("agent-yaml-editor") as HTMLTextAreaElement;
    expect(editor.value).toContain("apiVersion: ledger.agent/v1");
    expect(editor.value).toContain("key: new_agent");

    fireEvent.click(screen.getByTestId("agents-save"));

    await waitFor(() => expect(createAgentMock).toHaveBeenCalledTimes(1));
    expect(createAgentMock).toHaveBeenCalledWith({
      manifestSource: expect.stringContaining("key: new_agent"),
    });
    expect(createAgentMock.mock.calls[0]?.[0]).not.toHaveProperty("modelConnectionId");
    expect(createAgentMock.mock.calls[0]?.[0]).not.toHaveProperty("inputSchema");
    expect(createAgentMock.mock.calls[0]?.[0]).not.toHaveProperty("outputSchemaKey");
    expect(navigateMock).toHaveBeenCalledWith("/agents/123/edit");
  });

  it("loads existing agent manifestSource and saves through update", async () => {
    paramsMock.agentId = "12";
    updateAgentMock.mockResolvedValue(existingAgent);

    renderAgentsEditorPage();

    expect(screen.getByTestId("agent-yaml-editor")).toHaveValue(savedManifest);
    expect(screen.getAllByText("Macro Agent").length).toBeGreaterThan(0);
    expect(screen.getAllByText("macro_agent").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByTestId("agents-save"));

    await waitFor(() => expect(updateAgentMock).toHaveBeenCalledTimes(1));
    expect(updateAgentMock).toHaveBeenCalledWith({
      agentId: "12",
      payload: { manifestSource: savedManifest },
    });
    expect(updateAgentMock.mock.calls[0]?.[0].payload).not.toHaveProperty("modelConnectionId");
    expect(updateAgentMock.mock.calls[0]?.[0].payload).not.toHaveProperty("inputSchema");
    expect(updateAgentMock.mock.calls[0]?.[0].payload).not.toHaveProperty("outputSchemaKey");
  });

  it("hydrates duplicate mode from source YAML without preserving the source key", () => {
    searchParamsMock.set("duplicateFrom", "12");

    renderAgentsEditorPage();

    const editor = screen.getByTestId("agent-yaml-editor") as HTMLTextAreaElement;
    expect(editor.value).toContain("name: Macro Agent Copy");
    expect(editor.value).toContain("key: new_agent");
    expect(editor.value).toContain("modelConnection: primary_openai");
    expect(editor.value).toContain("outputSchema: summary_schema@5");
    expect(editor.value).not.toContain("key: macro_agent");
    expect(screen.getByTestId("agent-yaml-editor-shell")).toBeVisible();
    expectLegacyStructuredAuthoringControlsAbsent();
  });

  it("formats YAML source in the textarea without deriving structured controls", async () => {
    renderAgentsEditorPage();

    const unformattedManifest = `kind: Agent
apiVersion: ledger.agent/v1
spec:
  budgetUsd: "0"
  mcpServers: []
  skills: []
  outputSchema: summary_schema@1
  inputSchema:
    required: [ticker]
    properties:
      ticker:
        type: string
    type: object
    additionalProperties: false
  systemPrompt: You are concise.
  modelConnection: primary_model_connection
metadata:
  name: New Agent
  key: new_agent
  description: Describe what this agent does.
`;
    const editor = screen.getByTestId("agent-yaml-editor") as HTMLTextAreaElement;

    fireEvent.change(editor, { target: { value: unformattedManifest } });
    fireEvent.click(screen.getByTestId("agents-format-manifest"));

    await waitFor(() => expect(editor.value).toMatch(/^apiVersion: ledger\.agent\/v1\nkind: Agent\nmetadata:/));
    expect(editor.value).toContain("  modelConnection: primary_model_connection\n  systemPrompt: You are concise.");
    expect(editor.value).toContain("  inputSchema:\n    type: object");
    expect(toastSuccessMock).toHaveBeenCalledWith("Agent manifest formatted");
    expectLegacyStructuredAuthoringControlsAbsent();
  });

  it("runs backend manifest validation and renders diagnostics plus raw JSON previews", async () => {
    const compiledPayload = {
      budgetUsd: "0",
      inputSchema: { type: "object" },
      key: "new_agent",
      modelConnectionId: 44,
      name: "New Agent",
      outputSchemaKey: "summary_schema",
      systemPrompt: "You are concise.",
    };
    const runInputSchema = { properties: { ticker: { type: "string" } }, type: "object" };
    validateAgentManifestMock.mockResolvedValue({
      compiledPayload,
      diagnostics: [
        {
          column: 9,
          line: 12,
          message: "Skill pin resolves with a warning",
          path: "spec.skills[0]",
          severity: "warning",
        },
      ],
      metadata: {
        apiVersion: "ledger.agent/v1",
        description: "Describe what this agent does.",
        key: "new_agent",
        name: "New Agent",
      },
      runInputSchema,
    });

    renderAgentsEditorPage();

    const manifestSource = (screen.getByTestId("agent-yaml-editor") as HTMLTextAreaElement).value;
    fireEvent.click(screen.getByTestId("agents-validate-manifest"));

    await waitFor(() => expect(validateAgentManifestMock).toHaveBeenCalledWith({ manifestSource }));
    expect(screen.getByTestId("agent-backend-validation-status")).toHaveTextContent(
      "Backend validation has warnings",
    );
    expect(within(screen.getByTestId("agent-validation-feedback")).getByText("Skill pin resolves with a warning")).toBeVisible();
    expect(within(screen.getByTestId("agent-validation-feedback")).getByText("spec.skills[0]")).toBeVisible();
    expect(screen.getByTestId("agent-validation-metadata")).toHaveTextContent("ledger.agent/v1");
    expect(screen.getByTestId("agent-validation-metadata")).toHaveTextContent("new_agent");
    expect(screen.getByLabelText("Exact raw compiled agent JSON")).toHaveValue(JSON.stringify(compiledPayload, null, 2));
    expect(screen.getByLabelText("Exact raw agent run input schema JSON")).toHaveValue(JSON.stringify(runInputSchema, null, 2));

    fireEvent.change(screen.getByTestId("agent-yaml-editor"), {
      target: { value: `${manifestSource}\n# edited after validate\n` },
    });

    expect(screen.getByTestId("agent-backend-validation-status")).toHaveTextContent("Backend validation is stale");
    expect(screen.getByTestId("agent-compiled-stale")).toHaveTextContent("Compiled preview is stale");
  });

  it("surfaces local YAML diagnostics in the inspector shell", () => {
    renderAgentsEditorPage();

    fireEvent.change(screen.getByTestId("agent-yaml-editor"), {
      target: { value: "apiVersion: ledger.agent/v1\nkind: [" },
    });

    expect(screen.getByTestId("agent-local-parse-status")).toHaveTextContent("Local parse needs attention");
    expect(within(screen.getByTestId("agent-validation-feedback")).getByText(/malformed yaml/i)).toBeVisible();
  });

  it("focuses the YAML editor when selecting an actionable diagnostic", () => {
    renderAgentsEditorPage();

    const editor = screen.getByTestId("agent-yaml-editor") as HTMLTextAreaElement;
    fireEvent.change(editor, {
      target: { value: "apiVersion: ledger.agent/v1\nkind: [" },
    });

    fireEvent.click(within(screen.getByTestId("agent-validation-feedback")).getByText(/malformed yaml/i));

    expect(document.activeElement).toBe(editor);
    expect(editor.selectionStart).toBeGreaterThan(0);
  });

  it("tracks dirty state, protects beforeunload, and confirms editor-owned navigation", async () => {
    const confirmMock = vi.spyOn(window, "confirm").mockReturnValue(false);
    createAgentMock.mockResolvedValue({ id: 123 });

    renderAgentsEditorPage();

    expect(screen.getByTestId("agent-dirty-indicator")).toHaveTextContent("Saved baseline");
    fireEvent.change(screen.getByTestId("agent-yaml-editor"), {
      target: { value: `${savedManifest}\n# edited\n` },
    });

    expect(screen.getByTestId("agent-dirty-indicator")).toHaveTextContent("Unsaved changes");
    await waitFor(() => {
      const beforeUnloadEvent = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(beforeUnloadEvent);
      expect(beforeUnloadEvent.defaultPrevented).toBe(true);
    });

    fireEvent.click(screen.getByLabelText("Back to agents"));
    expect(confirmMock).toHaveBeenCalledWith("You have unsaved agent YAML changes. Leave this editor and discard them?");
    expect(navigateMock).not.toHaveBeenCalled();

    confirmMock.mockReturnValue(true);
    fireEvent.click(screen.getByLabelText("Back to agents"));
    expect(navigateMock).toHaveBeenCalledWith("/agents");

    confirmMock.mockRestore();
  });

  it("opens command snippets with Ctrl+K and inserts YAML at the cursor", async () => {
    renderAgentsEditorPage();

    const editor = screen.getByTestId("agent-yaml-editor") as HTMLTextAreaElement;
    const originalManifest = editor.value;
    editor.focus();
    editor.setSelectionRange(0, 0);

    fireEvent.keyDown(window, { ctrlKey: true, key: "k" });
    fireEvent.click(screen.getByText("Input schema field"));

    await waitFor(() => expect(editor.value).toContain("newField:"));
    expect(editor.value).toContain("description: Describe this agent input.");
    expect(editor.value).toContain(originalManifest);
  });

  it("archives an existing agent", async () => {
    paramsMock.agentId = "12";
    archiveAgentMock.mockResolvedValue({ id: 12 });

    renderAgentsEditorPage();
    fireEvent.click(screen.getByTestId("agents-archive"));

    await waitFor(() => expect(archiveAgentMock).toHaveBeenCalledWith("12"));
    expect(navigateMock).toHaveBeenCalledWith("/agents");
  });

  it("blocks run launch for unsaved changes with clear saved-version copy", () => {
    paramsMock.agentId = "12";

    renderAgentsEditorPage();

    fireEvent.change(screen.getByTestId("agent-yaml-editor"), {
      target: { value: `${savedManifest}\n# unsaved\n` },
    });

    expect(screen.getByTestId("agent-run-unsaved-blocked")).toHaveTextContent("Save required before run");
    expect(screen.getByTestId("agent-run-panel-launch")).toBeDisabled();
    expect(createAgentRunMock).not.toHaveBeenCalled();
  });

  it("launches a run from the saved agent version and navigates to the run detail", async () => {
    paramsMock.agentId = "12";
    createAgentRunMock.mockResolvedValue({ id: 902 });

    renderAgentsEditorPage();

    await waitFor(() => expect(screen.getByLabelText("Exact raw agent run-input JSON")).toHaveValue(JSON.stringify({ ticker: "example" }, null, 2)));
    fireEvent.click(screen.getByTestId("agent-run-panel-launch"));

    await waitFor(() => expect(createAgentRunMock).toHaveBeenCalledTimes(1));
    expect(createAgentRunMock).toHaveBeenCalledWith({
      agentId: "12",
      payload: { ticker: "example" },
      version: 9,
    });
    expect(navigateMock).toHaveBeenCalledWith("/runs/902");
  });
});
