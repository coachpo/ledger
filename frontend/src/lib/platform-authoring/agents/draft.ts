import type {
  AgentAuthoringBindingRefs,
  AgentAuthoringCreateInput,
  AgentAuthoringDraft,
  AgentAuthoringUpdateInput,
} from "./types";
import type { AgentRead } from "@/lib/types/agent";
import type { SchemaIRBuilderInput } from "../schema/types";
import type { ResourceRef } from "../common/resource-ref";

function createEmptyResourceRef(): ResourceRef {
  return { key: "", version: null };
}

function createEmptyBindingRefs(): AgentAuthoringBindingRefs {
  return {
    outputSchema: createEmptyResourceRef(),
    skills: [],
    mcpServers: [],
  };
}

function createResourceRef(ref: ResourceRef): ResourceRef {
  return { key: ref.key, version: ref.version };
}

export function createInitialAgentDraft(): AgentAuthoringDraft {
  return {
    key: "",
    name: "",
    description: "",
    modelConnectionId: "",
    systemPrompt: "",
    inputSchema: {} as unknown as SchemaIRBuilderInput,
    bindings: createEmptyBindingRefs(),
    maxToolRounds: "",
    budgetUsd: "",
    streaming: true,
  };
}

function bindingsFromRead(agent: AgentRead): AgentAuthoringBindingRefs {
  return {
    outputSchema: createResourceRef({ key: agent.outputSchema.key, version: agent.outputSchema.version }),
    skills: agent.skills.map((skill) => createResourceRef({ key: skill.key, version: skill.version })),
    mcpServers: agent.mcpServers.map((server) =>
      createResourceRef({ key: server.key, version: server.version }),
    ),
  };
}

export function agentDraftFromRead(agent: AgentRead): AgentAuthoringDraft {
  return {
    key: agent.key,
    name: agent.name,
    description: agent.description ?? "",
    modelConnectionId: String(agent.modelConnectionId),
    systemPrompt: agent.systemPrompt,
    inputSchema: agent.inputSchema as unknown as SchemaIRBuilderInput,
    bindings: bindingsFromRead(agent),
    maxToolRounds: String(agent.maxToolRounds),
    budgetUsd: agent.budgetUsd,
    streaming: agent.streaming,
  };
}

function bindingsToCreateInput(bindings: AgentAuthoringBindingRefs): AgentAuthoringBindingRefs {
  return {
    outputSchema: createResourceRef(bindings.outputSchema),
    skills: bindings.skills.map((skill) => createResourceRef(skill)),
    mcpServers: bindings.mcpServers.map((server) => createResourceRef(server)),
  };
}

function bindingsToUpdateInput(bindings: AgentAuthoringBindingRefs): AgentAuthoringBindingRefs {
  return bindingsToCreateInput(bindings);
}

export function agentDraftToCreateInput(draft: AgentAuthoringDraft): AgentAuthoringCreateInput {
  return {
    budgetUsd: draft.budgetUsd.trim() || undefined,
    description: draft.description.trim() || undefined,
    inputSchema: draft.inputSchema,
    key: draft.key.trim().toLowerCase(),
    maxToolRounds: draft.maxToolRounds.trim() ? Number(draft.maxToolRounds) : undefined,
    modelConnectionId: Number(draft.modelConnectionId),
    name: draft.name.trim(),
    streaming: draft.streaming,
    systemPrompt: draft.systemPrompt.trim(),
    ...bindingsToCreateInput(draft.bindings),
  };
}

export function agentDraftToUpdateInput(draft: AgentAuthoringDraft): AgentAuthoringUpdateInput {
  return {
    budgetUsd: draft.budgetUsd.trim() || undefined,
    description: draft.description.trim() || undefined,
    inputSchema: draft.inputSchema,
    maxToolRounds: draft.maxToolRounds.trim() ? Number(draft.maxToolRounds) : undefined,
    modelConnectionId: Number(draft.modelConnectionId),
    name: draft.name.trim(),
    streaming: draft.streaming,
    systemPrompt: draft.systemPrompt.trim(),
    ...bindingsToUpdateInput(draft.bindings),
  };
}

export function agentDraftBindingsFromResourceRefs(
  outputSchema: ResourceRef,
  skills: ResourceRef[],
  mcpServers: ResourceRef[],
): AgentAuthoringBindingRefs {
  return {
    outputSchema,
    skills,
    mcpServers,
  };
}
