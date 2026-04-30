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

async function loadCapabilitiesApi(baseUrl: string = "") {
  vi.resetModules();
  Reflect.set(import.meta.env, "VITE_API_BASE_URL", baseUrl);
  return import("./capabilities");
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

describe("capabilities api", () => {
  it("uses canonical capability endpoints and toolGrants payloads", async () => {
    const { createCapability, updateCapability } = await loadCapabilitiesApi("https://ledger.example.com/api/v1/");
    const payload = {
      key: "summarize_capability",
      name: "Summarize Capability",
      toolGrants: [{ tool: "ledger.reports.lookup" }],
    };
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 3, ...payload }, 201));
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 3, ...payload }, 200));

    await createCapability(payload);

    let lastCall = getLastFetchCall(fetchMock);
    expect(`${lastCall.url.origin}${lastCall.url.pathname}`).toBe("https://ledger.example.com/api/capabilities");
    expect(lastCall.init?.method).toBe("POST");
    expect(lastCall.init?.body).toBe(JSON.stringify(payload));

    await updateCapability(3, { name: "Updated", toolGrants: payload.toolGrants });

    lastCall = getLastFetchCall(fetchMock);
    expect(`${lastCall.url.origin}${lastCall.url.pathname}`).toBe("https://ledger.example.com/api/capabilities/3");
    expect(lastCall.init?.method).toBe("PATCH");
    expect(lastCall.init?.body).toBe(JSON.stringify({ name: "Updated", toolGrants: payload.toolGrants }));
  });
});
