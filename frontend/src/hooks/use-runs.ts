import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { buildRunsListQueryKey, getRun, listRuns } from "@/lib/api/runs";
import type { IdParam } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type { RunListParams, RunStepAgentRead } from "@/lib/types/run";

type RunQueryOptions = {
  refetchInterval?: false | number;
};

type RunsListHookData = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  items: Array<Record<string, any>>;
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type RunDetailHookData = Record<string, any> & {
  perStepOutputs: Record<string, RunStepAgentRead[]>;
};

export function useRuns(
  params: RunListParams = {},
  options: RunQueryOptions = {},
): UseQueryResult<RunsListHookData, Error> {
  return useQuery({
    queryKey: buildRunsListQueryKey(params),
    queryFn: ({ signal }) => listRuns(params, signal),
    refetchInterval: options.refetchInterval,
  }) as UseQueryResult<RunsListHookData, Error>;
}

export function useRun(
  runId: IdParam | undefined,
  options: RunQueryOptions = {},
): UseQueryResult<RunDetailHookData, Error> {
  const resolvedRunId = runId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.runs.detail(resolvedRunId),
    queryFn: ({ signal }) => getRun(resolvedRunId, signal),
    enabled: Boolean(runId),
    refetchInterval: options.refetchInterval,
  }) as UseQueryResult<RunDetailHookData, Error>;
}
