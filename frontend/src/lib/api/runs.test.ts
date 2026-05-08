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
    const { listRuns } = await loadRunsApi("https://ledger.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [] }, 200));

    await expect(
      listRuns({
        limit: 25,
        offset: 0,
        status: "running",
        targetId: 17,
        targetKey: " market_review ",
        targetKind: "workflow",
        targetVersion: 3,
      }),
    ).resolves.toEqual({ items: [] });

    const { init, url } = getLastFetchCall(fetchMock);

    expect(`${url.origin}${url.pathname}`).toBe("https://ledger.example.com/api/runs");
    expect(init?.method).toBe("GET");
    expect(Object.fromEntries(url.searchParams.entries())).toEqual({
      limit: "25",
      offset: "0",
      status: "running",
      targetId: "17",
      targetKey: "market_review",
      targetKind: "workflow",
      targetVersion: "3",
    });
  });

  it("uses the camelCase workflowPackage run target kind for package run filters", async () => {
    const { listRuns } = await loadRunsApi("https://ledger.example.com/api/v1/");
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
    const { getRunRerunDraft } = await loadRunsApi("https://ledger.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ sourceRunId: 42, parameters: { ticker: "MSFT" } }, 200));

    await expect(getRunRerunDraft(42)).resolves.toEqual({
      parameters: { ticker: "MSFT" },
      sourceRunId: 42,
    });

    const { init, url } = getLastFetchCall(fetchMock);

    expect(`${url.origin}${url.pathname}`).toBe("https://ledger.example.com/api/runs/42/rerun-draft");
    expect(init?.method).toBe("GET");
  });

  it("creates reruns with parameter payloads", async () => {
    const { createRunRerun } = await loadRunsApi("https://ledger.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 99, status: "queued" }, 201));

    await expect(createRunRerun(42, { parameters: { ticker: "MSFT" } })).resolves.toEqual({
      id: 99,
      status: "queued",
    });

    const { init, url } = getLastFetchCall(fetchMock);

    expect(`${url.origin}${url.pathname}`).toBe("https://ledger.example.com/api/runs/42/reruns");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ parameters: { ticker: "MSFT" } }));
  });

  it("reads step replay drafts with the step index query parameter", async () => {
    const { getRunStepReplayDraft } = await loadRunsApi("https://ledger.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ sourceRunId: 42, replayStepIndex: 2, parameters: { ticker: "MSFT" } }, 200));

    await expect(getRunStepReplayDraft(42, 2)).resolves.toEqual({
      parameters: { ticker: "MSFT" },
      replayStepIndex: 2,
      sourceRunId: 42,
    });

    const { init, url } = getLastFetchCall(fetchMock);

    expect(`${url.origin}${url.pathname}`).toBe("https://ledger.example.com/api/runs/42/step-replay-draft");
    expect(init?.method).toBe("GET");
    expect(Object.fromEntries(url.searchParams.entries())).toEqual({ stepIndex: "2" });
  });

  it("creates step replays with replay step and parameters", async () => {
    const { createRunStepReplay } = await loadRunsApi("https://ledger.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 100, status: "queued" }, 201));

    await expect(createRunStepReplay(42, { replayStepIndex: 2, parameters: { ticker: "MSFT" } })).resolves.toEqual({
      id: 100,
      status: "queued",
    });

    const { init, url } = getLastFetchCall(fetchMock);

    expect(`${url.origin}${url.pathname}`).toBe("https://ledger.example.com/api/runs/42/step-replays");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ replayStepIndex: 2, parameters: { ticker: "MSFT" } }));
  });
});
