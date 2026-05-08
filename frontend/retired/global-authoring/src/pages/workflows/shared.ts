import type { AgentRead } from "@/lib/types/agent";
import type { UnknownRecord } from "@/lib/types/common";
import type {
  WorkflowCreateInput,
  WorkflowRead,
  WorkflowStepAgentWrite,
  WorkflowWireSource,
} from "@/lib/types/workflow";

import {
  parseJsonValue,
  parseRequiredText,
} from "../platform-resource-shared";

type JsonSchema = UnknownRecord;

type SourceKind = "none" | "input" | "step";

export type WorkflowSection = "input" | "steps" | "output" | "review";

export const WORKFLOW_SECTIONS: { description: string; title: string; value: WorkflowSection }[] = [
  {
    description: "Define the workflow identity and request contract.",
    title: "Input",
    value: "input",
  },
  {
    description: "Pin agents by version and wire step slots.",
    title: "Steps",
    value: "steps",
  },
  {
    description: "Choose the final output slot. Add another final step if you need one more agent invocation.",
    title: "Output",
    value: "output",
  },
  {
    description: "Validate the draft, save it, and run it.",
    title: "Review",
    value: "review",
  },
];

export type WorkflowValidationIssue = {
  field: string;
  issue: string;
};

export type WiringSourceDraft = {
  from: SourceKind;
  path: string;
  slot: string;
  stepIndex: string;
};

export type WorkflowDraftAgent = {
  id: string;
  agentKey: string;
  agentVersion: string;
  optional: boolean;
  slot: string;
  wiring: Record<string, WiringSourceDraft>;
};

export type WorkflowDraftStep = {
  agents: WorkflowDraftAgent[];
  id: string;
};

export type WorkflowDraftOutput = {
  kind: "slot";
  path: string;
  slot: string;
  stepIndex: string;
};

export type WorkflowDraft = {
  description: string;
  inputSchemaText: string;
  key: string;
  name: string;
  output: WorkflowDraftOutput;
  steps: WorkflowDraftStep[];
};

function createDraftId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

function createEmptyWiringSource(): WiringSourceDraft {
  return { from: "none", path: "", slot: "", stepIndex: "" };
}

export function createEmptyWorkflowAgent(): WorkflowDraftAgent {
  return {
    id: createDraftId("agent"),
    agentKey: "",
    agentVersion: "",
    optional: false,
    slot: "",
    wiring: {},
  };
}

export function createEmptyWorkflowStep(): WorkflowDraftStep {
  return {
    agents: [createEmptyWorkflowAgent()],
    id: createDraftId("step"),
  };
}

export function createInitialWorkflowDraft(): WorkflowDraft {
  return {
    description: "",
    inputSchemaText: JSON.stringify(
      {
        type: "object",
        properties: {
          ticker: {
            type: "string",
            title: "Ticker",
            description: "Ticker symbol to research, such as AAPL.",
          },
        },
        required: ["ticker"],
      },
      null,
      2,
    ),
    key: "",
    name: "",
    output: { kind: "slot", path: "", slot: "", stepIndex: "1" },
    steps: [createEmptyWorkflowStep()],
  };
}

function sourceDraftFromRead(source?: WorkflowWireSource): WiringSourceDraft {
  if (!source) {
    return createEmptyWiringSource();
  }

  return {
    from: source.from,
    path: source.path ?? "",
    slot: source.slot ?? "",
    stepIndex: source.stepIndex ? String(source.stepIndex) : "",
  };
}

export function workflowDraftFromRead(workflow: WorkflowRead): WorkflowDraft {
  return {
    description: workflow.description ?? "",
    inputSchemaText: JSON.stringify(workflow.inputSchema, null, 2),
    key: workflow.key,
    name: workflow.name,
    output: {
      kind: "slot",
      path: workflow.outputSpec.path ?? "",
      slot: workflow.outputSpec.slot,
      stepIndex: String(workflow.outputSpec.stepIndex),
    },
    steps: workflow.steps.map((step) => ({
      agents: step.agents.map((agent) => ({
        id: createDraftId(`agent-${step.index}`),
        agentKey: agent.agentKey,
        agentVersion: String(agent.agentVersion),
        optional: agent.optional,
        slot: agent.slot,
        wiring: Object.fromEntries(
          Object.entries(agent.wiring).map(([field, source]) => [
            field,
            sourceDraftFromRead(source),
          ]),
        ),
      })),
      id: createDraftId(`step-${step.index}`),
    })),
  };
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

function toWireSourceWrite(source: WiringSourceDraft): WorkflowWireSource | undefined {
  if (source.from === "none") {
    return undefined;
  }

  if (source.from === "input") {
    return {
      from: "input",
      path: source.path.trim() || undefined,
    };
  }

  return {
    from: "step",
    path: source.path.trim() || undefined,
    slot: source.slot.trim() || undefined,
    stepIndex: parsePositiveInteger(source.stepIndex, "Referenced step"),
  };
}

function buildStepAgent(agent: WorkflowDraftAgent): WorkflowStepAgentWrite {
  const wiringEntries = Object.entries(agent.wiring)
    .map(([field, source]) => [field, toWireSourceWrite(source)] as const)
    .filter((entry): entry is readonly [string, WorkflowWireSource] => Boolean(entry[1]));

  return {
    agentKey: parseRequiredText("Agent", agent.agentKey),
    agentVersion: parsePositiveInteger(agent.agentVersion, "Agent version") ?? null,
    optional: agent.optional,
    slot: parseRequiredText("Slot", agent.slot),
    wiring: wiringEntries.length > 0 ? Object.fromEntries(wiringEntries) : undefined,
  };
}

export function buildWorkflowPayload(draft: WorkflowDraft): WorkflowCreateInput {
  const inputSchema = parseJsonValue<JsonSchema>("Input schema", draft.inputSchemaText, {});
  const outputSpec: WorkflowCreateInput["outputSpec"] = {
    kind: "slot",
    path: draft.output.path.trim() || undefined,
    slot: parseRequiredText("Output slot", draft.output.slot),
    stepIndex: parsePositiveInteger(draft.output.stepIndex, "Output step") ?? 1,
  };

  return {
    description: draft.description.trim() || undefined,
    inputSchema,
    key: parseRequiredText("Key", draft.key).toLowerCase(),
    name: parseRequiredText("Name", draft.name),
    outputSpec,
    steps: draft.steps.map((step, index) => ({
      agents: step.agents.map((agent) => buildStepAgent(agent)),
      index: index + 1,
    })),
  };
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

export function getObjectProperties(schema: unknown): Record<string, JsonSchema> {
  const record = asRecord(schema);
  const properties = record ? asRecord(record.properties) : undefined;
  if (!properties) {
    return {};
  }

  return Object.fromEntries(
    Object.entries(properties).filter((entry): entry is [string, JsonSchema] => Boolean(asRecord(entry[1]))),
  );
}

export function getSchemaFieldNames(
  schema: unknown,
  wiring: Record<string, WiringSourceDraft>,
): string[] {
  return Array.from(
    new Set([...Object.keys(getObjectProperties(schema)), ...Object.keys(wiring)]),
  ).sort((left, right) => left.localeCompare(right));
}

function getRequiredFields(schema: unknown): Set<string> {
  const record = asRecord(schema);
  const required = record?.required;
  if (!Array.isArray(required)) {
    return new Set<string>();
  }

  return new Set(required.filter((entry): entry is string => typeof entry === "string"));
}

function resolveSchemaAtPath(schema: unknown, path: string): JsonSchema | undefined {
  const trimmed = path.trim();
  const initial = asRecord(schema);
  if (!initial) {
    return undefined;
  }

  if (!trimmed) {
    return initial as JsonSchema;
  }

  let current: Record<string, unknown> | undefined = initial;
  for (const segment of trimmed.split(".").map((part) => part.trim()).filter(Boolean)) {
    const properties = current ? getObjectProperties(current) : {};
    current = asRecord(properties[segment]);
    if (!current) {
      return undefined;
    }
  }

  return current as JsonSchema;
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

export function findAgentByKey(agents: readonly AgentRead[], key: string): AgentRead | undefined {
  return agents.find((agent) => agent.key === key.trim());
}

type StepSlotMetadata = {
  optional: boolean;
  outputSchema: unknown;
};

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
  fieldPath: string;
  priorSlots: Map<number, Record<string, StepSlotMetadata>>;
  source: WiringSourceDraft;
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

  if (source.from === "none") {
    if (targetIsRequired) {
      issues.push({ field: fieldPath, issue: `${fieldName} requires a wiring source` });
    }
    return issues;
  }

  const targetPath = source.path.trim();

  if (source.from === "input") {
    const effectivePath = targetPath || fieldName;
    const sourceSchema = resolveSchemaAtPath(draftInputSchema, effectivePath);

    if (!sourceSchema) {
      issues.push({
        field: fieldPath,
        issue: `Input path '${effectivePath}' was not found`,
      });
      return issues;
    }

    if (!isTypeCompatible(sourceSchema, targetFieldSchema)) {
      issues.push({
        field: fieldPath,
        issue: "Wired source type is not compatible with the target field schema",
      });
    }

    return issues;
  }

  const referencedStep = Number(source.stepIndex.trim());
  if (!Number.isInteger(referencedStep) || referencedStep <= 0) {
    issues.push({ field: fieldPath, issue: "Select an earlier step for this wiring source" });
    return issues;
  }

  const slots = priorSlots.get(referencedStep);
  const slotName = source.slot.trim();

  if (!slots || !slotName || !slots[slotName]) {
    issues.push({
      field: fieldPath,
      issue: `Slot '${slotName || "(empty)"}' was not found on step ${referencedStep}`,
    });
    return issues;
  }

  const slotMetadata = slots[slotName];
  if (slotMetadata.optional && targetIsRequired) {
    issues.push({
      field: fieldPath,
      issue: "Optional slots can only wire into optional target fields",
    });
  }

  const sourceSchema = resolveSchemaAtPath(slotMetadata.outputSchema, targetPath);
  if (targetPath && !sourceSchema) {
    issues.push({
      field: fieldPath,
      issue: `Path '${targetPath}' was not found on slot '${slotName}'`,
    });
    return issues;
  }

  if (!isTypeCompatible(sourceSchema ?? slotMetadata.outputSchema, targetFieldSchema)) {
    issues.push({
      field: fieldPath,
      issue: "Wired source type is not compatible with the target field schema",
    });
  }

  const selectedAgent = agents.find((agent) => agent.outputSchema.jsonSchema === slotMetadata.outputSchema);
  void selectedAgent;

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
    issues.push({ field: `${fieldPrefix}.agentKey`, issue: "Select an agent" });
  }

  if (!slot) {
    issues.push({ field: `${fieldPrefix}.slot`, issue: "Slot is required" });
  }

  const resolvedAgent = findAgentByKey(agents, agentKey);
  const targetFields = getSchemaFieldNames(resolvedAgent?.inputSchema, draftAgent.wiring);
  const requiredFields = getRequiredFields(resolvedAgent?.inputSchema);
  const priorSlots = collectPriorSlots(draft.steps, agents, currentStepIndex);

  targetFields.forEach((fieldName) => {
    const source = draftAgent.wiring[fieldName] ?? createEmptyWiringSource();
    const targetFieldSchema = getObjectProperties(resolvedAgent?.inputSchema)[fieldName];
    issues.push(
      ...validateWiringEntry({
        agents,
        draftInputSchema: parseJsonValue<JsonSchema>("Input schema", draft.inputSchemaText, {}),
        fieldName,
        fieldPath: `${fieldPrefix}.wiring.${fieldName}`,
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
      issues.push({
        field: `${fieldPrefix}.agentVersion`,
        issue: error instanceof Error ? error.message : "Agent version is invalid",
      });
    }
  }

  return issues;
}

export function validateWorkflowDraft(
  draft: WorkflowDraft,
  agents: readonly AgentRead[],
): WorkflowValidationIssue[] {
  const issues: WorkflowValidationIssue[] = [];

  try {
    parseRequiredText("Key", draft.key);
  } catch (error) {
    issues.push({ field: "key", issue: error instanceof Error ? error.message : "Key is required" });
  }

  try {
    parseRequiredText("Name", draft.name);
  } catch (error) {
    issues.push({ field: "name", issue: error instanceof Error ? error.message : "Name is required" });
  }

  try {
    parseJsonValue<JsonSchema>("Input schema", draft.inputSchemaText, {});
  } catch (error) {
    issues.push({
      field: "inputSchema",
      issue: error instanceof Error ? error.message : "Input schema must be valid JSON",
    });
  }

  if (draft.steps.length === 0) {
    issues.push({ field: "steps", issue: "At least one step is required" });
  }

  draft.steps.forEach((step, stepIndex) => {
    const fieldPrefix = `steps[${stepIndex}]`;
    if (step.agents.length === 0) {
      issues.push({ field: `${fieldPrefix}.agents`, issue: "Add at least one agent to the step" });
      return;
    }

    const seenSlots = new Set<string>();
    step.agents.forEach((agent, agentIndex) => {
      const slot = agent.slot.trim();
      if (slot) {
        if (seenSlots.has(slot)) {
          issues.push({
            field: `steps[${stepIndex}].agents[${agentIndex}].slot`,
            issue: "Duplicate slot name within the same step",
          });
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
    issues.push({ field: "outputSpec.stepIndex", issue: "Select an output step" });
  } else {
    const slots = collectPriorSlots(draft.steps, agents, draft.steps.length + 1).get(outputStep);
    if (!slots || !slotName || !slots[slotName]) {
      issues.push({
        field: "outputSpec.slot",
        issue: `Slot '${slotName || "(empty)"}' was not found on step ${outputStep}`,
      });
    }
  }

  return issues;
}
