import { describe, expect, it, vi } from "vitest";

const reactQueryState = vi.hoisted(() => ({
  invalidateQueriesMock: vi.fn(),
  useMutationMock: vi.fn((options: unknown) => options),
  useQueryMock: vi.fn((options: unknown) => options),
}));

const runsApiState = vi.hoisted(() => ({
  createRunRerunMock: vi.fn(),
  getRunMock: vi.fn(),
  getRunRerunDraftMock: vi.fn(),
  listRunsMock: vi.fn(),
}));

vi.mock("@tanstack/react-query", () => ({
  useMutation: reactQueryState.useMutationMock,
  useQuery: reactQueryState.useQueryMock,
  useQueryClient: () => ({ invalidateQueries: reactQueryState.invalidateQueriesMock }),
}));

vi.mock("@/lib/api/runs", () => ({
  createRunRerun: runsApiState.createRunRerunMock,
  getRun: runsApiState.getRunMock,
  getRunRerunDraft: runsApiState.getRunRerunDraftMock,
  listRuns: runsApiState.listRunsMock,
}));

import { queryKeys } from "@/lib/query-keys";
import type { RunListRead, RunRead, RunStatus } from "@/lib/types/run";
import * as runsHooks from "./use-runs";

const { useCreateRunRerun, useRun, useRunRerunDraft, useRuns } = runsHooks;

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
      progress: {
        unit: "invocation",
        terminalCount: status === "queued" || status === "running" ? 0 : 1,
        totalCount: 1,
        percent: status === "queued" || status === "running" ? 0 : 100,
      },
      queue: null,
      scheduleFireId: null,
      scheduleId: null,
      scheduleProvenance: null,
      scheduleReason: null,
      scheduledFor: null,
      targetId: 100 + index,
      targetKey: "market_review",
      targetKind: "workflowPackage",
      totalTokens: 0,
      traceId: null,
      workflowKey: null,
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
    extensionDependencies: [],
    packageProvenance: null,
    progress: {
      unit: "invocation",
      terminalCount: status === "queued" || status === "running" ? 0 : 1,
      totalCount: 1,
      percent: status === "queued" || status === "running" ? 0 : 100,
    },
    queue: null,
    scheduleFireId: null,
    scheduleId: null,
    scheduleProvenance: null,
    scheduleReason: null,
    scheduledFor: null,
    queuedAt: "2026-05-15T10:00:00Z",
    sourceRunId: null,
    startedAt: status === "queued" ? null : "2026-05-15T10:01:00Z",
    status,
    steps: [],
    targetId: 100,
    targetKey: "market_review",
    targetKind: "workflowPackage",
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
  it("uses the canonical package-only list query key", () => {
    reactQueryState.useQueryMock.mockClear();

    const params = {
      status: "running" as const,
      workflowKey: " market_review ",
      workflowPackageKey: " market_review_package ",
    };

    useRuns(params, { refetchInterval: 2_000 });

    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        queryKey: queryKeys.platform.runs.list(params),
        refetchInterval: expect.any(Function),
      }),
    );
    expect(queryKeys.platform.runs.list(params)).toEqual([
      "api",
      "platform",
      "runs",
      "list",
      {
        offset: 0,
        status: "running",
        workflowKey: "market_review",
        workflowPackageKey: "market_review_package",
      },
    ]);
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

});
