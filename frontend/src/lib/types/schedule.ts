import type { UnknownRecord } from "./common";
import type { RunStatus } from "./run";

export type ScheduleStatus = "enabled" | "paused";
export type ScheduleWriteStatus = "enabled" | "paused";
export type ScheduleFireStatus = "pending" | "queued" | "skipped" | "failed";
type ScheduleFireReason = "scheduled" | "manual";
export type ScheduleOverlapPolicy = "skip" | "queue";
export type ScheduleMisfirePolicy = "skip" | "catchUpOne";
export type ScheduleRecurrenceType = "interval" | "daily" | "weekly" | "monthly";
export type ScheduleIntervalUnit = "minutes" | "hours" | "days";
export type ScheduleDayOfWeek = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";

interface ScheduleIntervalRecurrence {
  type: "interval";
  every: number;
  unit: ScheduleIntervalUnit;
}

interface ScheduleDailyRecurrence {
  type: "daily";
  atLocalTime: string;
}

interface ScheduleWeeklyRecurrence {
  type: "weekly";
  daysOfWeek: ScheduleDayOfWeek[];
  atLocalTime: string;
}

interface ScheduleMonthlyRecurrence {
  type: "monthly";
  daysOfMonth: number[];
  atLocalTime: string;
}

export type ScheduleRecurrence =
  | ScheduleIntervalRecurrence
  | ScheduleDailyRecurrence
  | ScheduleWeeklyRecurrence
  | ScheduleMonthlyRecurrence;

export interface ScheduleCreateRequest {
  packageId: number;
  workflowKey: string;
  name: string;
  description?: string | null;
  status?: ScheduleWriteStatus;
  timezone: string;
  recurrence: ScheduleRecurrence;
  startsAt?: string | null;
  endsAt?: string | null;
  overlapPolicy?: ScheduleOverlapPolicy;
  misfirePolicy?: ScheduleMisfirePolicy;
  misfireGraceSeconds?: number;
  inputTemplate?: UnknownRecord;
  templateVars?: UnknownRecord;
}

export interface ScheduleUpdateRequest {
  name?: string;
  description?: string | null;
  status?: ScheduleWriteStatus;
  timezone?: string;
  recurrence?: ScheduleRecurrence;
  startsAt?: string | null;
  endsAt?: string | null;
  overlapPolicy?: ScheduleOverlapPolicy;
  misfirePolicy?: ScheduleMisfirePolicy;
  misfireGraceSeconds?: number;
  inputTemplate?: UnknownRecord;
  templateVars?: UnknownRecord;
}

export interface ScheduleRead {
  id: number;
  packageId: number;
  packageKey: string;
  workflowKey: string;
  name: string;
  description: string | null;
  status: ScheduleStatus;
  timezone: string;
  recurrence: ScheduleRecurrence;
  startsAt: string | null;
  endsAt: string | null;
  nextFireAt: string | null;
  overlapPolicy: ScheduleOverlapPolicy;
  misfirePolicy: ScheduleMisfirePolicy;
  misfireGraceSeconds: number;
  latestFireId: number | null;
  latestRunId: number | null;
  latestStatus: ScheduleFireStatus | null;
  createdAt: string;
  updatedAt: string;
}

export interface ScheduleListRead {
  items: ScheduleRead[];
  totalCount: number;
  limit: number;
  offset: number;
}

export interface ScheduleFireRead {
  id: number;
  scheduleId: number;
  fireKey: string;
  reason: ScheduleFireReason;
  status: ScheduleFireStatus;
  scheduledFor: string;
  scheduledLocalDate: string | null;
  scheduledLocalTime: string | null;
  scheduledLocalDateTime: string | null;
  materializedAt: string | null;
  runId: number | null;
  renderedParameters: UnknownRecord;
  skipReason: string | null;
  errorCode: string | null;
  errorMessage: string | null;
  createdAt: string;
}

export interface ScheduleFireListRead {
  items: ScheduleFireRead[];
  totalCount: number;
  limit: number;
  offset: number;
}

export interface SchedulePreviewUnsavedRequest {
  packageId: number;
  workflowKey: string;
  timezone: string;
  recurrence: ScheduleRecurrence;
  scheduledFor: string;
  templateVars?: UnknownRecord;
  inputTemplate?: UnknownRecord;
}

export interface SchedulePreviewRequest {
  scheduledFor?: string | null;
}

export interface ScheduleValidationError {
  field: string;
  issue: string;
}

export interface SchedulePreviewRead {
  scheduleId: number | null;
  scheduledFor: string | null;
  templateContext: UnknownRecord;
  renderedParameters: UnknownRecord;
  validationErrors: ScheduleValidationError[];
  ready: boolean;
}

export interface ScheduleRunNowRequest {
  idempotencyKey: string;
  scheduledFor: string;
}

interface ScheduleRunNowRunRead {
  id: number;
  status: RunStatus;
  workflowPackageId: number;
  workflowPackageKey: string;
  workflowKey: string;
  createdAt: string;
}

export interface ScheduleRunNowRead {
  scheduleId: number;
  fire: ScheduleFireRead;
  run: ScheduleRunNowRunRead;
}

export interface ScheduleListParams {
  packageId?: number;
  packageKey?: string;
  workflowKey?: string;
  status?: ScheduleStatus;
  limit?: number;
  offset?: number;
}

export interface ScheduleFireListParams {
  limit?: number;
  offset?: number;
}
