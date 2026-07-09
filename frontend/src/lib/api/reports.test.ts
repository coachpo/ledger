import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ORIGINAL_API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const ORIGINAL_FETCH = globalThis.fetch;
const ORIGINAL_CREATE_OBJECT_URL = URL.createObjectURL;
const ORIGINAL_REVOKE_OBJECT_URL = URL.revokeObjectURL;

function createFetchMock() {
  return vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>();
}

function textResponse(body: string, status: number): Response {
  return new Response(body, {
    status,
    headers: {
      "content-disposition": 'attachment; filename="agent_memory_snapshot.md"',
      "content-type": "text/markdown",
    },
  });
}

async function loadReportsApi(baseUrl: string = "") {
  vi.resetModules();
  Reflect.set(import.meta.env, "VITE_API_BASE_URL", baseUrl);
  return import("./reports");
}

let fetchMock = createFetchMock();
let createObjectUrlMock = vi.fn();
let revokeObjectUrlMock = vi.fn();

beforeEach(() => {
  fetchMock = createFetchMock();
  createObjectUrlMock = vi.fn(() => "blob:report-download");
  revokeObjectUrlMock = vi.fn();
  globalThis.fetch = fetchMock as typeof fetch;
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: createObjectUrlMock,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: revokeObjectUrlMock,
  });
  localStorage.clear();
  Reflect.set(import.meta.env, "VITE_API_BASE_URL", "");
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  localStorage.clear();
  globalThis.fetch = ORIGINAL_FETCH;
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: ORIGINAL_CREATE_OBJECT_URL,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: ORIGINAL_REVOKE_OBJECT_URL,
  });
  Reflect.set(import.meta.env, "VITE_API_BASE_URL", ORIGINAL_API_BASE_URL);
});

describe("reports api", () => {
  it("downloads reports through authenticated blob requests and retries after a 401 prompt", async () => {
    const { downloadReport } = await loadReportsApi("https://signaldeck.example.com/api/v1/");
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const promptSpy = vi.spyOn(window, "prompt").mockReturnValue("fresh-token");
    vi.useFakeTimers();
    localStorage.setItem("signaldeck.apiToken", "stale-token");
    fetchMock
      .mockResolvedValueOnce(textResponse("Unauthorized", 401))
      .mockResolvedValueOnce(textResponse("# Memory Snapshot", 200));

    await expect(downloadReport("agent_memory_snapshot")).resolves.toBeUndefined();

    expect(promptSpy).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get("Authorization")).toBe(
      "Bearer stale-token",
    );
    expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get("Authorization")).toBe(
      "Bearer fresh-token",
    );
    expect(createObjectUrlMock).toHaveBeenCalledTimes(1);
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(revokeObjectUrlMock).not.toHaveBeenCalled();
    await vi.runAllTimersAsync();
    expect(revokeObjectUrlMock).toHaveBeenCalledWith("blob:report-download");
  });
});
