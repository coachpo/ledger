import {
  requestPlatform,
  toPathSegment,
  toQueryRecord,
  type IdParam,
} from "../api-client";
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
} from "../types/memory";

function memoryPath(memoryId: IdParam): string {
  return `/memory/${toPathSegment(memoryId)}`;
}

function adminMemoryPath(memoryId: IdParam): string {
  return `/memory/admin/entries/${toPathSegment(memoryId)}`;
}

function normalizeOptionalText(
  value: string | null | undefined,
): string | undefined {
  const normalized = value?.trim();
  return normalized ? normalized : undefined;
}

function normalizeOptionalKind(
  value: string | null | undefined,
): string | undefined {
  return normalizeOptionalText(value)?.toLowerCase();
}

export function normalizeMemoryAdminListParams(
  params: MemoryAdminListParams = {},
): MemoryAdminListParams {
  return {
    agentKey: normalizeOptionalText(params.agentKey),
    kind: normalizeOptionalKind(params.kind),
    limit: params.limit ?? 50,
    offset: params.offset ?? 0,
    packageKey: normalizeOptionalText(params.packageKey),
    query: normalizeOptionalText(params.query),
    runId: params.runId ?? undefined,
    scopeType: params.scopeType ?? undefined,
    sort: params.sort ?? "updatedAtDesc",
    visibleToWorkflow: params.visibleToWorkflow ?? undefined,
    workflowKey: normalizeOptionalText(params.workflowKey),
  };
}

export function normalizeMemoryAdminHistoryParams(
  params: MemoryAdminHistoryParams = {},
): MemoryAdminHistoryParams {
  return {
    limit: params.limit,
    offset: params.offset ?? 0,
  };
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
  return requestPlatform<MemoryApiEventListRead>(
    `${memoryPath(memoryId)}/events`,
    {
      body: payload,
      method: "POST",
      signal,
    },
  );
}
export function listAdminMemoryEntries(
  params: MemoryAdminListParams = {},
  signal?: AbortSignal,
): Promise<MemoryAdminListRead> {
  return requestPlatform<MemoryAdminListRead>("/memory/admin/entries", {
    query: toQueryRecord(normalizeMemoryAdminListParams(params)),
    signal,
  });
}

export function createAdminMemoryEntry(
  payload: MemoryAdminCreateRequest,
  signal?: AbortSignal,
): Promise<MemoryAdminEntryRead> {
  return requestPlatform<MemoryAdminEntryRead>("/memory/admin/entries", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function getAdminMemoryEntry(
  memoryId: IdParam,
  signal?: AbortSignal,
): Promise<MemoryAdminEntryRead> {
  return requestPlatform<MemoryAdminEntryRead>(adminMemoryPath(memoryId), {
    signal,
  });
}

export function listAdminMemoryRevisions(
  memoryId: IdParam,
  params: MemoryAdminHistoryParams = {},
  signal?: AbortSignal,
): Promise<MemoryAdminRevisionListRead> {
  return requestPlatform<MemoryAdminRevisionListRead>(
    `${adminMemoryPath(memoryId)}/revisions`,
    { query: toQueryRecord(normalizeMemoryAdminHistoryParams(params)), signal },
  );
}
export function listAdminMemoryEvents(
  memoryId: IdParam,
  params: MemoryAdminHistoryParams = {},
  signal?: AbortSignal,
): Promise<MemoryAdminEventListRead> {
  return requestPlatform<MemoryAdminEventListRead>(
    `${adminMemoryPath(memoryId)}/events`,
    { query: toQueryRecord(normalizeMemoryAdminHistoryParams(params)), signal },
  );
}

export function createAdminMemoryRevision(
  memoryId: IdParam,
  payload: MemoryAdminRevisionCreateRequest,
  signal?: AbortSignal,
): Promise<MemoryAdminEntryRead> {
  return requestPlatform<MemoryAdminEntryRead>(
    `${adminMemoryPath(memoryId)}/revisions`,
    { body: payload, method: "POST", signal },
  );
}

export function updateAdminMemoryWorkflowVisibility(
  memoryId: IdParam,
  payload: MemoryAdminWorkflowVisibilityUpdateRequest,
  signal?: AbortSignal,
): Promise<MemoryAdminEntryRead> {
  return requestPlatform<MemoryAdminEntryRead>(
    `${adminMemoryPath(memoryId)}/workflow-visibility`,
    {
      body: payload,
      method: "PATCH",
      signal,
    },
  );
}

export function deleteAdminMemoryEntry(
  memoryId: IdParam,
  signal?: AbortSignal,
): Promise<void> {
  return requestPlatform<void>(adminMemoryPath(memoryId), {
    method: "DELETE",
    signal,
  });
}
export const memoryApi = {
  admin: {
    create: createAdminMemoryEntry,
    createRevision: createAdminMemoryRevision,
    delete: deleteAdminMemoryEntry,
    detail: getAdminMemoryEntry,
    events: listAdminMemoryEvents,
    list: listAdminMemoryEntries,
    normalizeHistoryParams: normalizeMemoryAdminHistoryParams,
    normalizeListParams: normalizeMemoryAdminListParams,
    revisions: listAdminMemoryRevisions,
    updateWorkflowVisibility: updateAdminMemoryWorkflowVisibility,
  },
  detail: getMemoryDetail,
  events: listMemoryEvents,
  list: listMemory,
  revisions: listMemoryRevisions,
} as const;
