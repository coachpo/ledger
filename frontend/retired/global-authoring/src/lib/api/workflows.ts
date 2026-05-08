import { requestPlatform, toPathSegment, toQueryRecord, type IdParam } from "../api-client";
import type {
  WorkflowCreateInput,
  WorkflowLaunchCreateInput,
  WorkflowLaunchCreateResponse,
  WorkflowLaunchRead,
  WorkflowListParams,
  WorkflowListRead,
  WorkflowManifestValidationInput,
  WorkflowManifestValidationRead,
  WorkflowRead,
  WorkflowUpdateInput,
  WorkflowVersionRead,
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

export function validateWorkflowManifest(
  payload: WorkflowManifestValidationInput,
  signal?: AbortSignal,
): Promise<WorkflowManifestValidationRead> {
  return requestPlatform<WorkflowManifestValidationRead>("/workflows/validate-manifest", {
    body: payload,
    method: "POST",
    signal,
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

export function getWorkflowLaunch(
  workflowId: IdParam,
  options: { signal?: AbortSignal; version?: number } = {},
): Promise<WorkflowLaunchRead> {
  return requestPlatform<WorkflowLaunchRead>(`${workflowPath(workflowId)}/launch`, {
    query: toQueryRecord({ version: options.version }),
    signal: options.signal,
  });
}

export function listWorkflowVersions(
  workflowId: IdParam,
  signal?: AbortSignal,
): Promise<{ items: WorkflowVersionRead[] }> {
  return requestPlatform<{ items: WorkflowVersionRead[] }>(`${workflowPath(workflowId)}/versions`, {
    signal,
  });
}

export function createWorkflowLaunch(
  workflowId: IdParam,
  payload: WorkflowLaunchCreateInput,
  signal?: AbortSignal,
): Promise<WorkflowLaunchCreateResponse> {
  return requestPlatform<WorkflowLaunchCreateResponse>(`${workflowPath(workflowId)}/launches`, {
    body: payload,
    method: "POST",
    signal,
  });
}

export const workflowsApi = {
  archive: archiveWorkflow,
  create: createWorkflow,
  createLaunch: createWorkflowLaunch,
  get: getWorkflow,
  getLaunch: getWorkflowLaunch,
  list: listWorkflows,
  listVersions: listWorkflowVersions,
  update: updateWorkflow,
  validateManifest: validateWorkflowManifest,
} as const;
