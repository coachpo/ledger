import { requestPlatform, toPathSegment, toQueryRecord, type IdParam } from "../api-client";
import { queryKeys } from "../query-keys";
import type {
  RunCreatedRead,
  RunForkCreateRequest,
  RunForkDraftRead,
  RunListParams,
  RunListRead,
  RunRead,
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
    offset: params.offset ?? 0,
    status: params.status,
    targetId: params.targetId,
    targetKey: normalizeOptionalText(params.targetKey),
    targetKind: params.targetKind,
    targetVersion: params.targetVersion,
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

export function getRunForkDraft(
  runId: IdParam,
  forkStepIndex: number,
  signal?: AbortSignal,
): Promise<RunForkDraftRead> {
  return requestPlatform<RunForkDraftRead>(`${runPath(runId)}/fork-draft`, {
    query: { forkStepIndex },
    signal,
  });
}

export function createRunFork(
  runId: IdParam,
  payload: RunForkCreateRequest,
): Promise<RunCreatedRead> {
  return requestPlatform<RunCreatedRead>(`${runPath(runId)}/forks`, {
    body: payload,
    method: "POST",
  });
}

export const runsApi = {
  buildListQueryKey: buildRunsListQueryKey,
  createFork: createRunFork,
  get: getRun,
  getForkDraft: getRunForkDraft,
  list: listRuns,
  normalizeListParams: normalizeRunListParams,
} as const;
