import { describe, expect, it, vi } from "vitest";

const reactQueryState = vi.hoisted(() => ({
  invalidateQueriesMock: vi.fn(),
  useMutationMock: vi.fn((options: unknown) => options),
  useQueryMock: vi.fn((options: unknown) => options),
}));

const runsApiState = vi.hoisted(() => ({
  buildRunsListQueryKeyMock: vi.fn((params: unknown) => ["api", "platform", "runs", "list", params]),
  createRunRerunMock: vi.fn(),
  createRunStepReplayMock: vi.fn(),
  getRunMock: vi.fn(),
  getRunRerunDraftMock: vi.fn(),
  getRunStepReplayDraftMock: vi.fn(),
  listRunsMock: vi.fn(),
}));

vi.mock("@tanstack/react-query", () => ({
  useMutation: reactQueryState.useMutationMock,
  useQuery: reactQueryState.useQueryMock,
  useQueryClient: () => ({ invalidateQueries: reactQueryState.invalidateQueriesMock }),
}));

vi.mock("@/lib/api/runs", () => ({
  buildRunsListQueryKey: runsApiState.buildRunsListQueryKeyMock,
  createRunRerun: runsApiState.createRunRerunMock,
  createRunStepReplay: runsApiState.createRunStepReplayMock,
  getRun: runsApiState.getRunMock,
  getRunRerunDraft: runsApiState.getRunRerunDraftMock,
  getRunStepReplayDraft: runsApiState.getRunStepReplayDraftMock,
  listRuns: runsApiState.listRunsMock,
}));

import { queryKeys } from "@/lib/query-keys";
import type { RunListRead, RunRead, RunStatus } from "@/lib/types/run";
import { useCreateRunRerun, useCreateRunStepReplay, useRun, useRunRerunDraft, useRuns, useRunStepReplayDraft } from "./use-runs";

type RefetchIntervalResolver<TData> = (query: {
  state: { data: TData | undefined };
}) => false | number | undefined;

function runListWithStatuses(statuses: RunStatus[]): RunListRead {
  return {
    items: statuses.map((status, index) => ({
      finishedAt: status === "queued" || status === "running" ? null : "2026-05-15T10:02:00Z",
      id: index + 1,
      queuedAt: "2026-05-15T10:00:00Z",
      startedAt: status === "queued" ? null : "2026-05-15T10:01:00Z",
      status,
      targetId: 100 + index,
      targetKey: "market_review",
      targetKind: "workflowPackage",
      targetVersion: 1,
      totalTokens: 0,
      traceId: null,
    })),
  };
}

function runDetailWithStatus(status: RunStatus): RunRead {
  return {
    createdAt: "2026-05-15T10:00:00Z",
    error: null,
    executedTokens: 0,
    finalOutput: null,
    finishedAt: status === "queued" || status === "running" ? null : "2026-05-15T10:02:00Z",
    id: 18,
    inheritedTokens: 0,
    input: {},
    lineageRootRunId: null,
    memoryArtifacts: [],
    extensionDependencies: [],
    packageProvenance: null,
    queuedAt: "2026-05-15T10:00:00Z",
    replayStepIndex: null,
    resumeStepIndex: 1,
    sourceRunId: null,
    startedAt: status === "queued" ? null : "2026-05-15T10:01:00Z",
    status,
    steps: [],
    targetId: 100,
    targetKey: "market_review",
    targetKind: "workflowPackage",
    targetVersion: 1,
    totalTokens: 0,
    traceId: null,
    updatedAt: "2026-05-15T10:00:00Z",
  };
}

function lastQueryOptions<TData>() {
  return reactQueryState.useQueryMock.mock.calls.at(-1)?.[0] as {
    refetchInterval: RefetchIntervalResolver<TData>;
  };
}

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
        refetchInterval: expect.any(Function),
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
        refetchInterval: expect.any(Function),
      }),
    );
  });

  it("polls run lists only while queued or running runs are present", () => {
    reactQueryState.useQueryMock.mockClear();

    useRuns({}, { refetchInterval: 2_000 });

    const queryOptions = lastQueryOptions<RunListRead>();
    expect(queryOptions.refetchInterval({ state: { data: undefined } })).toBe(false);
    expect(
      queryOptions.refetchInterval({
        state: { data: runListWithStatuses(["succeeded", "failed"]) },
      }),
    ).toBe(false);
    expect(
      queryOptions.refetchInterval({
        state: { data: runListWithStatuses(["succeeded", "running"]) },
      }),
    ).toBe(2_000);
    expect(
      queryOptions.refetchInterval({
        state: { data: runListWithStatuses(["queued", "failed"]) },
      }),
    ).toBe(2_000);
  });

  it("polls run details only while queued or running", () => {
    reactQueryState.useQueryMock.mockClear();

    useRun(18, { refetchInterval: 2_000 });

    const queryOptions = lastQueryOptions<RunRead>();
    expect(queryOptions.refetchInterval({ state: { data: undefined } })).toBe(false);
    expect(
      queryOptions.refetchInterval({
        state: { data: runDetailWithStatus("succeeded") },
      }),
    ).toBe(false);
    expect(
      queryOptions.refetchInterval({
        state: { data: runDetailWithStatus("failed") },
      }),
    ).toBe(false);
    expect(
      queryOptions.refetchInterval({
        state: { data: runDetailWithStatus("queued") },
      }),
    ).toBe(2_000);
    expect(
      queryOptions.refetchInterval({
        state: { data: runDetailWithStatus("running") },
      }),
    ).toBe(2_000);
  });

  it("keys rerun draft queries by run id", () => {
    reactQueryState.useQueryMock.mockClear();

    useRunRerunDraft(18, { enabled: true });

    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.platform.runs.rerunDraft(18),
      }),
    );

    useRunRerunDraft(undefined);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.runs.rerunDraft(""),
      }),
    );
  });

  it("keys step replay draft queries by run id and step", () => {
    reactQueryState.useQueryMock.mockClear();

    useRunStepReplayDraft(18, 2, { enabled: true });

    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.platform.runs.stepReplayDraft(18, 2),
      }),
    );

    useRunStepReplayDraft(undefined, 2);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.runs.stepReplayDraft("", 2),
      }),
    );

    useRunStepReplayDraft(18, undefined, { enabled: true });
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.runs.stepReplayDraft(18, 0),
      }),
    );
  });

  it("invalidates run list, details, and rerun draft after rerun create", async () => {
    reactQueryState.useMutationMock.mockClear();
    reactQueryState.invalidateQueriesMock.mockClear();

    useCreateRunRerun();

    const mutationOptions = reactQueryState.useMutationMock.mock.calls.at(-1)?.[0] as {
      onSuccess: (createdRun: { id: number }, variables: { runId: number; payload: { parameters: Record<string, unknown> } }) => Promise<void>;
    };

    await mutationOptions.onSuccess({ id: 99 }, { runId: 18, payload: { parameters: { ticker: "MSFT" } } });

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.detail(18),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.rerunDraft(18),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.detail(99),
    });
  });

  it("invalidates run list, details, and step replay draft after step replay create", async () => {
    reactQueryState.useMutationMock.mockClear();
    reactQueryState.invalidateQueriesMock.mockClear();

    useCreateRunStepReplay();

    const mutationOptions = reactQueryState.useMutationMock.mock.calls.at(-1)?.[0] as {
      onSuccess: (createdRun: { id: number }, variables: { runId: number; payload: { replayStepIndex: number } }) => Promise<void>;
    };

    await mutationOptions.onSuccess({ id: 100 }, { runId: 18, payload: { replayStepIndex: 2 } });

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.detail(18),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.stepReplayDraft(18, 2),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.detail(100),
    });
  });
});
