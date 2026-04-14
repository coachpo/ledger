import { type IdParam, type RequestQueryValue, requestV2, toPathSegment } from "../api-client";
import type {
  RuntimeApprovalListParams,
  RuntimeApprovalListRead,
  RuntimeApprovalRead,
  RuntimeRunListParams,
  RuntimeRunListRead,
  RuntimeRunRead,
  RuntimeTraceEventListParams,
  RuntimeTraceEventListRead,
  StudioArtifactListParams,
} from "../types/studio";
import type { RuntimeArtifactListRead, RuntimeArtifactRead } from "../types/runtime";

function studioRunPath(runId: IdParam): string {
  return `/studio/runs/${toPathSegment(runId)}`;
}

function studioApprovalPath(approvalId: IdParam): string {
  return `/studio/approvals/${toPathSegment(approvalId)}`;
}

function toQueryRecord<T extends object>(
  params?: T,
): Record<string, RequestQueryValue> | undefined {
  return params as Record<string, RequestQueryValue> | undefined;
}

export function listStudioRuns(
  params?: RuntimeRunListParams,
  signal?: AbortSignal,
): Promise<RuntimeRunListRead> {
  return requestV2<RuntimeRunListRead>("/studio/runs", {
    query: toQueryRecord(params),
    signal,
  });
}

export function getStudioRun(runId: IdParam, signal?: AbortSignal): Promise<RuntimeRunRead> {
  return requestV2<RuntimeRunRead>(studioRunPath(runId), { signal });
}

export function getStudioRunArtifact(
  runId: IdParam,
  signal?: AbortSignal,
): Promise<RuntimeArtifactRead> {
  return requestV2<RuntimeArtifactRead>(`${studioRunPath(runId)}/artifacts`, { signal });
}

export function getStudioRunTrace(
  runId: IdParam,
  signal?: AbortSignal,
): Promise<RuntimeTraceEventListRead> {
  return requestV2<RuntimeTraceEventListRead>(`${studioRunPath(runId)}/trace`, { signal });
}

export function listStudioArtifacts(
  params?: StudioArtifactListParams,
  signal?: AbortSignal,
): Promise<RuntimeArtifactListRead> {
  return requestV2<RuntimeArtifactListRead>("/studio/artifacts", {
    query: toQueryRecord(params),
    signal,
  });
}

export function listStudioApprovals(
  params?: RuntimeApprovalListParams,
  signal?: AbortSignal,
): Promise<RuntimeApprovalListRead> {
  return requestV2<RuntimeApprovalListRead>("/studio/approvals", {
    query: toQueryRecord(params),
    signal,
  });
}

export function getStudioApproval(
  approvalId: IdParam,
  signal?: AbortSignal,
): Promise<RuntimeApprovalRead> {
  return requestV2<RuntimeApprovalRead>(studioApprovalPath(approvalId), { signal });
}

export function listStudioTraceEvents(
  params?: RuntimeTraceEventListParams,
  signal?: AbortSignal,
): Promise<RuntimeTraceEventListRead> {
  return requestV2<RuntimeTraceEventListRead>("/studio/trace-events", {
    query: toQueryRecord(params),
    signal,
  });
}

export const studioApi = {
  runs: {
    list: listStudioRuns,
    get: getStudioRun,
    getArtifact: getStudioRunArtifact,
    getTrace: getStudioRunTrace,
  },
  artifacts: {
    list: listStudioArtifacts,
  },
  approvals: {
    list: listStudioApprovals,
    get: getStudioApproval,
  },
  traceEvents: {
    list: listStudioTraceEvents,
  },
} as const;
