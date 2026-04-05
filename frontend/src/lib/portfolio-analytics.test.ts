import { describe, expect, it } from "vitest";

import type { BalanceRead } from "./types/balance";
import type { MarketQuoteRead } from "./types/market-data";
import type { PositionRead } from "./types/position";
import {
  computePortfolioAllocation,
  computePortfolioTotalValue,
  computePositionMarketValue,
  computePositionPnl,
  enrichPositionsWithQuotes,
  getSignedBalanceAmount,
  type PositionWithMarketData,
} from "./portfolio-analytics";

const FIXTURE_TIME = "2024-03-15T12:00:00Z";

function makePosition(overrides: Partial<PositionRead> = {}): PositionRead {
  return {
    id: 1,
    portfolioId: 1,
    symbol: "AAPL",
    name: "Apple Inc.",
    quantity: "10",
    averageCost: "150",
    currency: "USD",
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
    ...overrides,
  };
}

function makeQuote(overrides: Partial<MarketQuoteRead> = {}): MarketQuoteRead {
  return {
    symbol: "AAPL",

    price: "190",
    currency: "USD",
    provider: "test-provider",
    asOf: FIXTURE_TIME,
    isStale: false,
    previousClose: "188",
    ...overrides,
  };
}

function makeBalance(overrides: Partial<BalanceRead> = {}): BalanceRead {
  return {
    id: 1,
    portfolioId: 1,
    label: "Broker Cash",
    amount: "500.25",
    currency: "USD",
    hasTradingOperations: overrides.hasTradingOperations ?? false,
    createdAt: FIXTURE_TIME,
    updatedAt: FIXTURE_TIME,
    ...overrides,
    operationType: overrides.operationType ?? "DEPOSIT",
  };
}

function withMarketData(overrides: Partial<PositionWithMarketData> = {}): PositionWithMarketData {
  return {
    ...makePosition(),
    currentPrice: "190",
    previousClose: "188",
    isStale: false,
    ...overrides,
  };
}

describe("portfolio analytics", () => {
  it("enriches positions with matching quotes and leaves missing quotes empty", () => {
    const positions = [makePosition(), makePosition({ id: 2, symbol: "MSFT", name: "Microsoft", quantity: "5" })];
    const quotes = [makeQuote()];

    const enriched = enrichPositionsWithQuotes(positions, quotes);

    expect(enriched).toEqual([
      { ...positions[0], currentPrice: "190", previousClose: "188", isStale: false },
      { ...positions[1], currentPrice: undefined, previousClose: undefined, isStale: undefined },
    ]);
  });

  it("computes market value for valid positions and returns null for missing or invalid prices", () => {
    expect(computePositionMarketValue(withMarketData({ quantity: "10.5", currentPrice: "190.25" }))).toBeCloseTo(1997.625);
    expect(computePositionMarketValue(withMarketData({ currentPrice: undefined }))).toBeNull();
    expect(computePositionMarketValue(withMarketData({ quantity: "not-a-number" }))).toBeNull();
  });

  it("computes profit, loss, and missing-price P&L states", () => {
    expect(computePositionPnl(withMarketData({ quantity: "10", averageCost: "150", currentPrice: "175" }))).toEqual({
      unrealized: 250,
      unrealizedPercent: 250 / 1500,
    });
    expect(computePositionPnl(withMarketData({ quantity: "10", averageCost: "150", currentPrice: "120" }))).toEqual({
      unrealized: -300,
      unrealizedPercent: -300 / 1500,
    });
    expect(computePositionPnl(withMarketData({ currentPrice: undefined }))).toEqual({
      unrealized: null,
      unrealizedPercent: null,
    });
    expect(computePositionPnl(withMarketData({ quantity: "10", averageCost: "0", currentPrice: "175" }))).toEqual({
      unrealized: 1750,
      unrealizedPercent: null,
    });
  });

  it("totals marked positions with balances and ignores invalid numeric inputs", () => {
    const positions = [withMarketData(), withMarketData({ id: 2, symbol: "MSFT", quantity: "5", currentPrice: undefined })];
    const balances = [makeBalance(), makeBalance({ id: 2, label: "FX", amount: "invalid" })];

    expect(computePortfolioTotalValue(positions, balances)).toBeCloseTo(2400.25);
  });

  it("treats withdrawals as negative cash", () => {
    const deposit = makeBalance({ amount: "1000" });
    const withdrawal = makeBalance({ id: 2, label: "Cash Out", amount: "200", operationType: "WITHDRAWAL" });

    expect(getSignedBalanceAmount(deposit)).toBe(1000);
    expect(getSignedBalanceAmount(withdrawal)).toBe(-200);
    expect(computePortfolioTotalValue([], [deposit, withdrawal])).toBe(800);
  });

  it("builds sorted allocation data and handles zero total portfolios", () => {
    const positions = [
      withMarketData({ symbol: "AAPL", quantity: "10", currentPrice: "190" }),
      withMarketData({ id: 2, symbol: "MSFT", quantity: "5", currentPrice: "120" }),
      withMarketData({ id: 3, symbol: "CASH", quantity: "1", currentPrice: undefined }),
    ];

    const allocation = computePortfolioAllocation(positions, 2500);

    expect(allocation).toHaveLength(2);
    expect(allocation[0]).toEqual({ symbol: "AAPL", value: 1900, percent: 1900 / 2500 });
    expect(allocation[1]).toEqual({ symbol: "MSFT", value: 600, percent: 600 / 2500 });
    expect(computePortfolioAllocation(positions, 0)).toEqual([]);
  });
});
