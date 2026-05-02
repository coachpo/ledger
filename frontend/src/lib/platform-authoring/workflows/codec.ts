import type { AgentRead } from "@/lib/types/agent";
import type {
  WorkflowCreateInput,
  WorkflowRead,
  WorkflowStepAgentWrite,
  WorkflowWireSource,
} from "@/lib/types/workflow";
import { parseJsonValue, parseRequiredText } from "@/pages/platform-resource-shared";

import { createEmptyWorkflowAgent, createEmptyWorkflowStep } from "./draft";
import type {
  WorkflowDraft,
  WorkflowDraftAgent,
  WorkflowDraftOutput,
  WorkflowDraftStep,
  WorkflowJsonSchema,
  WireBinding,
} from "./types";

function createDraftId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

export function workflowPathTokensToPath(pathTokens: readonly string[]): string | undefined {
  const path = pathTokens.map((token) => token.trim()).filter(Boolean).join(".");
  return path || undefined;
}

export function workflowPathToTokens(path?: string | null): string[] {
  const trimmed = path?.trim();
  if (!trimmed) {
    return [];
  }

  return trimmed
    .split(".")
    .map((part) => part.trim())
    .filter(Boolean);
}

function createEmptyWireBinding(): WireBinding {
  return { source: "none", stepIndex: null, slot: null, pathTokens: [] };
}

function wireBindingFromWireSource(source?: WorkflowWireSource): WireBinding {
  if (!source) {
    return createEmptyWireBinding();
  }

  return {
    source: source.from,
    stepIndex: source.stepIndex ?? null,
    slot: source.slot ?? null,
    pathTokens: workflowPathToTokens(source.path),
  };
}

function wireBindingToWireSource(binding: WireBinding): WorkflowWireSource | undefined {
  if (binding.source === "none") {
    return undefined;
  }

  if (binding.source === "input") {
    return {
      from: "input",
      path: workflowPathTokensToPath(binding.pathTokens),
    };
  }

  return {
    from: "step",
    path: workflowPathTokensToPath(binding.pathTokens),
    slot: binding.slot ?? undefined,
    stepIndex: binding.stepIndex ?? undefined,
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
    output: { kind: "slot", pathTokens: [], slot: "", stepIndex: "1" },
    steps: [createEmptyWorkflowStep()],
  };
}

export function workflowDraftFromRead(workflow: WorkflowRead): WorkflowDraft {
  const output: WorkflowDraftOutput = {
    kind: "slot",
    pathTokens: workflowPathToTokens(workflow.outputSpec.path),
    slot: workflow.outputSpec.slot,
    stepIndex: String(workflow.outputSpec.stepIndex),
  };

  return {
    description: workflow.description ?? "",
    inputSchemaText: JSON.stringify(workflow.inputSchema, null, 2),
    key: workflow.key,
    name: workflow.name,
    output,
    steps: workflow.steps.map((step) => ({
      agents: step.agents.map((agent) => ({
        agentKey: agent.agentKey,
        agentVersion: String(agent.agentVersion),
        optional: agent.optional,
        slot: agent.slot,
        wiring: Object.fromEntries(
          Object.entries(agent.wiring).map(([field, source]) => [field, wireBindingFromWireSource(source)]),
        ),
      })),
      id: createDraftId(`step-${step.index}`),
    })),
  };
}

export function createWorkflowDraftFromOutputSpec(
  outputSpec: WorkflowRead["outputSpec"],
): WorkflowDraftOutput {
  return {
    kind: "slot",
    pathTokens: workflowPathToTokens(outputSpec.path),
    slot: outputSpec.slot,
    stepIndex: String(outputSpec.stepIndex),
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

function buildStepAgent(agent: WorkflowDraftAgent): WorkflowStepAgentWrite {
  const wiringEntries = Object.entries(agent.wiring)
    .map(([field, source]) => [field, wireBindingToWireSource(source)] as const)
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
  const inputSchema = parseJsonValue<WorkflowJsonSchema>("Input schema", draft.inputSchemaText, {});
  const outputSpec: WorkflowCreateInput["outputSpec"] = {
    kind: "slot",
    path: workflowPathTokensToPath(draft.output.pathTokens),
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

export function findAgentByKey(agents: readonly AgentRead[], key: string): AgentRead | undefined {
  return agents.find((agent) => agent.key === key.trim());
}

export function createEmptyWorkflowAgentDraft(): WorkflowDraftAgent {
  return createEmptyWorkflowAgent();
}

export function createEmptyWorkflowStepDraft(): WorkflowDraftStep {
  return createEmptyWorkflowStep();
}

export function createEmptyWireBindingDraft(): WireBinding {
  return createEmptyWireBinding();
}
