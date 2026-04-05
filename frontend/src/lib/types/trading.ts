import type { PositionCompactRead } from "./position";
import type { BalanceCompactRead } from "./balance";

export type TradingSide = "BUY" | "SELL" | "DIVIDEND" | "SPLIT";

export interface TradingOperationBase {
  symbol: string;
  executedAt: string;
}

export interface CashTradingOperationBase extends TradingOperationBase {
  balanceId: number;
}

export interface BuyOperationInput extends CashTradingOperationBase {
  side: "BUY";
  quantity: string;
  price: string;
  commission?: string;
}

export interface SellOperationInput extends CashTradingOperationBase {
  side: "SELL";
  quantity: string;
  price: string;
  commission?: string;
}

export interface DividendOperationInput extends CashTradingOperationBase {
  side: "DIVIDEND";
  dividendAmount: string;
  commission?: string;
}

export interface SplitOperationInput extends TradingOperationBase {
  side: "SPLIT";
  splitRatio: string;
}

export type TradingOperationInput =
  | BuyOperationInput
  | SellOperationInput
  | DividendOperationInput
  | SplitOperationInput;

export interface TradingOperationRead {
  id: number;
  portfolioId: number;
  balanceId: number | null;
  balanceLabel: string;
  symbol: string;
  side: TradingSide;
  quantity: string | null;
  price: string | null;
  commission: string;
  dividendAmount: string | null;
  splitRatio: string | null;
  currency: string;
  executedAt: string;
  createdAt: string;
}

export interface TradingOperationResult {
  operation: TradingOperationRead;
  updatedPosition: PositionCompactRead | null;
  updatedBalance: BalanceCompactRead | null;
}
