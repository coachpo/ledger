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

vi.mock("@/lib/api/workflows", () => ({
  archiveWorkflow: vi.fn(),
  createWorkflow: vi.fn(),
  createWorkflowRun: vi.fn(),
  getWorkflow: vi.fn(),
  listWorkflows: vi.fn(),
  updateWorkflow: vi.fn(),
}));

import { queryKeys } from "@/lib/query-keys";
import { useCreateWorkflow, useCreateWorkflowRun, useWorkflow } from "./use-workflows";

type CapturedMutationOptions = {
  onSuccess?: (result: unknown, variables: unknown) => unknown;
};

describe("useWorkflows", () => {
  it("uses platform workflow detail keys and disables detail queries without an id", () => {
    reactQueryState.useQueryMock.mockClear();

    useWorkflow(undefined);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.workflows.detail(""),
      }),
    );

    useWorkflow(15, 2);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.platform.workflows.detail(15, 2),
      }),
    );
  });

  it("invalidates platform workflow list and detail scopes after create", async () => {
    reactQueryState.invalidateQueriesMock.mockReset();
    reactQueryState.capturedMutationOptions = null;

    useCreateWorkflow();

    expect(reactQueryState.capturedMutationOptions).not.toBeNull();
    if (reactQueryState.capturedMutationOptions === null) {
      throw new Error("Expected mutation options to be captured");
    }
    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;

    await mutationOptions.onSuccess?.({ id: 15, version: 1 }, { key: "stock_analysis" });

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflows.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflows.detail(15),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflows.detail(15, 1),
    });
  });

  it("invalidates platform run caches after triggering a workflow run", async () => {
    reactQueryState.invalidateQueriesMock.mockReset();
    reactQueryState.capturedMutationOptions = null;

    useCreateWorkflowRun();

    expect(reactQueryState.capturedMutationOptions).not.toBeNull();
    if (reactQueryState.capturedMutationOptions === null) {
      throw new Error("Expected mutation options to be captured");
    }
    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;

    await mutationOptions.onSuccess?.({ id: 23 }, { ticker: "AVGO" });

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.detail(23),
    });
  });
});
