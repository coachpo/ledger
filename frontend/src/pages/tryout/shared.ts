import { formatDateTime } from "@/lib/format";
import {
  buildRuntimeInputs,
  createRuntimeInputRow,
  type RuntimeInputRow,
} from "@/lib/runtime-inputs";
import type {
  PersonaProfileRef,
  RuntimeRunRead,
} from "@/lib/types/runtime";
import type {
  AgentSpecRead,
  PersonaProfileRead,
  WorkflowSpecRead,
} from "@/lib/types/studio";

export type TryoutTargetKind = "workflow" | "single_agent";

export type TryoutDraft = {
  agentSpecId: string;
  personaProfileKeys: string[];
  runtimeInputRows: RuntimeInputRow[];
  runtimeInputsOpen: boolean;
  targetKind: TryoutTargetKind;
  workflowSpecId: string;
};

export const initialDraft: TryoutDraft = {
  agentSpecId: "",
  personaProfileKeys: [],
  runtimeInputRows: [],
  runtimeInputsOpen: false,
  targetKind: "workflow",
  workflowSpecId: "",
};

export function sortByKey<T extends { key: string }>(items: T[]) {
  return [...items].sort((left, right) => left.key.localeCompare(right.key));
}

export function stringifyJson(value: unknown) {
  if (value === null || value === undefined) {
    return "No final output captured yet.";
  }

  return JSON.stringify(value, null, 2);
}

export function formatDateTimeOrFallback(
  value: string | null | undefined,
  fallback = "Not available",
) {
  return value ? formatDateTime(value) : fallback;
}

export function getTargetSummary(run: RuntimeRunRead | undefined) {
  if (!run) {
    return "No persisted run selected yet.";
  }

  if (run.executionKind === "workflow") {
    return `${run.workflowSpecKey ?? "Unknown workflow"} · v${run.workflowSpecVersion ?? "?"}`;
  }

  return `${run.agentSpecKey ?? "Unknown agent"} · v${run.agentSpecVersion ?? "?"}`;
}

export function toPersonaRef(persona: PersonaProfileRead): PersonaProfileRef {
  return {
    canonicalTargetId: persona.canonicalTargetId,
    origin: persona.origin,
    personaKind: persona.kind,
    personaProfileKey: persona.key,
    personaProfileVersion: persona.version,
    selectionSource: "tryout_ui",
  };
}

export function buildValidationMessages(params: {
  agentSpec: AgentSpecRead | undefined;
  selectedTargetKind: TryoutTargetKind;
  workflowSpec: WorkflowSpecRead | undefined;
}) {
  const { agentSpec, selectedTargetKind, workflowSpec } = params;
  const messages: string[] = [];

  if (selectedTargetKind === "workflow") {
    if (!workflowSpec) {
      messages.push("Select a workflow spec to execute the Tryout flow.");
    }
  }

  if (selectedTargetKind === "single_agent" && !agentSpec) {
    messages.push("Select a single-agent spec to execute the Tryout flow.");
  }

  return messages;
}

export function buildRuntimeInputMap(draft: TryoutDraft) {
  return buildRuntimeInputs(draft.runtimeInputRows);
}

export function buildNewTryoutInputRow() {
  return createRuntimeInputRow("tryout");
}
