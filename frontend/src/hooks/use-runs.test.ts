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
import { useCreateRunRerun, useCreateRunStepReplay, useRun, useRunRerunDraft, useRuns, useRunStepReplayDraft } from "./use-runs";

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
