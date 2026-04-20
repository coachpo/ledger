import { requestPlatform, toPathSegment, toQueryRecord, type IdParam } from "../api-client";
import type { RunCreatedRead } from "../types/run";
import type {
  WorkflowCreateInput,
  WorkflowListParams,
  WorkflowListRead,
  WorkflowRead,
  WorkflowRunCreateInput,
  WorkflowUpdateInput,
} from "../types/workflow";

function workflowPath(workflowId: IdParam): string {
  return `/workflows/${toPathSegment(workflowId)}`;
}

export function listWorkflows(
  params?: WorkflowListParams,
  signal?: AbortSignal,
): Promise<WorkflowListRead> {
  return requestPlatform<WorkflowListRead>("/workflows", {
    query: toQueryRecord(params),
    signal,
  });
}

export function getWorkflow(
  workflowId: IdParam,
  options: { signal?: AbortSignal; version?: number } = {},
): Promise<WorkflowRead> {
  return requestPlatform<WorkflowRead>(workflowPath(workflowId), {
    query: toQueryRecord({ version: options.version }),
    signal: options.signal,
  });
}

export function createWorkflow(
  payload: WorkflowCreateInput,
  signal?: AbortSignal,
): Promise<WorkflowRead> {
  return requestPlatform<WorkflowRead>("/workflows", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function updateWorkflow(
  workflowId: IdParam,
  payload: WorkflowUpdateInput,
  signal?: AbortSignal,
): Promise<WorkflowRead> {
  return requestPlatform<WorkflowRead>(workflowPath(workflowId), {
    body: payload,
    method: "POST",
    signal,
  });
}

export function archiveWorkflow(
  workflowId: IdParam,
  signal?: AbortSignal,
): Promise<WorkflowRead> {
  return requestPlatform<WorkflowRead>(workflowPath(workflowId), {
    method: "DELETE",
    signal,
  });
}

export function createWorkflowRun(
  workflowId: IdParam,
  payload: WorkflowRunCreateInput,
  options: { signal?: AbortSignal; version?: number } = {},
): Promise<RunCreatedRead> {
  return requestPlatform<RunCreatedRead>(`${workflowPath(workflowId)}/runs`, {
    body: payload,
    method: "POST",
    query: toQueryRecord({ version: options.version }),
    signal: options.signal,
  });
}

export const workflowsApi = {
  archive: archiveWorkflow,
  create: createWorkflow,
  createRun: createWorkflowRun,
  get: getWorkflow,
  list: listWorkflows,
  update: updateWorkflow,
} as const;
