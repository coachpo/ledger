import type { AgentRead } from "@/lib/types/agent";

import { parseJsonValue, parseRequiredText } from "@/pages/platform-resource-shared";

import { createPlatformAuthoringIssue } from "../common/issues";
import { joinFieldPath, type FieldPath } from "../common/field-path";
import type {
  WorkflowDraft,
  WorkflowDraftAgent,
  WorkflowDraftStep,
  WorkflowJsonSchema,
  WorkflowValidationIssue,
  WireBinding,
} from "./types";

export type { WorkflowValidationIssue };
export type WorkflowValidationIssues = WorkflowValidationIssue[];

interface StepSlotMetadata {
  optional: boolean;
  outputSchema: unknown;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function getTypeName(schema: unknown): string | undefined {
  const record = asRecord(schema);
  if (!record) {
    return undefined;
  }

  const type = record.type;
  if (typeof type === "string") {
    return type;
  }

  if (Array.isArray(type)) {
    const value = type.find((entry): entry is string => typeof entry === "string" && entry !== "null");
    if (value) {
      return value;
    }
  }

  if (asRecord(record.properties)) {
    return "object";
  }

  return undefined;
}

export function getObjectProperties(schema: unknown): Record<string, WorkflowJsonSchema> {
  const record = asRecord(schema);
  const properties = record ? asRecord(record.properties) : undefined;
  if (!properties) {
    return {};
  }

  return Object.fromEntries(
    Object.entries(properties).filter((entry): entry is [string, WorkflowJsonSchema] =>
      Boolean(asRecord(entry[1])),
    ),
  );
}

export function getSchemaFieldNames(
  schema: unknown,
  wiring: Record<string, WireBinding>,
): string[] {
  return Array.from(new Set([...Object.keys(getObjectProperties(schema)), ...Object.keys(wiring)])).sort(
    (left, right) => left.localeCompare(right),
  );
}

function getRequiredFields(schema: unknown): Set<string> {
  const record = asRecord(schema);
  const required = record?.required;
  if (!Array.isArray(required)) {
    return new Set<string>();
  }

  return new Set(required.filter((entry): entry is string => typeof entry === "string"));
}

function resolveSchemaAtPath(schema: unknown, path: string): WorkflowJsonSchema | undefined {
  const trimmed = path.trim();
  const initial = asRecord(schema);
  if (!initial) {
    return undefined;
  }

  if (!trimmed) {
    return initial as WorkflowJsonSchema;
  }

  let current: Record<string, unknown> | undefined = initial;
  for (const segment of trimmed.split(".").map((part) => part.trim()).filter(Boolean)) {
    const properties = current ? getObjectProperties(current) : {};
    current = asRecord(properties[segment]);
    if (!current) {
      return undefined;
    }
  }

  return current as WorkflowJsonSchema;
}

function isTypeCompatible(sourceSchema: unknown, targetSchema: unknown): boolean {
  const sourceType = getTypeName(sourceSchema);
  const targetType = getTypeName(targetSchema);

  if (!sourceType || !targetType) {
    return true;
  }

  if (sourceType === targetType) {
    return true;
  }

  return sourceType === "integer" && targetType === "number";
}

function parsePositiveInteger(value: string, label: string): number | undefined {
  const trimmed = value.trim();

  if (!trimmed) {
    return undefined;
  }

  const parsed = Number(trimmed);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`${label} must be a positive whole number.`);
  }

  return parsed;
}

function createIssue(field: FieldPath, issue: string): WorkflowValidationIssue {
  return createPlatformAuthoringIssue(field, issue);
}

function createFieldPath(...segments: string[]): FieldPath {
  return segments.reduce<FieldPath>((path, segment) => joinFieldPath(path, segment), "");
}

function collectPriorSlots(
  steps: readonly WorkflowDraftStep[],
  agents: readonly AgentRead[],
  currentStepIndex: number,
): Map<number, Record<string, StepSlotMetadata>> {
  const result = new Map<number, Record<string, StepSlotMetadata>>();

  steps.slice(0, currentStepIndex).forEach((step, index) => {
    const slots = step.agents.reduce<Record<string, StepSlotMetadata>>((accumulator, agentDraft) => {
      const agent = findAgentByKey(agents, agentDraft.agentKey);
      const slot = agentDraft.slot.trim();
      if (agent && slot) {
        accumulator[slot] = {
          optional: agentDraft.optional,
          outputSchema: agent.outputSchema.jsonSchema,
        };
      }
      return accumulator;
    }, {});

    result.set(index + 1, slots);
  });

  return result;
}

function validateWiringEntry(props: {
  agents: readonly AgentRead[];
  draftInputSchema: unknown;
  fieldName: string;
  fieldPath: FieldPath;
  priorSlots: Map<number, Record<string, StepSlotMetadata>>;
  source: WireBinding;
  targetFieldSchema: unknown;
  targetIsRequired: boolean;
}) {
  const {
    agents,
    draftInputSchema,
    fieldName,
    fieldPath,
    priorSlots,
    source,
    targetFieldSchema,
    targetIsRequired,
  } = props;

  const issues: WorkflowValidationIssue[] = [];

  if (source.source === "none") {
    if (targetIsRequired) {
      issues.push(createIssue(fieldPath, `${fieldName} requires a wiring source`));
    }
    return issues;
  }

  const targetPath = source.pathTokens.join(".");

  if (source.source === "input") {
    const effectivePath = targetPath || fieldName;
    const sourceSchema = resolveSchemaAtPath(draftInputSchema, effectivePath);

    if (!sourceSchema) {
      issues.push(createIssue(fieldPath, `Input path '${effectivePath}' was not found`));
      return issues;
    }

    if (!isTypeCompatible(sourceSchema, targetFieldSchema)) {
      issues.push(createIssue(fieldPath, "Wired source type is not compatible with the target field schema"));
    }

    return issues;
  }

  const referencedStep = source.stepIndex ?? 0;
  if (!Number.isInteger(referencedStep) || referencedStep <= 0) {
    issues.push(createIssue(fieldPath, "Select an earlier step for this wiring source"));
    return issues;
  }

  const slots = priorSlots.get(referencedStep);
  const slotName = source.slot?.trim() ?? "";

  if (!slots || !slotName || !slots[slotName]) {
    issues.push(createIssue(fieldPath, `Slot '${slotName || "(empty)"}' was not found on step ${referencedStep}`));
    return issues;
  }

  const slotMetadata = slots[slotName];
  if (slotMetadata.optional && targetIsRequired) {
    issues.push(createIssue(fieldPath, "Optional slots can only wire into optional target fields"));
  }

  const sourceSchema = resolveSchemaAtPath(slotMetadata.outputSchema, targetPath);
  if (targetPath && !sourceSchema) {
    issues.push(createIssue(fieldPath, `Path '${targetPath}' was not found on slot '${slotName}'`));
    return issues;
  }

  if (!isTypeCompatible(sourceSchema ?? slotMetadata.outputSchema, targetFieldSchema)) {
    issues.push(createIssue(fieldPath, "Wired source type is not compatible with the target field schema"));
  }

  void agents;
  return issues;
}

function validateDraftAgent(props: {
  agents: readonly AgentRead[];
  currentStepIndex: number;
  draft: WorkflowDraft;
  fieldPrefix: string;
  draftAgent: WorkflowDraftAgent;
}) {
  const { agents, currentStepIndex, draft, draftAgent, fieldPrefix } = props;
  const issues: WorkflowValidationIssue[] = [];
  const agentKey = draftAgent.agentKey.trim();
  const slot = draftAgent.slot.trim();

  if (!agentKey) {
    issues.push(createIssue(createFieldPath(fieldPrefix, "agentKey"), "Select an agent"));
  }

  if (!slot) {
    issues.push(createIssue(createFieldPath(fieldPrefix, "slot"), "Slot is required"));
  }

  const resolvedAgent = findAgentByKey(agents, agentKey);
  const targetFields = getSchemaFieldNames(resolvedAgent?.inputSchema, draftAgent.wiring);
  const requiredFields = getRequiredFields(resolvedAgent?.inputSchema);
  const priorSlots = collectPriorSlots(draft.steps, agents, currentStepIndex);

  targetFields.forEach((fieldName) => {
    const source = draftAgent.wiring[fieldName] ?? { source: "none", stepIndex: null, slot: null, pathTokens: [] };
    const targetFieldSchema = getObjectProperties(resolvedAgent?.inputSchema)[fieldName];
    issues.push(
      ...validateWiringEntry({
        agents,
        draftInputSchema: parseJsonValue<WorkflowJsonSchema>("Input schema", draft.inputSchemaText, {}),
        fieldName,
        fieldPath: createFieldPath(fieldPrefix, "wiring", fieldName),
        priorSlots,
        source,
        targetFieldSchema,
        targetIsRequired: requiredFields.has(fieldName),
      }),
    );
  });

  if (draftAgent.agentVersion.trim()) {
    try {
      parsePositiveInteger(draftAgent.agentVersion, "Agent version");
    } catch (error) {
      issues.push(
        createIssue(
          createFieldPath(fieldPrefix, "agentVersion"),
          error instanceof Error ? error.message : "Agent version is invalid",
        ),
      );
    }
  }

  return issues;
}

export function findAgentByKey(agents: readonly AgentRead[], key: string): AgentRead | undefined {
  return agents.find((agent) => agent.key === key.trim());
}

export function validateWorkflowDraft(
  draft: WorkflowDraft,
  agents: readonly AgentRead[],
): WorkflowValidationIssue[] {
  const issues: WorkflowValidationIssue[] = [];

  try {
    parseRequiredText("Key", draft.key);
  } catch (error) {
    issues.push(createIssue("key", error instanceof Error ? error.message : "Key is required"));
  }

  try {
    parseRequiredText("Name", draft.name);
  } catch (error) {
    issues.push(createIssue("name", error instanceof Error ? error.message : "Name is required"));
  }

  try {
    parseJsonValue<WorkflowJsonSchema>("Input schema", draft.inputSchemaText, {});
  } catch (error) {
    issues.push(
      createIssue(
        "inputSchema",
        error instanceof Error ? error.message : "Input schema must be valid JSON",
      ),
    );
  }

  if (draft.steps.length === 0) {
    issues.push(createIssue("steps", "At least one step is required"));
  }

  draft.steps.forEach((step, stepIndex) => {
    const fieldPrefix = `steps[${stepIndex}]`;
    if (step.agents.length === 0) {
      issues.push(createIssue(createFieldPath(fieldPrefix, "agents"), "Add at least one agent to the step"));
      return;
    }

    const seenSlots = new Set<string>();
    step.agents.forEach((agent, agentIndex) => {
      const slot = agent.slot.trim();
      if (slot) {
        if (seenSlots.has(slot)) {
          issues.push(
            createIssue(
              `steps[${stepIndex}].agents[${agentIndex}].slot`,
              "Duplicate slot name within the same step",
            ),
          );
        }
        seenSlots.add(slot);
      }

      issues.push(
        ...validateDraftAgent({
          agents,
          currentStepIndex: stepIndex,
          draft,
          draftAgent: agent,
          fieldPrefix: `steps[${stepIndex}].agents[${agentIndex}]`,
        }),
      );
    });
  });

  const outputStep = Number(draft.output.stepIndex.trim());
  const slotName = draft.output.slot.trim();

  if (!Number.isInteger(outputStep) || outputStep <= 0) {
    issues.push(createIssue("outputSpec.stepIndex", "Select an output step"));
  } else {
    const slots = collectPriorSlots(draft.steps, agents, draft.steps.length + 1).get(outputStep);
    if (!slots || !slotName || !slots[slotName]) {
      issues.push(
        createIssue(
          "outputSpec.slot",
          `Slot '${slotName || "(empty)"}' was not found on step ${outputStep}`,
        ),
      );
    }
  }

  return issues;
}

export function isWorkflowValidationIssue(issue: unknown): issue is WorkflowValidationIssue {
  return Boolean(issue && typeof issue === "object" && "field" in issue && "issue" in issue);
}
