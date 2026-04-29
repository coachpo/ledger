import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  archiveWorkflow,
  createWorkflow,
  createWorkflowRun,
  getWorkflow,
  listWorkflows,
  updateWorkflow,
  validateWorkflowManifest,
} from "@/lib/api/workflows";
import type { IdParam } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type {
  WorkflowCreateInput,
  WorkflowListParams,
  WorkflowManifestValidationInput,
  WorkflowRunCreateInput,
  WorkflowUpdateInput,
} from "@/lib/types/workflow";

type UpdateWorkflowVariables = {
  payload: WorkflowUpdateInput;
  workflowId: IdParam;
};

type CreateWorkflowRunVariables = {
  payload: WorkflowRunCreateInput;
  version?: number;
  workflowId: IdParam;
};

function invalidateWorkflowScope(queryClient: QueryClient, workflowId: IdParam, version?: number) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflows.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflows.detail(workflowId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflows.detail(workflowId, version) }),
  ]);
}

export function useWorkflows(params: WorkflowListParams = {}) {
  return useQuery({
    queryKey: queryKeys.platform.workflows.list(params),
    queryFn: ({ signal }) => listWorkflows(params, signal),
  });
}

export function useWorkflow(workflowId: IdParam | undefined, version?: number) {
  const resolvedWorkflowId = workflowId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.workflows.detail(resolvedWorkflowId, version),
    queryFn: ({ signal }) => getWorkflow(resolvedWorkflowId, { signal, version }),
    enabled: Boolean(workflowId),
  });
}

export function useValidateWorkflowManifest() {
  return useMutation({
    mutationFn: (payload: WorkflowManifestValidationInput) => validateWorkflowManifest(payload),
  });
}

export function useCreateWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: WorkflowCreateInput) => createWorkflow(payload),
    onSuccess: async (workflow) => {
      await invalidateWorkflowScope(queryClient, workflow.id, workflow.version);
    },
  });
}

export function useUpdateWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ payload, workflowId }: UpdateWorkflowVariables) => updateWorkflow(workflowId, payload),
    onSuccess: async (workflow, { workflowId }) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflows.detail(workflowId) });
      await invalidateWorkflowScope(queryClient, workflow.id, workflow.version);
    },
  });
}

export function useArchiveWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (workflowId: IdParam) => archiveWorkflow(workflowId),
    onSuccess: async (workflow, workflowId) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflows.detail(workflowId) });
      await invalidateWorkflowScope(queryClient, workflow.id, workflow.version);
    },
  });
}

export function useCreateWorkflowRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ payload, version, workflowId }: CreateWorkflowRunVariables) => {
      return createWorkflowRun(workflowId, payload, { version });
    },
    onSuccess: async (run) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.all });
      await queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.detail(run.id) });
    },
  });
}
