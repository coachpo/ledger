import { describe, expect, it, vi } from "vitest";

const reactQueryState = vi.hoisted(() => ({
  useQueryMock: vi.fn((options: unknown) => options),
}));

const memoryApiState = vi.hoisted(() => ({
  listMemoryMock: vi.fn(),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: reactQueryState.useQueryMock,
}));

vi.mock("@/lib/api/memory", () => ({
  getMemoryDetail: vi.fn(),
  listMemory: memoryApiState.listMemoryMock,
  listMemoryEvents: vi.fn(),
  listMemoryRevisions: vi.fn(),
}));

import { queryKeys } from "@/lib/query-keys";
import type { MemoryApiListRead, MemoryApiListRequest } from "@/lib/types/memory";
import { useMemoryList } from "./use-memory";
type MemoryListQueryOptions = {
  enabled: boolean;
  queryFn: (context: { signal: AbortSignal }) => Promise<MemoryApiListRead>;
  queryKey: readonly unknown[];
};

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

function lastQueryOptions() {
  return reactQueryState.useQueryMock.mock.calls.at(-1)?.[0] as MemoryListQueryOptions;
}

describe("useMemoryList", () => {
  it("uses the canonical memory list query key and enabled option", async () => {
    reactQueryState.useQueryMock.mockClear();
    memoryApiState.listMemoryMock.mockClear();

    const payload = memoryPayload();
    const response = memoryListResponse(payload);
    memoryApiState.listMemoryMock.mockResolvedValue(response);

    useMemoryList(payload, { enabled: false });

    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.memory.list(payload),
      }),
    );

    const signal = new AbortController().signal;
    await expect(lastQueryOptions().queryFn({ signal })).resolves.toBe(response);
    expect(memoryApiState.listMemoryMock).toHaveBeenLastCalledWith(payload, signal);
  });
});
