import type { UnknownRecord } from "@/lib/types/common";
import type {
  RunAgentInvocationRead,
  RunOperationInvocationRead,
  RunQueueReason,
  RunRerunDraftRead,
  RunStatus,
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

export type RunDraftReadiness = Pick<
  RunRerunDraftRead,
  "ready" | "blockingErrors" | "warnings"
>;

export type RunDraftReadinessDiagnostic = {
  field: string;
  issue: string;
  severity: "error" | "warning";
};

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
  if (status === "queued") {
    return " · Queued";
  }
  if (status === "cancelled") {
    return " · Cancelled";
  }
  return " · Still running";
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

  if (status === "cancelled") {
    return "neutral";
  }

  return status === "queued" ? "warning" : "neutral";
}

export function formatTargetKindLabel(_targetKind: RunTargetKind): string {
  return "Workflow Package";
}

export function describeRunTarget(_targetKind: RunTargetKind): string {
  return "Workflow package run captured an immutable executable snapshot at launch.";
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
