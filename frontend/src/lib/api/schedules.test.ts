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

function getLastFetchCall(fetchMock: ReturnType<typeof createFetchMock>) {
  const call = fetchMock.mock.calls.at(-1);
  if (!call) {
    throw new Error("Expected fetch to be called");
  }
  const [input, init] = call;
  return { init, url: new URL(String(input)) };
}

async function loadSchedulesApi(baseUrl = "") {
  vi.resetModules();
  Reflect.set(import.meta.env, "VITE_API_BASE_URL", baseUrl);
  return import("./schedules");
}

const weeklyRecurrence = {
  type: "weekly" as const,
  daysOfWeek: ["mon" as const, "tue" as const],
  atLocalTime: "09:00",
};

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

describe("schedules api", () => {
  it("lists scheduled tasks from the unversioned platform endpoint", async () => {
    const { listScheduledTasks } = await loadSchedulesApi("https://signaldeck.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [], totalCount: 0, limit: 20, offset: 0 }, 200));

    await expect(
      listScheduledTasks({ packageKey: " research ", workflowKey: " daily ", status: "enabled" }),
    ).resolves.toEqual({ items: [], totalCount: 0, limit: 20, offset: 0 });

    const { init, url } = getLastFetchCall(fetchMock);
    expect(`${url.origin}${url.pathname}`).toBe("https://signaldeck.example.com/api/schedules");
    expect(Object.fromEntries(url.searchParams.entries())).toEqual({
      offset: "0",
      packageKey: "research",
      status: "enabled",
      workflowKey: "daily",
    });
    expect(init?.method).toBe("GET");
  });

  it("creates, updates, and deletes scheduled tasks", async () => {
    const { createScheduledTask, deleteScheduledTask, updateScheduledTask } = await loadSchedulesApi(
      "https://signaldeck.example.com/api/v1/",
    );
    const createPayload = {
      packageId: 12,
      workflowKey: "daily_research",
      name: "Daily market brief",
      timezone: "America/New_York",
      recurrence: weeklyRecurrence,
      inputTemplate: { asOfDate: "{{fire.scheduledLocalDate}}" },
      templateVars: { analysisTag: "daily" },
    };
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 44 }, 201));
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 44, status: "paused" }, 200));
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));

    await createScheduledTask(createPayload);
    let lastCall = getLastFetchCall(fetchMock);
    expect(`${lastCall.url.origin}${lastCall.url.pathname}`).toBe("https://signaldeck.example.com/api/schedules");
    expect(lastCall.init?.method).toBe("POST");
    expect(lastCall.init?.body).toBe(JSON.stringify(createPayload));

    await updateScheduledTask(44, { status: "paused", endsAt: null });
    lastCall = getLastFetchCall(fetchMock);
    expect(`${lastCall.url.origin}${lastCall.url.pathname}`).toBe("https://signaldeck.example.com/api/schedules/44");
    expect(lastCall.init?.method).toBe("PATCH");
    expect(lastCall.init?.body).toBe(JSON.stringify({ status: "paused", endsAt: null }));

    await expect(deleteScheduledTask(44)).resolves.toBeUndefined();
    lastCall = getLastFetchCall(fetchMock);
    expect(`${lastCall.url.origin}${lastCall.url.pathname}`).toBe("https://signaldeck.example.com/api/schedules/44");
    expect(lastCall.init?.method).toBe("DELETE");
  });

  it("previews unsaved and saved scheduled task inputs", async () => {
    const { previewScheduledTask, previewUnsavedScheduledTask } = await loadSchedulesApi(
      "https://signaldeck.example.com/api/v1/",
    );
    const previewRead = {
      scheduleId: null,
      scheduledFor: "2026-06-01T13:00:00Z",
      templateContext: { fire: { scheduledLocalDate: "2026-06-01" } },
      renderedParameters: { asOfDate: "2026-06-01" },
      validationErrors: [],
      ready: true,
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(previewRead, 200));
    fetchMock.mockResolvedValueOnce(jsonResponse({ ...previewRead, scheduleId: 44 }, 200));

    await previewUnsavedScheduledTask({
      packageId: 12,
      workflowKey: "daily_research",
      timezone: "America/New_York",
      recurrence: weeklyRecurrence,
      scheduledFor: "2026-06-01T13:00:00Z",
      inputTemplate: { asOfDate: "{{fire.scheduledLocalDate}}" },
      templateVars: { analysisTag: "daily" },
    });
    let lastCall = getLastFetchCall(fetchMock);
    expect(`${lastCall.url.origin}${lastCall.url.pathname}`).toBe("https://signaldeck.example.com/api/schedules/preview");
    expect(lastCall.init?.method).toBe("POST");

    await previewScheduledTask(44, { scheduledFor: "2026-06-01T13:00:00Z" });
    lastCall = getLastFetchCall(fetchMock);
    expect(`${lastCall.url.origin}${lastCall.url.pathname}`).toBe("https://signaldeck.example.com/api/schedules/44/preview");
    expect(lastCall.init?.method).toBe("POST");
    expect(lastCall.init?.body).toBe(JSON.stringify({ scheduledFor: "2026-06-01T13:00:00Z" }));
  });

  it("runs scheduled tasks now and reads fire history", async () => {
    const { listScheduledTaskFires, runScheduledTaskNow } = await loadSchedulesApi(
      "https://signaldeck.example.com/api/v1/",
    );
    fetchMock.mockResolvedValueOnce(jsonResponse({ scheduleId: 44, fire: { id: 801 }, run: { id: 2104 } }, 201));
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [], totalCount: 0, limit: 50, offset: 0 }, 200));

    await runScheduledTaskNow(44, {
      idempotencyKey: "manual-fire-2026-06-01T13:00:00Z",
      scheduledFor: "2026-06-01T13:00:00Z",
    });
    let lastCall = getLastFetchCall(fetchMock);
    expect(`${lastCall.url.origin}${lastCall.url.pathname}`).toBe("https://signaldeck.example.com/api/schedules/44/run-now");
    expect(lastCall.init?.method).toBe("POST");

    await listScheduledTaskFires(44, { limit: 10 });
    lastCall = getLastFetchCall(fetchMock);
    expect(`${lastCall.url.origin}${lastCall.url.pathname}`).toBe("https://signaldeck.example.com/api/schedules/44/fires");
    expect(Object.fromEntries(lastCall.url.searchParams.entries())).toEqual({ limit: "10", offset: "0" });
    expect(lastCall.init?.method).toBe("GET");
  });
});
