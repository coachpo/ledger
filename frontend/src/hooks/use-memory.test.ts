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
  MemoryAdminStatusUpdateRequest,
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
  useMemoryList,
  useUpdateAdminMemoryStatus,
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
    status: "approved",
    subjectRefs: [],
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
      status: "archived" as const,
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
      status: "archived",
      workflowKey: "daily_research",
    });
    expect(url.searchParams.has("accessContext")).toBe(false);
    expect(url.searchParams.has("visibility")).toBe(false);
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

  it("revises admin memory and updates admin status through separate mutation endpoints", async () => {
    const response = adminEntry({ revisionId: "rev-admin-2" });
    const revisionPayload: MemoryAdminRevisionCreateRequest = {
      content: "Updated admin memory content",
      provenance: response.provenance,
      summary: "Updated admin memory",
    };
    const statusPayload: MemoryAdminStatusUpdateRequest = {
      status: "archived",
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
    const archivedResponse = { ...response, status: "archived" as const };
    fetchMock.mockResolvedValueOnce(jsonResponse(archivedResponse));
    useUpdateAdminMemoryStatus();
    const statusOptions = lastMutationOptions<
      MemoryAdminEntryRead,
      { memoryId: string; payload: MemoryAdminStatusUpdateRequest }
    >();
    await statusOptions.mutationFn({
      memoryId: "mem-admin-1",
      payload: statusPayload,
    });
    lastCall = getLastFetchCall(fetchMock);
    expect(lastCall.url.pathname).toBe(
      "/api/memory/admin/entries/mem-admin-1/status",
    );
    expect(lastCall.init?.method).toBe("PATCH");
    expect(lastCall.init?.body).toBe(JSON.stringify(statusPayload));

    await statusOptions.onSuccess?.(archivedResponse, {
      memoryId: "mem-admin-1",
      payload: statusPayload,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.admin.lists(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.admin.detail("mem-admin-1"),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.admin.detail(archivedResponse.memoryId),
    });
  });
});
