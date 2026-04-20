import { useQuery } from "@tanstack/react-query";
import { getRun, listRuns } from "@/lib/api/runs";
import type { IdParam } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type { RunListParams } from "@/lib/types/run";

type RunQueryOptions = {
  refetchInterval?: false | number;
};

export function useRuns(params: RunListParams = {}, options: RunQueryOptions = {}) {
  return useQuery({
    queryKey: queryKeys.platform.runs.list(params),
    queryFn: ({ signal }) => listRuns(params, signal),
    refetchInterval: options.refetchInterval,
  });
}

export function useRun(runId: IdParam | undefined, options: RunQueryOptions = {}) {
  const resolvedRunId = runId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.runs.detail(resolvedRunId),
    queryFn: ({ signal }) => getRun(resolvedRunId, signal),
    enabled: Boolean(runId),
    refetchInterval: options.refetchInterval,
  });
}
