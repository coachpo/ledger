import type { UnknownRecord } from "./common";

export type SpecOrigin = "seeded" | "managed" | "imported";
export type SpecLifecycleStatus = "DRAFT" | "ACTIVE" | "DEPRECATED" | "ARCHIVED";
export type PersonaProfileKind =
  | "role_template"
  | "character_profile"
  | "builtin_profile"
  | "managed_persona";
export type CapabilityType = "tool" | "connector" | "bundle";
export type ApprovalMode = "not_required" | "required";

export type RuntimeCallerType = "tryout" | "studio" | "api";
export type ArchivedRuntimeCallerType = "backtest";
export type RuntimeRunCallerType = RuntimeCallerType | ArchivedRuntimeCallerType;
export type RuntimeExecutionKind = "workflow" | "single_agent";
export type RuntimeRunStatus =
  | "QUEUED"
  | "RUNNING"
  | "WAITING_APPROVAL"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELLED";
export type RuntimeApprovalStatus = "PENDING" | "APPROVED" | "DENIED" | "EXPIRED";
export type RuntimeTraceEventType =
  | "RUN_CREATED"
  | "STEP_STARTED"
  | "STEP_COMPLETED"
  | "TOOL_CALLED"
  | "TOOL_RETURNED"
  | "APPROVAL_REQUESTED"
  | "APPROVAL_RESOLVED"
  | "RUN_COMPLETED"
  | "RUN_FAILED"
  | "RUN_CANCELLED"
  | "RUN_EXPIRED"
  | "WARNING_EMITTED";

export interface TraceSummary {
  eventCount: number;
  toolCallCount: number;
  warningCount: number;
  lastEventAt: string | null;
}

export interface ApprovalSummary {
  totalCount: number;
  pendingCount: number;
  approvedCount: number;
  deniedCount: number;
  expiredCount: number;
}

export interface TerminalError {
  code: string;
  message: string;
}

export interface PersonaProfileRef {
  personaProfileKey: string;
  personaProfileVersion?: number | null;
  canonicalTargetId?: string | null;
  personaKind?: PersonaProfileKind | null;
  origin?: SpecOrigin | null;
  selectionSource?: string | null;
  parentPersonaProfileRef?: PersonaProfileRef | null;
  legacySourceVersion?: number | null;
}

export interface CapabilityRef {
  capabilityKey: string;
  capabilityVersion?: number | null;
  capabilityType?: CapabilityType | null;
  selectionSource?: string | null;
  effectiveApprovalMode?: ApprovalMode | null;
  effectiveConfig?: UnknownRecord | null;
}

export interface ResolvedCapabilityRead {
  capabilityKey: string;
  capabilityVersion: number;
  capabilityType: CapabilityType;
  approvalMode: ApprovalMode;
  displayName: string | null;
  transport: string | null;
  lifecycle: string | null;
  effectiveConfig: UnknownRecord;
}

export interface WorkflowAgentRef {
  stepKey: string;
  agentSpecKey: string;
  agentSpecVersion: number;
  personaProfileRefs: PersonaProfileRef[];
  capabilityRefs: CapabilityRef[];
}

export interface ResolvedBuiltinVersionRead {
  canonicalTargetId: string;
  handle: string;
  revision: number;
}

export interface ResolvedRoleVersionRead {
  canonicalTargetId: string;
  roleId: number;
  version: number;
}

export interface ResolvedCharacterVersionRead {
  canonicalTargetId: string;
  characterId: number;
  version: number;
}

export interface ResolvedBundleVersionRead {
  bundleKey: string;
  revision: number;
}

export interface ResolvedToolVersionRead {
  toolId: string;
  revision: number;
}

export interface ResolvedConnectorVersionRead {
  connectorId: string;
  revision: number;
}

export interface ResolvedMentionRead {
  originalText: string;
  sourceHandle: string;
  canonicalTargetId: string;
  targetType: string;
  mentionOrder: number;
  personaProfileKey: string;
  personaProfileVersion: number;
  legacyRoleId?: number | null;
  legacyRoleVersion?: number | null;
  legacyCharacterId?: number | null;
  legacyCharacterVersion?: number | null;
}

export interface ApprovalDetailSummary {
  approvalMode: ApprovalMode | null;
  displayName: string | null;
  transport: string | null;
}

export interface RuntimeRunCreateInput {
  callerType: RuntimeCallerType;
  callerId?: number | null;
  callerScopeKey?: string | null;
  callerIdentityKey?: string | null;
  executionKind: RuntimeExecutionKind;
  workflowSpecKey?: string | null;
  workflowSpecVersion?: number | null;
  agentSpecKey?: string | null;
  agentSpecVersion?: number | null;
  inputs?: Record<string, string>;
  personaProfileRefs?: PersonaProfileRef[];
  persistRun?: boolean;
}

export interface RuntimeRunCreated {
  runId: number;
  status: RuntimeRunStatus;
  expiresAt: string | null;
}

export interface RuntimeRunListItem {
  runId: number;
  status: RuntimeRunStatus;
  callerType: RuntimeRunCallerType;
  callerId: number | null;
  callerScopeKey: string | null;
  callerIdentityKey: string | null;
  executionKind: RuntimeExecutionKind;
  workflowSpecKey: string | null;
  workflowSpecVersion: number | null;
  agentSpecKey: string | null;
  agentSpecVersion: number | null;
  attemptNumber: number;
  expiresAt: string | null;
  createdAt: string;
}

export interface RuntimeRunRead extends RuntimeRunListItem {
  pendingApprovalIds: number[];
  finalOutput: unknown | null;
  traceSummary: TraceSummary;
  approvalSummary: ApprovalSummary;
  updatedAt: string;
  terminalError: TerminalError | null;
}

export interface RuntimeRunListRead {
  items: RuntimeRunListItem[];
  nextCursor: string | null;
}

export interface RuntimeArtifactRead {
  runId: number;
  finalOutput: unknown | null;
  reportMarkdown: string | null;
  normalizedTradeDecisions: UnknownRecord[] | null;
  entryPromptHash: string;
  fullUserPromptHash: string;
  authoredEntryPromptBody: string | null;
  compiledEntryPromptBody: string | null;
  executionContextBody: string | null;
  promptReportSlug: string | null;
  rawMentionHandles: string[];
  resolvedMentions: ResolvedMentionRead[];
  mentionedTargetOutputs: UnknownRecord[];
  resolvedPersonaProfileRefs: PersonaProfileRef[];
  resolvedWorkflowAgentRefs: WorkflowAgentRef[] | null;
  resolvedCapabilities: ResolvedCapabilityRead[];
  resolvedBuiltinVersions: ResolvedBuiltinVersionRead[];
  resolvedRoleVersions: ResolvedRoleVersionRead[];
  resolvedCharacterVersions: ResolvedCharacterVersionRead[];
  resolvedBundleVersions: ResolvedBundleVersionRead[];
  resolvedToolVersions: ResolvedToolVersionRead[];
  resolvedConnectorVersions: ResolvedConnectorVersionRead[];
  traceSummary: TraceSummary;
  approvalSummary: ApprovalSummary;
  createdAt: string | null;
  terminalError: TerminalError | null;
}

export interface RuntimeArtifactListRead {
  items: RuntimeArtifactRead[];
  nextCursor: string | null;
}

export interface RuntimeApprovalListItem {
  approvalId: number;
  runId: number;
  status: RuntimeApprovalStatus;
  capabilityKey: string;
  stepKey: string;
  callerType: RuntimeRunCallerType;
  callerId: number | null;
  createdAt: string;
}

export interface RuntimeApprovalRead extends RuntimeApprovalListItem {
  summary: ApprovalDetailSummary;
  allowedActions: Array<"approve" | "deny">;
}

export interface RuntimeApprovalListRead {
  items: RuntimeApprovalListItem[];
  nextCursor: string | null;
}

export interface RuntimeApprovalActionInput {
  actor: string;
  reason: string;
}

export interface RuntimeApprovalActionRead {
  approvalId: number;
  status: RuntimeApprovalStatus;
  runId: number;
  resolvedAt: string;
  runStatus: RuntimeRunStatus;
}

export interface RuntimeCancelRead {
  runId: number;
  status: RuntimeRunStatus;
  approvalSummary: ApprovalSummary;
}

export interface RuntimeTraceEventRead {
  runId: number;
  eventIndex: number;
  eventType: RuntimeTraceEventType;
  stepKey: string | null;
  capabilityKey: string | null;
  callerType: RuntimeRunCallerType;
  callerId: number | null;
  createdAt: string;
  approvalId: number | null;
  payload: UnknownRecord;
}

export interface RuntimeTraceEventListRead {
  items: RuntimeTraceEventRead[];
  nextCursor: string | null;
}

export interface RuntimeRunListParams {
  callerType?: RuntimeCallerType;
  callerId?: number;
  callerScopeKey?: string;
  callerIdentityKey?: string;
  workflowSpecKey?: string;
}

export interface RuntimeApprovalListParams {
  runId?: number;
  callerType?: RuntimeCallerType;
  callerId?: number;
  workflowSpecKey?: string;
  capabilityKey?: string;
  status?: RuntimeApprovalStatus;
}

export interface RuntimeTraceEventListParams {
  runId?: number;
  callerType?: RuntimeCallerType;
  callerId?: number;
  workflowSpecKey?: string;
  capabilityKey?: string;
  eventType?: RuntimeTraceEventType;
}
