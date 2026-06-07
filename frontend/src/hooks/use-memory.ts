import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import {
  getMemoryDetail,
  listMemory,
  listMemoryEvents,
  listMemoryRevisions,
} from "@/lib/api/memory";
import type { IdParam } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type {
  MemoryApiAccessRequest,
  MemoryApiEntryRead,
  MemoryApiEventListRead,
  MemoryApiListRead,
  MemoryApiListRequest,
  MemoryApiRevisionListRead,
} from "@/lib/types/memory";

type MemoryQueryOptions = {
  enabled?: boolean;
};

export function useMemoryList(
  payload: MemoryApiListRequest,
  options: MemoryQueryOptions = {},
): UseQueryResult<MemoryApiListRead, Error> {
  return useQuery({
    queryKey: queryKeys.platform.memory.list(payload),
    queryFn: ({ signal }) => listMemory(payload, signal),
    enabled: options.enabled ?? true,
  });
}

export function useMemoryDetail(
  memoryId: IdParam | undefined,
  payload: MemoryApiAccessRequest,
  options: MemoryQueryOptions = {},
): UseQueryResult<MemoryApiEntryRead, Error> {
  const resolvedMemoryId = memoryId ?? "";

  return useQuery({
    queryKey: [...queryKeys.platform.memory.detail(resolvedMemoryId), payload] as const,
    queryFn: ({ signal }) => getMemoryDetail(resolvedMemoryId, payload, signal),
    enabled: Boolean(memoryId) && (options.enabled ?? true),
  });
}

export function useMemoryRevisions(
  memoryId: IdParam | undefined,
  payload: MemoryApiAccessRequest,
  options: MemoryQueryOptions = {},
): UseQueryResult<MemoryApiRevisionListRead, Error> {
  const resolvedMemoryId = memoryId ?? "";

  return useQuery({
    queryKey: [...queryKeys.platform.memory.revisions(resolvedMemoryId), payload] as const,
    queryFn: ({ signal }) => listMemoryRevisions(resolvedMemoryId, payload, signal),
    enabled: Boolean(memoryId) && (options.enabled ?? true),
  });
}

export function useMemoryEvents(
  memoryId: IdParam | undefined,
  payload: MemoryApiAccessRequest,
  options: MemoryQueryOptions = {},
): UseQueryResult<MemoryApiEventListRead, Error> {
  const resolvedMemoryId = memoryId ?? "";

  return useQuery({
    queryKey: [...queryKeys.platform.memory.events(resolvedMemoryId), payload] as const,
    queryFn: ({ signal }) => listMemoryEvents(resolvedMemoryId, payload, signal),
    enabled: Boolean(memoryId) && (options.enabled ?? true),
  });
}
