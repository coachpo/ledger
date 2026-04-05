import type { TradingOperationRead, TradingOperationInput, TradingOperationResult } from "../types/trading";
import { type IdParam, portfolioPath, request } from "../api-client";

export function listTradingOperations(
  portfolioId: IdParam,
  signal?: AbortSignal,
): Promise<TradingOperationRead[]> {
  return request<TradingOperationRead[]>(
    `${portfolioPath(portfolioId)}/trading-operations`,
    { signal },
  );
}

export function createTradingOperation(
  portfolioId: IdParam,
  input: TradingOperationInput,
  signal?: AbortSignal,
): Promise<TradingOperationResult> {
  return request<TradingOperationResult>(`${portfolioPath(portfolioId)}/trading-operations`, {
    body: input,
    method: "POST",
    signal,
  });
}

export const tradingOperationsApi = {
  create: createTradingOperation,
  list: listTradingOperations,
} as const;
