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
  it("sends target-aware list filters to the platform runs endpoint", async () => {
    const { listRuns } = await loadRunsApi("https://signaldeck.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [] }, 200));

    await expect(
      listRuns({
        limit: 25,
        offset: 0,
        status: "running",
        targetId: 17,
        targetKey: " market_review ",
        targetKind: "workflow",
      }),
    ).resolves.toEqual({ items: [] });

    const { init, url } = getLastFetchCall(fetchMock);

    expect(`${url.origin}${url.pathname}`).toBe("https://signaldeck.example.com/api/runs");
    expect(init?.method).toBe("GET");
    expect(Object.fromEntries(url.searchParams.entries())).toEqual({
      limit: "25",
      offset: "0",
      status: "running",
      targetId: "17",
      targetKey: "market_review",
      targetKind: "workflow",
    });
  });

  it("uses the camelCase workflowPackage run target kind for package run filters", async () => {
    const { listRuns } = await loadRunsApi("https://signaldeck.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [] }, 200));
    const targetKind: RunTargetKind = "workflowPackage";

    await expect(
      listRuns({
        targetKind,
        workflowKey: " summarize ",
        workflowPackageKey: " research_package ",
      }),
    ).resolves.toEqual({ items: [] });

    const { url } = getLastFetchCall(fetchMock);

    expect(Object.fromEntries(url.searchParams.entries())).toEqual({
      offset: "0",
      targetKind: "workflowPackage",
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

  it("preserves legacy replay lineage fields on run detail reads", async () => {
    const { getRun } = await loadRunsApi("https://signaldeck.example.com/api/v1/");
    const legacyReplayLineage = {
      createdAt: "2026-05-15T10:00:00Z",
      error: null,
      executedTokens: 7,
      finalOutput: { summary: "legacy replay output" },
      finishedAt: "2026-05-15T10:02:00Z",
      id: 42,
      inheritedTokens: 5,
      input: { ticker: "TSLA" },
      lineageRootRunId: 11,
      memoryArtifacts: [],
      memoryEvents: [],
      extensionDependencies: [],
      packageProvenance: null,
      queuedAt: "2026-05-15T10:00:00Z",
      replayStepIndex: 2,
      resumeStepIndex: 2,
      sourceRunId: 11,
      startedAt: "2026-05-15T10:01:00Z",
      status: "succeeded",
      steps: [
        {
          id: 201,
          index: 1,
          invocations: [{ id: 301, resolvedInputOrigin: "copied", sourceInvocationId: 77 }],
          operationInvocations: [],
          origin: "copied",
          runId: 42,
          sourceRunId: 11,
          sourceRunStepId: 101,
          sourceStepIndex: 1,
          status: "succeeded",
        },
      ],
      targetId: 12,
      targetKey: "runtime_package",
      targetKind: "workflowPackage" as RunTargetKind,
      totalTokens: 12,
      traceId: "trace-legacy-replay",
      updatedAt: "2026-05-15T10:00:00Z",
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(legacyReplayLineage, 200));

    await expect(getRun(42)).resolves.toEqual(legacyReplayLineage);

    const { init, url } = getLastFetchCall(fetchMock);

    expect(`${url.origin}${url.pathname}`).toBe("https://signaldeck.example.com/api/runs/42");
    expect(init?.method).toBe("GET");
    expect(legacyReplayLineage.replayStepIndex).toBe(2);
    expect(legacyReplayLineage.resumeStepIndex).toBe(2);
    expect(legacyReplayLineage.steps[0].invocations[0].sourceInvocationId).toBe(77);
  });

  it("reads fork drafts with the source invocation query parameter", async () => {
    const { getRunForkDraft } = await loadRunsApi("https://signaldeck.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          sourceRunId: 42,
          sourceInvocationId: 77,
          targetKind: "workflowPackage",
          targetId: 12,
          targetKey: "runtime_package",
          invocationInput: { ticker: "MSFT" },
          packageProvenance: null,
        },
        200,
      ),
    );

    await expect(getRunForkDraft(42, 77)).resolves.toEqual({
      invocationInput: { ticker: "MSFT" },
      packageProvenance: null,
      sourceInvocationId: 77,
      sourceRunId: 42,
      targetId: 12,
      targetKey: "runtime_package",
      targetKind: "workflowPackage",
    });

    const { init, url } = getLastFetchCall(fetchMock);

    expect(`${url.origin}${url.pathname}`).toBe("https://signaldeck.example.com/api/runs/42/fork-draft");
    expect(init?.method).toBe("GET");
    expect(Object.fromEntries(url.searchParams.entries())).toEqual({ sourceInvocationId: "77" });
  });

  it("creates forks with source invocation input payloads", async () => {
    const { createRunFork } = await loadRunsApi("https://signaldeck.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 100, status: "queued" }, 201));

    await expect(
      createRunFork(42, {
        sourceInvocationId: 77,
        invocationInput: { ticker: "TSLA" },
      }),
    ).resolves.toEqual({
      id: 100,
      status: "queued",
    });

    const { init, url } = getLastFetchCall(fetchMock);

    expect(`${url.origin}${url.pathname}`).toBe("https://signaldeck.example.com/api/runs/42/forks");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(
      JSON.stringify({
        sourceInvocationId: 77,
        invocationInput: { ticker: "TSLA" },
      }),
    );
  });
});
