import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  archiveAgent,
  createAgentRun,
  createAgent,
  getAgent,
  listAgents,
  updateAgent,
} from "@/lib/api/agents";
import type { IdParam } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type { AgentCreateInput, AgentListParams, AgentRunCreateInput, AgentUpdateInput } from "@/lib/types/agent";

type UpdateAgentVariables = {
  agentId: IdParam;
  payload: AgentUpdateInput;
};

type CreateAgentRunVariables = {
  agentId: IdParam;
  payload: AgentRunCreateInput;
  version?: number;
};

function invalidateAgentScope(queryClient: QueryClient, agentId: IdParam, version?: number) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.agents.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.agents.detail(agentId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.agents.detail(agentId, version) }),
  ]);
}

export function useAgents(params: AgentListParams = {}) {
  return useQuery({
    queryKey: queryKeys.platform.agents.list(params),
    queryFn: ({ signal }) => listAgents(params, signal),
  });
}

export function useAgent(agentId: IdParam | undefined, version?: number) {
  const resolvedAgentId = agentId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.agents.detail(resolvedAgentId, version),
    queryFn: ({ signal }) => getAgent(resolvedAgentId, { signal, version }),
    enabled: Boolean(agentId),
  });
}

export function useCreateAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: AgentCreateInput) => createAgent(payload),
    onSuccess: async (agent) => {
      await invalidateAgentScope(queryClient, agent.id, agent.version);
    },
  });
}

export function useUpdateAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ agentId, payload }: UpdateAgentVariables) => updateAgent(agentId, payload),
    onSuccess: async (agent, { agentId }) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.platform.agents.detail(agentId) });
      await invalidateAgentScope(queryClient, agent.id, agent.version);
    },
  });
}

export function useArchiveAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (agentId: IdParam) => archiveAgent(agentId),
    onSuccess: async (agent, agentId) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.platform.agents.detail(agentId) });
      await invalidateAgentScope(queryClient, agent.id, agent.version);
    },
  });
}

export function useCreateAgentRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ agentId, payload, version }: CreateAgentRunVariables) => {
      return createAgentRun(agentId, payload, { version });
    },
    onSuccess: async (run) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.all });
      await queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.detail(run.id) });
    },
  });
}
