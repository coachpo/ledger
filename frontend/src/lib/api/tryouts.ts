import { type IdParam, requestV2, toPathSegment } from "../api-client";
import type { RuntimeRunCreated } from "../types/runtime";
import type { TryoutExecuteInput, TryoutPersistRead, TryoutRead } from "../types/tryout";

function tryoutPath(runId: IdParam): string {
  return `/tryouts/${toPathSegment(runId)}`;
}

export function createTryout(
  payload: TryoutExecuteInput,
  signal?: AbortSignal,
): Promise<RuntimeRunCreated> {
  return requestV2<RuntimeRunCreated>("/tryouts", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function getTryout(runId: IdParam, signal?: AbortSignal): Promise<TryoutRead> {
  return requestV2<TryoutRead>(tryoutPath(runId), { signal });
}

export function persistTryout(
  runId: IdParam,
  signal?: AbortSignal,
): Promise<TryoutPersistRead> {
  return requestV2<TryoutPersistRead>(`${tryoutPath(runId)}/persist`, {
    method: "POST",
    signal,
  });
}

export const tryoutsApi = {
  create: createTryout,
  get: getTryout,
  persist: persistTryout,
} as const;
