import type { SchemaIRBuilderInput } from "../schema/types";
import type { ResourceRef } from "../common/resource-ref";
import type {
  AgentCreateInput,
  AgentRead,
  AgentStatus,
  AgentUpdateInput,
} from "@/lib/types/agent";

export type AgentAuthoringSchemaInput = SchemaIRBuilderInput;
export type AgentAuthoringResourceRef = ResourceRef;

export interface AgentAuthoringBindingRefs {
  outputSchema: AgentAuthoringResourceRef;
  skills: AgentAuthoringResourceRef[];
  mcpServers: AgentAuthoringResourceRef[];
}

export interface AgentAuthoringDraft {
  key: string;
  name: string;
  description: string;
  modelConnectionId: string;
  systemPrompt: string;
  inputSchema: AgentAuthoringSchemaInput;
  bindings: AgentAuthoringBindingRefs;
  maxToolRounds: string;
  budgetUsd: string;
  streaming: boolean;
}

export type AgentAuthoringCreateInput = Omit<
  AgentCreateInput,
  "inputSchema" | "outputSchemaKey" | "outputSchemaVersion" | "skills" | "mcpServers"
> &
  AgentAuthoringBindingRefs & {
    inputSchema: AgentAuthoringSchemaInput;
  };

export type AgentAuthoringUpdateInput = Omit<
  AgentUpdateInput,
  "inputSchema" | "outputSchemaKey" | "outputSchemaVersion" | "skills" | "mcpServers"
> &
  AgentAuthoringBindingRefs & {
    inputSchema: AgentAuthoringSchemaInput;
  };

export interface AgentAuthoringSnapshot {
  agent: AgentRead;
  draft: AgentAuthoringDraft;
}

export type AgentAuthoringStatus = AgentStatus;
