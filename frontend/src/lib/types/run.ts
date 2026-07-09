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

export type RunStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";
type RunQueueState = "waiting" | "blocked";
export type RunQueueReason =
  | "awaiting-worker-capacity"
  | "blocked-by-package-serial-policy";
export type RunStepStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "skipped";
type RunStepOrigin = "planned";
type RunInvocationInputMode = "passthrough" | "wired";
type RunInvocationResolvedInputOrigin = "derived" | "passthrough";
type RunInvocationOutputOrigin = "executed";
type RunOperationKind = "http";
export type RunTargetKind = "workflowPackage";
type RunInvocationResourceScope = "global" | "packageLocal";
type RunScheduleReason = "scheduled" | "manual";

interface RunInvocationScopedRef {
  scope: RunInvocationResourceScope;
  id?: number;
  localId?: number;
  key?: string;
  version?: number;
}

interface RunTargetIdentityRead {
  targetKind: RunTargetKind;
  targetId: number;
  targetKey: string;
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

type RunProviderRetryAttemptOutcome =
  | "retryScheduled"
  | "retryAfterHonored"
  | "exhausted";
type RunProviderRetryTerminalOutcome =
  | "succeededAfterRetry"
  | "exhausted";

interface RunProviderRetryAttemptRead {
  attempt: number;
  outcome: RunProviderRetryAttemptOutcome;
  errorCode: string;
  statusCode?: number | null;
  failureClass: string;
  delayMs?: number | null;
}

interface RunProviderRetriesRead {
  policy: "transientProviderRetry/v1";
  maxAttempts: number;
  attempts: RunProviderRetryAttemptRead[];
  terminalOutcome: RunProviderRetryTerminalOutcome;
}

interface RunModelGatewayMetadataRead {
  selectedStrategies?: RunModelGatewaySelectedStrategiesRead | null;
  usage?: RunModelGatewayUsageRead | null;
  providerRetries?: RunProviderRetriesRead | null;
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
  /** Derived snapshot field for historical run provenance; prefer protocolProfile. */
  apiStyle: ModelConnectionApiStyle;
  timeoutSeconds: number;
  hasApiKey: boolean;
}

interface RunExtensionDependencyRead {
  extensionKey: string;
  surfaces: string[];
  fields: string[];
}

interface RunPackageLocalResourceRefsRead {
  agents: string[];
  outputSchemas: string[];
  capabilityProfiles: string[];
  mcpServers: string[];
  workflows: string[];
}

interface RunPackagePreflightSummaryRead {
  ready: boolean;
  blockingErrors: UnknownRecord[];
  warnings: UnknownRecord[];
}

interface RunProgressRead {
  unit: "invocation";
  terminalCount: number;
  totalCount: number;
  percent: number;
}

interface RunQueueRead {
  state: RunQueueState;
  reason: RunQueueReason;
  message: string;
  blockingRunId: number | null;
}

interface RunScheduleProvenanceRead {
  scheduleId: number | null;
  scheduleFireId: number | null;
  scheduleName: string | null;
  packageId: number | null;
  packageKey: string | null;
  workflowKey: string | null;
  timezone: string | null;
  recurrence: UnknownRecord | null;
  fireKey: string | null;
  reason: RunScheduleReason | null;
  scheduledFor: string | null;
  scheduledLocalDate: string | null;
  scheduledLocalTime: string | null;
  scheduledLocalDateTime: string | null;
  materializedAt: string | null;
  scheduleDeletedAt: string | null;
}

interface RunPackageLaunchSnapshotRead {
  workflowKey: string;
  workflowName: string;
  workflowDescription: string;
  inputSchema: UnknownRecord;
  parameters: UnknownRecord;
}

interface RunCurrentPackageAuditRead {
  available: boolean;
  manifestHash?: string | null;
  compiledHash?: string | null;
  manifestHashMatchesSnapshot?: boolean | null;
  compiledHashMatchesSnapshot?: boolean | null;
  unavailableReason?: string | null;
}

interface RunPackageProvenanceRead {
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
  scheduleId: number | null;
  scheduleFireId: number | null;
  scheduledFor: string | null;
  scheduleReason: RunScheduleReason | null;
  scheduleProvenance: RunScheduleProvenanceRead | null;
  traceId: string | null;
  workflowKey: string | null;
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
  finalOutput: unknown | null;
  status: RunStatus;
  totalTokens: number;
  inheritedTokens: number;
  executedTokens: number;
  progress: RunProgressRead;
  queue: RunQueueRead | null;
  scheduleId: number | null;
  scheduleFireId: number | null;
  scheduledFor: string | null;
  scheduleReason: RunScheduleReason | null;
  scheduleProvenance: RunScheduleProvenanceRead | null;
  traceId: string | null;
  error: string | null;
  queuedAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  createdAt: string;
  updatedAt: string;
  steps: RunStepRead[];
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

export interface RunListParams {
  workflowPackageId?: number;
  workflowPackageKey?: string;
  workflowKey?: string;
  modelConnectionKey?: string;
  status?: RunStatus;
  limit?: number;
  offset?: number;
}
