import type { SchemaIRBuilderInput } from "../schema/types";
import type { ResourceRef } from "../common/resource-ref";
import type { AgentRead } from "@/lib/types/agent";

import type {
  AgentAuthoringBindingRefs,
  AgentAuthoringCreateInput,
  AgentAuthoringDraft,
  AgentAuthoringUpdateInput,
} from "./types";

function cloneResourceRef(ref: ResourceRef): ResourceRef {
  return { key: ref.key, version: ref.version };
}

export function createEmptyAgentBindingRefs(): AgentAuthoringBindingRefs {
  return {
    outputSchema: { key: "", version: null },
    skills: [],
    mcpServers: [],
  };
}

export function agentBindingRefsFromRead(agent: AgentRead): AgentAuthoringBindingRefs {
  return {
    outputSchema: cloneResourceRef({ key: agent.outputSchema.key, version: agent.outputSchema.version }),
    skills: agent.skills.map((skill) => cloneResourceRef({ key: skill.key, version: skill.version })),
    mcpServers: agent.mcpServers.map((server) =>
      cloneResourceRef({ key: server.key, version: server.version }),
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
    bindings: agentBindingRefsFromRead(agent),
    budgetUsd: agent.budgetUsd,
  };
}

function toAgentWriteRefs(bindings: AgentAuthoringBindingRefs): AgentAuthoringBindingRefs {
  return {
    outputSchema: cloneResourceRef(bindings.outputSchema),
    skills: bindings.skills.map((skill) => cloneResourceRef(skill)),
    mcpServers: bindings.mcpServers.map((server) => cloneResourceRef(server)),
  };
}

function normalizeDraftKey(key: string): string {
  return key.trim().toLowerCase();
}

function toAuthoringCreateInput(draft: AgentAuthoringDraft): AgentAuthoringCreateInput {
  return {
    budgetUsd: draft.budgetUsd.trim() || undefined,
    description: draft.description.trim() || undefined,
    inputSchema: draft.inputSchema,
    key: normalizeDraftKey(draft.key),
    modelConnectionId: Number(draft.modelConnectionId),
    name: draft.name.trim(),
    systemPrompt: draft.systemPrompt.trim(),
    ...toAgentWriteRefs(draft.bindings),
  };
}

export function agentDraftToCreateInput(draft: AgentAuthoringDraft): AgentAuthoringCreateInput {
  return toAuthoringCreateInput(draft);
}

export function agentDraftToUpdateInput(draft: AgentAuthoringDraft): AgentAuthoringUpdateInput {
  const { key: _ignored, ...payload } = toAuthoringCreateInput(draft);

  return payload;
}

export function agentBindingsFromResourceRefs(
  outputSchema: ResourceRef,
  skills: ResourceRef[],
  mcpServers: ResourceRef[],
): AgentAuthoringBindingRefs {
  return {
    outputSchema: cloneResourceRef(outputSchema),
    skills: skills.map((skill) => cloneResourceRef(skill)),
    mcpServers: mcpServers.map((server) => cloneResourceRef(server)),
  };
}
