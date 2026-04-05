import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  commitPositionImport,
  createPosition,
  deletePosition,
  getPositionSymbolLookup,
  listPositions,
  previewPositionImport,
  updatePosition,
} from "@/lib/api/positions";
import { invalidatePortfolioScope, queryKeys } from "@/lib/query-keys";
import type { PositionUpdateInput, PositionWriteInput } from "@/lib/types/position";

type IdParam = number | string;

type UpdatePositionVariables = {
  positionId: number;
  data: PositionUpdateInput;
};

export function usePositions(portfolioId: IdParam | undefined) {
  const resolvedPortfolioId = portfolioId ?? "";

  return useQuery({
    queryKey: queryKeys.positions.list(resolvedPortfolioId),
    queryFn: ({ signal }) => listPositions(resolvedPortfolioId, signal),
    enabled: Boolean(portfolioId),
  });
}

export function useCreatePosition(portfolioId: IdParam) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: PositionWriteInput) => createPosition(portfolioId, data),
    onSuccess: () => invalidatePortfolioScope(queryClient, portfolioId),
  });
}

export function usePositionSymbolLookup(
  portfolioId: IdParam | undefined,
  symbol: string | undefined,
) {
  const resolvedPortfolioId = portfolioId ?? "";
  const normalizedSymbol = symbol?.trim().toUpperCase() ?? "";

  return useQuery({
    queryKey: queryKeys.positions.lookup(resolvedPortfolioId, normalizedSymbol),
    queryFn: ({ signal }) =>
      getPositionSymbolLookup(resolvedPortfolioId, normalizedSymbol, signal),
    enabled: Boolean(portfolioId) && normalizedSymbol.length > 0,
  });
}

export function useUpdatePosition(portfolioId: IdParam) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ positionId, data }: UpdatePositionVariables) =>
      updatePosition(portfolioId, positionId, data),
    onSuccess: () => invalidatePortfolioScope(queryClient, portfolioId),
  });
}

export function useDeletePosition(portfolioId: IdParam) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (positionId: number) => deletePosition(portfolioId, positionId),
    onSuccess: () => invalidatePortfolioScope(queryClient, portfolioId),
  });
}

export function useCsvPreview(portfolioId: IdParam) {
  return useMutation({
    mutationFn: (file: File) => previewPositionImport(portfolioId, file),
  });
}

export function useCsvCommit(portfolioId: IdParam) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (file: File) => commitPositionImport(portfolioId, file),
    onSuccess: () => invalidatePortfolioScope(queryClient, portfolioId),
  });
}
