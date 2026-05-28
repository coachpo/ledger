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
  | "wiring";

export type RunInspectionMode =
  | "summary"
  | "execution"
  | "diagnostics"
  | "inputs"
  | "outputs"
  | "runtime"
  | "memory"
  | "lineage"
  | "metadata";

export type RunInspectionState = {
  mode: RunInspectionMode;
  pane: RunInspectionPane;
  selected?: boolean;
  target: RunInspectionTarget;
};

type RunInspectionIndex = {
  agentInvocationIds: Set<number>;
  memoryIds: Set<string>;
  operationInvocationIds: Set<number>;
  stepIndexes: Set<number>;
};

export const RUN_INSPECTION_MODES = [
  "summary",
  "execution",
  "diagnostics",
  "inputs",
  "outputs",
  "runtime",
  "memory",
  "lineage",
  "metadata",
] as const satisfies readonly RunInspectionMode[];

const RUN_INSPECTION_MODE_ALIASES: Record<string, RunInspectionMode> = {
  audit: "metadata",
  diagnostics: "diagnostics",
  execution: "execution",
  input: "inputs",
  inputs: "inputs",
  lineage: "lineage",
  memory: "memory",
  metadata: "metadata",
  output: "outputs",
  outputs: "outputs",
  overview: "summary",
  runtime: "runtime",
  steps: "execution",
  summary: "summary",
  tokens: "runtime",
};

const RUN_PANES: RunInspectionPane[] = [
  "finalOutput",
  "input",
  "lineage",
  "memory",
  "error",
];
const STEP_PANES: RunInspectionPane[] = ["details", "lineage", "error"];
const AGENT_INVOCATION_PANES: RunInspectionPane[] = [
  "output",
  "input",
  "wiring",
  "lineage",
  "error",
];
const OPERATION_INVOCATION_PANES: RunInspectionPane[] = [
  "output",
  "request",
  "response",
  "lineage",
  "error",
];
const MEMORY_ARTIFACT_PANES: RunInspectionPane[] = [
  "details",
  "provenance",
  "lineage",
];

function buildInspectionIndex(
  run: RunRead,
  steps: RunStepRead[],
): RunInspectionIndex {
  return {
    agentInvocationIds: new Set(
      steps.flatMap((step) =>
        step.invocations.map((invocation) => invocation.id),
      ),
    ),
    memoryIds: new Set(
      (run.memoryArtifacts ?? []).map((artifact) => artifact.memoryId),
    ),
    operationInvocationIds: new Set(
      steps.flatMap((step) =>
        step.operationInvocations.map((invocation) => invocation.id),
      ),
    ),
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

function parseRunInspectionMode(raw: string | null): RunInspectionMode | null {
  if (!raw || !Object.hasOwn(RUN_INSPECTION_MODE_ALIASES, raw)) {
    return null;
  }
  return RUN_INSPECTION_MODE_ALIASES[raw];
}

export function defaultRunInspectionMode(run: RunRead): RunInspectionMode {
  if (run.status === "succeeded") {
    return "outputs";
  }
  if (run.status === "running" || run.status === "failed") {
    return "execution";
  }
  return "summary";
}

function modeForPane(
  target: RunInspectionTarget,
  pane: RunInspectionPane,
): RunInspectionMode | null {
  if (target.type === "memoryArtifact") {
    return "memory";
  }
  if (target.type !== "run") {
    return pane === "error" ? "diagnostics" : "execution";
  }

  if (pane === "finalOutput" || pane === "output") {
    return "outputs";
  }
  if (pane === "input") {
    return "inputs";
  }
  if (pane === "lineage") {
    return "lineage";
  }
  if (pane === "memory") {
    return "memory";
  }
  if (pane === "error") {
    return "diagnostics";
  }
  return null;
}

function defaultPaneForMode(
  target: RunInspectionTarget,
  mode: RunInspectionMode,
): RunInspectionPane {
  if (target.type !== "run") {
    return defaultPaneForTarget(target);
  }
  if (mode === "inputs") {
    return "input";
  }
  if (mode === "lineage") {
    return "lineage";
  }
  if (mode === "memory") {
    return "memory";
  }
  if (mode === "diagnostics") {
    return "error";
  }
  return "finalOutput";
}

export function inspectionPanesForTarget(
  target: RunInspectionTarget,
): RunInspectionPane[] {
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
  if (
    target.type === "agentInvocation" ||
    target.type === "operationInvocation"
  ) {
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
    return {
      type: "agentInvocation",
      invocationId: Number(invocationMatch[1]),
    };
  }
  if (operationMatch) {
    return {
      type: "operationInvocation",
      invocationId: Number(operationMatch[1]),
    };
  }
  return null;
}

function targetExists(
  target: RunInspectionTarget,
  index: RunInspectionIndex,
): boolean {
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

function canonicalTarget(
  run: RunRead,
  steps: RunStepRead[],
  searchParams: URLSearchParams,
  hash: string,
): RunInspectionTarget {
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

function hasExplicitInspectionState(
  searchParams: URLSearchParams,
  hash: string,
): boolean {
  return Boolean(
    searchParams.has("mode") ||
      searchParams.has("inspect") ||
      searchParams.has("pane") ||
      parseAnchorTarget(hash),
  );
}

function hasFailureEvidence(value: {
  errorCode: string | null;
  errorDetails: unknown[];
  errorMessage: string | null;
  status: string;
}): boolean {
  return Boolean(
    value.status === "failed" ||
      value.errorCode ||
      value.errorMessage ||
      value.errorDetails.length > 0,
  );
}

function defaultFailedInspectionState(
  run: RunRead,
  steps: RunStepRead[],
): Pick<RunInspectionState, "mode" | "pane" | "target"> | null {
  if (run.status !== "failed") {
    return null;
  }

  for (const step of steps) {
    const invocation = step.invocations.find(hasFailureEvidence);
    if (invocation) {
      return {
        mode: "execution",
        pane: "error",
        target: { type: "agentInvocation", invocationId: invocation.id },
      };
    }
  }

  for (const step of steps) {
    const invocation = step.operationInvocations.find(hasFailureEvidence);
    if (invocation) {
      return {
        mode: "execution",
        pane: "error",
        target: { type: "operationInvocation", invocationId: invocation.id },
      };
    }
  }

  const failedStep = steps.find(
    (step) => step.status === "failed" || Boolean(step.error),
  );
  if (failedStep) {
    return {
      mode: "execution",
      pane: "error",
      target: { type: "step", stepIndex: failedStep.index },
    };
  }

  if (run.error) {
    return { mode: "execution", pane: "error", target: { type: "run" } };
  }

  return null;
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
  const failedDefault = hasExplicitInspectionState(searchParams, hash)
    ? null
    : defaultFailedInspectionState(run, steps);
  const target =
    failedDefault?.target ?? canonicalTarget(run, steps, searchParams, hash);
  const requestedMode = parseRunInspectionMode(searchParams.get("mode"));
  const requestedPane = searchParams.get("pane") as RunInspectionPane | null;
  const hasExplicitSelection = Boolean(
    searchParams.has("inspect") || searchParams.has("pane") || parseAnchorTarget(hash),
  );
  const validPanes = inspectionPanesForTarget(target);
  const requestedPaneIsValid = Boolean(
    requestedPane && validPanes.includes(requestedPane),
  );
  const targetMode = modeForPane(target, defaultPaneForTarget(target));
  const fallbackMode =
    requestedMode ??
    failedDefault?.mode ??
    (target.type === "run" ? defaultRunInspectionMode(run) : targetMode) ??
    defaultRunInspectionMode(run);
  const pane = requestedPaneIsValid
    ? (requestedPane as RunInspectionPane)
    : (failedDefault?.pane ?? defaultPaneForMode(target, fallbackMode));
  const inferredMode = modeForPane(target, pane);

  const mode =
    requestedMode ??
    failedDefault?.mode ??
    (requestedPaneIsValid || target.type !== "run" ? inferredMode : null) ??
    defaultRunInspectionMode(run);

  return {
    mode,
    pane,
    selected: !(mode === "metadata" && !hasExplicitSelection),
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

export function inspectionTargetKindLabel(target: RunInspectionTarget): string {
  if (target.type === "step") {
    return "Step evidence";
  }
  if (target.type === "agentInvocation") {
    return "Agent invocation";
  }
  if (target.type === "operationInvocation") {
    return "Operation invocation";
  }
  if (target.type === "memoryArtifact") {
    return "Memory artifact";
  }
  return "Run evidence";
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
    wiring: "Wiring",
  };

  return labels[pane];
}
