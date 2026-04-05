export type MarketHistoryRange = "1mo" | "3mo" | "ytd" | "1y" | "max";

export interface MarketQuoteRead {
  symbol: string;
  name?: string | null;
  price: string;
  currency: string;
  provider: string;
  asOf: string | null;
  isStale: boolean;
  previousClose: string | null;
}

export interface MarketQuoteListRead {
  quotes: MarketQuoteRead[];
  warnings: string[];
}

export interface MarketHistoryPointRead {
  at: string;
  close: string;
}

export interface MarketHistorySeriesRead {
  symbol: string;
  currency: string | null;
  provider: string;
  points: MarketHistoryPointRead[];
}

export interface MarketHistoryRead {
  range: MarketHistoryRange;
  interval: string;
  series: MarketHistorySeriesRead[];
  warnings: string[];
}

export interface GetMarketQuotesParams {
  symbols: string[];
}

export interface GetMarketHistoryParams {
  symbols: string[];
  range?: MarketHistoryRange;
}
