import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createTryout, getTryout, persistTryout } from "@/lib/api/tryouts";
import { queryKeys } from "@/lib/query-keys";
import type { TryoutExecuteInput } from "@/lib/types/tryout";

type IdParam = number | string;

function invalidateTryoutCollections(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.tryouts.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.runtime.runs.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.studio.runs.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.studio.artifacts.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.studio.approvals.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.studio.traceEvents.all }),
  ]);
}

function invalidateTryoutRunScope(queryClient: QueryClient, runId: IdParam) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.tryouts.detail(runId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.runtime.runs.detail(runId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.runtime.runs.artifact(runId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.runtime.runs.trace(runId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.studio.runs.detail(runId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.studio.runs.artifact(runId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.studio.runs.trace(runId) }),
  ]);
}

export function useTryout(runId: IdParam | undefined) {
  const resolvedRunId = runId ?? "";

  return useQuery({
    queryKey: queryKeys.tryouts.detail(resolvedRunId),
    queryFn: ({ signal }) => getTryout(resolvedRunId, signal),
    enabled: Boolean(runId),
  });
}

export function useCreateTryout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: TryoutExecuteInput) => createTryout(payload),
    onSuccess: async (tryout) => {
      await invalidateTryoutCollections(queryClient);
      await invalidateTryoutRunScope(queryClient, tryout.runId);
    },
  });
}

export function usePersistTryout(runId: IdParam | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      if (!runId) {
        throw new Error("Tryout run id is required to persist.");
      }

      return persistTryout(runId);
    },
    onSuccess: async (tryout) => {
      await invalidateTryoutCollections(queryClient);
      await invalidateTryoutRunScope(queryClient, tryout.runId);
    },
  });
}
