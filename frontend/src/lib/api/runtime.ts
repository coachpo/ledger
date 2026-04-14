import { type IdParam, type RequestQueryValue, requestV2, toPathSegment } from "../api-client";
import type {
  RuntimeApprovalActionInput,
  RuntimeApprovalActionRead,
  RuntimeApprovalListParams,
  RuntimeApprovalListRead,
  RuntimeApprovalRead,
  RuntimeArtifactRead,
  RuntimeCancelRead,
  RuntimeRunCreateInput,
  RuntimeRunCreated,
  RuntimeRunListParams,
  RuntimeRunListRead,
  RuntimeRunRead,
  RuntimeTraceEventListParams,
  RuntimeTraceEventListRead,
} from "../types/runtime";

function runtimeRunPath(runId: IdParam): string {
  return `/runtime/runs/${toPathSegment(runId)}`;
}

function runtimeApprovalPath(approvalId: IdParam): string {
  return `/runtime/approvals/${toPathSegment(approvalId)}`;
}

function toQueryRecord<T extends object>(
  params?: T,
): Record<string, RequestQueryValue> | undefined {
  return params as Record<string, RequestQueryValue> | undefined;
}

export function listRuntimeRuns(
  params?: RuntimeRunListParams,
  signal?: AbortSignal,
): Promise<RuntimeRunListRead> {
  return requestV2<RuntimeRunListRead>("/runtime/runs", {
    query: toQueryRecord(params),
    signal,
  });
}

export function createRuntimeRun(
  payload: RuntimeRunCreateInput,
  signal?: AbortSignal,
): Promise<RuntimeRunCreated> {
  return requestV2<RuntimeRunCreated>("/runtime/runs", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function getRuntimeRun(runId: IdParam, signal?: AbortSignal): Promise<RuntimeRunRead> {
  return requestV2<RuntimeRunRead>(runtimeRunPath(runId), { signal });
}

export function getRuntimeRunArtifact(
  runId: IdParam,
  signal?: AbortSignal,
): Promise<RuntimeArtifactRead> {
  return requestV2<RuntimeArtifactRead>(`${runtimeRunPath(runId)}/artifacts`, { signal });
}

export function getRuntimeRunTrace(
  runId: IdParam,
  signal?: AbortSignal,
): Promise<RuntimeTraceEventListRead> {
  return requestV2<RuntimeTraceEventListRead>(`${runtimeRunPath(runId)}/trace`, { signal });
}

export function cancelRuntimeRun(
  runId: IdParam,
  signal?: AbortSignal,
): Promise<RuntimeCancelRead> {
  return requestV2<RuntimeCancelRead>(`${runtimeRunPath(runId)}/cancel`, {
    method: "POST",
    signal,
  });
}

export function listRuntimeApprovals(
  params?: RuntimeApprovalListParams,
  signal?: AbortSignal,
): Promise<RuntimeApprovalListRead> {
  return requestV2<RuntimeApprovalListRead>("/runtime/approvals", {
    query: toQueryRecord(params),
    signal,
  });
}

export function getRuntimeApproval(
  approvalId: IdParam,
  signal?: AbortSignal,
): Promise<RuntimeApprovalRead> {
  return requestV2<RuntimeApprovalRead>(runtimeApprovalPath(approvalId), { signal });
}

export function listRuntimeTraceEvents(
  params?: RuntimeTraceEventListParams,
  signal?: AbortSignal,
): Promise<RuntimeTraceEventListRead> {
  return requestV2<RuntimeTraceEventListRead>("/runtime/trace-events", {
    query: toQueryRecord(params),
    signal,
  });
}

export function approveRuntimeApproval(
  approvalId: IdParam,
  payload: RuntimeApprovalActionInput,
  signal?: AbortSignal,
): Promise<RuntimeApprovalActionRead> {
  return requestV2<RuntimeApprovalActionRead>(`${runtimeApprovalPath(approvalId)}/approve`, {
    body: payload,
    method: "POST",
    signal,
  });
}

export function denyRuntimeApproval(
  approvalId: IdParam,
  payload: RuntimeApprovalActionInput,
  signal?: AbortSignal,
): Promise<RuntimeApprovalActionRead> {
  return requestV2<RuntimeApprovalActionRead>(`${runtimeApprovalPath(approvalId)}/deny`, {
    body: payload,
    method: "POST",
    signal,
  });
}

export const runtimeApi = {
  runs: {
    list: listRuntimeRuns,
    create: createRuntimeRun,
    get: getRuntimeRun,
    getArtifact: getRuntimeRunArtifact,
    getTrace: getRuntimeRunTrace,
    cancel: cancelRuntimeRun,
  },
  approvals: {
    list: listRuntimeApprovals,
    get: getRuntimeApproval,
    approve: approveRuntimeApproval,
    deny: denyRuntimeApproval,
  },
  traceEvents: {
    list: listRuntimeTraceEvents,
  },
} as const;
