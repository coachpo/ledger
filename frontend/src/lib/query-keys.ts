import type { QueryClient } from "@tanstack/react-query";
import type { GetMarketHistoryParams, GetMarketQuotesParams } from "./types/market-data";

const apiRoot = ["api"] as const;
type IdParam = number | string;

function normalizeId(id: IdParam) {
  return String(id);
}

function portfolioRoot(portfolioId: IdParam) {
  return [...apiRoot, "portfolios", normalizeId(portfolioId)] as const;
}

function normalizeSymbols(symbols: readonly string[]) {
  return [...new Set(symbols.map((symbol) => symbol.trim()).filter(Boolean))].sort();
}

function normalizePositionSymbol(symbol: string) {
  return symbol.trim().toUpperCase();
}

function normalizeHistoryParams(params: GetMarketHistoryParams) {
  return {
    range: params.range ?? "3mo",
    symbols: normalizeSymbols(params.symbols),
  };
}

const portfoliosQueryKeys = {
  all: [...apiRoot, "portfolios"] as const,
  detail: (portfolioId: IdParam) =>
    [...apiRoot, "portfolios", "detail", normalizeId(portfolioId)] as const,
  details: () => [...apiRoot, "portfolios", "detail"] as const,
  list: () => [...apiRoot, "portfolios", "list"] as const,
  lists: () => [...apiRoot, "portfolios", "list"] as const,
} as const;

const balancesQueryKeys = {
  all: (portfolioId: IdParam) => [...portfolioRoot(portfolioId), "balances"] as const,
  detail: (portfolioId: IdParam, balanceId: IdParam) =>
    [...portfolioRoot(portfolioId), "balances", "detail", normalizeId(balanceId)] as const,
  list: (portfolioId: IdParam) => [...portfolioRoot(portfolioId), "balances", "list"] as const,
} as const;

const positionsQueryKeys = {
  all: (portfolioId: IdParam) => [...portfolioRoot(portfolioId), "positions"] as const,
  detail: (portfolioId: IdParam, positionId: IdParam) =>
    [...portfolioRoot(portfolioId), "positions", "detail", normalizeId(positionId)] as const,
  list: (portfolioId: IdParam) => [...portfolioRoot(portfolioId), "positions", "list"] as const,
  lookup: (portfolioId: IdParam, symbol: string) =>
    [...portfolioRoot(portfolioId), "positions", "lookup", normalizePositionSymbol(symbol)] as const,
} as const;

const tradesQueryKeys = {
  all: (portfolioId: IdParam) => [...portfolioRoot(portfolioId), "trades"] as const,
  detail: (portfolioId: IdParam, tradeId: IdParam) =>
    [...portfolioRoot(portfolioId), "trades", "detail", normalizeId(tradeId)] as const,
  list: (portfolioId: IdParam) => [...portfolioRoot(portfolioId), "trades", "list"] as const,
} as const;

const marketDataQueryKeys = {
  all: (portfolioId: IdParam) => [...portfolioRoot(portfolioId), "marketData"] as const,
  quotes: (portfolioId: IdParam, params: GetMarketQuotesParams) =>
    [...portfolioRoot(portfolioId), "marketData", "quotes", normalizeSymbols(params.symbols)] as const,
} as const;

const marketHistoryQueryKeys = {
  all: (portfolioId: IdParam) => [...portfolioRoot(portfolioId), "marketHistory"] as const,
  series: (portfolioId: IdParam, params: GetMarketHistoryParams) =>
    [...portfolioRoot(portfolioId), "marketHistory", "series", normalizeHistoryParams(params)] as const,
} as const;

const templatesQueryKeys = {
  all: [...apiRoot, "templates"] as const,
  compile: (templateId: IdParam) =>
    [...apiRoot, "templates", "compile", normalizeId(templateId)] as const,
  list: () => [...apiRoot, "templates", "list"] as const,
} as const;

const reportsQueryKeys = {
  all: [...apiRoot, "reports"] as const,
  detail: (reportId: IdParam) =>
    [...apiRoot, "reports", "detail", normalizeId(reportId)] as const,
  list: () => [...apiRoot, "reports", "list"] as const,
} as const;

const backtestsQueryKeys = {
  all: [...apiRoot, "backtests"] as const,
  detail: (backtestId: IdParam) =>
    [...apiRoot, "backtests", "detail", normalizeId(backtestId)] as const,
  list: () => [...apiRoot, "backtests", "list"] as const,
} as const;

export const queryKeys = {
  backtests: backtestsQueryKeys,
  portfolios: portfoliosQueryKeys,
  balances: balancesQueryKeys,
  positions: positionsQueryKeys,
  trades: tradesQueryKeys,
  tradingOperations: tradesQueryKeys,
  marketData: marketDataQueryKeys,
  marketHistory: marketHistoryQueryKeys,
  templates: templatesQueryKeys,
  reports: reportsQueryKeys,
} as const;

export function invalidatePortfolioScope(
  queryClient: QueryClient,
  portfolioId: number | string,
) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: portfolioRoot(portfolioId) }),
    queryClient.invalidateQueries({ queryKey: portfoliosQueryKeys.all }),
  ]);
}
