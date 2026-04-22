import type { WorkflowDraft, WorkflowDraftAgent, WorkflowDraftOutput, WorkflowDraftStep, WireBinding } from "./types";
import type { WorkflowOutputSpecRead, WorkflowRead, WorkflowWireSource } from "@/lib/types/workflow";

function createDraftId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

function createEmptyWireBinding(): WireBinding {
  return { source: "none", stepIndex: null, slot: null, pathTokens: [] };
}

export function createEmptyWorkflowAgent(): WorkflowDraftAgent {
  return {
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
        properties: { ticker: { type: "string" } },
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

function pathTokensFromPath(path?: string | null): string[] {
  const trimmed = path?.trim();
  if (!trimmed) {
    return [];
  }

  return trimmed.split(".").map((part) => part.trim()).filter(Boolean);
}

function pathTokensFromWireSource(source?: WorkflowWireSource): string[] {
  return pathTokensFromPath(source?.path);
}

function wireBindingFromWireSource(source?: WorkflowWireSource): WireBinding {
  if (!source) {
    return createEmptyWireBinding();
  }

  return {
    source: source.from,
    stepIndex: source.stepIndex ?? null,
    slot: source.slot ?? null,
    pathTokens: pathTokensFromWireSource(source),
  };
}

export function workflowDraftFromRead(workflow: WorkflowRead): WorkflowDraft {
  const output: WorkflowDraftOutput =
    workflow.outputSpec.kind === "slot"
      ? {
          kind: "slot",
          pathTokens: pathTokensFromPath(workflow.outputSpec.path),
          slot: workflow.outputSpec.slot,
          stepIndex: String(workflow.outputSpec.stepIndex),
        }
      : {
          agentKey: workflow.outputSpec.agentKey,
          agentVersion: String(workflow.outputSpec.agentVersion),
          kind: "agent",
          wiring: Object.fromEntries(
            Object.entries(workflow.outputSpec.wiring).map(([field, source]) => [
              field,
              wireBindingFromWireSource(source),
            ]),
          ),
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

export function createWorkflowDraftFromOutputSpec(outputSpec: WorkflowOutputSpecRead): WorkflowDraftOutput {
  return outputSpec.kind === "slot"
    ? {
        kind: "slot",
        pathTokens: pathTokensFromPath(outputSpec.path),
        slot: outputSpec.slot,
        stepIndex: String(outputSpec.stepIndex),
      }
    : {
        agentKey: outputSpec.agentKey,
        agentVersion: String(outputSpec.agentVersion),
        kind: "agent",
        wiring: Object.fromEntries(
          Object.entries(outputSpec.wiring).map(([field, source]) => [field, wireBindingFromWireSource(source)]),
        ),
      };
}

export function wireBindingToPath(binding: WireBinding): string | undefined {
  const path = binding.pathTokens.map((token) => token.trim()).filter(Boolean).join(".");
  return path || undefined;
}

export function createEmptyWireBindingDraft(): WireBinding {
  return createEmptyWireBinding();
}
