import { requestPlatform, toPathSegment, toQueryRecord, type IdParam } from "../api-client";
import { queryKeys } from "../query-keys";
import type {
  RunCreatedRead,
  RunListParams,
  RunListRead,
  RunRead,
  RunRerunCreateRequest,
  RunRerunDraftRead,
  RunStepReplayCreateRequest,
  RunStepReplayDraftRead,
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
    targetId: params.targetId,
    targetKey: normalizeOptionalText(params.targetKey),
    targetKind: params.targetKind,
    workflowKey: normalizeOptionalText(params.workflowKey),
    workflowPackageId: params.workflowPackageId,
    workflowPackageKey: normalizeOptionalText(params.workflowPackageKey),
  };
}

export function buildRunsListQueryKey(params: RunListParams = {}) {
  return [...queryKeys.platform.runs.all, "list", normalizeRunListParams(params)] as const;
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

export function getRunStepReplayDraft(
  runId: IdParam,
  stepIndex: number,
  signal?: AbortSignal,
): Promise<RunStepReplayDraftRead> {
  return requestPlatform<RunStepReplayDraftRead>(`${runPath(runId)}/step-replay-draft`, {
    query: { stepIndex },
    signal,
  });
}

export function createRunStepReplay(
  runId: IdParam,
  payload: RunStepReplayCreateRequest,
): Promise<RunCreatedRead> {
  return requestPlatform<RunCreatedRead>(`${runPath(runId)}/step-replays`, {
    body: payload,
    method: "POST",
  });
}

export const runsApi = {
  buildListQueryKey: buildRunsListQueryKey,
  createRerun: createRunRerun,
  createStepReplay: createRunStepReplay,
  get: getRun,
  getRerunDraft: getRunRerunDraft,
  getStepReplayDraft: getRunStepReplayDraft,
  list: listRuns,
  normalizeListParams: normalizeRunListParams,
} as const;
