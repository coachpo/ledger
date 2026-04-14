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

vi.mock("@/lib/api/studio", () => ({
  getStudioApproval: vi.fn(),
  getStudioRun: vi.fn(),
  getStudioRunArtifact: vi.fn(),
  getStudioRunTrace: vi.fn(),
  listStudioApprovals: vi.fn(),
  listStudioArtifacts: vi.fn(),
  listStudioRuns: vi.fn(),
  listStudioTraceEvents: vi.fn(),
}));

vi.mock("@/lib/api/agent-specs", () => ({
  activateAgentSpec: vi.fn(),
  archiveAgentSpec: vi.fn(),
  createAgentSpec: vi.fn(),
  deprecateAgentSpec: vi.fn(),
  getAgentSpec: vi.fn(),
  listAgentSpecs: vi.fn(),
  updateAgentSpec: vi.fn(),
}));

vi.mock("@/lib/api/workflow-specs", () => ({
  activateWorkflowSpec: vi.fn(),
  archiveWorkflowSpec: vi.fn(),
  createWorkflowSpec: vi.fn(),
  deprecateWorkflowSpec: vi.fn(),
  getWorkflowSpec: vi.fn(),
  listWorkflowSpecs: vi.fn(),
  updateWorkflowSpec: vi.fn(),
}));

vi.mock("@/lib/api/capabilities", () => ({
  activateCapability: vi.fn(),
  createCapability: vi.fn(),
  getCapability: vi.fn(),
  listCapabilities: vi.fn(),
  updateCapability: vi.fn(),
}));

import { queryKeys } from "@/lib/query-keys";
import {
  useActivateStudioCapability,
  useCreateStudioAgentSpec,
  useCreateStudioWorkflowSpec,
  useStudioRun,
} from "./use-studio";

type CapturedMutationOptions = {
  onSuccess?: (result: unknown, variables: unknown) => unknown;
};

describe("useStudio", () => {
  it("uses studio run detail keys and disables detail queries without an id", () => {
    reactQueryState.useQueryMock.mockClear();

    useStudioRun(undefined);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.studio.runs.detail(""),
      }),
    );

    useStudioRun(9);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.studio.runs.detail(9),
      }),
    );
  });

  it("invalidates studio agent spec list and detail after create", async () => {
    reactQueryState.invalidateQueriesMock.mockReset();
    reactQueryState.capturedMutationOptions = null;

    useCreateStudioAgentSpec();

    expect(reactQueryState.capturedMutationOptions).not.toBeNull();
    if (reactQueryState.capturedMutationOptions === null) {
      throw new Error("Expected mutation options to be captured");
    }
    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;

    await mutationOptions.onSuccess?.({ id: 11 }, { key: "managed_agent" });

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.studio.agentSpecs.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.studio.agentSpecs.detail(11),
    });
  });

  it("invalidates studio workflow spec list and detail after create", async () => {
    reactQueryState.invalidateQueriesMock.mockReset();
    reactQueryState.capturedMutationOptions = null;

    useCreateStudioWorkflowSpec();

    expect(reactQueryState.capturedMutationOptions).not.toBeNull();
    if (reactQueryState.capturedMutationOptions === null) {
      throw new Error("Expected mutation options to be captured");
    }
    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;

    await mutationOptions.onSuccess?.(
      { id: 15 },
      { key: "managed_workflow" },
    );

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.studio.workflowSpecs.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.studio.workflowSpecs.detail(15),
    });
  });

  it("invalidates studio capability list and detail after activation", async () => {
    reactQueryState.invalidateQueriesMock.mockReset();
    reactQueryState.capturedMutationOptions = null;

    useActivateStudioCapability();

    expect(reactQueryState.capturedMutationOptions).not.toBeNull();
    if (reactQueryState.capturedMutationOptions === null) {
      throw new Error("Expected mutation options to be captured");
    }
    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;

    await mutationOptions.onSuccess?.({ id: 21 }, 21);

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.studio.capabilities.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.studio.capabilities.detail(21),
    });
  });
});
