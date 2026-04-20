import { requestPlatform, toPathSegment, toQueryRecord, type IdParam } from "../api-client";
import type {
  McpServerConnectionTestRead,
  McpServerCreateInput,
  McpServerListParams,
  McpServerListRead,
  McpServerRead,
  McpServerUpdateInput,
} from "../types/mcp-server";

function mcpServerPath(serverId: IdParam): string {
  return `/mcp-servers/${toPathSegment(serverId)}`;
}

export function listMcpServers(
  params?: McpServerListParams,
  signal?: AbortSignal,
): Promise<McpServerListRead> {
  return requestPlatform<McpServerListRead>("/mcp-servers", {
    query: toQueryRecord(params),
    signal,
  });
}

export function getMcpServer(
  serverId: IdParam,
  signal?: AbortSignal,
): Promise<McpServerRead> {
  return requestPlatform<McpServerRead>(mcpServerPath(serverId), { signal });
}

export function createMcpServer(
  payload: McpServerCreateInput,
  signal?: AbortSignal,
): Promise<McpServerRead> {
  return requestPlatform<McpServerRead>("/mcp-servers", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function updateMcpServer(
  serverId: IdParam,
  payload: McpServerUpdateInput,
  signal?: AbortSignal,
): Promise<McpServerRead> {
  return requestPlatform<McpServerRead>(mcpServerPath(serverId), {
    body: payload,
    method: "PATCH",
    signal,
  });
}

export function activateMcpServer(
  serverId: IdParam,
  signal?: AbortSignal,
): Promise<McpServerRead> {
  return requestPlatform<McpServerRead>(`${mcpServerPath(serverId)}/activate`, {
    method: "POST",
    signal,
  });
}

export function testMcpServerConnection(
  serverId: IdParam,
  signal?: AbortSignal,
): Promise<McpServerConnectionTestRead> {
  return requestPlatform<McpServerConnectionTestRead>(`${mcpServerPath(serverId)}/connection-test`, {
    method: "POST",
    signal,
  });
}

export function archiveMcpServer(
  serverId: IdParam,
  signal?: AbortSignal,
): Promise<McpServerRead> {
  return requestPlatform<McpServerRead>(mcpServerPath(serverId), {
    method: "DELETE",
    signal,
  });
}

export const mcpServersApi = {
  activate: activateMcpServer,
  archive: archiveMcpServer,
  create: createMcpServer,
  get: getMcpServer,
  list: listMcpServers,
  testConnection: testMcpServerConnection,
  update: updateMcpServer,
} as const;
