import { type IdParam, type RequestQueryValue, requestV2, toPathSegment } from "../api-client";
import type {
  AgentSpecDraftCreateInput,
  AgentSpecDraftUpdateInput,
  AgentSpecListRead,
  AgentSpecRead,
  StudioSpecListParams,
} from "../types/studio";

function agentSpecPath(specId: IdParam): string {
  return `/agent-specs/${toPathSegment(specId)}`;
}

function toQueryRecord<T extends object>(
  params?: T,
): Record<string, RequestQueryValue> | undefined {
  return params as Record<string, RequestQueryValue> | undefined;
}

export function listAgentSpecs(
  params?: StudioSpecListParams,
  signal?: AbortSignal,
): Promise<AgentSpecListRead> {
  return requestV2<AgentSpecListRead>("/agent-specs", {
    query: toQueryRecord(params),
    signal,
  });
}

export function getAgentSpec(specId: IdParam, signal?: AbortSignal): Promise<AgentSpecRead> {
  return requestV2<AgentSpecRead>(agentSpecPath(specId), { signal });
}

export function createAgentSpec(
  payload: AgentSpecDraftCreateInput,
  signal?: AbortSignal,
): Promise<AgentSpecRead> {
  return requestV2<AgentSpecRead>("/agent-specs", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function updateAgentSpec(
  specId: IdParam,
  payload: AgentSpecDraftUpdateInput,
  signal?: AbortSignal,
): Promise<AgentSpecRead> {
  return requestV2<AgentSpecRead>(agentSpecPath(specId), {
    body: payload,
    method: "PATCH",
    signal,
  });
}

export function activateAgentSpec(specId: IdParam, signal?: AbortSignal): Promise<AgentSpecRead> {
  return requestV2<AgentSpecRead>(`${agentSpecPath(specId)}/activate`, {
    method: "POST",
    signal,
  });
}

export function deprecateAgentSpec(specId: IdParam, signal?: AbortSignal): Promise<AgentSpecRead> {
  return requestV2<AgentSpecRead>(`${agentSpecPath(specId)}/deprecate`, {
    method: "POST",
    signal,
  });
}

export function archiveAgentSpec(specId: IdParam, signal?: AbortSignal): Promise<AgentSpecRead> {
  return requestV2<AgentSpecRead>(`${agentSpecPath(specId)}/archive`, {
    method: "POST",
    signal,
  });
}

export const agentSpecsApi = {
  list: listAgentSpecs,
  get: getAgentSpec,
  create: createAgentSpec,
  update: updateAgentSpec,
  activate: activateAgentSpec,
  deprecate: deprecateAgentSpec,
  archive: archiveAgentSpec,
} as const;
