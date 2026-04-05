import type { GetMarketQuotesParams, MarketQuoteListRead, GetMarketHistoryParams, MarketHistoryRead } from "../types/market-data";
import { type IdParam, portfolioPath, request, serializeSymbols } from "../api-client";

export function getMarketQuotes(
  portfolioId: IdParam,
  params: GetMarketQuotesParams,
  signal?: AbortSignal,
): Promise<MarketQuoteListRead> {
  return request<MarketQuoteListRead>(`${portfolioPath(portfolioId)}/market-data/quotes`, {
    query: { symbols: serializeSymbols(params.symbols) },
    signal,
  });
}

export function getMarketHistory(
  portfolioId: IdParam,
  params: GetMarketHistoryParams,
  signal?: AbortSignal,
): Promise<MarketHistoryRead> {
  return request<MarketHistoryRead>(`${portfolioPath(portfolioId)}/market-data/history`, {
    query: {
      range: params.range ?? "3mo",
      symbols: serializeSymbols(params.symbols),
    },
    signal,
  });
}

export const marketDataApi = {
  history: getMarketHistory,
  quotes: getMarketQuotes,
} as const;
