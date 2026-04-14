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

vi.mock("@/lib/api/tryouts", () => ({
  createTryout: vi.fn(),
  getTryout: vi.fn(),
  persistTryout: vi.fn(),
}));

import { queryKeys } from "@/lib/query-keys";
import { usePersistTryout, useTryout } from "./use-tryouts";

type CapturedMutationOptions = {
  onSuccess?: (result: unknown, variables: unknown) => unknown;
};

describe("useTryouts", () => {
  it("uses tryout detail keys and disables the query without an id", () => {
    reactQueryState.useQueryMock.mockClear();

    useTryout(undefined);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.tryouts.detail(""),
      }),
    );

    useTryout(55);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.tryouts.detail(55),
      }),
    );
  });

  it("invalidates the same tryout run scope after persist", async () => {
    reactQueryState.invalidateQueriesMock.mockReset();
    reactQueryState.capturedMutationOptions = null;

    usePersistTryout(55);

    expect(reactQueryState.capturedMutationOptions).not.toBeNull();
    if (reactQueryState.capturedMutationOptions === null) {
      throw new Error("Expected mutation options to be captured");
    }
    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;

    await mutationOptions.onSuccess?.(
      {
        approvalSummary: {
          approvedCount: 0,
          deniedCount: 0,
          expiredCount: 0,
          pendingCount: 1,
          totalCount: 1,
        },
        expiresAt: null,
        finalOutput: null,
        reportMarkdown: null,
        runId: 55,
        status: "WAITING_APPROVAL",
        terminalError: null,
        traceSummary: {
          eventCount: 1,
          lastEventAt: null,
          toolCallCount: 0,
          warningCount: 0,
        },
      },
      undefined,
    );

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.tryouts.detail(55),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.runtime.runs.detail(55),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.studio.runs.detail(55),
    });
  });
});
