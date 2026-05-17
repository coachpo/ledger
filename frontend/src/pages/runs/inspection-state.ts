import type { RunRead, RunStepRead } from "@/lib/types/run";

export type RunInspectionTarget =
  | { type: "run" }
  | { type: "step"; stepIndex: number }
  | { type: "agentInvocation"; invocationId: number }
  | { type: "operationInvocation"; invocationId: number }
  | { type: "memoryArtifact"; memoryId: string };

export type RunInspectionPane =
  | "details"
  | "error"
  | "finalOutput"
  | "input"
  | "lineage"
  | "memory"
  | "output"
  | "provenance"
  | "request"
  | "response"
  | "trace"
  | "wiring";

export type RunInspectionState = {
  pane: RunInspectionPane;
  target: RunInspectionTarget;
};

type RunInspectionIndex = {
  agentInvocationIds: Set<number>;
  memoryIds: Set<string>;
  operationInvocationIds: Set<number>;
  stepIndexes: Set<number>;
};

const RUN_PANES: RunInspectionPane[] = ["finalOutput", "input", "trace", "lineage", "provenance", "memory"];
const STEP_PANES: RunInspectionPane[] = ["details", "lineage", "error"];
const AGENT_INVOCATION_PANES: RunInspectionPane[] = ["output", "input", "wiring", "trace", "lineage", "error"];
const OPERATION_INVOCATION_PANES: RunInspectionPane[] = ["output", "request", "response", "trace", "lineage", "error"];
const MEMORY_ARTIFACT_PANES: RunInspectionPane[] = ["details", "provenance", "lineage"];

function buildInspectionIndex(run: RunRead, steps: RunStepRead[]): RunInspectionIndex {
  return {
    agentInvocationIds: new Set(steps.flatMap((step) => step.invocations.map((invocation) => invocation.id))),
    memoryIds: new Set((run.memoryArtifacts ?? []).map((artifact) => artifact.memoryId)),
    operationInvocationIds: new Set(steps.flatMap((step) => step.operationInvocations.map((invocation) => invocation.id))),
    stepIndexes: new Set(steps.map((step) => step.index)),
  };
}
function parsePositiveInteger(value: string | undefined): number | null {
  if (!value) {
    return null;
  }

  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 1 ? parsed : null;
}

export function inspectionPanesForTarget(target: RunInspectionTarget): RunInspectionPane[] {
  if (target.type === "step") {
    return STEP_PANES;
  }
  if (target.type === "agentInvocation") {
    return AGENT_INVOCATION_PANES;
  }
  if (target.type === "operationInvocation") {
    return OPERATION_INVOCATION_PANES;
  }
  if (target.type === "memoryArtifact") {
    return MEMORY_ARTIFACT_PANES;
  }
  return RUN_PANES;
}
function defaultPaneForTarget(target: RunInspectionTarget): RunInspectionPane {
  if (target.type === "step" || target.type === "memoryArtifact") {
    return "details";
  }
  if (target.type === "agentInvocation" || target.type === "operationInvocation") {
    return "output";
  }
  return "finalOutput";
}

function parseInspectionTarget(raw: string | null): RunInspectionTarget | null {
  if (!raw || raw === "run") {
    return raw === "run" ? { type: "run" } : null;
  }

  const [type, value] = raw.split(":", 2);
  const numericValue = parsePositiveInteger(value);

  if (type === "step" && numericValue !== null) {
    return { type: "step", stepIndex: numericValue };
  }
  if (type === "invocation" && numericValue !== null) {
    return { type: "agentInvocation", invocationId: numericValue };
  }
  if (type === "operation" && numericValue !== null) {
    return { type: "operationInvocation", invocationId: numericValue };
  }
  if (type === "memory" && value) {
    return { type: "memoryArtifact", memoryId: value };
  }

  return null;
}

function parseAnchorTarget(hash: string): RunInspectionTarget | null {
  const normalizedHash = hash.startsWith("#") ? hash.slice(1) : hash;
  const stepMatch = /^step-(\d+)$/.exec(normalizedHash);
  const invocationMatch = /^invocation-(\d+)$/.exec(normalizedHash);
  const operationMatch = /^operation-invocation-(\d+)$/.exec(normalizedHash);

  if (stepMatch) {
    return { type: "step", stepIndex: Number(stepMatch[1]) };
  }
  if (invocationMatch) {
    return { type: "agentInvocation", invocationId: Number(invocationMatch[1]) };
  }
  if (operationMatch) {
    return { type: "operationInvocation", invocationId: Number(operationMatch[1]) };
  }
  if (normalizedHash === "run-trace-linkage") {
    return { type: "run" };
  }

  return null;
}

function targetExists(target: RunInspectionTarget, index: RunInspectionIndex): boolean {
  if (target.type === "run") {
    return true;
  }
  if (target.type === "step") {
    return index.stepIndexes.has(target.stepIndex);
  }
  if (target.type === "agentInvocation") {
    return index.agentInvocationIds.has(target.invocationId);
  }
  if (target.type === "operationInvocation") {
    return index.operationInvocationIds.has(target.invocationId);
  }
  return index.memoryIds.has(target.memoryId);
}

function canonicalTarget(run: RunRead, steps: RunStepRead[], searchParams: URLSearchParams, hash: string): RunInspectionTarget {
  const index = buildInspectionIndex(run, steps);
  const requestedTarget = parseInspectionTarget(searchParams.get("inspect"));
  if (requestedTarget && targetExists(requestedTarget, index)) {
    return requestedTarget;
  }

  const anchorTarget = parseAnchorTarget(hash);
  if (anchorTarget && targetExists(anchorTarget, index)) {
    return anchorTarget;
  }

  return { type: "run" };
}

export function resolveRunInspectionState({
  hash,
  run,
  searchParams,
  steps,
}: {
  hash: string;
  run: RunRead;
  searchParams: URLSearchParams;
  steps: RunStepRead[];
}): RunInspectionState {
  const target = canonicalTarget(run, steps, searchParams, hash);
  const requestedPane = searchParams.get("pane") as RunInspectionPane | null;
  const validPanes = inspectionPanesForTarget(target);

  return {
    pane: requestedPane && validPanes.includes(requestedPane) ? requestedPane : defaultPaneForTarget(target),
    target,
  };
}

export function serializeInspectionTarget(target: RunInspectionTarget): string {
  if (target.type === "step") {
    return `step:${target.stepIndex}`;
  }
  if (target.type === "agentInvocation") {
    return `invocation:${target.invocationId}`;
  }
  if (target.type === "operationInvocation") {
    return `operation:${target.invocationId}`;
  }
  if (target.type === "memoryArtifact") {
    return `memory:${target.memoryId}`;
  }
  return "run";
}

export function inspectionTargetHash(target: RunInspectionTarget): string {
  if (target.type === "step") {
    return `#step-${target.stepIndex}`;
  }
  if (target.type === "agentInvocation") {
    return `#invocation-${target.invocationId}`;
  }
  if (target.type === "operationInvocation") {
    return `#operation-invocation-${target.invocationId}`;
  }
  if (target.type === "memoryArtifact") {
    return `#memory-${target.memoryId}`;
  }
  return "#run-context";
}

export function inspectionPaneLabel(pane: RunInspectionPane): string {
  const labels: Record<RunInspectionPane, string> = {
    details: "Details",
    error: "Error",
    finalOutput: "Final output",
    input: "Run input",
    lineage: "Lineage",
    memory: "Memory",
    output: "Output",
    provenance: "Provenance",
    request: "Request",
    response: "Response",
    trace: "Trace",
    wiring: "Wiring",
  };

  return labels[pane];
}
