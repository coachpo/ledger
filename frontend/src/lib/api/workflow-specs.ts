import { type IdParam, type RequestQueryValue, requestV2, toPathSegment } from "../api-client";
import type {
  StudioSpecListParams,
  WorkflowSpecDraftCreateInput,
  WorkflowSpecDraftUpdateInput,
  WorkflowSpecListRead,
  WorkflowSpecRead,
} from "../types/studio";

function workflowSpecPath(specId: IdParam): string {
  return `/workflow-specs/${toPathSegment(specId)}`;
}

function toQueryRecord<T extends object>(
  params?: T,
): Record<string, RequestQueryValue> | undefined {
  return params as Record<string, RequestQueryValue> | undefined;
}

export function listWorkflowSpecs(
  params?: StudioSpecListParams,
  signal?: AbortSignal,
): Promise<WorkflowSpecListRead> {
  return requestV2<WorkflowSpecListRead>("/workflow-specs", {
    query: toQueryRecord(params),
    signal,
  });
}

export function getWorkflowSpec(
  specId: IdParam,
  signal?: AbortSignal,
): Promise<WorkflowSpecRead> {
  return requestV2<WorkflowSpecRead>(workflowSpecPath(specId), { signal });
}

export function createWorkflowSpec(
  payload: WorkflowSpecDraftCreateInput,
  signal?: AbortSignal,
): Promise<WorkflowSpecRead> {
  return requestV2<WorkflowSpecRead>("/workflow-specs", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function updateWorkflowSpec(
  specId: IdParam,
  payload: WorkflowSpecDraftUpdateInput,
  signal?: AbortSignal,
): Promise<WorkflowSpecRead> {
  return requestV2<WorkflowSpecRead>(workflowSpecPath(specId), {
    body: payload,
    method: "PATCH",
    signal,
  });
}

export function activateWorkflowSpec(
  specId: IdParam,
  signal?: AbortSignal,
): Promise<WorkflowSpecRead> {
  return requestV2<WorkflowSpecRead>(`${workflowSpecPath(specId)}/activate`, {
    method: "POST",
    signal,
  });
}

export function deprecateWorkflowSpec(
  specId: IdParam,
  signal?: AbortSignal,
): Promise<WorkflowSpecRead> {
  return requestV2<WorkflowSpecRead>(`${workflowSpecPath(specId)}/deprecate`, {
    method: "POST",
    signal,
  });
}

export function archiveWorkflowSpec(
  specId: IdParam,
  signal?: AbortSignal,
): Promise<WorkflowSpecRead> {
  return requestV2<WorkflowSpecRead>(`${workflowSpecPath(specId)}/archive`, {
    method: "POST",
    signal,
  });
}

export const workflowSpecsApi = {
  list: listWorkflowSpecs,
  get: getWorkflowSpec,
  create: createWorkflowSpec,
  update: updateWorkflowSpec,
  activate: activateWorkflowSpec,
  deprecate: deprecateWorkflowSpec,
  archive: archiveWorkflowSpec,
} as const;
