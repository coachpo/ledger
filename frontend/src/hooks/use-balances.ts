import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createBalance,
  deleteBalance,
  listBalances,
  updateBalance,
} from "@/lib/api/balances";
import { invalidatePortfolioScope, queryKeys } from "@/lib/query-keys";
import type { BalanceUpdateInput, BalanceWriteInput } from "@/lib/types/balance";

type IdParam = number | string;

type UpdateBalanceVariables = {
  balanceId: number;
  data: BalanceUpdateInput;
};

export function useBalances(portfolioId: IdParam | undefined) {
  const resolvedPortfolioId = portfolioId ?? "";

  return useQuery({
    queryKey: queryKeys.balances.list(resolvedPortfolioId),
    queryFn: ({ signal }) => listBalances(resolvedPortfolioId, signal),
    enabled: Boolean(portfolioId),
  });
}

export function useCreateBalance(portfolioId: IdParam) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: BalanceWriteInput) => createBalance(portfolioId, data),
    onSuccess: () => invalidatePortfolioScope(queryClient, portfolioId),
  });
}

export function useUpdateBalance(portfolioId: IdParam) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ balanceId, data }: UpdateBalanceVariables) =>
      updateBalance(portfolioId, balanceId, data),
    onSuccess: () => invalidatePortfolioScope(queryClient, portfolioId),
  });
}

export function useDeleteBalance(portfolioId: IdParam) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (balanceId: number) => deleteBalance(portfolioId, balanceId),
    onSuccess: () => invalidatePortfolioScope(queryClient, portfolioId),
  });
}
