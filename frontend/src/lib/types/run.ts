import type { UnknownRecord } from "./common";

export type RunStatus = "queued" | "running" | "succeeded" | "failed";
export type RunStepStatus = "pending" | "running" | "succeeded" | "failed" | "skipped";
export type RunStepOrigin = "planned" | "copied";
export type RunInvocationInputMode = "passthrough" | "wired";
export type RunInvocationResolvedInputOrigin = "derived" | "edited" | "copied" | "passthrough";
export type RunInvocationOutputOrigin = "executed" | "edited" | "copied";
export type RunTargetKind = "agent" | "workflow" | "workflowPackage";

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

export interface RunGraphMetadata {
  branchId?: string;
  fanoutId?: string;
  graphPath?: string;
  loopId?: string;
  loopIteration?: number;
  nodeId?: string;
  nodeKind?: "step" | "sequence" | "fanout" | "loop";
  sourceRefs?: unknown;
}

export interface RunMemoryProvenanceRead {
  agentKey: string;
  agentName?: string | null;
  agentVersion: number;
  createdByType: "agent";
  runId: number;
  stepId?: string | null;
  slot?: string | null;
  traceId?: string | null;
  workflowKey?: string | null;
  workflowVersion?: number | null;
}

export interface RunMemoryAuditReportLinkRead {
  slug: string;
  name: string;
  url: string;
  downloadUrl: string;
}

export interface RunMemoryArtifactRead {
  memoryId: string;
  summary: string;
  status: string;
  createdAt: string;
  provenance: RunMemoryProvenanceRead;
  sourceGraphMetadata?: (RunGraphMetadata & UnknownRecord) | null;
  auditLinks?: {
    report?: RunMemoryAuditReportLinkRead | null;
  } | null;
}

export interface RunPackageProvenanceRead {
  availability: UnknownRecord;
  launchSnapshot: UnknownRecord | null;
  localResourceRefs: UnknownRecord;
  preflightSummary: UnknownRecord | null;
  resolvedModelConnections: UnknownRecord[];
  workflowKey: string;
  workflowPackageHash: string;
  workflowPackageId: number;
  workflowPackageKey: string;
  workflowPackageVersion: number;
  workflowPackageVersionId: number | null;
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
  graphMetadata: RunGraphMetadata | null;
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
  graphMetadata: RunGraphMetadata | null;
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
  traceId: string | null;
  queuedAt: string;
  startedAt: string | null;
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
  replayStepIndex: number | null;
  resumeStepIndex: number;
  finalOutput: unknown | null;
  status: RunStatus;
  totalTokens: number;
  inheritedTokens: number;
  executedTokens: number;
  traceId: string | null;
  error: string | null;
  queuedAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  createdAt: string;
  updatedAt: string;
  steps: RunStepRead[];
  memoryArtifacts: RunMemoryArtifactRead[];
  packageProvenance: RunPackageProvenanceRead | null;
}

export interface RunRerunDraftRead extends RunTargetIdentityRead {
  sourceRunId: number;
  parameters: UnknownRecord;
}

export interface RunRerunCreateRequest {
  parameters: UnknownRecord;
}

export interface RunStepReplayDraftRead extends RunTargetIdentityRead {
  sourceRunId: number;
  replayStepIndex: number;
  parameters: UnknownRecord;
}

export interface RunStepReplayCreateRequest {
  replayStepIndex: number;
  parameters: UnknownRecord;
}

export interface RunListParams {
  targetKind?: RunTargetKind;
  targetId?: number;
  targetKey?: string;
  targetVersion?: number;
  workflowPackageId?: number;
  workflowPackageKey?: string;
  workflowKey?: string;
  modelConnectionKey?: string;
  status?: RunStatus;
  limit?: number;
  offset?: number;
}
