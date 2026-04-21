import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  activateMcpServer,
  archiveMcpServer,
  createMcpServer,
  getMcpServer,
  listMcpServers,
  testMcpServerConnection,
  updateMcpServer,
} from "@/lib/api/mcp-servers";
import type { IdParam } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type {
  McpServerCreateInput,
  McpServerListParams,
  McpServerUpdateInput,
} from "@/lib/types/mcp-server";

type UpdateMcpServerVariables = {
  payload: McpServerUpdateInput;
  serverId: IdParam;
};

function invalidateMcpServerScope(queryClient: QueryClient, serverId: IdParam) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.mcpServers.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.mcpServers.detail(serverId) }),
  ]);
}

export function useMcpServers(params: McpServerListParams = {}) {
  return useQuery({
    queryKey: queryKeys.platform.mcpServers.list(params),
    queryFn: ({ signal }) => listMcpServers(params, signal),
  });
}

export function useMcpServer(serverId: IdParam | undefined) {
  const resolvedServerId = serverId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.mcpServers.detail(resolvedServerId),
    queryFn: ({ signal }) => getMcpServer(resolvedServerId, signal),
    enabled: Boolean(serverId),
  });
}

export function useCreateMcpServer() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: McpServerCreateInput) => createMcpServer(payload),
    onSuccess: async (server) => {
      await invalidateMcpServerScope(queryClient, server.id);
    },
  });
}

export function useUpdateMcpServer() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ payload, serverId }: UpdateMcpServerVariables) => updateMcpServer(serverId, payload),
    onSuccess: async (server) => {
      await invalidateMcpServerScope(queryClient, server.id);
    },
  });
}

export function useActivateMcpServer() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (serverId: IdParam) => activateMcpServer(serverId),
    onSuccess: async (server) => {
      await invalidateMcpServerScope(queryClient, server.id);
    },
  });
}

export function useArchiveMcpServer() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (serverId: IdParam) => archiveMcpServer(serverId),
    onSuccess: async (server, serverId) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.platform.mcpServers.detail(serverId) });
      await invalidateMcpServerScope(queryClient, server.id);
    },
  });
}

export function useTestMcpServerConnection(serverId: IdParam | undefined) {
  return useMutation({
    mutationFn: async () => {
      if (!serverId) {
        throw new Error("MCP server id is required to test the connection.");
      }

      return testMcpServerConnection(serverId);
    },
  });
}
