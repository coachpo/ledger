import {
  type QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
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
import type { IdParam } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type {
  ScheduleCreateRequest,
  ScheduleFireListParams,
  ScheduleFireListRead,
  ScheduleListParams,
  ScheduleListRead,
  SchedulePreviewRead,
  SchedulePreviewRequest,
  SchedulePreviewUnsavedRequest,
  ScheduleRead,
  ScheduleRunNowRead,
  ScheduleRunNowRequest,
  ScheduleUpdateRequest,
} from "@/lib/types/schedule";

export type UpdateScheduledTaskVariables = {
  scheduleId: IdParam;
  payload: ScheduleUpdateRequest;
};

export type PreviewScheduledTaskVariables = {
  scheduleId: IdParam;
  payload?: SchedulePreviewRequest;
};

export type DeleteScheduledTaskVariables = {
  scheduleId: IdParam;
  latestRunId?: IdParam | null;
};

export type RunScheduledTaskNowVariables = {
  scheduleId: IdParam;
  payload: ScheduleRunNowRequest;
};

type ScheduleReadLike = Pick<ScheduleRead, "id" | "latestRunId">;

function invalidateLinkedRunDetail(
  queryClient: QueryClient,
  runId?: IdParam | null,
) {
  if (runId === undefined || runId === null) {
    return Promise.resolve();
  }

  return queryClient.invalidateQueries({
    queryKey: queryKeys.platform.runs.detail(runId),
  });
}

function invalidateLinkedRunViews(queryClient: QueryClient, runId?: IdParam | null) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.lists() }),
    invalidateLinkedRunDetail(queryClient, runId),
  ]);
}

function invalidateScheduledTaskDetailScope(
  queryClient: QueryClient,
  scheduleId: IdParam,
) {
  return Promise.all([
    queryClient.invalidateQueries({
      queryKey: queryKeys.platform.schedules.detail(scheduleId),
    }),
    queryClient.invalidateQueries({
      queryKey: queryKeys.platform.schedules.firesScope(scheduleId),
    }),
  ]);
}

function invalidateScheduledTaskById(
  queryClient: QueryClient,
  scheduleId: IdParam,
  runId?: IdParam | null,
) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.schedules.lists() }),
    invalidateScheduledTaskDetailScope(queryClient, scheduleId),
    invalidateLinkedRunViews(queryClient, runId),
  ]);
}

function invalidateScheduledTaskScope(
  queryClient: QueryClient,
  schedule: ScheduleReadLike,
) {
  return invalidateScheduledTaskById(queryClient, schedule.id, schedule.latestRunId);
}

export function useScheduledTasks(
  params: ScheduleListParams = {},
): UseQueryResult<ScheduleListRead, Error> {
  return useQuery({
    queryKey: queryKeys.platform.schedules.list(params),
    queryFn: ({ signal }) => listScheduledTasks(params, signal),
  });
}

export function useScheduledTask(
  scheduleId: IdParam | undefined,
): UseQueryResult<ScheduleRead, Error> {
  const resolvedScheduleId = scheduleId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.schedules.detail(resolvedScheduleId),
    queryFn: ({ signal }) => getScheduledTask(resolvedScheduleId, signal),
    enabled: Boolean(scheduleId),
  });
}

export function useScheduledTaskFires(
  scheduleId: IdParam | undefined,
  params: ScheduleFireListParams = {},
): UseQueryResult<ScheduleFireListRead, Error> {
  const resolvedScheduleId = scheduleId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.schedules.fires(resolvedScheduleId, params),
    queryFn: ({ signal }) => listScheduledTaskFires(resolvedScheduleId, params, signal),
    enabled: Boolean(scheduleId),
  });
}

export function useCreateScheduledTask() {
  const queryClient = useQueryClient();

  return useMutation<ScheduleRead, Error, ScheduleCreateRequest>({
    mutationFn: (payload) => createScheduledTask(payload),
    onSuccess: async (schedule) => {
      await invalidateScheduledTaskScope(queryClient, schedule);
    },
  });
}

export function useUpdateScheduledTask() {
  const queryClient = useQueryClient();

  return useMutation<ScheduleRead, Error, UpdateScheduledTaskVariables>({
    mutationFn: ({ scheduleId, payload }) => updateScheduledTask(scheduleId, payload),
    onSuccess: async (schedule, variables) => {
      await Promise.all([
        invalidateScheduledTaskScope(queryClient, schedule),
        queryClient.invalidateQueries({
          queryKey: queryKeys.platform.schedules.detail(variables.scheduleId),
        }),
      ]);
    },
  });
}

export function useDeleteScheduledTask() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, DeleteScheduledTaskVariables>({
    mutationFn: ({ scheduleId }) => deleteScheduledTask(scheduleId),
    onSuccess: async (_result, { scheduleId, latestRunId }) => {
      await invalidateScheduledTaskById(queryClient, scheduleId, latestRunId);
    },
  });
}

export function useDeleteScheduledTasks() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, DeleteScheduledTaskVariables[]>({
    mutationFn: async (schedules) => {
      const results = await Promise.allSettled(
        schedules.map(({ scheduleId }) => deleteScheduledTask(scheduleId)),
      );
      const firstRejected = results.find((result) => result.status === "rejected");

      if (firstRejected?.status === "rejected") {
        throw firstRejected.reason;
      }
    },
    onSettled: async (_result, _error, schedules) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.platform.schedules.lists(),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.platform.runs.lists(),
        }),
        ...schedules.flatMap(({ scheduleId, latestRunId }) => [
          invalidateScheduledTaskDetailScope(queryClient, scheduleId),
          invalidateLinkedRunDetail(queryClient, latestRunId),
        ]),
      ]);
    },
  });
}

export function usePreviewUnsavedScheduledTask() {
  return useMutation<SchedulePreviewRead, Error, SchedulePreviewUnsavedRequest>({
    mutationFn: (payload) => previewUnsavedScheduledTask(payload),
  });
}

export function usePreviewScheduledTask() {
  return useMutation<SchedulePreviewRead, Error, PreviewScheduledTaskVariables>({
    mutationFn: ({ scheduleId, payload }) => previewScheduledTask(scheduleId, payload),
  });
}

export function useRunScheduledTaskNow() {
  const queryClient = useQueryClient();

  return useMutation<ScheduleRunNowRead, Error, RunScheduledTaskNowVariables>({
    mutationFn: ({ scheduleId, payload }) => runScheduledTaskNow(scheduleId, payload),
    onSuccess: async (result) => {
      await Promise.all([
        invalidateScheduledTaskById(queryClient, result.scheduleId, result.run.id),
        queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.detail(result.run.id) }),
      ]);
    },
  });
}
