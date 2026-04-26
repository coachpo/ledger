import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
});
