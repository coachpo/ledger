import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  approveRuntimeApproval,
  cancelRuntimeRun,
  createRuntimeRun,
  denyRuntimeApproval,
  getRuntimeApproval,
  getRuntimeRun,
  getRuntimeRunArtifact,
  getRuntimeRunTrace,
  listRuntimeApprovals,
  listRuntimeRuns,
  listRuntimeTraceEvents,
} from "@/lib/api/runtime";
import { queryKeys } from "@/lib/query-keys";
import type {
  RuntimeApprovalActionInput,
  RuntimeApprovalListParams,
  RuntimeRunCreateInput,
  RuntimeRunListParams,
  RuntimeTraceEventListParams,
} from "@/lib/types/runtime";

type IdParam = number | string;

type ResolveRuntimeApprovalVariables = {
  approvalId: IdParam;
  payload: RuntimeApprovalActionInput;
};

function invalidateRuntimeCollections(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.runtime.runs.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.runtime.approvals.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.runtime.traceEvents.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.studio.runs.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.studio.artifacts.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.studio.approvals.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.studio.traceEvents.all }),
  ]);
}

function invalidateRuntimeRunScope(queryClient: QueryClient, runId: IdParam) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.runtime.runs.detail(runId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.runtime.runs.artifact(runId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.runtime.runs.trace(runId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.studio.runs.detail(runId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.studio.runs.artifact(runId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.studio.runs.trace(runId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.tryouts.detail(runId) }),
  ]);
}

function invalidateRuntimeApprovalScope(queryClient: QueryClient, approvalId: IdParam) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.runtime.approvals.detail(approvalId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.studio.approvals.detail(approvalId) }),
  ]);
}

export function useRuntimeRuns(params: RuntimeRunListParams = {}) {
  return useQuery({
    queryKey: queryKeys.runtime.runs.list(params),
    queryFn: ({ signal }) => listRuntimeRuns(params, signal),
  });
}

export function useRuntimeRun(runId: IdParam | undefined) {
  const resolvedRunId = runId ?? "";

  return useQuery({
    queryKey: queryKeys.runtime.runs.detail(resolvedRunId),
    queryFn: ({ signal }) => getRuntimeRun(resolvedRunId, signal),
    enabled: Boolean(runId),
  });
}

export function useRuntimeRunArtifact(runId: IdParam | undefined) {
  const resolvedRunId = runId ?? "";

  return useQuery({
    queryKey: queryKeys.runtime.runs.artifact(resolvedRunId),
    queryFn: ({ signal }) => getRuntimeRunArtifact(resolvedRunId, signal),
    enabled: Boolean(runId),
  });
}

export function useRuntimeRunTrace(runId: IdParam | undefined) {
  const resolvedRunId = runId ?? "";

  return useQuery({
    queryKey: queryKeys.runtime.runs.trace(resolvedRunId),
    queryFn: ({ signal }) => getRuntimeRunTrace(resolvedRunId, signal),
    enabled: Boolean(runId),
  });
}

export function useRuntimeApprovals(params: RuntimeApprovalListParams = {}) {
  return useQuery({
    queryKey: queryKeys.runtime.approvals.list(params),
    queryFn: ({ signal }) => listRuntimeApprovals(params, signal),
  });
}

export function useRuntimeApproval(approvalId: IdParam | undefined) {
  const resolvedApprovalId = approvalId ?? "";

  return useQuery({
    queryKey: queryKeys.runtime.approvals.detail(resolvedApprovalId),
    queryFn: ({ signal }) => getRuntimeApproval(resolvedApprovalId, signal),
    enabled: Boolean(approvalId),
  });
}

export function useRuntimeTraceEvents(params: RuntimeTraceEventListParams = {}) {
  return useQuery({
    queryKey: queryKeys.runtime.traceEvents.list(params),
    queryFn: ({ signal }) => listRuntimeTraceEvents(params, signal),
  });
}

export function useCreateRuntimeRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: RuntimeRunCreateInput) => createRuntimeRun(payload),
    onSuccess: async (run) => {
      await invalidateRuntimeCollections(queryClient);
      await invalidateRuntimeRunScope(queryClient, run.runId);
    },
  });
}

export function useCancelRuntimeRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (runId: IdParam) => cancelRuntimeRun(runId),
    onSuccess: async (run) => {
      await invalidateRuntimeCollections(queryClient);
      await invalidateRuntimeRunScope(queryClient, run.runId);
    },
  });
}

export function useApproveRuntimeApproval() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ approvalId, payload }: ResolveRuntimeApprovalVariables) =>
      approveRuntimeApproval(approvalId, payload),
    onSuccess: async (result) => {
      await invalidateRuntimeCollections(queryClient);
      await invalidateRuntimeApprovalScope(queryClient, result.approvalId);
      await invalidateRuntimeRunScope(queryClient, result.runId);
    },
  });
}

export function useDenyRuntimeApproval() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ approvalId, payload }: ResolveRuntimeApprovalVariables) =>
      denyRuntimeApproval(approvalId, payload),
    onSuccess: async (result) => {
      await invalidateRuntimeCollections(queryClient);
      await invalidateRuntimeApprovalScope(queryClient, result.approvalId);
      await invalidateRuntimeRunScope(queryClient, result.runId);
    },
  });
}
