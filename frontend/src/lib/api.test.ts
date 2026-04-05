import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PortfolioRead, PortfolioWriteInput } from "./types/portfolio";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000/api/v1";
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

function textResponse(body: string, status: number): Response {
  return new Response(body, {
    status,
    headers: { "content-type": "text/plain" },
  });
}

async function loadApiModule(baseUrl: string = "") {
  vi.resetModules();
  Reflect.set(import.meta.env, "VITE_API_BASE_URL", baseUrl);
  const [apiClient, backtestsApi, marketDataApi, portfoliosApi, positionsApi] = await Promise.all([
    import("./api-client"),
    import("./api/backtests"),
    import("./api/market-data"),
    import("./api/portfolios"),
    import("./api/positions"),
  ]);

  return {
    ...apiClient,
    ...backtestsApi,
    ...marketDataApi,
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

    await expect(createPortfolio(portfolioInput)).resolves.toEqual(portfolioFixture);

    const { init, url } = getLastFetchCall(fetchMock);
    expect(url).toBe(`${DEFAULT_API_BASE_URL}/portfolios`);
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify(portfolioInput));
    expect(new Headers(init?.headers).get("Accept")).toBe("application/json");
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
  });

  it("maps JSON detail strings into ApiRequestError messages for 404 responses", async () => {
    const { ApiRequestError, getPortfolio } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "Portfolio not found" }, 404));

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
      message: "Portfolio not found",
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
            { issue: "Missing field" },
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
      ],
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

  it("encodes path segments and query parameters against a configured base URL", async () => {
    const { getMarketQuotes } = await loadApiModule("https://ledger.example.com/api/v2/");
    fetchMock.mockResolvedValueOnce(jsonResponse([], 200));

    await expect(
      getMarketQuotes("portfolio with/slash", {
        symbols: ["BRK/B", "AAPL"],
      }),
    ).resolves.toEqual([]);

    const { url } = getLastFetchCall(fetchMock);
    expect(url).toBe(
      "https://ledger.example.com/api/v2/portfolios/portfolio%20with%2Fslash/market-data/quotes?symbols=BRK%2FB%2CAAPL",
    );
  });

  it("encodes symbol lookup requests against the configured base URL", async () => {
    const { getPositionSymbolLookup } = await loadApiModule("https://ledger.example.com/api/v2/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ symbol: "BRK/B", name: "Berkshire Hathaway Inc." }, 200));

    await expect(
      getPositionSymbolLookup("portfolio with/slash", "BRK/B"),
    ).resolves.toEqual({ symbol: "BRK/B", name: "Berkshire Hathaway Inc." });

    const { url } = getLastFetchCall(fetchMock);
    expect(url).toBe(
      "https://ledger.example.com/api/v2/portfolios/portfolio%20with%2Fslash/positions/lookup?symbol=BRK%2FB",
    );
  });

  it("sends a successful GET request for listBacktests", async () => {
    const { listBacktests } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(
      jsonResponse([{ id: 1, name: "Daily Backtest", status: "RUNNING" }], 200),
    );

    await expect(listBacktests()).resolves.toHaveLength(1);

    const { init, url } = getLastFetchCall(fetchMock);
    expect(url).toBe(`${DEFAULT_API_BASE_URL}/backtests`);
    expect(init?.method).toBe("GET");
  });
});
