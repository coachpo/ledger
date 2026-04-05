import type { PositionRead } from "./types/position";
import type { MarketQuoteRead } from "./types/market-data";
import type { BalanceRead } from "./types/balance";

export interface PositionWithMarketData extends PositionRead {
  currentPrice?: string;
  previousClose?: string;
  isStale?: boolean;
}

export function enrichPositionsWithQuotes(
  positions: PositionRead[],
  quotes: MarketQuoteRead[]
): PositionWithMarketData[] {
  const quoteMap = new Map(quotes.map((q) => [q.symbol, q]));

  return positions.map((position) => {
    const quote = quoteMap.get(position.symbol);
    return {
      ...position,
      currentPrice: quote?.price,
      previousClose: quote?.previousClose ?? undefined,
      isStale: quote?.isStale,
    };
  });
}

export function computePositionMarketValue(position: PositionWithMarketData): number | null {
  if (!position.currentPrice) return null;

  const quantity = parseFloat(position.quantity);
  const price = parseFloat(position.currentPrice);

  if (isNaN(quantity) || isNaN(price)) return null;

  return quantity * price;
}

export function computePositionPnl(
  position: PositionWithMarketData
): { unrealized: number | null; unrealizedPercent: number | null } {
  if (!position.currentPrice) {
    return { unrealized: null, unrealizedPercent: null };
  }

  const quantity = parseFloat(position.quantity);
  const currentPrice = parseFloat(position.currentPrice);
  const averageCost = parseFloat(position.averageCost);

  if (isNaN(quantity) || isNaN(currentPrice) || isNaN(averageCost)) {
    return { unrealized: null, unrealizedPercent: null };
  }

  const unrealized = (currentPrice - averageCost) * quantity;
  const totalCost = averageCost * quantity;
  const unrealizedPercent = totalCost !== 0 ? unrealized / totalCost : null;

  return { unrealized, unrealizedPercent };
}

export function getSignedBalanceAmount(balance: BalanceRead): number | null {
  const amount = parseFloat(balance.amount);
  if (isNaN(amount)) {
    return null;
  }

  return balance.operationType === "WITHDRAWAL" ? -amount : amount;
}

export function computePortfolioTotalValue(
  positions: PositionWithMarketData[],
  balances: BalanceRead[]
): number {
  let total = 0;

  for (const position of positions) {
    const marketValue = computePositionMarketValue(position);
    if (marketValue !== null) {
      total += marketValue;
    }
  }

  for (const balance of balances) {
    const amount = getSignedBalanceAmount(balance);
    if (amount !== null) {
      total += amount;
    }
  }

  return total;
}

export function computePortfolioAllocation(
  positions: PositionWithMarketData[],
  totalValue: number
): Array<{ symbol: string; value: number; percent: number }> {
  if (totalValue <= 0) return [];

  const allocation: Array<{ symbol: string; value: number; percent: number }> = [];

  for (const position of positions) {
    const marketValue = computePositionMarketValue(position);
    if (marketValue !== null && marketValue > 0) {
      allocation.push({
        symbol: position.symbol,
        value: marketValue,
        percent: marketValue / totalValue,
      });
    }
  }

  return allocation.sort((a, b) => b.value - a.value);
}
