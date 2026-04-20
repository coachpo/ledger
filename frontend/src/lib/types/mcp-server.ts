import type { UnknownRecord } from "./common";

export type McpServerStatus = "draft" | "published" | "deprecated" | "archived";
export type McpServerTransport = "stdio" | "http-sse";

export interface McpServerCreateInput {
  key: string;
  name: string;
  description?: string;
  transport: McpServerTransport;
  command?: string | null;
  url?: string | null;
  auth?: UnknownRecord;
  enabled?: boolean;
}

export interface McpServerUpdateInput {
  name?: string;
  description?: string;
  transport?: McpServerTransport;
  command?: string | null;
  url?: string | null;
  auth?: UnknownRecord;
  enabled?: boolean;
}

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
  name: string;
  description: string;
  transport: McpServerTransport;
  command: string | null;
  url: string | null;
  auth: UnknownRecord;
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface McpServerListRead {
  items: McpServerRead[];
}

export interface McpServerListParams {
  status?: McpServerStatus;
  enabled?: boolean;
  transport?: McpServerTransport;
}
