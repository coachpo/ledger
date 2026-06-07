import { requestPlatform, toPathSegment, type IdParam } from "../api-client";
import type {
  MemoryApiAccessRequest,
  MemoryApiEntryRead,
  MemoryApiEventListRead,
  MemoryApiListRead,
  MemoryApiListRequest,
  MemoryApiRevisionListRead,
} from "../types/memory";

function memoryPath(memoryId: IdParam): string {
  return `/memory/${toPathSegment(memoryId)}`;
}

export function listMemory(
  payload: MemoryApiListRequest,
  signal?: AbortSignal,
): Promise<MemoryApiListRead> {
  return requestPlatform<MemoryApiListRead>("/memory", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function getMemoryDetail(
  memoryId: IdParam,
  payload: MemoryApiAccessRequest,
  signal?: AbortSignal,
): Promise<MemoryApiEntryRead> {
  return requestPlatform<MemoryApiEntryRead>(`${memoryPath(memoryId)}/detail`, {
    body: payload,
    method: "POST",
    signal,
  });
}

export function listMemoryRevisions(
  memoryId: IdParam,
  payload: MemoryApiAccessRequest,
  signal?: AbortSignal,
): Promise<MemoryApiRevisionListRead> {
  return requestPlatform<MemoryApiRevisionListRead>(
    `${memoryPath(memoryId)}/revisions`,
    { body: payload, method: "POST", signal },
  );
}

export function listMemoryEvents(
  memoryId: IdParam,
  payload: MemoryApiAccessRequest,
  signal?: AbortSignal,
): Promise<MemoryApiEventListRead> {
  return requestPlatform<MemoryApiEventListRead>(`${memoryPath(memoryId)}/events`, {
    body: payload,
    method: "POST",
    signal,
  });
}

export const memoryApi = {
  detail: getMemoryDetail,
  events: listMemoryEvents,
  list: listMemory,
  revisions: listMemoryRevisions,
} as const;
