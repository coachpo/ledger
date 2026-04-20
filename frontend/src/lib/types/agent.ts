import type { UnknownRecord } from "./common";
import type { McpClientBoundaryRead, McpServerStatus, McpServerTransport } from "./mcp-server";
import type { OutputSchemaRead } from "./output-schema";
import type { SkillRead } from "./skill";

export type AgentStatus = "draft" | "published" | "deprecated" | "archived";

export interface AgentSkillRefWrite {
  skillKey: string;
  skillVersion?: number | null;
}

export interface AgentMcpServerRefWrite {
  mcpServerKey: string;
  mcpServerVersion?: number | null;
}

export interface AgentCreateInput {
  key: string;
  name: string;
  description?: string;
  model: string;
  systemPrompt: string;
  inputSchema: UnknownRecord;
  outputSchemaKey: string;
  outputSchemaVersion?: number | null;
  skills?: AgentSkillRefWrite[];
  mcpServers?: AgentMcpServerRefWrite[];
  temperature?: number;
  maxToolRounds?: number;
  budgetUsd?: string;
  streaming?: boolean;
}

export type AgentUpdateInput = Omit<AgentCreateInput, "key">;

export interface AgentMcpServerRead {
  id: number;
  key: string;
  version: number;
  status: McpServerStatus;
  name: string;
  description: string;
  transport: McpServerTransport;
  enabled: boolean;
  boundary: McpClientBoundaryRead;
}

export interface AgentRead {
  id: number;
  key: string;
  version: number;
  status: AgentStatus;
  name: string;
  description: string;
  model: string;
  systemPrompt: string;
  inputSchema: UnknownRecord;
  outputSchema: OutputSchemaRead;
  skills: SkillRead[];
  mcpServers: AgentMcpServerRead[];
  temperature: number;
  maxToolRounds: number;
  budgetUsd: string;
  streaming: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface AgentListRead {
  items: AgentRead[];
}

export interface AgentListParams {
  status?: AgentStatus;
  model?: string;
}

export interface AgentTestPanelRequest {
  sampleInput?: UnknownRecord;
}

export interface AgentTestPanelRead {
  agent: AgentRead;
  sampleInput: UnknownRecord;
}
