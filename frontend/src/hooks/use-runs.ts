import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import {
  buildRunsListQueryKey,
  createRunRerun,
  createRunStepReplay,
  getRun,
  getRunRerunDraft,
  getRunStepReplayDraft,
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
  RunStepReplayCreateRequest,
  RunStepReplayDraftRead,
} from "@/lib/types/run";

type RunQueryOptions = {
  refetchInterval?: false | number;
};

type DraftQueryOptions = RunQueryOptions & {
  enabled?: boolean;
};

export type CreateRunRerunVariables = {
  runId: IdParam;
  payload: RunRerunCreateRequest;
};

export type CreateRunStepReplayVariables = {
  runId: IdParam;
  payload: RunStepReplayCreateRequest;
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

export function useRunStepReplayDraft(
  runId: IdParam | undefined,
  stepIndex: number | undefined,
  options: DraftQueryOptions = {},
): UseQueryResult<RunStepReplayDraftRead, Error> {
  const resolvedRunId = runId ?? "";
  const resolvedStepIndex = stepIndex ?? 0;

  return useQuery({
    queryKey: queryKeys.platform.runs.stepReplayDraft(resolvedRunId, resolvedStepIndex),
    queryFn: ({ signal }) => getRunStepReplayDraft(resolvedRunId, resolvedStepIndex, signal),
    enabled: Boolean(runId) && stepIndex !== undefined && (options.enabled ?? true),
    refetchInterval: options.refetchInterval,
  });
}

export function useCreateRunStepReplay() {
  const queryClient = useQueryClient();

  return useMutation<RunCreatedRead, Error, CreateRunStepReplayVariables>({
    mutationFn: ({ runId, payload }) => createRunStepReplay(runId, payload),
    onSuccess: async (createdRun, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.detail(variables.runId) }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.platform.runs.stepReplayDraft(variables.runId, variables.payload.replayStepIndex),
        }),
        queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.detail(createdRun.id) }),
      ]);
    },
  });
}
