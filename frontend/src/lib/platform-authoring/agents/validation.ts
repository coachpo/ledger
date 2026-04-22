import { joinFieldPath, type FieldPath } from "../common/field-path";
import { createPlatformAuthoringIssue, type PlatformAuthoringIssue } from "../common/issues";
import type { ResourceRef } from "../common/resource-ref";
import type { AgentAuthoringBindingRefs, AgentAuthoringDraft } from "./types";

export type AgentValidationIssue = PlatformAuthoringIssue;
export type AgentValidationIssues = AgentValidationIssue[];

export const createAgentValidationIssue = createPlatformAuthoringIssue;

export function joinAgentPath(path: FieldPath, segment: string): FieldPath {
  return joinFieldPath(path, segment);
}

function requiredText(label: string, value: string, field: FieldPath): AgentValidationIssue | null {
  if (value.trim()) {
    return null;
  }

  return createAgentValidationIssue(field, `${label} is required.`);
}

function optionalNumericText(
  label: string,
  value: string,
  field: FieldPath,
  props: { integer?: boolean; min?: number } = {},
): AgentValidationIssue | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed)) {
    return createAgentValidationIssue(field, `${label} must be a valid number.`);
  }

  if (props.integer && !Number.isInteger(parsed)) {
    return createAgentValidationIssue(field, `${label} must be a whole number.`);
  }

  if (typeof props.min === "number" && parsed < props.min) {
    return createAgentValidationIssue(field, `${label} must be greater than or equal to ${props.min}.`);
  }

  return null;
}

function validateResourceRef(ref: ResourceRef, field: FieldPath, label: string): AgentValidationIssue[] {
  const issues: AgentValidationIssue[] = [];

  if (!ref.key.trim()) {
    issues.push(createAgentValidationIssue(field, `${label} is required.`));
  }

  if (ref.version !== null && (!Number.isInteger(ref.version) || ref.version <= 0)) {
    issues.push(createAgentValidationIssue(field, `${label} version must be a positive whole number.`));
  }

  return issues;
}

function validateResourceRefList(
  label: string,
  refs: readonly ResourceRef[],
  field: FieldPath,
): AgentValidationIssue[] {
  return refs.flatMap((ref, index) => validateResourceRef(ref, joinAgentPath(field, `[${index}]`), label));
}

export function validateAgentBindingRefs(
  bindings: AgentAuthoringBindingRefs,
  field: FieldPath = "bindings",
): AgentValidationIssue[] {
  return [
    ...validateResourceRef(bindings.outputSchema, joinAgentPath(field, "outputSchema"), "Output schema"),
    ...validateResourceRefList("Skill", bindings.skills, joinAgentPath(field, "skills")),
    ...validateResourceRefList("MCP server", bindings.mcpServers, joinAgentPath(field, "mcpServers")),
  ];
}

export function validateAgentDraft(draft: AgentAuthoringDraft): AgentValidationIssue[] {
  const issues: AgentValidationIssue[] = [];

  const keyIssue = requiredText("Key", draft.key, "key");
  if (keyIssue) {
    issues.push(keyIssue);
  }

  const nameIssue = requiredText("Name", draft.name, "name");
  if (nameIssue) {
    issues.push(nameIssue);
  }

  const modelIssue = requiredText("Model", draft.model, "model");
  if (modelIssue) {
    issues.push(modelIssue);
  }

  const systemPromptIssue = requiredText("System prompt", draft.systemPrompt, "systemPrompt");
  if (systemPromptIssue) {
    issues.push(systemPromptIssue);
  }

  const temperatureIssue = optionalNumericText("Temperature", draft.temperature, "temperature", {
    min: 0,
  });
  if (temperatureIssue) {
    issues.push(temperatureIssue);
  }

  const maxToolRoundsIssue = optionalNumericText("Max tool rounds", draft.maxToolRounds, "maxToolRounds", {
    integer: true,
    min: 1,
  });
  if (maxToolRoundsIssue) {
    issues.push(maxToolRoundsIssue);
  }

  const outputSchemaIssue = validateResourceRef(
    draft.bindings.outputSchema,
    joinAgentPath("bindings", "outputSchema"),
    "Output schema",
  );
  issues.push(...outputSchemaIssue);
  issues.push(...validateResourceRefList("Skill", draft.bindings.skills, joinAgentPath("bindings", "skills")));
  issues.push(...validateResourceRefList("MCP server", draft.bindings.mcpServers, joinAgentPath("bindings", "mcpServers")));

  return issues;
}
