export type OrchestrationMentionKind = "builtin" | "character";

export interface OrchestrationRoleRead {
  id: number;
  key: string;
  name: string;
  description: string | null;
  systemPrompt: string;
  capabilityBundleKeys: string[];
  enabled: boolean;
  version: number;
  createdAt: string;
  updatedAt: string;
}

export interface OrchestrationRoleCreateInput {
  key: string;
  name: string;
  description?: string | null;
  systemPrompt: string;
  capabilityBundleKeys?: string[];
  enabled?: boolean;
}

export interface OrchestrationRoleUpdateInput {
  name?: string;
  description?: string | null;
  systemPrompt?: string;
  capabilityBundleKeys?: string[];
  enabled?: boolean;
}

export interface OrchestrationCharacterRead {
  id: number;
  handle: string;
  displayName: string;
  description: string | null;
  roleId: number;
  roleKey: string;
  promptAppend: string | null;
  capabilityBundleKeys: string[];
  enabled: boolean;
  version: number;
  createdAt: string;
  updatedAt: string;
}

export interface OrchestrationCharacterCreateInput {
  handle: string;
  displayName: string;
  description?: string | null;
  roleId: number;
  promptAppend?: string | null;
  capabilityBundleKeys?: string[];
  enabled?: boolean;
}

export interface OrchestrationCharacterUpdateInput {
  displayName?: string;
  description?: string | null;
  roleId?: number;
  promptAppend?: string | null;
  capabilityBundleKeys?: string[];
  enabled?: boolean;
}

export interface OrchestrationMentionCatalogItem {
  handle: string;
  canonicalTargetId: string;
  displayName: string;
  description: string | null;
  kind: OrchestrationMentionKind;
  roleKey?: string | null;
}
