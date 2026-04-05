import { useQuery } from "@tanstack/react-query";
import { getMarketHistory, getMarketQuotes } from "@/lib/api/market-data";
import { queryKeys } from "@/lib/query-keys";
import type { GetMarketHistoryParams, GetMarketQuotesParams } from "@/lib/types/market-data";

type IdParam = number | string;

export function useMarketQuotes(
  portfolioId: IdParam | undefined,
  symbols: GetMarketQuotesParams["symbols"],
) {
  const resolvedPortfolioId = portfolioId ?? "";
  const hasSymbols = symbols.some((symbol) => symbol.trim().length > 0);

  return useQuery({
    queryKey: queryKeys.marketData.quotes(resolvedPortfolioId, { symbols }),
    queryFn: ({ signal }) => getMarketQuotes(resolvedPortfolioId, { symbols }, signal),
    enabled: Boolean(portfolioId) && hasSymbols,
  });
}

export function useMarketHistory(
  portfolioId: IdParam | undefined,
  symbols: GetMarketHistoryParams["symbols"],
  range?: GetMarketHistoryParams["range"],
) {
  const resolvedPortfolioId = portfolioId ?? "";
  const params: GetMarketHistoryParams = { symbols, range };
  const hasSymbols = symbols.some((symbol) => symbol.trim().length > 0);

  return useQuery({
    queryKey: queryKeys.marketHistory.series(resolvedPortfolioId, params),
    queryFn: ({ signal }) => getMarketHistory(resolvedPortfolioId, params, signal),
    enabled: Boolean(portfolioId) && hasSymbols,
  });
}
