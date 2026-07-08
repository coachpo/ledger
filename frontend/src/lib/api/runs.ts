import { requestPlatform, toPathSegment, toQueryRecord, type IdParam } from "../api-client";
import type {
  RunCreatedRead,
  RunListParams,
  RunListRead,
  RunRead,
  RunRerunCreateRequest,
  RunRerunDraftRead,
} from "../types/run";

function runPath(runId: IdParam): string {
  return `/runs/${toPathSegment(runId)}`;
}

function normalizeOptionalText(value: string | undefined): string | undefined {
  const normalized = value?.trim();
  return normalized ? normalized : undefined;
}

export function normalizeRunListParams(params: RunListParams = {}): RunListParams {
  return {
    limit: params.limit,
    modelConnectionKey: normalizeOptionalText(params.modelConnectionKey),
    offset: params.offset ?? 0,
    status: params.status,
    workflowKey: normalizeOptionalText(params.workflowKey),
    workflowPackageId: params.workflowPackageId,
    workflowPackageKey: normalizeOptionalText(params.workflowPackageKey),
  };
}

export function listRuns(params?: RunListParams, signal?: AbortSignal): Promise<RunListRead> {
  return requestPlatform<RunListRead>("/runs", {
    query: toQueryRecord(normalizeRunListParams(params)),
    signal,
  });
}

export function getRun(runId: IdParam, signal?: AbortSignal): Promise<RunRead> {
  return requestPlatform<RunRead>(runPath(runId), { signal });
}

export function getRunRerunDraft(
  runId: IdParam,
  signal?: AbortSignal,
): Promise<RunRerunDraftRead> {
  return requestPlatform<RunRerunDraftRead>(`${runPath(runId)}/rerun-draft`, { signal });
}

export function createRunRerun(
  runId: IdParam,
  payload: RunRerunCreateRequest,
): Promise<RunCreatedRead> {
  return requestPlatform<RunCreatedRead>(`${runPath(runId)}/reruns`, {
    body: payload,
    method: "POST",
  });
}

export const runsApi = {
  createRerun: createRunRerun,
  get: getRun,
  getRerunDraft: getRunRerunDraft,
  list: listRuns,
  normalizeListParams: normalizeRunListParams,
} as const;
