import type { UnknownRecord } from "./common";

export type RunStatus = "running" | "succeeded" | "failed";
export type RunStepStatus = "pending" | "running" | "succeeded" | "failed" | "skipped";
export type RunStepOrigin = "planned" | "copied";
export type RunInvocationInputMode = "passthrough" | "wired";
export type RunInvocationResolvedInputOrigin = "derived" | "edited" | "copied" | "passthrough";
export type RunInvocationOutputOrigin = "executed" | "edited" | "copied";
export type RunTargetKind = "agent" | "workflow";

export interface RunTargetIdentityRead {
  targetKind: RunTargetKind;
  targetId: number;
  targetKey: string;
  targetVersion: number;
}

export interface RunAgentErrorRead {
  code: string;
  message: string;
  details: UnknownRecord[];
}

export interface RunAgentInvocationRead {
  id: number;
  runStepId: number;
  runId: number;
  stepIndex: number;
  slot: string;
  position: number;
  agentId: number;
  agentKey: string;
  agentVersion: number;
  outputSchemaId: number;
  outputSchemaVersion: number;
  inputMode: RunInvocationInputMode;
  wiring: UnknownRecord;
  optional: boolean;
  status: RunStepStatus;
  resolvedInput: UnknownRecord;
  resolvedInputOrigin: RunInvocationResolvedInputOrigin;
  output: unknown | null;
  outputOrigin: RunInvocationOutputOrigin | null;
  errorCode: string | null;
  errorMessage: string | null;
  errorDetails: UnknownRecord[];
  tokens: number;
  costUsd: string;
  durationMs: number | null;
  traceSpanId: string | null;
  sourceInvocationId: number | null;
  startedAt: string | null;
  finishedAt: string | null;
  persistedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface RunStepRead {
  id: number;
  runId: number;
  index: number;
  status: RunStepStatus;
  origin: RunStepOrigin;
  sourceRunStepId: number | null;
  sourceRunId: number | null;
  sourceStepIndex: number | null;
  error: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  persistedAt: string | null;
  createdAt: string;
  updatedAt: string;
  invocations: RunAgentInvocationRead[];
}

export interface RunCreatedRead extends RunTargetIdentityRead {
  id: number;
  status: RunStatus;
  traceId: string | null;
  createdAt: string;
}

export interface RunListItemRead extends RunTargetIdentityRead {
  id: number;
  status: RunStatus;
  totalTokens: number;
  totalCostUsd: string;
  traceId: string | null;
  startedAt: string;
  finishedAt: string | null;
}

export interface RunListRead {
  items: RunListItemRead[];
}

export interface RunRead extends RunTargetIdentityRead {
  id: number;
  input: UnknownRecord;
  sourceRunId: number | null;
  lineageRootRunId: number | null;
  forkedFromStepIndex: number | null;
  resumeStepIndex: number;
  finalOutput: unknown | null;
  status: RunStatus;
  totalTokens: number;
  totalCostUsd: string;
  inheritedTokens: number;
  inheritedCostUsd: string;
  executedTokens: number;
  executedCostUsd: string;
  traceId: string | null;
  error: string | null;
  startedAt: string;
  finishedAt: string | null;
  createdAt: string;
  updatedAt: string;
  steps: RunStepRead[];
}

export interface RunForkInvocationDraftRead {
  sourceInvocationId: number;
  stepIndex: number;
  slot: string;
  agentKey: string;
  resolvedInput: UnknownRecord;
  output: unknown;
}

export interface RunForkStepDraftRead {
  sourceRunStepId: number;
  index: number;
  invocations: RunForkInvocationDraftRead[];
}

export interface RunForkDraftRead extends RunTargetIdentityRead {
  sourceRunId: number;
  forkStepIndex: number;
  input: UnknownRecord;
  steps: RunForkStepDraftRead[];
}

export interface RunForkInvocationEdit {
  stepIndex: number;
  slot: string;
  resolvedInput?: UnknownRecord | null;
  output?: unknown | null;
}

export interface RunForkCreateRequest {
  forkStepIndex: number;
  input?: UnknownRecord | null;
  invocationEdits?: RunForkInvocationEdit[];
}

export interface RunListParams {
  targetKind?: RunTargetKind;
  targetId?: number;
  targetKey?: string;
  targetVersion?: number;
  status?: RunStatus;
  limit?: number;
  offset?: number;
}
