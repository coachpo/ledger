import type { UnknownRecord } from "./common";
import type {
  ModelConnectionApiStyle,
  ModelConnectionCapabilities,
  ModelConnectionOutputStrategyPolicy,
  ModelConnectionParallelToolCallsPolicy,
  ModelConnectionProtocolProfile,
  ModelConnectionReasoningEffort,
  ModelConnectionReasoningPolicy,
  ModelConnectionStreamingPolicy,
} from "./model-connection";

export type RunStatus = "queued" | "running" | "succeeded" | "failed";
export type RunQueueState = "waiting" | "blocked";
export type RunQueueReason = "awaiting-worker-capacity" | "blocked-by-package-serial-policy";
export type RunStepStatus = "pending" | "running" | "succeeded" | "failed" | "skipped";
export type RunStepOrigin = "planned" | "copied";
export type RunInvocationInputMode = "passthrough" | "wired";
export type RunInvocationResolvedInputOrigin = "derived" | "edited" | "copied" | "passthrough";
export type RunInvocationOutputOrigin = "executed" | "edited" | "copied";
export type RunOperationKind = "http";
export type RunTargetKind = "agent" | "workflow" | "workflowPackage";
export type RunInvocationResourceScope = "global" | "packageLocal";

export interface RunInvocationScopedRef {
  scope: RunInvocationResourceScope;
  id?: number;
  localId?: number;
  key?: string;
  version?: number;
}

export interface RunTargetIdentityRead {
  targetKind: RunTargetKind;
  targetId: number;
  targetKey: string;
}

export interface RunAgentErrorRead {
  code: string;
  message: string;
  details: UnknownRecord[];
}

export interface RunModelGatewaySelectedStrategiesRead {
  outputStrategy?: string | null;
  toolCallStrategy?: string | null;
  parallelToolCalls?: boolean | null;
  reasoningStrategy?: string | null;
  reasoningEffort?: string | null;
  streamingStrategy?: string | null;
}

export interface RunModelGatewayUsageRead {
  inputTokens?: number | null;
  outputTokens?: number | null;
  totalTokens?: number | null;
}

export interface RunModelGatewayMetadataRead {
  selectedStrategies?: RunModelGatewaySelectedStrategiesRead | null;
  usage?: RunModelGatewayUsageRead | null;
}

export interface RunGraphMetadata {
  [key: string]: unknown;
  branchId?: string;
  fanoutId?: string;
  graphPath?: string;
  loopId?: string;
  loopIteration?: number;
  modelGateway?: RunModelGatewayMetadataRead | null;
  nodeId?: string;
  nodeKind?: "step" | "sequence" | "fanout" | "loop" | "http";
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

export type RunMemoryEventType =
  | "retrieved"
  | "injected"
  | "written"
  | "reused"
  | "superseded"
  | "reviewed"
  | "failed";

export interface RunMemoryEventRead {
  id: number;
  runId: number;
  runStepId: number | null;
  runAgentInvocationId: number | null;
  runOperationInvocationId: number | null;
  stepId: string | null;
  invocationId: string | null;
  eventType: RunMemoryEventType;
  memoryId: string | null;
  revisionId: string | null;
  retrievalMode: string | null;
  filters: UnknownRecord;
  budget: UnknownRecord;
  excerpt: string | null;
  injectedText: string | null;
  resultSnapshot: UnknownRecord;
  statusSnapshot: UnknownRecord;
  traceSpanId: string | null;
  createdAt: string;
}

export interface RunPackageResolvedModelConnectionRead {
  key: string;
  name: string;
  protocolProfile: ModelConnectionProtocolProfile;
  baseUrl: string;
  modelId: string;
  reasoningEffort: ModelConnectionReasoningEffort | null;
  capabilities: ModelConnectionCapabilities;
  outputStrategyPolicy: ModelConnectionOutputStrategyPolicy;
  parallelToolCallsPolicy: ModelConnectionParallelToolCallsPolicy;
  reasoningPolicy: ModelConnectionReasoningPolicy;
  streamingPolicy: ModelConnectionStreamingPolicy;
  probeCacheTtlSeconds: number;
  /** @deprecated Historical compatibility only; use protocolProfile. */
  apiStyle: ModelConnectionApiStyle;
  timeoutSeconds: number;
  hasApiKey: boolean;
}

export interface RunExtensionDependencyRead {
  extensionKey: string;
  surfaces: string[];
  fields: string[];
}

export interface RunPackageLocalResourceRefsRead {
  agents: string[];
  outputSchemas: string[];
  capabilityProfiles: string[];
  mcpServers: string[];
  workflows: string[];
}

export interface RunPackagePreflightSummaryRead {
  ready: boolean;
  blockingErrors: UnknownRecord[];
  warnings: UnknownRecord[];
}

export interface RunProgressRead {
  unit: "invocation";
  terminalCount: number;
  totalCount: number;
  percent: number;
}

export interface RunQueueRead {
  state: RunQueueState;
  reason: RunQueueReason;
  message: string;
  blockingRunId: number | null;
}

export interface RunPackageLaunchSnapshotRead {
  workflowKey: string;
  workflowName: string;
  workflowDescription: string;
  inputSchema: UnknownRecord;
  parameters: UnknownRecord;
}

export interface RunCurrentPackageAuditRead {
  available: boolean;
  manifestHash?: string | null;
  compiledHash?: string | null;
  manifestHashMatchesSnapshot?: boolean | null;
  compiledHashMatchesSnapshot?: boolean | null;
  unavailableReason?: string | null;
}

export interface RunPackageProvenanceRead {
  workflowPackageId: number;
  workflowPackageKey: string;
  workflowPackageName: string;
  workflowPackageDescription: string;
  workflowPackageStatus?: string | null;
  workflowPackageManifestHash: string;
  workflowPackageCompiledHash: string;
  workflowKey: string;
  workflowName: string;
  workflowDescription: string;
  manifestSource: string;
  packageDefinition: UnknownRecord;
  compiledPlan: UnknownRecord;
  launchSnapshot: RunPackageLaunchSnapshotRead | null;
  extensionDependencies: RunExtensionDependencyRead[];
  localResourceRefs: RunPackageLocalResourceRefsRead;
  resolvedModelConnections: RunPackageResolvedModelConnectionRead[];
  preflightSummary: RunPackagePreflightSummaryRead | null;
  currentPackage: RunCurrentPackageAuditRead | null;
}

export interface RunAgentInvocationRead {
  id: number;
  runStepId: number;
  runId: number;
  stepIndex: number;
  slot: string;
  position: number;
  agentRef: RunInvocationScopedRef;
  outputSchemaRef: RunInvocationScopedRef;
  agentKey: string;
  agentVersion: number;
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

export interface RunOperationInvocationRead {
  id: number;
  runStepId: number;
  runId: number;
  stepIndex: number;
  slot: string;
  position: number;
  operationKey: string;
  operationKind: RunOperationKind;
  outputSchemaRef: RunInvocationScopedRef;
  outputSchemaVersion: number;
  method: string | null;
  timeoutSeconds: number | null;
  requestMetadata: UnknownRecord;
  responseMetadata: UnknownRecord;
  graphMetadata: RunGraphMetadata | null;
  optional: boolean;
  status: RunStepStatus;
  output: unknown | null;
  outputOrigin: RunInvocationOutputOrigin | null;
  errorCode: string | null;
  errorMessage: string | null;
  errorDetails: UnknownRecord[];
  durationMs: number | null;
  traceSpanId: string | null;
  sourceOperationInvocationId: number | null;
  sourceRunId: number | null;
  sourceRunStepId: number | null;
  sourceStepIndex: number | null;
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
  operationInvocations: RunOperationInvocationRead[];
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
  progress: RunProgressRead;
  queue: RunQueueRead | null;
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
  progress: RunProgressRead;
  queue: RunQueueRead | null;
  traceId: string | null;
  error: string | null;
  queuedAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  createdAt: string;
  updatedAt: string;
  steps: RunStepRead[];
  memoryArtifacts: RunMemoryArtifactRead[];
  memoryEvents: RunMemoryEventRead[];
  extensionDependencies: RunExtensionDependencyRead[];
  packageProvenance: RunPackageProvenanceRead | null;
}

export interface RunRerunDraftRead extends RunTargetIdentityRead {
  sourceRunId: number;
  parameters: UnknownRecord;
  ready: boolean;
  blockingErrors: UnknownRecord[];
  warnings: UnknownRecord[];
  packageProvenance: RunPackageProvenanceRead | null;
}

export interface RunRerunCreateRequest {
  parameters: UnknownRecord;
}

export interface RunForkDraftRead extends RunTargetIdentityRead {
  sourceRunId: number;
  sourceInvocationId: number;
  invocationInput: UnknownRecord;
  ready: boolean;
  blockingErrors: UnknownRecord[];
  warnings: UnknownRecord[];
  packageProvenance: RunPackageProvenanceRead | null;
}

export interface RunForkCreateRequest {
  sourceInvocationId: number;
  invocationInput: UnknownRecord;
}

export interface RunListParams {
  targetKind?: RunTargetKind;
  targetId?: number;
  targetKey?: string;
  workflowPackageId?: number;
  workflowPackageKey?: string;
  workflowKey?: string;
  modelConnectionKey?: string;
  status?: RunStatus;
  limit?: number;
  offset?: number;
}
