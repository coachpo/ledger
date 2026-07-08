import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TextTemplateRead, TextTemplateWriteInput } from "./types/text-template";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000/api/v1";
const ORIGINAL_API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const ORIGINAL_FETCH = globalThis.fetch;

function createFetchMock() {
  return vi.fn<
    (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
  >();
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function textResponse(body: string, status: number): Response {
  return new Response(body, {
    status,
    headers: { "content-type": "text/plain" },
  });
}

async function loadApiModule(baseUrl: string = "") {
  vi.resetModules();
  Reflect.set(import.meta.env, "VITE_API_BASE_URL", baseUrl);
  const [
    apiClient,
    extensionsApi,
    modelConnectionsApi,
    templatesApi,
  ] = await Promise.all([
    import("./api-client"),
    import("./api/extensions"),
    import("./api/model-connections"),
    import("./api/templates"),
  ]);

  return {
    ...apiClient,
    ...extensionsApi,
    ...modelConnectionsApi,
    ...templatesApi,
  };
}

function getLastFetchCall(fetchMock: ReturnType<typeof createFetchMock>): {
  init: RequestInit | undefined;
  url: string;
} {
  const call = fetchMock.mock.calls.at(-1);

  if (!call) {
    throw new Error("Expected fetch to be called");
  }

  const [input, init] = call;
  return { init, url: String(input) };
}

const templateFixture: TextTemplateRead = {
  id: 1,
  name: "Daily summary",
  content: "Market summary",
  createdAt: "2024-03-15T12:00:00Z",
  updatedAt: "2024-03-15T12:00:00Z",
};

const templateInput: TextTemplateWriteInput = {
  name: "Daily summary",
  content: "Market summary",
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

describe("api client", () => {
  it("sends a successful GET request for listTemplates", async () => {
    const { listTemplates } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(jsonResponse([templateFixture], 200));

    await expect(listTemplates()).resolves.toEqual([templateFixture]);

    const { init, url } = getLastFetchCall(fetchMock);
    expect(url).toBe(`${DEFAULT_API_BASE_URL}/templates`);
    expect(init?.method).toBe("GET");
    expect(init?.body).toBeUndefined();
    expect(new Headers(init?.headers).get("Accept")).toBe("application/json");
  });

  it("sends a successful POST request for createTemplate", async () => {
    const { createTemplate } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(jsonResponse(templateFixture, 201));

    await expect(createTemplate(templateInput)).resolves.toEqual(
      templateFixture,
    );

    const { init, url } = getLastFetchCall(fetchMock);
    expect(url).toBe(`${DEFAULT_API_BASE_URL}/templates`);
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify(templateInput));
    expect(new Headers(init?.headers).get("Accept")).toBe("application/json");
    expect(new Headers(init?.headers).get("Content-Type")).toBe(
      "application/json",
    );
  });

  it("preserves status, code, message, and validation details for 422 responses", async () => {
    const { ApiRequestError, createTemplate } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          code: "validation_error",
          message: "Validation failed",
          details: [
            { field: "name", issue: "Required" },
            { field: "content", issue: "Required" },
            {
              code: "extension_disabled",
              extensionKey: "signaldeck.finance",
              surface: "tool.marketQuote",
              retryAfterSeconds: 30,
              enabled: false,
              optional: null,
            },
            {
              field: "credentials",
              issue: "Invalid credentials",
              apiKey: "sk-secret",
              exceptionType: "RuntimeError",
              debugPayload: { path: "/home/qing/private.py" },
              rawList: ["internal"],
              "bad-key": "not exposed",
            },
            "not an object",
          ],
        },
        422,
      ),
    );

    let error: unknown;
    try {
      await createTemplate(templateInput);
    } catch (caught) {
      error = caught;
    }

    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error).toMatchObject({
      status: 422,
      code: "validation_error",
      message: "Validation failed",
      details: [
        { field: "name", issue: "Required" },
        { field: "content", issue: "Required" },
        {
          code: "extension_disabled",
          extensionKey: "signaldeck.finance",
          surface: "tool.marketQuote",
          retryAfterSeconds: 30,
          enabled: false,
          optional: null,
        },
        { field: "credentials", issue: "Invalid credentials" },
      ],
    });
  });

  it("drops malformed non-array details from JSON error envelopes", async () => {
    const { ApiRequestError, listTemplates } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          code: "validation_error",
          message: "Validation failed",
          details: { field: "name", issue: "Required" },
        },
        422,
      ),
    );

    let error: unknown;
    try {
      await listTemplates();
    } catch (caught) {
      error = caught;
    }

    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error).toMatchObject({
      status: 422,
      code: "validation_error",
      message: "Validation failed",
      details: [],
    });
  });

  it("falls back to a generic request_failed error for 500 text responses", async () => {
    const { ApiRequestError, listTemplates } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(textResponse("Internal Server Error", 500));

    let error: unknown;
    try {
      await listTemplates();
    } catch (caught) {
      error = caught;
    }

    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error).toMatchObject({
      status: 500,
      code: "request_failed",
      message: "Internal Server Error",
      details: [],
    });
  });

  it("derives v1 and platform URLs from a configured versioned base", async () => {
    const { buildApiUrl, buildPlatformApiUrl } = await loadApiModule(
      "https://signaldeck.example.com/api/v2/",
    );

    expect(buildApiUrl("/templates")).toBe(
      "https://signaldeck.example.com/api/v1/templates",
    );
    expect(buildPlatformApiUrl("/workflow-packages")).toBe(
      "https://signaldeck.example.com/api/workflow-packages",
    );
  });

  it("routes platform modules through the unversioned api base", async () => {
    const { listModelConnections } = await loadApiModule(
      "https://signaldeck.example.com/api/v1/",
    );
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [] }, 200));

    await expect(listModelConnections()).resolves.toEqual({ items: [] });

    const { url } = getLastFetchCall(fetchMock);
    expect(url).toBe("https://signaldeck.example.com/api/model-connections");
  });

  it("lists and toggles extensions through the unversioned api base", async () => {
    const { listExtensions, toggleExtension } = await loadApiModule(
      "https://signaldeck.example.com/api/v1/",
    );
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [] }, 200));

    await expect(listExtensions()).resolves.toEqual({ items: [] });
    expect(getLastFetchCall(fetchMock).url).toBe(
      "https://signaldeck.example.com/api/extensions",
    );

    fetchMock.mockResolvedValueOnce(
      jsonResponse({ key: "signaldeck.finance", enabled: false }, 200),
    );
    await expect(
      toggleExtension("signaldeck.finance", { enabled: false }),
    ).resolves.toMatchObject({ enabled: false, key: "signaldeck.finance" });

    const { init, url } = getLastFetchCall(fetchMock);
    expect(url).toBe(
      "https://signaldeck.example.com/api/extensions/signaldeck.finance",
    );
    expect(init?.method).toBe("PATCH");
    expect(init?.body).toBe(JSON.stringify({ enabled: false }));
  });

  it("encodes v1 path segments against the derived base URL", async () => {
    const { getTemplate } = await loadApiModule(
      "https://signaldeck.example.com/api/",
    );
    fetchMock.mockResolvedValueOnce(
      jsonResponse(templateFixture, 200),
    );

    await expect(getTemplate("template with/slash")).resolves.toEqual(
      templateFixture,
    );

    const { url } = getLastFetchCall(fetchMock);
    expect(url).toBe(
      "https://signaldeck.example.com/api/v1/templates/template%20with%2Fslash",
    );
  });
});
