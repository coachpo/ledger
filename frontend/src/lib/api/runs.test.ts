import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RunTargetKind } from "../types/run";

const ORIGINAL_API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const ORIGINAL_FETCH = globalThis.fetch;

function createFetchMock() {
  return vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>();
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function getLastFetchCall(fetchMock: ReturnType<typeof createFetchMock>): {
  init: RequestInit | undefined;
  url: URL;
} {
  const call = fetchMock.mock.calls.at(-1);

  if (!call) {
    throw new Error("Expected fetch to be called");
  }

  const [input, init] = call;
  return { init, url: new URL(String(input)) };
}

async function loadRunsApi(baseUrl: string = "") {
  vi.resetModules();
  Reflect.set(import.meta.env, "VITE_API_BASE_URL", baseUrl);
  return import("./runs");
}

let fetchMock = createFetchMock();

beforeEach(() => {
  fetchMock = createFetchMock();
  globalThis.fetch = fetchMock as typeof fetch;
  Reflect.set(import.meta.env, "VITE_API_BASE_URL", "");
});

afterEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = ORIGINAL_FETCH;
  Reflect.set(import.meta.env, "VITE_API_BASE_URL", ORIGINAL_API_BASE_URL);
});

describe("runs api", () => {
  it("sends package-only list filters to the platform runs endpoint", async () => {
    const { listRuns } = await loadRunsApi("https://signaldeck.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [] }, 200));

    await expect(
      listRuns({
        limit: 25,
        offset: 0,
        status: "running",
        workflowPackageId: 17,
        workflowPackageKey: " market_review_package ",
        workflowKey: " market_review ",
      }),
    ).resolves.toEqual({ items: [] });

    const { init, url } = getLastFetchCall(fetchMock);

    expect(`${url.origin}${url.pathname}`).toBe("https://signaldeck.example.com/api/runs");
    expect(init?.method).toBe("GET");
    expect(Object.fromEntries(url.searchParams.entries())).toEqual({
      limit: "25",
      offset: "0",
      status: "running",
      workflowPackageId: "17",
      workflowPackageKey: "market_review_package",
      workflowKey: "market_review",
    });
  });

  it("uses package-only run filters", async () => {
    const { listRuns } = await loadRunsApi("https://signaldeck.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [] }, 200));

    await expect(
      listRuns({
        workflowKey: " summarize ",
        workflowPackageKey: " research_package ",
      }),
    ).resolves.toEqual({ items: [] });

    const { url } = getLastFetchCall(fetchMock);

    expect(Object.fromEntries(url.searchParams.entries())).toEqual({
      offset: "0",
      workflowKey: "summarize",
      workflowPackageKey: "research_package",
    });
  });

  it("reads rerun drafts from the rerun draft endpoint", async () => {
    const { getRunRerunDraft } = await loadRunsApi("https://signaldeck.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ sourceRunId: 42, parameters: { ticker: "MSFT" } }, 200));

    await expect(getRunRerunDraft(42)).resolves.toEqual({
      parameters: { ticker: "MSFT" },
      sourceRunId: 42,
    });

    const { init, url } = getLastFetchCall(fetchMock);

    expect(`${url.origin}${url.pathname}`).toBe("https://signaldeck.example.com/api/runs/42/rerun-draft");
    expect(init?.method).toBe("GET");
  });

  it("creates reruns with parameter payloads", async () => {
    const { createRunRerun } = await loadRunsApi("https://signaldeck.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 99, status: "queued" }, 201));

    await expect(createRunRerun(42, { parameters: { ticker: "MSFT" } })).resolves.toEqual({
      id: 99,
      status: "queued",
    });

    const { init, url } = getLastFetchCall(fetchMock);

    expect(`${url.origin}${url.pathname}`).toBe("https://signaldeck.example.com/api/runs/42/reruns");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ parameters: { ticker: "MSFT" } }));
  });

  it("cancels runs through the platform cancel endpoint", async () => {
    const { cancelRun } = await loadRunsApi("https://signaldeck.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 42, status: "cancelled" }, 200));

    await expect(cancelRun(42)).resolves.toEqual({
      id: 42,
      status: "cancelled",
    });

    const { init, url } = getLastFetchCall(fetchMock);

    expect(`${url.origin}${url.pathname}`).toBe("https://signaldeck.example.com/api/runs/42/cancel");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBeUndefined();
  });

  it("reads run details from the run endpoint", async () => {
    const { getRun } = await loadRunsApi("https://signaldeck.example.com/api/v1/");
    const runDetail = {
      createdAt: "2026-05-15T10:00:00Z",
      error: null,
      executedTokens: 7,
      finalOutput: { summary: "run output" },
      finishedAt: "2026-05-15T10:02:00Z",
      id: 42,
      inheritedTokens: 0,
      input: { ticker: "TSLA" },
      extensionDependencies: [],
      packageProvenance: null,
      queuedAt: "2026-05-15T10:00:00Z",
      sourceRunId: 11,
      startedAt: "2026-05-15T10:01:00Z",
      status: "succeeded",
      steps: [
        {
          id: 201,
          index: 1,
          invocations: [{ id: 301, resolvedInputOrigin: "passthrough" }],
          operationInvocations: [],
          origin: "planned",
          runId: 42,
          status: "succeeded",
        },
      ],
      targetId: 12,
      targetKey: "runtime_package",
      targetKind: "workflowPackage" as RunTargetKind,
      totalTokens: 12,
      traceId: "trace-run-detail",
      updatedAt: "2026-05-15T10:00:00Z",
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(runDetail, 200));

    await expect(getRun(42)).resolves.toEqual(runDetail);

    const { init, url } = getLastFetchCall(fetchMock);

    expect(`${url.origin}${url.pathname}`).toBe("https://signaldeck.example.com/api/runs/42");
    expect(init?.method).toBe("GET");
  });
});
