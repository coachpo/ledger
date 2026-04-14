import type { UnknownRecord } from "./common";
import type {
  ApprovalMode,
  CapabilityType,
  RuntimeApprovalListParams,
  RuntimeArtifactListRead,
  RuntimeApprovalListRead,
  RuntimeApprovalRead,
  RuntimeArtifactRead,
  RuntimeRunListParams,
  RuntimeRunListRead,
  RuntimeRunRead,
  RuntimeTraceEventListParams,
  RuntimeTraceEventListRead,
  SpecLifecycleStatus,
  SpecOrigin,
} from "./runtime";

export type {
  RuntimeApprovalListRead,
  RuntimeApprovalRead,
  RuntimeArtifactListRead,
  RuntimeArtifactRead,
  RuntimeRunListRead,
  RuntimeRunRead,
  RuntimeTraceEventListRead,
};

export type { RuntimeApprovalListParams, RuntimeRunListParams, RuntimeTraceEventListParams };

export interface FinalOutputContractRead {
  kind: string;
  schema: UnknownRecord | null;
  description: string;
}

export interface MentionPolicyRead {
  version: number;
  allowCharacterPersonas: boolean;
  allowedBuiltinHandles: string[];
}

export interface ApprovalPolicyOverrideRead {
  stepKey: string;
  capabilityKey?: string | null;
  approvalMode: ApprovalMode;
}

export interface AgentSpecRead {
  id: number;
  key: string;
  version: number;
  origin: SpecOrigin;
  status: SpecLifecycleStatus;
  name: string;
  instructions: string;
  modelPolicy: UnknownRecord;
  finalOutputContract: FinalOutputContractRead | null;
  defaultCapabilityBundleKeys: string[];
  defaultPersonaProfileKeys: string[];
  createdAt: string;
  updatedAt: string;
}

export interface AgentSpecListRead {
  items: AgentSpecRead[];
}

export interface AgentSpecDraftCreateInput {
  key: string;
  name: string;
  instructions: string;
  modelPolicy?: UnknownRecord;
  finalOutputContract?: FinalOutputContractRead | null;
  defaultCapabilityBundleKeys?: string[];
  defaultPersonaProfileKeys?: string[];
}

export interface AgentSpecDraftUpdateInput {
  name?: string;
  instructions?: string;
  modelPolicy?: UnknownRecord;
  finalOutputContract?: FinalOutputContractRead | null;
  defaultCapabilityBundleKeys?: string[];
  defaultPersonaProfileKeys?: string[];
}

export interface WorkflowSpecRead {
  id: number;
  key: string;
  version: number;
  origin: SpecOrigin;
  status: SpecLifecycleStatus;
  name: string;
  graphDefinition: UnknownRecord;
  finalOutputContract: UnknownRecord;
  mentionPolicy: MentionPolicyRead;
  executionMode: string | null;
  defaultToolIds: string[];
  allowedCapabilityBundleKeys: string[];
  connectorIds: string[];
  reviewMode: string | null;
  approvalPolicyOverrides: ApprovalPolicyOverrideRead[];
  createdAt: string;
  updatedAt: string;
  entryAgentKey: string | null;
}

export interface WorkflowSpecListRead {
  items: WorkflowSpecRead[];
}

export interface PersonaProfileRead {
  id: number;
  key: string;
  version: number;
  origin: SpecOrigin;
  status: SpecLifecycleStatus;
  kind: "role_template" | "character_profile" | "builtin_profile" | "managed_persona";
  displayName: string;
  enabled: boolean;
  handle: string | null;
  canonicalTargetId: string;
  parentProfileKey: string | null;
  parentProfileVersion: number | null;
  legacySourceVersion: number | null;
  systemPromptFragment: string;
  promptAppendFragment: string;
  defaultCapabilityBundleKeys: string[];
  createdAt: string;
  updatedAt: string;
}

export interface PersonaProfileListRead {
  items: PersonaProfileRead[];
}

export interface StudioVersionHistoryItem {
  version: number;
  status: SpecLifecycleStatus;
  origin: SpecOrigin;
  createdAt: string;
}

export interface StudioVersionHistoryRead {
  items: StudioVersionHistoryItem[];
}

export interface PersonaProfileDraftCreateInput {
  key: string;
  displayName: string;
  enabled?: boolean;
  handle?: string | null;
  systemPromptFragment?: string;
  promptAppendFragment?: string;
  defaultCapabilityBundleKeys?: string[];
}

export interface PersonaProfileDraftUpdateInput {
  displayName?: string;
  enabled?: boolean;
  handle?: string | null;
  systemPromptFragment?: string;
  promptAppendFragment?: string;
  defaultCapabilityBundleKeys?: string[];
}

export interface WorkflowSpecDraftCreateInput {
  key: string;
  name: string;
  graphDefinition?: UnknownRecord;
  finalOutputContract: FinalOutputContractRead;
  mentionPolicy: MentionPolicyRead;
  executionMode?: string | null;
  defaultToolIds?: string[];
  allowedCapabilityBundleKeys?: string[];
  connectorIds?: string[];
  reviewMode?: string | null;
  approvalPolicyOverrides?: ApprovalPolicyOverrideRead[];
}

export interface WorkflowSpecDraftUpdateInput {
  name?: string;
  graphDefinition?: UnknownRecord;
  finalOutputContract?: FinalOutputContractRead;
  mentionPolicy?: MentionPolicyRead;
  executionMode?: string | null;
  defaultToolIds?: string[];
  allowedCapabilityBundleKeys?: string[];
  connectorIds?: string[];
  reviewMode?: string | null;
  approvalPolicyOverrides?: ApprovalPolicyOverrideRead[];
}

export interface CapabilityBundleMemberWrite {
  memberType: CapabilityType;
  capabilityKey: string;
  capabilityVersion: number;
}

export type CapabilityBundleMemberRead = CapabilityBundleMemberWrite;

export interface CapabilityRegistryEntryRead {
  id: number;
  key: string;
  version: number;
  origin: SpecOrigin;
  status: SpecLifecycleStatus;
  type: CapabilityType;
  displayName: string;
  description: string;
  approvalMode: ApprovalMode;
  adapterKey: string | null;
  configSchema: UnknownRecord | null;
  bundleMembers: CapabilityBundleMemberRead[] | null;
  transport: string | null;
  lifecycle: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface CapabilityRegistryEntryListRead {
  items: CapabilityRegistryEntryRead[];
}

export interface CapabilityRegistryEntryDraftCreateInput {
  key: string;
  type: CapabilityType;
  displayName: string;
  description: string;
  approvalMode?: ApprovalMode | null;
  adapterKey?: string | null;
  configSchema?: UnknownRecord | null;
  bundleMembers?: CapabilityBundleMemberWrite[] | null;
  transport?: string | null;
  lifecycle?: string | null;
}

export interface CapabilityRegistryEntryDraftUpdateInput {
  type?: CapabilityType;
  displayName?: string;
  description?: string;
  approvalMode?: ApprovalMode | null;
  adapterKey?: string | null;
  configSchema?: UnknownRecord | null;
  bundleMembers?: CapabilityBundleMemberWrite[] | null;
  transport?: string | null;
  lifecycle?: string | null;
}

export interface StudioArtifactListParams {
  runId?: number;
  callerType?: RuntimeRunListParams["callerType"];
  callerId?: number;
  workflowSpecKey?: string;
  personaProfileKey?: string;
  capabilityKey?: string;
}

export interface StudioSpecListParams {
  origin?: SpecOrigin;
  status?: SpecLifecycleStatus;
}

export interface PersonaProfileListParams extends StudioSpecListParams {
  kind?: PersonaProfileRead["kind"];
  enabled?: boolean;
}

export interface CapabilityListParams extends StudioSpecListParams {
  type?: CapabilityType;
}
