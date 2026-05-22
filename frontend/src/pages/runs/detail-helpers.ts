import type {
  RunAgentInvocationRead,
  RunOperationInvocationRead,
  RunRead,
  RunStatus,
  RunStepRead,
  RunStepStatus,
  RunTargetKind,
} from "@/lib/types/run";

export type TraceSpanEntry = {
  invocationId: number;
  invocationKind: "agent" | "operation";
  slot: string;
  spanId: string;
  stepIndex: number;
};

export type RunForkAvailability = {
  isAvailable: boolean;
  reason: string | null;
};

export type ForkTargetContext = {
  invocation: RunAgentInvocationRead;
  step: RunStepRead;
};

export const DEFAULT_FORK_UNAVAILABLE_REASON = "Forking is available for succeeded Workflow Package runs and succeeded agent invocations.";

export function isTerminalStatus(status: RunStepStatus): boolean {
  return status === "succeeded" || status === "failed" || status === "skipped";
}

export function progressForInvocations(invocations: Array<{ status: RunStepStatus }>, fallbackStatus?: RunStepStatus | RunStatus): number {
  if (invocations.length === 0) {
    return fallbackStatus && fallbackStatus !== "running" && fallbackStatus !== "pending" ? 100 : 0;
  }

  const completed = invocations.filter((invocation) => isTerminalStatus(invocation.status)).length;
  return Math.round((completed / invocations.length) * 100);
}

export function progressForRun(status: RunStatus, steps: RunStepRead[]): number {
  if (status === "queued") {
    return 0;
  }

  const invocations = steps.flatMap((step) => [...step.invocations, ...step.operationInvocations]);

  if (invocations.length === 0) {
    return status === "running" ? 0 : 100;
  }

  if (status !== "running") {
    return 100;
  }

  return progressForInvocations(invocations);
}

export function formatUnfinishedRunStatus(status: RunStatus): string {
  return status === "queued" ? " · Awaiting execution" : " · Still running";
}

export function formatTargetKindLabel(targetKind: RunTargetKind): string {
  if (targetKind === "workflowPackage") {
    return "Workflow Package";
  }

  return targetKind === "agent" ? "Agent" : "Workflow";
}

export function describeRunTarget(targetKind: RunTargetKind): string {
  if (targetKind === "workflowPackage") {
    return "Workflow package run captured an immutable executable snapshot at launch.";
  }

  return targetKind === "agent"
    ? "Standalone agent execution with a single runnable target."
    : "Workflow execution with step-by-step agent orchestration.";
}

export function sortedInvocations(invocations: RunAgentInvocationRead[]): RunAgentInvocationRead[] {
  return [...invocations].sort((left, right) => left.position - right.position || left.slot.localeCompare(right.slot));
}

export function sortedOperationInvocations(invocations: RunOperationInvocationRead[]): RunOperationInvocationRead[] {
  return [...invocations].sort((left, right) => left.position - right.position || left.slot.localeCompare(right.slot));
}

export function findForkTargetContext(
  steps: RunStepRead[],
  resumeStepIndex: number | undefined,
  invocationId: number | undefined,
): ForkTargetContext | null {
  if (resumeStepIndex === undefined || invocationId === undefined) {
    return null;
  }

  const step = steps.find((item) => item.index === resumeStepIndex);
  const invocation = step?.invocations.find((item) => item.id === invocationId);
  return step && invocation ? { invocation, step } : null;
}

export function getRunForkAvailability(
  run: RunRead,
  steps: RunStepRead[],
  resumeStepIndex: number | undefined,
  invocationId: number | undefined,
): RunForkAvailability {
  if (run.targetKind !== "workflowPackage" || run.status !== "succeeded") {
    return {
      isAvailable: false,
      reason: DEFAULT_FORK_UNAVAILABLE_REASON,
    };

  }

  if (resumeStepIndex === undefined || invocationId === undefined) {
    return {
      isAvailable: false,
      reason: DEFAULT_FORK_UNAVAILABLE_REASON,
    };
  }

  const selectedStep = steps.find((step) => step.index === resumeStepIndex);
  if (!selectedStep) {
    return {
      isAvailable: false,
      reason: `Step ${resumeStepIndex} is not available on this run.`,
    };
  }

  const selectedInvocation = selectedStep.invocations.find((invocation) => invocation.id === invocationId);
  if (!selectedInvocation) {
    return {
      isAvailable: false,
      reason: `Agent invocation #${invocationId} is not available on Step ${resumeStepIndex}.`,
    };
  }

  if (selectedStep.status !== "succeeded") {
    return {
      isAvailable: false,
      reason: `Step ${resumeStepIndex} is ${selectedStep.status}; only succeeded workflow steps can be forked.`,
    };
  }

  if (selectedInvocation.status !== "succeeded") {
    return {
      isAvailable: false,
      reason: `${selectedInvocation.slot} invocation is ${selectedInvocation.status}; only succeeded agent invocations can be forked.`,
    };
  }

  if (!selectedInvocation.persistedAt) {
    return {
      isAvailable: false,
      reason: `${selectedInvocation.slot} invocation has no persisted input snapshot to fork.`,
    };
  }

  return { isAvailable: true, reason: null };
}

export function hasCurrentForkLineage(run: RunRead, steps: RunStepRead[]): boolean {
  if (!run.sourceRunId) {
    return false;
  }

  return steps.some(
    (step) =>
      step.index === run.resumeStepIndex
      && step.invocations.some((invocation) => invocation.resolvedInputOrigin === "edited" && invocation.sourceInvocationId !== null),
  );
}
