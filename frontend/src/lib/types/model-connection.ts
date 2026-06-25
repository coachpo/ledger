export type ModelConnectionReasoningEffort = string;
export type ModelConnectionProtocolProfile =
  | "openai_chat_completions"
  | "openai_responses";
/** Derived snapshot field for historical run provenance. */
export type ModelConnectionApiStyle = "responses" | "chat_completions";
export type ModelConnectionCapabilityStatus =
  | "supported"
  | "unsupported"
  | "unknown"
  | "notApplicable";
export type ModelConnectionOutputStrategyPolicy =
  | "require_strict_schema"
  | "prefer_strict_schema"
  | "allow_json_object_validation"
  | "allow_plain_text";
export type ModelConnectionParallelToolCallsPolicy = "allow" | "serialize" | "forbid";
export type ModelConnectionReasoningPolicy = "allow" | "forbid";
export type ModelConnectionStreamingPolicy = "allow" | "forbid";

export interface ModelConnectionCapabilityState {
  status: ModelConnectionCapabilityStatus;
  detail?: string | null;
  lastProbedAt?: string | null;
}

export interface ModelConnectionCapabilities {
  textGeneration: ModelConnectionCapabilityState;
  chatCompletions: ModelConnectionCapabilityState;
  responsesApi: ModelConnectionCapabilityState;
  streaming: ModelConnectionCapabilityState;
  nativeToolCalls: ModelConnectionCapabilityState;
  parallelToolCalls: ModelConnectionCapabilityState;
  jsonObjectOutput: ModelConnectionCapabilityState;
  strictJsonSchemaOutput: ModelConnectionCapabilityState;
  reasoningHints: ModelConnectionCapabilityState;
  usageReporting: ModelConnectionCapabilityState;
  systemMessages: ModelConnectionCapabilityState;
}

export interface ModelConnectionCreateInput {
  key: string;
  name: string;
  description?: string;
  protocolProfile?: ModelConnectionProtocolProfile;
  baseUrl: string;
  modelId: string;
  reasoningEffort?: ModelConnectionReasoningEffort | null;
  timeoutSeconds?: number;
  apiKey?: string;
}

export interface ModelConnectionUpdateInput {
  name?: string;
  description?: string | null;
  protocolProfile?: ModelConnectionProtocolProfile;
  baseUrl?: string;
  modelId?: string;
  reasoningEffort?: ModelConnectionReasoningEffort | null;
  timeoutSeconds?: number;
  apiKey?: string;
}

export interface ModelConnectionListItemRead {
  id: number;
  key: string;
  name: string;
  description: string;
  protocolProfile: ModelConnectionProtocolProfile;
  baseUrl: string;
  modelId: string;
  reasoningEffort: ModelConnectionReasoningEffort | null;
  capabilities: ModelConnectionCapabilities;
  outputStrategyPolicy: ModelConnectionOutputStrategyPolicy;
  parallelToolCallsPolicy: ModelConnectionParallelToolCallsPolicy;
  reasoningPolicy: ModelConnectionReasoningPolicy;
  streamingPolicy: ModelConnectionStreamingPolicy;
  lastProbedAt?: string | null;
  probeCacheTtlSeconds: number;
  timeoutSeconds: number;
  lastTestedAt?: string | null;
  lastTestOk?: boolean | null;
  lastTestMessage?: string | null;
}

export interface ModelConnectionRead extends ModelConnectionListItemRead {
  createdAt: string;
  updatedAt: string;
}

export interface ModelConnectionListRead {
  items: ModelConnectionListItemRead[];
}

export type ModelConnectionListParams = Record<string, never>;

export interface ModelConnectionConnectionTestRead {
  modelConnectionId: number;
  ok: boolean;
  message: string;
  lastTestedAt: string;
}

export interface ModelConnectionCapabilityProbeRequest {
  capabilityKeys?: (keyof ModelConnectionCapabilities)[];
  refresh?: boolean;
}

export interface ModelConnectionCapabilityProbeRead {
  modelConnectionId: number;
  requestedCapabilityKeys: (keyof ModelConnectionCapabilities)[];
  cached: boolean;
  lastProbedAt: string;
  probeCacheTtlSeconds: number;
  capabilities: ModelConnectionCapabilities;
}
