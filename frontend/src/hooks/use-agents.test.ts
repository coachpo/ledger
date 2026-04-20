import { describe, expect, it, vi } from "vitest";

const reactQueryState = vi.hoisted(() => ({
  capturedMutationOptions: null as {
    onSuccess?: (result: unknown, variables: unknown) => unknown;
  } | null,
  invalidateQueriesMock: vi.fn(),
  useQueryMock: vi.fn((options: unknown) => options),
}));

vi.mock("@tanstack/react-query", () => ({
  useMutation: (options: { onSuccess?: (result: unknown, variables: unknown) => unknown }) => {
    reactQueryState.capturedMutationOptions = options;
    return { mutate: vi.fn(), options };
  },
  useQuery: reactQueryState.useQueryMock,
  useQueryClient: () => ({
    invalidateQueries: reactQueryState.invalidateQueriesMock,
  }),
}));

vi.mock("@/lib/api/agents", () => ({
  archiveAgent: vi.fn(),
  createAgent: vi.fn(),
  getAgent: vi.fn(),
  listAgents: vi.fn(),
  resolveAgentTestPanel: vi.fn(),
  updateAgent: vi.fn(),
}));

import { queryKeys } from "@/lib/query-keys";
import { useAgent, useCreateAgent } from "./use-agents";

type CapturedMutationOptions = {
  onSuccess?: (result: unknown, variables: unknown) => unknown;
};

describe("useAgents", () => {
  it("uses platform detail keys and disables detail queries without an id", () => {
    reactQueryState.useQueryMock.mockClear();

    useAgent(undefined);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.agents.detail(""),
      }),
    );

    useAgent(11, 2);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.platform.agents.detail(11, 2),
      }),
    );
  });

  it("invalidates platform agent list and detail scopes after create", async () => {
    reactQueryState.invalidateQueriesMock.mockReset();
    reactQueryState.capturedMutationOptions = null;

    useCreateAgent();

    expect(reactQueryState.capturedMutationOptions).not.toBeNull();
    if (reactQueryState.capturedMutationOptions === null) {
      throw new Error("Expected mutation options to be captured");
    }
    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;

    await mutationOptions.onSuccess?.({ id: 11, version: 1 }, { key: "research_agent" });

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
