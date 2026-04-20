import { requestPlatform, toPathSegment, toQueryRecord, type IdParam } from "../api-client";
import type {
  AgentCreateInput,
  AgentListParams,
  AgentListRead,
  AgentRead,
  AgentTestPanelRead,
  AgentTestPanelRequest,
  AgentUpdateInput,
} from "../types/agent";

function agentPath(agentId: IdParam): string {
  return `/agents/${toPathSegment(agentId)}`;
}

export function listAgents(
  params?: AgentListParams,
  signal?: AbortSignal,
): Promise<AgentListRead> {
  return requestPlatform<AgentListRead>("/agents", {
    query: toQueryRecord(params),
    signal,
  });
}

export function getAgent(
  agentId: IdParam,
  options: { signal?: AbortSignal; version?: number } = {},
): Promise<AgentRead> {
  return requestPlatform<AgentRead>(agentPath(agentId), {
    query: toQueryRecord({ version: options.version }),
    signal: options.signal,
  });
}

export function createAgent(
  payload: AgentCreateInput,
  signal?: AbortSignal,
): Promise<AgentRead> {
  return requestPlatform<AgentRead>("/agents", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function updateAgent(
  agentId: IdParam,
  payload: AgentUpdateInput,
  signal?: AbortSignal,
): Promise<AgentRead> {
  return requestPlatform<AgentRead>(agentPath(agentId), {
    body: payload,
    method: "POST",
    signal,
  });
}

export function archiveAgent(agentId: IdParam, signal?: AbortSignal): Promise<AgentRead> {
  return requestPlatform<AgentRead>(agentPath(agentId), {
    method: "DELETE",
    signal,
  });
}

export function resolveAgentTestPanel(
  agentId: IdParam,
  payload: AgentTestPanelRequest,
  options: { signal?: AbortSignal; version?: number } = {},
): Promise<AgentTestPanelRead> {
  return requestPlatform<AgentTestPanelRead>(`${agentPath(agentId)}/test-panel`, {
    body: payload,
    method: "POST",
    query: toQueryRecord({ version: options.version }),
    signal: options.signal,
  });
}

export const agentsApi = {
  archive: archiveAgent,
  create: createAgent,
  get: getAgent,
  list: listAgents,
  resolveTestPanel: resolveAgentTestPanel,
  update: updateAgent,
} as const;
