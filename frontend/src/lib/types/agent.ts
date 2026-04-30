import type { UnknownRecord } from "./common";
import type { CapabilityRead } from "./capability";
import type { McpClientBoundaryRead, McpServerStatus, McpServerTransport } from "./mcp-server";
import type { ModelConnectionListItemRead } from "./model-connection";
import type { OutputSchemaRead } from "./output-schema";

export type AgentStatus = "draft" | "published" | "deprecated" | "archived";
export type AgentManifestApiVersion = "ledger.agent/v1";
export type AgentManifestDiagnosticSeverity = "error" | "warning";

export interface AgentCapabilityRefWrite {
  capabilityKey: string;
  capabilityVersion?: number | null;
}

export interface AgentMcpServerRefWrite {
  mcpServerKey: string;
  mcpServerVersion?: number | null;
}

export interface AgentCompiledCreateInput {
  key: string;
  name: string;
  description?: string;
  modelConnectionId: number;
  systemPrompt: string;
  inputSchema: UnknownRecord;
  outputSchemaKey: string;
  outputSchemaVersion?: number | null;
  capabilities?: AgentCapabilityRefWrite[];
  mcpServers?: AgentMcpServerRefWrite[];
  budgetUsd?: string;
}

export type AgentCompiledUpdateInput = Omit<AgentCompiledCreateInput, "key">;

export interface AgentManifestWriteInput {
  manifestSource: string;
}

export type AgentManifestCreateInput = AgentManifestWriteInput;
export type AgentManifestUpdateInput = AgentManifestWriteInput;
export type AgentCreateInput = AgentManifestCreateInput;
export type AgentUpdateInput = AgentManifestUpdateInput;

export interface AgentManifestDiagnostic {
  severity: AgentManifestDiagnosticSeverity;
  message: string;
  path: string;
  line: number | null;
  column: number | null;
}

export interface AgentManifestValidationMetadata {
  apiVersion: AgentManifestApiVersion;
  key: string;
  name: string;
  description: string;
}

export type AgentManifestValidationInput = AgentManifestWriteInput;

export interface AgentManifestValidationRead {
  diagnostics: AgentManifestDiagnostic[];
  metadata: AgentManifestValidationMetadata | null;
  compiledPayload: AgentCompiledCreateInput | null;
  runInputSchema: UnknownRecord | null;
}

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
  manifestApiVersion: AgentManifestApiVersion;
  manifestSource: string;
  manifestHash: string;
  compilerVersion: string;
  modelConnectionId: number;
  modelConnection: ModelConnectionListItemRead;
  systemPrompt: string;
  inputSchema: UnknownRecord;
  outputSchema: OutputSchemaRead;
  capabilities: CapabilityRead[];
  mcpServers: AgentMcpServerRead[];
  budgetUsd: string;
  createdAt: string;
  updatedAt: string;
}

export interface AgentListRead {
  items: AgentRead[];
}

export interface AgentListParams {
  status?: AgentStatus;
}

export type AgentRunCreateInput = UnknownRecord;
