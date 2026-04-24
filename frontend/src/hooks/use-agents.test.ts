import { beforeEach, describe, expect, it, vi } from "vitest";

const apiState = vi.hoisted(() => ({
  archiveAgentMock: vi.fn(),
  createAgentMock: vi.fn(),
  getAgentMock: vi.fn(),
  listAgentsMock: vi.fn(),
  resolveAgentTestPanelMock: vi.fn(),
  updateAgentMock: vi.fn(),
}));

const reactQueryState = vi.hoisted(() => ({
  capturedMutationOptions: null as {
    mutationFn?: (variables: unknown) => unknown;
    onSuccess?: (result: unknown, variables: unknown) => unknown;
  } | null,
  invalidateQueriesMock: vi.fn(),
  useQueryMock: vi.fn((options: unknown) => options),
}));

vi.mock("@tanstack/react-query", () => ({
  useMutation: (options: {
    mutationFn?: (variables: unknown) => unknown;
    onSuccess?: (result: unknown, variables: unknown) => unknown;
  }) => {
    reactQueryState.capturedMutationOptions = options;
    return { mutate: vi.fn(), options };
  },
  useQuery: reactQueryState.useQueryMock,
  useQueryClient: () => ({
    invalidateQueries: reactQueryState.invalidateQueriesMock,
  }),
}));

vi.mock("@/lib/api/agents", () => ({
  archiveAgent: apiState.archiveAgentMock,
  createAgent: apiState.createAgentMock,
  getAgent: apiState.getAgentMock,
  listAgents: apiState.listAgentsMock,
  resolveAgentTestPanel: apiState.resolveAgentTestPanelMock,
  updateAgent: apiState.updateAgentMock,
}));

import { queryKeys } from "@/lib/query-keys";
import { useAgent, useCreateAgent } from "./use-agents";

type CapturedMutationOptions = {
  mutationFn?: (variables: unknown) => unknown;
  onSuccess?: (result: unknown, variables: unknown) => unknown;
};

describe("useAgents", () => {
  beforeEach(() => {
    apiState.archiveAgentMock.mockReset();
    apiState.createAgentMock.mockReset();
    apiState.getAgentMock.mockReset();
    apiState.listAgentsMock.mockReset();
    apiState.resolveAgentTestPanelMock.mockReset();
    apiState.updateAgentMock.mockReset();
    reactQueryState.capturedMutationOptions = null;
    reactQueryState.invalidateQueriesMock.mockReset();
    reactQueryState.useQueryMock.mockClear();
  });

  it("uses platform detail keys and disables detail queries without an id", () => {
    useAgent(undefined);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ enabled: false, queryKey: queryKeys.platform.agents.detail("") }),
    );

    useAgent(11, 2);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ enabled: true, queryKey: queryKeys.platform.agents.detail(11, 2) }),
    );
  });

  it("delegates create payloads with modelConnectionId and invalidates platform agent scopes after create", async () => {
    useCreateAgent();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    const payload = {
      inputSchema: { type: "object" },
      key: "research_agent",
      mcpServers: [],
      modelConnectionId: 44,
      name: "Research Agent",
      outputSchemaKey: "summary_schema",
      skills: [],
      systemPrompt: "Analyze carefully.",
    };

    await mutationOptions.mutationFn?.(payload);
    expect(apiState.createAgentMock).toHaveBeenCalledWith(payload);

    await mutationOptions.onSuccess?.({ id: 11, version: 1 }, payload);
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.agents.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.agents.detail(11),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.agents.detail(11, 1),
    });
  });
});
