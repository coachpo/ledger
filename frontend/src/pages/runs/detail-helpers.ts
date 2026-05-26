import type { UnknownRecord } from "@/lib/types/common";
import type {
  RunAgentInvocationRead,
  RunOperationInvocationRead,
  RunQueueReason,
  RunRead,
  RunRerunDraftRead,
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

export type RunDraftReadiness = Pick<
  RunRerunDraftRead,
  "ready" | "blockingErrors" | "warnings"
>;

export type RunDraftReadinessDiagnostic = {
  field: string;
  issue: string;
  severity: "error" | "warning";
};

export type RunFinalOutputState = {
  description: string;
  isPending: boolean;
  label: "Captured" | "Not produced" | "Pending";
  tone: "danger" | "success" | "warning";
};

export const DEFAULT_FORK_UNAVAILABLE_REASON =
  "Forking is available for succeeded Workflow Package runs and succeeded agent invocations.";

function isUnknownRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function diagnosticFromRecord(
  value: unknown,
  severity: RunDraftReadinessDiagnostic["severity"],
): RunDraftReadinessDiagnostic {
  const record = isUnknownRecord(value) ? value : {};
  return {
    field: stringValue(record.field) || stringValue(record.path) || "$",
    issue:
      stringValue(record.issue) ||
      stringValue(record.message) ||
      "Review this run draft diagnostic.",
    severity,
  };
}

export function diagnosticsFromDraftReadiness(
  readiness: RunDraftReadiness | null | undefined,
): RunDraftReadinessDiagnostic[] {
  if (!readiness) {
    return [];
  }

  return [
    ...readiness.blockingErrors.map((diagnostic) =>
      diagnosticFromRecord(diagnostic, "error"),
    ),
    ...readiness.warnings.map((diagnostic) =>
      diagnosticFromRecord(diagnostic, "warning"),
    ),
  ];
}

export function isTerminalStatus(status: RunStepStatus): boolean {
  return status === "succeeded" || status === "failed" || status === "skipped";
}

export function finalOutputState(run: Pick<RunRead, "finalOutput" | "status">): RunFinalOutputState {
  if (run.finalOutput !== null) {
    return {
      description: "Rendered and raw views use the same immutable payload.",
      isPending: false,
      label: "Captured",
      tone: "success",
    };
  }

  if (run.status === "queued" || run.status === "running") {
    return {
      description: "Final output is not available yet.",
      isPending: true,
      label: "Pending",
      tone: "warning",
    };
  }

  if (run.status === "failed") {
    return {
      description: "Run failed before final output was produced.",
      isPending: false,
      label: "Not produced",
      tone: "danger",
    };
  }

  return {
    description: "The run completed with an explicit null final output.",
    isPending: false,
    label: "Captured",
    tone: "success",
  };
}

export function progressForInvocations(
  invocations: Array<{ status: RunStepStatus }>,
  fallbackStatus?: RunStepStatus | RunStatus,
): number {
  if (invocations.length === 0) {
    return fallbackStatus &&
      fallbackStatus !== "running" &&
      fallbackStatus !== "pending"
      ? 100
      : 0;
  }

  const completed = invocations.filter((invocation) =>
    isTerminalStatus(invocation.status),
  ).length;
  return Math.round((completed / invocations.length) * 100);
}

export function formatUnfinishedRunStatus(status: RunStatus): string {
  return status === "queued" ? " · Queued" : " · Still running";
}

export function formatQueueReasonTitle(reason: RunQueueReason): string {
  return reason === "blocked-by-package-serial-policy"
    ? "Blocked by package serial policy"
    : "Awaiting worker capacity";
}

export function runStatusTone(
  status: RunStatus,
): "neutral" | "success" | "warning" | "danger" {
  if (status === "succeeded") {
    return "success";
  }

  if (status === "failed") {
    return "danger";
  }

  return status === "queued" ? "warning" : "neutral";
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

export function sortedInvocations(
  invocations: RunAgentInvocationRead[],
): RunAgentInvocationRead[] {
  return [...invocations].sort(
    (left, right) =>
      left.position - right.position || left.slot.localeCompare(right.slot),
  );
}

export function sortedOperationInvocations(
  invocations: RunOperationInvocationRead[],
): RunOperationInvocationRead[] {
  return [...invocations].sort(
    (left, right) =>
      left.position - right.position || left.slot.localeCompare(right.slot),
  );
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

  const selectedInvocation = selectedStep.invocations.find(
    (invocation) => invocation.id === invocationId,
  );
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

export function hasCurrentForkLineage(
  run: RunRead,
  steps: RunStepRead[],
): boolean {
  if (!run.sourceRunId) {
    return false;
  }

  return steps.some(
    (step) =>
      step.index === run.resumeStepIndex &&
      step.invocations.some(
        (invocation) =>
          invocation.resolvedInputOrigin === "edited" &&
          invocation.sourceInvocationId !== null,
      ),
  );
}
