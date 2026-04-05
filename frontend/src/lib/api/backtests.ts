import type { BacktestCreateInput, BacktestRead } from "../types/backtest";
import { type IdParam, request, toPathSegment } from "../api-client";

function backtestPath(backtestId: IdParam): string {
  return `/backtests/${toPathSegment(backtestId)}`;
}

export function listBacktests(signal?: AbortSignal): Promise<BacktestRead[]> {
  return request<BacktestRead[]>("/backtests", { signal });
}

export function getBacktest(
  backtestId: IdParam,
  signal?: AbortSignal,
): Promise<BacktestRead> {
  return request<BacktestRead>(backtestPath(backtestId), { signal });
}

export function createBacktest(
  input: BacktestCreateInput,
  signal?: AbortSignal,
): Promise<BacktestRead> {
  return request<BacktestRead>("/backtests", {
    method: "POST",
    body: input,
    signal,
  });
}

export function cancelBacktest(
  backtestId: IdParam,
  signal?: AbortSignal,
): Promise<BacktestRead> {
  return request<BacktestRead>(`${backtestPath(backtestId)}/cancel`, {
    method: "POST",
    signal,
  });
}

export function deleteBacktest(
  backtestId: IdParam,
  signal?: AbortSignal,
): Promise<void> {
  return request<void>(backtestPath(backtestId), {
    method: "DELETE",
    signal,
  });
}

export const backtestsApi = {
  list: listBacktests,
  get: getBacktest,
  create: createBacktest,
  cancel: cancelBacktest,
  delete: deleteBacktest,
} as const;
