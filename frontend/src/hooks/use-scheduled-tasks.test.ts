import { beforeEach, describe, expect, it, vi } from "vitest";

const reactQueryState = vi.hoisted(() => ({
  capturedMutationOptions: null as {
    mutationFn?: (variables: unknown) => unknown;
    onSuccess?: (result: unknown, variables: unknown) => unknown;
  } | null,
  invalidateQueriesMock: vi.fn(),
  useQueryMock: vi.fn((options: unknown) => options),
}));

vi.mock("@tanstack/react-query", () => ({
  useMutation: (options: {
    mutationFn?: (variables: unknown) => unknown;
    onSuccess?: (result: unknown, variables: unknown) => unknown;
  }) => {
    reactQueryState.capturedMutationOptions = options;
    return { mutate: vi.fn(), options };
  },
  useQuery: reactQueryState.useQueryMock,
  useQueryClient: () => ({
    invalidateQueries: reactQueryState.invalidateQueriesMock,
  }),
}));

vi.mock("@/lib/api/schedules", () => ({
  createScheduledTask: vi.fn(),
  deleteScheduledTask: vi.fn(),
  getScheduledTask: vi.fn(),
  listScheduledTaskFires: vi.fn(),
  listScheduledTasks: vi.fn(),
  previewScheduledTask: vi.fn(),
  previewUnsavedScheduledTask: vi.fn(),
  runScheduledTaskNow: vi.fn(),
  updateScheduledTask: vi.fn(),
}));

import {
  createScheduledTask,
  deleteScheduledTask,
  getScheduledTask,
  listScheduledTaskFires,
  listScheduledTasks,
  previewScheduledTask,
  previewUnsavedScheduledTask,
  runScheduledTaskNow,
  updateScheduledTask,
} from "@/lib/api/schedules";
import { queryKeys } from "@/lib/query-keys";
import {
  useCreateScheduledTask,
  useDeleteScheduledTask,
  usePreviewScheduledTask,
  usePreviewUnsavedScheduledTask,
  useRunScheduledTaskNow,
  useScheduledTask,
  useScheduledTaskFires,
  useScheduledTasks,
  useUpdateScheduledTask,
} from "./use-scheduled-tasks";

type CapturedMutationOptions = {
  mutationFn?: (variables: unknown) => unknown;
  onSuccess?: (result: unknown, variables: unknown) => unknown;
};

describe("useScheduledTasks", () => {
  beforeEach(() => {
    reactQueryState.capturedMutationOptions = null;
    reactQueryState.invalidateQueriesMock.mockReset();
    reactQueryState.useQueryMock.mockReset();
    vi.mocked(createScheduledTask).mockReset();
    vi.mocked(deleteScheduledTask).mockReset();
    vi.mocked(getScheduledTask).mockReset();
    vi.mocked(listScheduledTaskFires).mockReset();
    vi.mocked(listScheduledTasks).mockReset();
    vi.mocked(previewScheduledTask).mockReset();
    vi.mocked(previewUnsavedScheduledTask).mockReset();
    vi.mocked(runScheduledTaskNow).mockReset();
    vi.mocked(updateScheduledTask).mockReset();
  });

  it("uses canonical list, detail, and fire-history query keys", () => {
    useScheduledTasks({ packageKey: " research ", workflowKey: " daily ", status: "enabled" });
    expect(reactQueryState.useQueryMock).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        queryKey: queryKeys.platform.schedules.list({
          packageKey: "research",
          workflowKey: "daily",
          status: "enabled",
        }),
      }),
    );

    useScheduledTask(undefined);
    expect(reactQueryState.useQueryMock).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.schedules.detail(""),
      }),
    );

    useScheduledTask(44);
    expect(reactQueryState.useQueryMock).toHaveBeenNthCalledWith(
      3,
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.platform.schedules.detail(44),
      }),
    );

    useScheduledTaskFires(44, { limit: 25 });
    expect(reactQueryState.useQueryMock).toHaveBeenNthCalledWith(
      4,
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.platform.schedules.fires(44, { limit: 25 }),
      }),
    );
  });

  it("calls schedule query functions with the same params and abort signals", async () => {
    const signal = new AbortController().signal;

    useScheduledTasks({ packageKey: " research ", workflowKey: " daily ", limit: 10 });
    let queryOptions = reactQueryState.useQueryMock.mock.calls.at(-1)?.[0] as {
      queryFn: (context: { signal: AbortSignal }) => unknown;
    };
    await queryOptions.queryFn({ signal });
    expect(listScheduledTasks).toHaveBeenCalledWith(
      { packageKey: " research ", workflowKey: " daily ", limit: 10 },
      signal,
    );

    useScheduledTask(44);
    queryOptions = reactQueryState.useQueryMock.mock.calls.at(-1)?.[0] as {
      queryFn: (context: { signal: AbortSignal }) => unknown;
    };
    await queryOptions.queryFn({ signal });
    expect(getScheduledTask).toHaveBeenCalledWith(44, signal);

    useScheduledTaskFires(44, { limit: 20 });
    queryOptions = reactQueryState.useQueryMock.mock.calls.at(-1)?.[0] as {
      queryFn: (context: { signal: AbortSignal }) => unknown;
    };
    await queryOptions.queryFn({ signal });
    expect(listScheduledTaskFires).toHaveBeenCalledWith(44, { limit: 20 }, signal);
  });

  it("passes preview payloads through without invalidating caches", async () => {
    usePreviewUnsavedScheduledTask();
    let mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.({ packageId: 12, workflowKey: "daily", scheduledFor: "now" });
    expect(previewUnsavedScheduledTask).toHaveBeenCalledWith({
      packageId: 12,
      workflowKey: "daily",
      scheduledFor: "now",
    });

    usePreviewScheduledTask();
    mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.({ scheduleId: 44, payload: { scheduledFor: "now" } });
    expect(previewScheduledTask).toHaveBeenCalledWith(44, { scheduledFor: "now" });
    expect(reactQueryState.invalidateQueriesMock).not.toHaveBeenCalled();
  });

  it("invalidates schedule and linked run scopes after create", async () => {
    useCreateScheduledTask();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.({ packageId: 12, workflowKey: "daily" });
    expect(createScheduledTask).toHaveBeenCalledWith({ packageId: 12, workflowKey: "daily" });

    await mutationOptions.onSuccess?.({ id: 44, latestRunId: 2104 }, undefined);
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.schedules.lists(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.schedules.detail(44),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.schedules.firesScope(44),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.lists(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.detail(2104),
    });
  });

  it("updates scheduled tasks and invalidates the requested detail key", async () => {
    useUpdateScheduledTask();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.({ scheduleId: "44", payload: { status: "paused" } });
    expect(updateScheduledTask).toHaveBeenCalledWith("44", { status: "paused" });

    await mutationOptions.onSuccess?.({ id: 44, latestRunId: null }, { scheduleId: "44" });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.schedules.detail("44"),
    });
  });

  it("deletes scheduled tasks through the API and invalidates schedule and linked run scopes", async () => {
    useDeleteScheduledTask();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.({ scheduleId: 44, latestRunId: 2104 });
    expect(deleteScheduledTask).toHaveBeenCalledWith(44);

    await mutationOptions.onSuccess?.(undefined, { scheduleId: 44, latestRunId: 2104 });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.schedules.lists(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.schedules.detail(44),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.schedules.firesScope(44),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.lists(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.detail(2104),
    });
  });

  it("invalidates schedule fires and run views after run-now", async () => {
    useRunScheduledTaskNow();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.({
      scheduleId: 44,
      payload: { idempotencyKey: "manual-1", scheduledFor: "2026-06-01T13:00:00Z" },
    });
    expect(runScheduledTaskNow).toHaveBeenCalledWith(44, {
      idempotencyKey: "manual-1",
      scheduledFor: "2026-06-01T13:00:00Z",
    });

    await mutationOptions.onSuccess?.({ scheduleId: 44, run: { id: 2104 } }, undefined);
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.schedules.lists(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.schedules.detail(44),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.schedules.firesScope(44),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.detail(2104),
    });
  });
});
