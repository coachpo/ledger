import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createTradingOperation,
  listTradingOperations,
} from "@/lib/api/trading-operations";
import { invalidatePortfolioScope, queryKeys } from "@/lib/query-keys";
import type { TradingOperationInput } from "@/lib/types/trading";

type IdParam = number | string;

export function useTradingOperations(portfolioId: IdParam | undefined) {
  const resolvedPortfolioId = portfolioId ?? "";

  return useQuery({
    queryKey: queryKeys.tradingOperations.list(resolvedPortfolioId),
    queryFn: ({ signal }) => listTradingOperations(resolvedPortfolioId, signal),
    enabled: Boolean(portfolioId),
  });
}

export function useCreateTradingOperation(portfolioId: IdParam) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: TradingOperationInput) => createTradingOperation(portfolioId, data),
    onSuccess: () => invalidatePortfolioScope(queryClient, portfolioId),
  });
}
