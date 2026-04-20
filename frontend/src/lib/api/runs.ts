import { requestPlatform, toPathSegment, toQueryRecord, type IdParam } from "../api-client";
import type { RunListParams, RunListRead, RunRead } from "../types/run";

function runPath(runId: IdParam): string {
  return `/runs/${toPathSegment(runId)}`;
}

export function listRuns(params?: RunListParams, signal?: AbortSignal): Promise<RunListRead> {
  return requestPlatform<RunListRead>("/runs", {
    query: toQueryRecord(params),
    signal,
  });
}

export function getRun(runId: IdParam, signal?: AbortSignal): Promise<RunRead> {
  return requestPlatform<RunRead>(runPath(runId), { signal });
}

export const runsApi = {
  get: getRun,
  list: listRuns,
} as const;
