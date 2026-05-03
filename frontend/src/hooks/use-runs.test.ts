import { describe, expect, it, vi } from "vitest";

const reactQueryState = vi.hoisted(() => ({
  invalidateQueriesMock: vi.fn(),
  useMutationMock: vi.fn((options: unknown) => options),
  useQueryMock: vi.fn((options: unknown) => options),
}));

const runsApiState = vi.hoisted(() => ({
  buildRunsListQueryKeyMock: vi.fn((params: unknown) => ["api", "platform", "runs", "list", params]),
  createRunForkMock: vi.fn(),
  getRunForkDraftMock: vi.fn(),
  getRunMock: vi.fn(),
  listRunsMock: vi.fn(),
}));

vi.mock("@tanstack/react-query", () => ({
  useMutation: reactQueryState.useMutationMock,
  useQuery: reactQueryState.useQueryMock,
  useQueryClient: () => ({ invalidateQueries: reactQueryState.invalidateQueriesMock }),
}));

vi.mock("@/lib/api/runs", () => ({
  buildRunsListQueryKey: runsApiState.buildRunsListQueryKeyMock,
  createRunFork: runsApiState.createRunForkMock,
  getRun: runsApiState.getRunMock,
  getRunForkDraft: runsApiState.getRunForkDraftMock,
  listRuns: runsApiState.listRunsMock,
}));

import { queryKeys } from "@/lib/query-keys";
import { useCreateRunFork, useRun, useRunForkDraft, useRuns } from "./use-runs";

describe("useRuns hooks", () => {
  it("uses the API helper's target-aware list query key", () => {
    reactQueryState.useQueryMock.mockClear();
    runsApiState.buildRunsListQueryKeyMock.mockClear();

    const params = {
      status: "running" as const,
      targetKey: "market_review",
      targetKind: "workflow" as const,
      targetVersion: 2,
    };

    useRuns(params, { refetchInterval: 2_000 });

    expect(runsApiState.buildRunsListQueryKeyMock).toHaveBeenLastCalledWith(params);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        queryKey: ["api", "platform", "runs", "list", params],
        refetchInterval: 2_000,
      }),
    );
  });

  it("keeps detail queries keyed by run id and disabled without an id", () => {
    reactQueryState.useQueryMock.mockClear();

    useRun(undefined);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.runs.detail(""),
      }),
    );

    useRun(18, { refetchInterval: 2_000 });
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.platform.runs.detail(18),
        refetchInterval: 2_000,
      }),
    );
  });

  it("keys fork draft queries by run id and fork step", () => {
    reactQueryState.useQueryMock.mockClear();

    useRunForkDraft(18, 2, { enabled: true });

    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.platform.runs.forkDraft(18, 2),
      }),
    );

    useRunForkDraft(undefined, 2);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.runs.forkDraft("", 2),
      }),
    );

    useRunForkDraft(18, undefined, { enabled: true });
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.runs.forkDraft(18, 0),
      }),
    );
  });

  it("invalidates run list, details, and fork draft after fork create", async () => {
    reactQueryState.useMutationMock.mockClear();
    reactQueryState.invalidateQueriesMock.mockClear();

    useCreateRunFork();

    const mutationOptions = reactQueryState.useMutationMock.mock.calls.at(-1)?.[0] as {
      onSuccess: (createdRun: { id: number }, variables: { runId: number; payload: { forkStepIndex: number } }) => Promise<void>;
    };

    await mutationOptions.onSuccess({ id: 99 }, { runId: 18, payload: { forkStepIndex: 2 } });

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.detail(18),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.forkDraft(18, 2),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.detail(99),
    });
  });
});
