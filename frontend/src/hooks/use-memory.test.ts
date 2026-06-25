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

import { memoryApi } from "@/lib/api/memory";
import { queryKeys } from "@/lib/query-keys";
import type {
  WorkflowMemoryAuditEventListRead,
  WorkflowMemoryProposalListRead,
  WorkflowMemoryQuarantineListRead,
  WorkflowMemoryReviewActionRead,
} from "@/lib/types/memory";
import {
  useApproveWorkflowMemoryProposal,
  useRejectWorkflowMemoryProposal,
  useWorkflowMemoryAuditEvents,
  useWorkflowMemoryProposals,
  useWorkflowMemoryQuarantine,
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

function proposalListResponse(): WorkflowMemoryProposalListRead {
  return {
    items: [],
    limit: 50,
    offset: 0,
    status: "review_pending",
    total: 0,
  };
}

function auditListResponse(): WorkflowMemoryAuditEventListRead {
  return { items: [], limit: 50, offset: 0, total: 0 };
}

function quarantineListResponse(): WorkflowMemoryQuarantineListRead {
  return { items: [], limit: 50, offset: 0, total: 0, unresolvedOnly: true };
}

function reviewActionResponse(): WorkflowMemoryReviewActionRead {
  return {
    activeMemoryId: "memory_active_1",
    decision: {
      createdAt: "2026-06-16T12:05:00Z",
      decidedBy: "review_api",
      decision: "commit",
      decisionId: "decision_1",
      policySnapshot: { mode: "review" },
      proposalId: "proposal_1",
      reason: "Looks valid",
      reasonCode: "operator_approved",
    },
    proposal: {
      agentKey: "analyst",
      content: { summary: "Memory candidate" },
      createdAt: "2026-06-16T12:00:00Z",
      detectors: {},
      invocationId: null,
      kind: "insight",
      namespace: "research",
      packageKey: "research_package",
      proposalId: "proposal_1",
      reason: "Needs human review",
      runId: 42,
      sourceOutputPath: null,
      status: "committed",
      stepId: "summarize",
      updatedAt: "2026-06-16T12:05:00Z",
      workflowKey: "daily",
    },
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

describe("workflow memory review hooks", () => {
  it("lists review proposals through GET /api/memory/proposals", async () => {
    const params = { limit: 20, offset: 5, status: "all" as const };
    const response = { ...proposalListResponse(), ...params, total: 2 };
    fetchMock.mockResolvedValueOnce(jsonResponse(response));

    useWorkflowMemoryProposals(params, { enabled: false });

    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.memory.proposals(params),
      }),
    );

    await expect(
      lastQueryOptions<WorkflowMemoryProposalListRead>().queryFn({
        signal: new AbortController().signal,
      }),
    ).resolves.toEqual(response);
    const { init, url } = getLastFetchCall(fetchMock);
    expect(url.pathname).toBe("/api/memory/proposals");
    expect(init?.method).toBe("GET");
    expect(Object.fromEntries(url.searchParams.entries())).toEqual({
      limit: "20",
      offset: "5",
      status: "all",
    });
  });

  it("lists audit events and quarantine records through review endpoints", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(auditListResponse()));
    useWorkflowMemoryAuditEvents({ limit: 10 });
    await lastQueryOptions<WorkflowMemoryAuditEventListRead>().queryFn({
      signal: new AbortController().signal,
    });
    let lastCall = getLastFetchCall(fetchMock);
    expect(lastCall.url.pathname).toBe("/api/memory/audit-events");
    expect(Object.fromEntries(lastCall.url.searchParams.entries())).toEqual({
      limit: "10",
      offset: "0",
    });

    fetchMock.mockResolvedValueOnce(jsonResponse(quarantineListResponse()));
    useWorkflowMemoryQuarantine({ unresolvedOnly: false });
    await lastQueryOptions<WorkflowMemoryQuarantineListRead>().queryFn({
      signal: new AbortController().signal,
    });
    lastCall = getLastFetchCall(fetchMock);
    expect(lastCall.url.pathname).toBe("/api/memory/quarantine");
    expect(Object.fromEntries(lastCall.url.searchParams.entries())).toEqual({
      limit: "50",
      offset: "0",
      unresolvedOnly: "false",
    });
  });

  it("approves and rejects proposals with review invalidation", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(reviewActionResponse()));
    useApproveWorkflowMemoryProposal();
    const approveOptions = lastMutationOptions<
      WorkflowMemoryReviewActionRead,
      { proposalId: string; payload?: { reason?: string | null } }
    >();
    await approveOptions.mutationFn({
      proposalId: "proposal_1",
      payload: { reason: "Looks valid" },
    });
    let lastCall = getLastFetchCall(fetchMock);
    expect(lastCall.url.pathname).toBe(
      "/api/memory/proposals/proposal_1/actions/approve",
    );
    expect(lastCall.init?.method).toBe("POST");
    expect(lastCall.init?.body).toBe(JSON.stringify({ reason: "Looks valid" }));
    await approveOptions.onSuccess?.(reviewActionResponse(), {
      proposalId: "proposal_1",
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.proposalsScope(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.auditEventsScope(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.memory.quarantineScope(),
    });

    fetchMock.mockResolvedValueOnce(jsonResponse(reviewActionResponse()));
    useRejectWorkflowMemoryProposal();
    const rejectOptions = lastMutationOptions<
      WorkflowMemoryReviewActionRead,
      { proposalId: string; payload?: { reason?: string | null } }
    >();
    await rejectOptions.mutationFn({ proposalId: "proposal_2" });
    lastCall = getLastFetchCall(fetchMock);
    expect(lastCall.url.pathname).toBe(
      "/api/memory/proposals/proposal_2/actions/reject",
    );
    expect(lastCall.init?.body).toBe(JSON.stringify({}));
  });

  it("exports only the review memory API helpers", () => {
    expect(Object.keys(memoryApi).sort()).toEqual([
      "approveProposal",
      "auditEvents",
      "proposals",
      "quarantine",
      "rejectProposal",
    ]);
  });
});
