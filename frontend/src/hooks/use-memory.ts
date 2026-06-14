import {
  type QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  createAdminMemoryEntry,
  createAdminMemoryRevision,
  deleteAdminMemoryEntry,
  getAdminMemoryEntry,
  getMemoryDetail,
  listAdminMemoryEntries,
  listAdminMemoryEvents,
  listAdminMemoryRevisions,
  listMemory,
  listMemoryEvents,
  listMemoryRevisions,
  updateAdminMemoryWorkflowVisibility,
} from "@/lib/api/memory";
import type { IdParam } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type {
  MemoryAdminCreateRequest,
  MemoryAdminEntryRead,
  MemoryAdminEventListRead,
  MemoryAdminHistoryParams,
  MemoryAdminListParams,
  MemoryAdminListRead,
  MemoryAdminRevisionCreateRequest,
  MemoryAdminRevisionListRead,
  MemoryAdminWorkflowVisibilityUpdateRequest,
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

export type ReviseAdminMemoryVariables = {
  memoryId: IdParam;
  payload: MemoryAdminRevisionCreateRequest;
};

export type UpdateAdminMemoryWorkflowVisibilityVariables = {
  memoryId: IdParam;
  payload: MemoryAdminWorkflowVisibilityUpdateRequest;
};

function invalidateAdminMemoryEntryScope(
  queryClient: QueryClient,
  memoryId: IdParam,
) {
  return Promise.all([
    queryClient.invalidateQueries({
      queryKey: queryKeys.platform.memory.admin.lists(),
    }),
    queryClient.invalidateQueries({
      queryKey: queryKeys.platform.memory.admin.detail(memoryId),
    }),
    queryClient.invalidateQueries({
      queryKey: queryKeys.platform.memory.admin.revisionsScope(memoryId),
    }),
    queryClient.invalidateQueries({
      queryKey: queryKeys.platform.memory.admin.eventsScope(memoryId),
    }),
  ]);
}
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
    queryKey: queryKeys.platform.memory.detail(resolvedMemoryId, payload),
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
    queryKey: queryKeys.platform.memory.revisions(resolvedMemoryId, payload),
    queryFn: ({ signal }) =>
      listMemoryRevisions(resolvedMemoryId, payload, signal),
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
    queryKey: queryKeys.platform.memory.events(resolvedMemoryId, payload),
    queryFn: ({ signal }) =>
      listMemoryEvents(resolvedMemoryId, payload, signal),
    enabled: Boolean(memoryId) && (options.enabled ?? true),
  });
}

export function useAdminMemoryEntries(
  params: MemoryAdminListParams = {},
  options: MemoryQueryOptions = {},
): UseQueryResult<MemoryAdminListRead, Error> {
  return useQuery({
    queryKey: queryKeys.platform.memory.admin.list(params),
    queryFn: ({ signal }) => listAdminMemoryEntries(params, signal),
    enabled: options.enabled ?? true,
  });
}

export function useAdminMemoryEntry(
  memoryId: IdParam | undefined,
  options: MemoryQueryOptions = {},
): UseQueryResult<MemoryAdminEntryRead, Error> {
  const resolvedMemoryId = memoryId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.memory.admin.detail(resolvedMemoryId),
    queryFn: ({ signal }) => getAdminMemoryEntry(resolvedMemoryId, signal),
    enabled: Boolean(memoryId) && (options.enabled ?? true),
  });
}

export function useAdminMemoryRevisions(
  memoryId: IdParam | undefined,
  params: MemoryAdminHistoryParams = {},
  options: MemoryQueryOptions = {},
): UseQueryResult<MemoryAdminRevisionListRead, Error> {
  const resolvedMemoryId = memoryId ?? "";
  return useQuery({
    queryKey: queryKeys.platform.memory.admin.revisions(
      resolvedMemoryId,
      params,
    ),
    queryFn: ({ signal }) =>
      listAdminMemoryRevisions(resolvedMemoryId, params, signal),
    enabled: Boolean(memoryId) && (options.enabled ?? true),
  });
}

export function useAdminMemoryEvents(
  memoryId: IdParam | undefined,
  params: MemoryAdminHistoryParams = {},
  options: MemoryQueryOptions = {},
): UseQueryResult<MemoryAdminEventListRead, Error> {
  const resolvedMemoryId = memoryId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.memory.admin.events(resolvedMemoryId, params),
    queryFn: ({ signal }) =>
      listAdminMemoryEvents(resolvedMemoryId, params, signal),
    enabled: Boolean(memoryId) && (options.enabled ?? true),
  });
}

export function useCreateAdminMemoryEntry() {
  const queryClient = useQueryClient();

  return useMutation<MemoryAdminEntryRead, Error, MemoryAdminCreateRequest>({
    mutationFn: (payload) => createAdminMemoryEntry(payload),
    onSuccess: async (entry) => {
      await invalidateAdminMemoryEntryScope(queryClient, entry.memoryId);
    },
  });
}

export function useCreateAdminMemoryRevision() {
  const queryClient = useQueryClient();

  return useMutation<MemoryAdminEntryRead, Error, ReviseAdminMemoryVariables>({
    mutationFn: ({ memoryId, payload }) =>
      createAdminMemoryRevision(memoryId, payload),
    onSuccess: async (entry, variables) => {
      await Promise.all([
        invalidateAdminMemoryEntryScope(queryClient, variables.memoryId),
        invalidateAdminMemoryEntryScope(queryClient, entry.memoryId),
      ]);
    },
  });
}

export function useUpdateAdminMemoryWorkflowVisibility() {
  const queryClient = useQueryClient();

  return useMutation<
    MemoryAdminEntryRead,
    Error,
    UpdateAdminMemoryWorkflowVisibilityVariables
  >({
    mutationFn: ({ memoryId, payload }) =>
      updateAdminMemoryWorkflowVisibility(memoryId, payload),
    onSuccess: async (entry, variables) => {
      await Promise.all([
        invalidateAdminMemoryEntryScope(queryClient, variables.memoryId),
        invalidateAdminMemoryEntryScope(queryClient, entry.memoryId),
      ]);
    },
  });
}

export function useDeleteAdminMemoryEntry() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, IdParam>({
    mutationFn: (memoryId) => deleteAdminMemoryEntry(memoryId),
    onSuccess: async (_result, memoryId) => {
      await invalidateAdminMemoryEntryScope(queryClient, memoryId);
    },
  });
}
