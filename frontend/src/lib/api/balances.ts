import type { BalanceRead, BalanceWriteInput, BalanceUpdateInput } from "../types/balance";
import { type IdParam, portfolioPath, request, toPathSegment } from "../api-client";

export function listBalances(
  portfolioId: IdParam,
  signal?: AbortSignal,
): Promise<BalanceRead[]> {
  return request<BalanceRead[]>(`${portfolioPath(portfolioId)}/balances`, {
    signal,
  });
}

export function createBalance(
  portfolioId: IdParam,
  input: BalanceWriteInput,
  signal?: AbortSignal,
): Promise<BalanceRead> {
  return request<BalanceRead>(`${portfolioPath(portfolioId)}/balances`, {
    body: input,
    method: "POST",
    signal,
  });
}

export function updateBalance(
  portfolioId: IdParam,
  balanceId: IdParam,
  input: BalanceUpdateInput,
  signal?: AbortSignal,
): Promise<BalanceRead> {
  return request<BalanceRead>(
    `${portfolioPath(portfolioId)}/balances/${toPathSegment(balanceId)}`,
    {
      body: input,
      method: "PATCH",
      signal,
    },
  );
}

export function deleteBalance(
  portfolioId: IdParam,
  balanceId: IdParam,
  signal?: AbortSignal,
): Promise<void> {
  return request<void>(`${portfolioPath(portfolioId)}/balances/${toPathSegment(balanceId)}`, {
    method: "DELETE",
    signal,
  });
}

export const balancesApi = {
  create: createBalance,
  delete: deleteBalance,
  list: listBalances,
  update: updateBalance,
} as const;
