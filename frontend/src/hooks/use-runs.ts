import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import {
  buildRunsListQueryKey,
  createRunFork,
  getRun,
  getRunForkDraft,
  listRuns,
} from "@/lib/api/runs";
import type { IdParam } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type {
  RunCreatedRead,
  RunForkCreateRequest,
  RunForkDraftRead,
  RunListParams,
  RunListRead,
  RunRead,
} from "@/lib/types/run";

type RunQueryOptions = {
  refetchInterval?: false | number;
};

type RunForkDraftQueryOptions = RunQueryOptions & {
  enabled?: boolean;
};

export type CreateRunForkVariables = {
  runId: IdParam;
  payload: RunForkCreateRequest;
};

export function useRuns(
  params: RunListParams = {},
  options: RunQueryOptions = {},
): UseQueryResult<RunListRead, Error> {
  return useQuery({
    queryKey: buildRunsListQueryKey(params),
    queryFn: ({ signal }) => listRuns(params, signal),
    refetchInterval: options.refetchInterval,
  });
}

export function useRun(
  runId: IdParam | undefined,
  options: RunQueryOptions = {},
): UseQueryResult<RunRead, Error> {
  const resolvedRunId = runId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.runs.detail(resolvedRunId),
    queryFn: ({ signal }) => getRun(resolvedRunId, signal),
    enabled: Boolean(runId),
    refetchInterval: options.refetchInterval,
  });
}

export function useRunForkDraft(
  runId: IdParam | undefined,
  forkStepIndex: number | undefined,
  options: RunForkDraftQueryOptions = {},
): UseQueryResult<RunForkDraftRead, Error> {
  const resolvedRunId = runId ?? "";
  const resolvedForkStepIndex = forkStepIndex ?? 0;

  return useQuery({
    queryKey: queryKeys.platform.runs.forkDraft(resolvedRunId, resolvedForkStepIndex),
    queryFn: ({ signal }) => getRunForkDraft(resolvedRunId, resolvedForkStepIndex, signal),
    enabled: Boolean(runId) && forkStepIndex !== undefined && (options.enabled ?? true),
    refetchInterval: options.refetchInterval,
  });
}

export function useCreateRunFork() {
  const queryClient = useQueryClient();

  return useMutation<RunCreatedRead, Error, CreateRunForkVariables>({
    mutationFn: ({ runId, payload }) => createRunFork(runId, payload),
    onSuccess: async (createdRun, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.detail(variables.runId) }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.platform.runs.forkDraft(variables.runId, variables.payload.forkStepIndex),
        }),
        queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.detail(createdRun.id) }),
      ]);
    },
  });
}
