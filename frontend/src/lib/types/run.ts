import type { UnknownRecord } from "./common";

export type RunStatus = "running" | "succeeded" | "failed";

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

export interface RunStepAgentRead {
  slot: string;
  agentId: number;
  agentKey: string;
  agentVersion: number;
  outputSchemaId: number;
  outputSchemaVersion: number;
  resolvedInput: UnknownRecord;
  output: unknown | null;
  error: RunAgentErrorRead | null;
  status: RunStatus;
  tokens: number;
  costUsd: string;
  durationMs: number | null;
  traceSpanId: string | null;
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
  perStepOutputs: Record<string, RunStepAgentRead[]>;
  finalOutput: unknown | null;
  status: RunStatus;
  totalTokens: number;
  totalCostUsd: string;
  traceId: string | null;
  error: string | null;
  startedAt: string;
  finishedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface RunListParams {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any;
  targetKind?: RunTargetKind;
  targetId?: number;
  targetKey?: string;
  targetVersion?: number;
  status?: RunStatus;
  limit?: number;
  offset?: number;
}
