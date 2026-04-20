import type { UnknownRecord } from "./common";

export type RunStatus = "running" | "succeeded" | "failed";

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

export interface RunCreatedRead {
  id: number;
  status: RunStatus;
  workflowId: number;
  workflowKey: string;
  workflowVersion: number;
  traceId: string | null;
  createdAt: string;
}

export interface RunListItemRead {
  id: number;
  workflowId: number;
  workflowKey: string;
  workflowVersion: number;
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

export interface RunRead {
  id: number;
  workflowId: number;
  workflowKey: string;
  workflowVersion: number;
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
  workflowId?: number;
  workflowKey?: string;
  workflowVersion?: number;
  status?: RunStatus;
  limit?: number;
  offset?: number;
}
