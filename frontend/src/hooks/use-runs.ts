import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import {
  cancelRun,
  createRunRerun,
  getRun,
  getRunRerunDraft,
  listRuns,
} from "@/lib/api/runs";
import type { IdParam } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type {
  RunCreatedRead,
  RunListParams,
  RunListRead,
  RunRead,
  RunRerunCreateRequest,
  RunRerunDraftRead,
  RunStatus,
} from "@/lib/types/run";

type RunQueryOptions = {
  refetchInterval?: false | number;
};

type DraftQueryOptions = RunQueryOptions & {
  enabled?: boolean;
};

const ACTIVE_RUN_STATUSES = new Set<RunStatus>(["queued", "running"]);

function isActiveRunStatus(status: RunStatus): boolean {
  return ACTIVE_RUN_STATUSES.has(status);
}

function activeRefetchInterval(options: RunQueryOptions): false | number {
  return options.refetchInterval ?? false;
}

function hasActiveListRun(data: RunListRead | undefined): boolean {
  return data?.items.some((run) => isActiveRunStatus(run.status)) ?? false;
}

function hasActiveDetailRun(data: RunRead | undefined): boolean {
  return data ? isActiveRunStatus(data.status) : false;
}

export type CreateRunRerunVariables = {
  runId: IdParam;
  payload: RunRerunCreateRequest;
};

export function useCancelRun() {
  const queryClient = useQueryClient();

  return useMutation<RunRead, Error, IdParam>({
    mutationFn: cancelRun,
    onSuccess: async (_cancelledRun, runId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.detail(runId) }),
      ]);
    },
  });
}

export function useRuns(
  params: RunListParams = {},
  options: RunQueryOptions = {},
): UseQueryResult<RunListRead, Error> {
  const refetchInterval = activeRefetchInterval(options);

  return useQuery({
    queryKey: queryKeys.platform.runs.list(params),
    queryFn: ({ signal }) => listRuns(params, signal),
    refetchInterval: (query) =>
      hasActiveListRun(query.state.data) ? refetchInterval : false,
  });
}

export function useRun(
  runId: IdParam | undefined,
  options: RunQueryOptions = {},
): UseQueryResult<RunRead, Error> {
  const resolvedRunId = runId ?? "";
  const refetchInterval = activeRefetchInterval(options);

  return useQuery({
    queryKey: queryKeys.platform.runs.detail(resolvedRunId),
    queryFn: ({ signal }) => getRun(resolvedRunId, signal),
    enabled: Boolean(runId),
    refetchInterval: (query) =>
      hasActiveDetailRun(query.state.data) ? refetchInterval : false,
  });
}

export function useRunRerunDraft(
  runId: IdParam | undefined,
  options: DraftQueryOptions = {},
): UseQueryResult<RunRerunDraftRead, Error> {
  const resolvedRunId = runId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.runs.rerunDraft(resolvedRunId),
    queryFn: ({ signal }) => getRunRerunDraft(resolvedRunId, signal),
    enabled: Boolean(runId) && (options.enabled ?? true),
    refetchInterval: options.refetchInterval,
  });
}

export function useCreateRunRerun() {
  const queryClient = useQueryClient();

  return useMutation<RunCreatedRead, Error, CreateRunRerunVariables>({
    mutationFn: ({ runId, payload }) => createRunRerun(runId, payload),
    onSuccess: async (createdRun, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.detail(variables.runId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.rerunDraft(variables.runId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.detail(createdRun.id) }),
      ]);
    },
  });
}
