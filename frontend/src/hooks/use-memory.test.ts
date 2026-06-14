import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const reactQueryState = vi.hoisted(() => ({
  invalidateQueriesMock: vi.fn(() => Promise.resolve()),
  useMutationMock: vi.fn((options: unknown) => options),
  useQueryClientMock: vi.fn(),
  useQueryMock: vi.fn((options: unknown) => options),
}));

vi.mock("@tanstack/react-query", () => ({
  useMutation: reactQueryState.useMutationMock,
  useQuery: reactQueryState.useQueryMock,
  useQueryClient: reactQueryState.useQueryClientMock,
}));

import { queryKeys } from "@/lib/query-keys";
import type {
  MemoryAdminCreateRequest,
  MemoryAdminEntryRead,
  MemoryAdminListRead,
  MemoryAdminRevisionCreateRequest,
  MemoryAdminWorkflowVisibilityUpdateRequest,
  MemoryApiListRead,
  MemoryApiListRequest,
} from "@/lib/types/memory";
import {
  useAdminMemoryEntries,
  useAdminMemoryEntry,
  useAdminMemoryEvents,
  useAdminMemoryRevisions,
  useCreateAdminMemoryEntry,
  useCreateAdminMemoryRevision,
  useDeleteAdminMemoryEntry,
  useMemoryList,
  useUpdateAdminMemoryWorkflowVisibility,
} from "./use-memory";

type QueryOptions<T> = {
  enabled: boolean;
  queryFn: (context: { signal: AbortSignal }) => Promise<T>;
  queryKey: readonly unknown[];
};

type MutationOptions<TData, TVariables> = {
  mutationFn: (variables: TVariables) => Promise<TData>;
  onSuccess?: (data: TData, variables: TVariables) => Promise<void> | void;
};

const ORIGINAL_FETCH = globalThis.fetch;

function createFetchMock() {
  return vi.fn<
    (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
  >();
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}
function lastQueryOptions<T>() {
  return reactQueryState.useQueryMock.mock.calls.at(-1)?.[0] as QueryOptions<T>;
}

function lastMutationOptions<TData, TVariables>() {
  return reactQueryState.useMutationMock.mock.calls.at(
    -1,
  )?.[0] as MutationOptions<TData, TVariables>;
}

function getLastFetchCall(fetchMock: ReturnType<typeof createFetchMock>) {
  const call = fetchMock.mock.calls.at(-1);
  if (!call) {
    throw new Error("Expected fetch to be called");
  }
  const [input, init] = call;
  return { init, url: new URL(String(input)) };
}

function memoryPayload(): MemoryApiListRequest {
  return {
    accessContext: {
      packageKey: "research_package",
      workflowKey: "daily_research",
    },
    limit: 25,
    query: "earnings",
    scope: { scopeKey: "42", scopeType: "run" },
    visibility: "explicit-scope",
  };
}

function memoryListResponse(payload: MemoryApiListRequest): MemoryApiListRead {
  return {
    count: 0,
    items: [],
    limit: payload.limit ?? 50,
    offset: payload.offset ?? 0,
    scope: payload.scope,
    visibility: payload.visibility ?? "explicit-scope",
  };
}

function adminEntry(
  overrides: Partial<MemoryAdminEntryRead> = {},
): MemoryAdminEntryRead {
  return {
    attributes: { confidence: "high" },
    content: "Admin-created memory content",
    createdAt: "2026-06-13T12:00:00Z",
    kind: "insight",
    memoryId: "mem-admin-1",
    provenance: {
      agentKey: "local-instance-operator",
      agentVersion: 1,
      createdByType: "operator",
      runId: 41,
    },
    reflections: [],
    revision: {
      contentHash: "a".repeat(64),
      createdAt: "2026-06-13T12:00:00Z",
      revisionId: "rev-admin-1",
      version: 1,
    },
    revisionId: "rev-admin-1",
    scope: { scopeKey: "research_package", scopeType: "package" },
    subjectRefs: [],
    visibleToWorkflow: true,
    summary: "Admin memory",
    updatedAt: "2026-06-13T12:05:00Z",
    ...overrides,
  };
}

let fetchMock = createFetchMock();

beforeEach(() => {
  fetchMock = createFetchMock();
  globalThis.fetch = fetchMock as typeof fetch;
  reactQueryState.invalidateQueriesMock.mockClear();
  reactQueryState.useMutationMock.mockClear();
  reactQueryState.useQueryClientMock.mockReturnValue({
    invalidateQueries: reactQueryState.invalidateQueriesMock,
  });
  reactQueryState.useQueryMock.mockClear();
});

afterEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = ORIGINAL_FETCH;
});

describe("useMemoryList", () => {
  it("keeps scoped runtime reads on POST /api/memory with explicit-scope payloads", async () => {
    const payload = memoryPayload();
    const response = memoryListResponse(payload);
    fetchMock.mockResolvedValueOnce(jsonResponse(response));

    useMemoryList(payload, { enabled: false });

    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.memory.list(payload),
      }),
    );

    const signal = new AbortController().signal;
    await expect(
      lastQueryOptions<MemoryApiListRead>().queryFn({ signal }),
    ).resolves.toEqual(response);
    const { init, url } = getLastFetchCall(fetchMock);
    expect(url.pathname).toBe("/api/memory");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify(payload));
  });
});

describe("admin memory hooks", () => {
  it("lists admin memory through GET /api/memory/admin/entries without scoped access payloads", async () => {
    const response: MemoryAdminListRead = {
      items: [],
      limit: 50,
      offset: 0,
      sort: "updatedAtDesc",
      total: 0,
    };
    const params = {
      packageKey: " research_package ",
      query: " operator note ",
      runId: 41,
      scopeType: "package" as const,
      visibleToWorkflow: true as const,
      workflowKey: " daily_research ",
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(response));

    useAdminMemoryEntries(params, { enabled: false });

    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.memory.admin.list(params),
      }),
    );

    await expect(
      lastQueryOptions<MemoryAdminListRead>().queryFn({
        signal: new AbortController().signal,
      }),
    ).resolves.toEqual(response);
    const { init, url } = getLastFetchCall(fetchMock);
    expect(url.pathname).toBe("/api/memory/admin/entries");
    expect(init?.method).toBe("GET");
    expect(init?.body).toBeUndefined();
    expect(Object.fromEntries(url.searchParams.entries())).toEqual({
      limit: "50",
      offset: "0",
      packageKey: "research_package",
      query: "operator note",
      runId: "41",
      scopeType: "package",
      sort: "updatedAtDesc",
      visibleToWorkflow: "true",
      workflowKey: "daily_research",
    });
    expect(url.searchParams.has("accessContext")).toBe(false);
    expect(url.searchParams.has("visibility")).toBe(false);
    expect(url.searchParams.has("status")).toBe(false);

    fetchMock.mockResolvedValueOnce(jsonResponse(response));
    useAdminMemoryEntries({ visibleToWorkflow: false }, { enabled: true });
    await lastQueryOptions<MemoryAdminListRead>().queryFn({
      signal: new AbortController().signal,
    });
    const hiddenCall = getLastFetchCall(fetchMock);
    expect(hiddenCall.url.pathname).toBe("/api/memory/admin/entries");
    expect(hiddenCall.url.searchParams.get("visibleToWorkflow")).toBe("false");
    expect(hiddenCall.url.searchParams.has("status")).toBe(false);
  });

  it("reads admin detail, revisions, and events through admin entry routes", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(adminEntry()));
    useAdminMemoryEntry("mem-admin-1");
    await lastQueryOptions<MemoryAdminEntryRead>().queryFn({
      signal: new AbortController().signal,
    });
    expect(getLastFetchCall(fetchMock).url.pathname).toBe(
      "/api/memory/admin/entries/mem-admin-1",
    );

    fetchMock.mockResolvedValueOnce(
      jsonResponse({ count: 0, items: [], limit: 50, offset: 0 }),
    );
    useAdminMemoryRevisions("mem-admin-1", { limit: 10 });
    await lastQueryOptions<unknown>().queryFn({
      signal: new AbortController().signal,
    });
    let lastCall = getLastFetchCall(fetchMock);
    expect(lastCall.url.pathname).toBe(
      "/api/memory/admin/entries/mem-admin-1/revisions",
    );
    expect(Object.fromEntries(lastCall.url.searchParams.entries())).toEqual({
      limit: "10",
      offset: "0",
    });

    fetchMock.mockResolvedValueOnce(
      jsonResponse({ count: 0, items: [], limit: 100, offset: 0 }),
    );
    useAdminMemoryEvents("mem-admin-1");
    await lastQueryOptions<unknown>().queryFn({
      signal: new AbortController().signal,
    });
    lastCall = getLastFetchCall(fetchMock);
    expect(lastCall.url.pathname).toBe(
      "/api/memory/admin/entries/mem-admin-1/events",
    );
    expect(Object.fromEntries(lastCall.url.searchParams.entries())).toEqual({
      offset: "0",
    });
  });

  it("creates admin memory and invalidates list, detail, revision, and event scopes", async () => {
    const response = adminEntry();
    const payload: MemoryAdminCreateRequest = {
      content: "Admin-created memory content",
      provenance: response.provenance,
      scope: response.scope,
      summary: "Admin memory",
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(response, 201));

    useCreateAdminMemoryEntry();
    const options = lastMutationOptions<
      MemoryAdminEntryRead,
      MemoryAdminCreateRequest
    >();

    await expect(options.mutationFn(payload)).resolves.toEqual(response);
    const { init, url } = getLastFetchCall(fetchMock);
    expect(url.pathname).toBe("/api/memory/admin/entries");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify(payload));

    await options.onSuccess?.(response, payload);
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.admin.lists(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.admin.detail(response.memoryId),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.admin.revisionsScope(
        response.memoryId,
      ),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.admin.eventsScope(response.memoryId),
    });
  });

  it("revises admin memory and updates workflow visibility through separate mutation endpoints", async () => {
    const response = adminEntry({ revisionId: "rev-admin-2" });
    const revisionPayload: MemoryAdminRevisionCreateRequest = {
      content: "Updated admin memory content",
      provenance: response.provenance,
      summary: "Updated admin memory",
    };
    const visibilityPayload: MemoryAdminWorkflowVisibilityUpdateRequest = {
      visibleToWorkflow: false,
      summary: "No longer current",
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(response, 201));
    useCreateAdminMemoryRevision();
    const revisionOptions = lastMutationOptions<
      MemoryAdminEntryRead,
      { memoryId: string; payload: MemoryAdminRevisionCreateRequest }
    >();
    await revisionOptions.mutationFn({
      memoryId: "mem-admin-1",
      payload: revisionPayload,
    });
    let lastCall = getLastFetchCall(fetchMock);
    expect(lastCall.url.pathname).toBe(
      "/api/memory/admin/entries/mem-admin-1/revisions",
    );
    expect(lastCall.init?.method).toBe("POST");
    expect(lastCall.init?.body).toBe(JSON.stringify(revisionPayload));

    await revisionOptions.onSuccess?.(response, {
      memoryId: "mem-admin-1",
      payload: revisionPayload,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.admin.lists(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.admin.detail("mem-admin-1"),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.admin.detail(response.memoryId),
    });

    reactQueryState.invalidateQueriesMock.mockClear();
    const hiddenResponse = { ...response, visibleToWorkflow: false };
    fetchMock.mockResolvedValueOnce(jsonResponse(hiddenResponse));
    useUpdateAdminMemoryWorkflowVisibility();
    const visibilityOptions = lastMutationOptions<
      MemoryAdminEntryRead,
      { memoryId: string; payload: MemoryAdminWorkflowVisibilityUpdateRequest }
    >();
    await visibilityOptions.mutationFn({
      memoryId: "mem-admin-1",
      payload: visibilityPayload,
    });
    lastCall = getLastFetchCall(fetchMock);
    expect(lastCall.url.pathname).toBe(
      "/api/memory/admin/entries/mem-admin-1/workflow-visibility",
    );
    expect(lastCall.url.pathname).not.toContain("/status");
    expect(lastCall.init?.method).toBe("PATCH");
    expect(lastCall.init?.body).toBe(JSON.stringify(visibilityPayload));

    await visibilityOptions.onSuccess?.(hiddenResponse, {
      memoryId: "mem-admin-1",
      payload: visibilityPayload,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.admin.lists(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.admin.detail("mem-admin-1"),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.admin.detail(hiddenResponse.memoryId),
    });
  });

  it("deletes admin memory through DELETE /api/memory/admin/entries/{memoryId} and invalidates the deleted memory scopes", async () => {
    const { memoryApi, deleteAdminMemoryEntry: deleteAdminMemoryEntryApi } =
      await import("@/lib/api/memory");

    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));

    expect(memoryApi.admin.delete).toBe(deleteAdminMemoryEntryApi);

    await expect(deleteAdminMemoryEntryApi("mem-admin-1")).resolves.toBeUndefined();
    let lastCall = getLastFetchCall(fetchMock);
    expect(lastCall.url.pathname).toBe("/api/memory/admin/entries/mem-admin-1");
    expect(lastCall.init?.method).toBe("DELETE");
    expect(lastCall.init?.body).toBeUndefined();

    reactQueryState.invalidateQueriesMock.mockClear();
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    useDeleteAdminMemoryEntry();
    const deleteOptions = lastMutationOptions<void, string>();

    await expect(deleteOptions.mutationFn("mem-admin-2")).resolves.toBeUndefined();
    lastCall = getLastFetchCall(fetchMock);
    expect(lastCall.url.pathname).toBe("/api/memory/admin/entries/mem-admin-2");
    expect(lastCall.init?.method).toBe("DELETE");

    await deleteOptions.onSuccess?.(undefined, "mem-admin-2");
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.admin.lists(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.admin.detail("mem-admin-2"),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.admin.revisionsScope("mem-admin-2"),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.admin.eventsScope("mem-admin-2"),
    });
  });

  it("normalizes admin memory visibility keys for all, visible, and hidden lists", () => {
    expect(queryKeys.platform.memory.admin.list()).toEqual([
      "api",
      "platform",
      "memory",
      "admin",
      "entries",
      "list",
      { limit: 50, offset: 0, sort: "updatedAtDesc" },
    ]);
    expect(
      queryKeys.platform.memory.admin.list({ visibleToWorkflow: true }),
    ).toEqual([
      "api",
      "platform",
      "memory",
      "admin",
      "entries",
      "list",
      { limit: 50, offset: 0, sort: "updatedAtDesc", visibleToWorkflow: true },
    ]);
    expect(
      queryKeys.platform.memory.admin.list({ visibleToWorkflow: false }),
    ).toEqual([
      "api",
      "platform",
      "memory",
      "admin",
      "entries",
      "list",
      { limit: 50, offset: 0, sort: "updatedAtDesc", visibleToWorkflow: false },
    ]);
  });
});
