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

vi.mock("@/lib/api/runtime", () => ({
  approveRuntimeApproval: vi.fn(),
  cancelRuntimeRun: vi.fn(),
  createRuntimeRun: vi.fn(),
  denyRuntimeApproval: vi.fn(),
  getRuntimeApproval: vi.fn(),
  getRuntimeRun: vi.fn(),
  getRuntimeRunArtifact: vi.fn(),
  getRuntimeRunTrace: vi.fn(),
  listRuntimeApprovals: vi.fn(),
  listRuntimeRuns: vi.fn(),
  listRuntimeTraceEvents: vi.fn(),
}));

import { buildApiUrl, buildV2ApiUrl } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import { useApproveRuntimeApproval, useRuntimeRun } from "./use-runtime";

type CapturedMutationOptions = {
  onSuccess?: (result: unknown, variables: unknown) => unknown;
};

describe("useRuntime", () => {
  it("keeps the v1 API base stable and gates runtime detail queries by id", () => {
    reactQueryState.useQueryMock.mockClear();

    expect(buildApiUrl("/orchestration/roles")).toBe(
      "http://127.0.0.1:8000/api/v1/orchestration/roles",
    );
    expect(buildV2ApiUrl("/runtime/runs")).toBe("http://127.0.0.1:8000/api/v2/runtime/runs");

    useRuntimeRun(undefined);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.runtime.runs.detail(""),
      }),
    );

    useRuntimeRun(42);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.runtime.runs.detail(42),
      }),
    );
  });

  it("invalidates runtime and mirrored studio scopes after approval resolution", async () => {
    reactQueryState.invalidateQueriesMock.mockReset();
    reactQueryState.capturedMutationOptions = null;

    useApproveRuntimeApproval();

    expect(reactQueryState.capturedMutationOptions).not.toBeNull();
    if (reactQueryState.capturedMutationOptions === null) {
      throw new Error("Expected mutation options to be captured");
    }
    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;

    await mutationOptions.onSuccess?.(
      {
        approvalId: 7,
        resolvedAt: "2026-04-14T12:00:00Z",
        runId: 42,
        runStatus: "WAITING_APPROVAL",
        status: "APPROVED",
      },
      {
        approvalId: 7,
        payload: { actor: "reviewer", reason: "Looks good" },
      },
    );

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.runtime.approvals.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.runtime.approvals.detail(7),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.runtime.runs.detail(42),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.studio.runs.detail(42),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.tryouts.detail(42),
    });
  });
});
