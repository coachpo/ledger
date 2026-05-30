import { requestPlatform, toPathSegment, toQueryRecord, type IdParam } from "../api-client";
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
} from "../types/schedule";

function schedulePath(scheduleId: IdParam): string {
  return `/schedules/${toPathSegment(scheduleId)}`;
}

function normalizeOptionalText(value: string | null | undefined): string | undefined {
  const normalized = value?.trim();
  return normalized ? normalized : undefined;
}

export function normalizeScheduleListParams(params: ScheduleListParams = {}): ScheduleListParams {
  return {
    limit: params.limit,
    offset: params.offset ?? 0,
    packageId: params.packageId,
    packageKey: normalizeOptionalText(params.packageKey),
    status: params.status,
    workflowKey: normalizeOptionalText(params.workflowKey),
  };
}

export function normalizeScheduleFireListParams(
  params: ScheduleFireListParams = {},
): ScheduleFireListParams {
  return {
    limit: params.limit,
    offset: params.offset ?? 0,
  };
}

export function listScheduledTasks(
  params: ScheduleListParams = {},
  signal?: AbortSignal,
): Promise<ScheduleListRead> {
  return requestPlatform<ScheduleListRead>("/schedules", {
    query: toQueryRecord(normalizeScheduleListParams(params)),
    signal,
  });
}

export function getScheduledTask(
  scheduleId: IdParam,
  signal?: AbortSignal,
): Promise<ScheduleRead> {
  return requestPlatform<ScheduleRead>(schedulePath(scheduleId), { signal });
}

export function createScheduledTask(
  payload: ScheduleCreateRequest,
  signal?: AbortSignal,
): Promise<ScheduleRead> {
  return requestPlatform<ScheduleRead>("/schedules", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function updateScheduledTask(
  scheduleId: IdParam,
  payload: ScheduleUpdateRequest,
  signal?: AbortSignal,
): Promise<ScheduleRead> {
  return requestPlatform<ScheduleRead>(schedulePath(scheduleId), {
    body: payload,
    method: "PATCH",
    signal,
  });
}

export function archiveScheduledTask(
  scheduleId: IdParam,
  signal?: AbortSignal,
): Promise<ScheduleRead> {
  return requestPlatform<ScheduleRead>(`${schedulePath(scheduleId)}/archive`, {
    method: "POST",
    signal,
  });
}

export function previewUnsavedScheduledTask(
  payload: SchedulePreviewUnsavedRequest,
  signal?: AbortSignal,
): Promise<SchedulePreviewRead> {
  return requestPlatform<SchedulePreviewRead>("/schedules/preview", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function previewScheduledTask(
  scheduleId: IdParam,
  payload: SchedulePreviewRequest = {},
  signal?: AbortSignal,
): Promise<SchedulePreviewRead> {
  return requestPlatform<SchedulePreviewRead>(`${schedulePath(scheduleId)}/preview`, {
    body: payload,
    method: "POST",
    signal,
  });
}

export function runScheduledTaskNow(
  scheduleId: IdParam,
  payload: ScheduleRunNowRequest,
  signal?: AbortSignal,
): Promise<ScheduleRunNowRead> {
  return requestPlatform<ScheduleRunNowRead>(`${schedulePath(scheduleId)}/run-now`, {
    body: payload,
    method: "POST",
    signal,
  });
}

export function listScheduledTaskFires(
  scheduleId: IdParam,
  params: ScheduleFireListParams = {},
  signal?: AbortSignal,
): Promise<ScheduleFireListRead> {
  return requestPlatform<ScheduleFireListRead>(`${schedulePath(scheduleId)}/fires`, {
    query: toQueryRecord(normalizeScheduleFireListParams(params)),
    signal,
  });
}

export const schedulesApi = {
  archive: archiveScheduledTask,
  create: createScheduledTask,
  get: getScheduledTask,
  list: listScheduledTasks,
  listFires: listScheduledTaskFires,
  normalizeFireListParams: normalizeScheduleFireListParams,
  normalizeListParams: normalizeScheduleListParams,
  preview: previewScheduledTask,
  previewUnsaved: previewUnsavedScheduledTask,
  runNow: runScheduledTaskNow,
  update: updateScheduledTask,
} as const;
