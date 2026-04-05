import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelBacktest,
  createBacktest,
  deleteBacktest,
  getBacktest,
  listBacktests,
} from "@/lib/api/backtests";
import { queryKeys } from "@/lib/query-keys";
import type { BacktestCreateInput, BacktestStatus } from "@/lib/types/backtest";

type BacktestId = number | string;

function isRunningStatus(status: BacktestStatus | undefined) {
  return (
    status === "PENDING" ||
    status === "RUNNING" ||
    status === "AWAITING_CALLBACK" ||
    status === "PROCESSING_CALLBACK"
  );
}

export function useBacktests() {
  return useQuery({
    queryKey: queryKeys.backtests.list(),
    queryFn: ({ signal }) => listBacktests(signal),
  });
}

export function useBacktest(backtestId: BacktestId | undefined) {
  const resolvedId = backtestId ?? "";

  return useQuery({
    queryKey: queryKeys.backtests.detail(resolvedId),
    queryFn: ({ signal }) => getBacktest(resolvedId, signal),
    enabled: Boolean(backtestId),
    refetchInterval: (query) =>
      isRunningStatus(query.state.data?.status) ? 5000 : false,
  });
}

export function useCreateBacktest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: BacktestCreateInput) => createBacktest(input),
    onSuccess: (backtest) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.backtests.list() });
      queryClient.invalidateQueries({ queryKey: queryKeys.backtests.detail(backtest.id) });
    },
  });
}

export function useCancelBacktest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (backtestId: BacktestId) => cancelBacktest(backtestId),
    onSuccess: (backtest) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.backtests.list() });
      queryClient.invalidateQueries({ queryKey: queryKeys.backtests.detail(backtest.id) });
    },
  });
}

export function useDeleteBacktest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (backtestId: BacktestId) => deleteBacktest(backtestId),
    onSuccess: (_, backtestId) => {
      queryClient.removeQueries({ queryKey: queryKeys.backtests.detail(backtestId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.backtests.list() });
    },
  });
}
