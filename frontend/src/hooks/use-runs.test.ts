import { describe, expect, it, vi } from "vitest";

const reactQueryState = vi.hoisted(() => ({
  useQueryMock: vi.fn((options: unknown) => options),
}));

const runsApiState = vi.hoisted(() => ({
  buildRunsListQueryKeyMock: vi.fn((params: unknown) => ["api", "platform", "runs", "list", params]),
  getRunMock: vi.fn(),
  listRunsMock: vi.fn(),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: reactQueryState.useQueryMock,
}));

vi.mock("@/lib/api/runs", () => ({
  buildRunsListQueryKey: runsApiState.buildRunsListQueryKeyMock,
  getRun: runsApiState.getRunMock,
  listRuns: runsApiState.listRunsMock,
}));

import { queryKeys } from "@/lib/query-keys";
import { useRun, useRuns } from "./use-runs";

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
});
