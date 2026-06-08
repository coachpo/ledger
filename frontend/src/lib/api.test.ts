import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PortfolioRead, PortfolioWriteInput } from "./types/portfolio";

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
    marketDataApi,
    modelConnectionsApi,
    portfoliosApi,
    positionsApi,
  ] = await Promise.all([
    import("./api-client"),
    import("./api/extensions"),
    import("./api/market-data"),
    import("./api/model-connections"),
    import("./api/portfolios"),
    import("./api/positions"),
  ]);

  return {
    ...apiClient,
    ...extensionsApi,
    ...marketDataApi,
    ...modelConnectionsApi,
    ...portfoliosApi,
    ...positionsApi,
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

const portfolioFixture: PortfolioRead = {
  id: 1,
  name: "Retirement",
  slug: "retirement",
  description: "Long-term holdings",
  baseCurrency: "USD",
  positionCount: 3,
  balanceCount: 2,
  createdAt: "2024-03-15T12:00:00Z",
  updatedAt: "2024-03-15T12:00:00Z",
};

const portfolioInput: PortfolioWriteInput = {
  name: "Retirement",
  slug: "retirement",
  description: "Long-term holdings",
  baseCurrency: "USD",
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
  it("sends a successful GET request for listPortfolios", async () => {
    const { listPortfolios } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(jsonResponse([portfolioFixture], 200));

    await expect(listPortfolios()).resolves.toEqual([portfolioFixture]);

    const { init, url } = getLastFetchCall(fetchMock);
    expect(url).toBe(`${DEFAULT_API_BASE_URL}/portfolios`);
    expect(init?.method).toBe("GET");
    expect(init?.body).toBeUndefined();
    expect(new Headers(init?.headers).get("Accept")).toBe("application/json");
  });

  it("sends a successful POST request for createPortfolio", async () => {
    const { createPortfolio } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(jsonResponse(portfolioFixture, 201));

    await expect(createPortfolio(portfolioInput)).resolves.toEqual(
      portfolioFixture,
    );

    const { init, url } = getLastFetchCall(fetchMock);
    expect(url).toBe(`${DEFAULT_API_BASE_URL}/portfolios`);
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify(portfolioInput));
    expect(new Headers(init?.headers).get("Accept")).toBe("application/json");
    expect(new Headers(init?.headers).get("Content-Type")).toBe(
      "application/json",
    );
  });

  it("does not read stale JSON detail aliases for 404 responses", async () => {
    const { ApiRequestError, getPortfolio } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: "Portfolio not found" }, 404),
    );

    let error: unknown;
    try {
      await getPortfolio(999);
    } catch (caught) {
      error = caught;
    }

    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error).toMatchObject({
      status: 404,
      code: "request_failed",
      message: "Request failed with status 404",
      details: [],
    });
  });

  it("preserves status, code, message, and validation details for 422 responses", async () => {
    const { ApiRequestError, createPortfolio } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          code: "validation_error",
          message: "Validation failed",
          details: [
            { field: "name", issue: "Required" },
            { field: "baseCurrency", issue: "Unsupported currency" },
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
      await createPortfolio(portfolioInput);
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
        { field: "baseCurrency", issue: "Unsupported currency" },
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
    const { ApiRequestError, listPortfolios } = await loadApiModule();
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
      await listPortfolios();
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
    const { ApiRequestError, listPortfolios } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(textResponse("Internal Server Error", 500));

    let error: unknown;
    try {
      await listPortfolios();
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

    expect(buildApiUrl("/portfolios")).toBe(
      "https://signaldeck.example.com/api/v1/portfolios",
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

  it("encodes symbol lookup requests against the derived v1 base URL", async () => {
    const { getPositionSymbolLookup } = await loadApiModule(
      "https://signaldeck.example.com/api/",
    );
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ symbol: "BRK/B", name: "Berkshire Hathaway Inc." }, 200),
    );

    await expect(
      getPositionSymbolLookup("portfolio with/slash", "BRK/B"),
    ).resolves.toEqual({ symbol: "BRK/B", name: "Berkshire Hathaway Inc." });

    const { url } = getLastFetchCall(fetchMock);
    expect(url).toBe(
      "https://signaldeck.example.com/api/v1/portfolios/portfolio%20with%2Fslash/positions/lookup?symbol=BRK%2FB",
    );
  });
});
