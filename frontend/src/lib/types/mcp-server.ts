export type McpServerStatus = "draft" | "published" | "deprecated" | "archived";
export type McpServerTransport = "stdio" | "http-sse";

export interface McpServerStdioConfig {
  name: string;
  description: string;
  enabled: boolean;
  transport: "stdio";
  command: string;
  args: string[];
  env: Record<string, string>;
}

export interface McpServerHttpSseConfig {
  name: string;
  description: string;
  enabled: boolean;
  transport: "http-sse";
  url: string;
  headers: Record<string, string>;
}

export type McpServerConfig = McpServerStdioConfig | McpServerHttpSseConfig;

export interface McpServerConfigEnvelope {
  mcpServers: Record<string, McpServerConfig>;
}

export type McpServerCreateInput = McpServerConfigEnvelope;
export type McpServerUpdateInput = McpServerConfigEnvelope;

export interface McpClientBoundaryRead {
  transport: McpServerTransport;
  command: string[] | null;
  url: string | null;
  headerNames: string[];
  envKeys: string[];
  enabled: boolean;
}

export interface McpServerConnectionTestRead {
  serverId: number;
  ok: boolean;
  message: string;
  boundary: McpClientBoundaryRead;
}

export interface McpServerRead {
  id: number;
  key: string;
  version: number;
  status: McpServerStatus;
  config: McpServerConfigEnvelope;
  createdAt: string;
  updatedAt: string;
}

export interface McpServerListItemRead {
  id: number;
  key: string;
  version: number;
  status: McpServerStatus;
  name: string;
  description: string;
  transport: McpServerTransport;
  enabled: boolean;
}

export interface McpServerListRead {
  items: McpServerListItemRead[];
}

export interface McpServerListParams {
  status?: McpServerStatus;
  enabled?: boolean;
  transport?: McpServerTransport;
}
