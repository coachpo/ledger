import type {
  ModelConnectionCapabilities,
  ModelConnectionCapabilityState,
  ModelConnectionCapabilityStatus,
  ModelConnectionOutputStrategyPolicy,
  ModelConnectionParallelToolCallsPolicy,
  ModelConnectionProtocolProfile,
  ModelConnectionReasoningPolicy,
  ModelConnectionStreamingPolicy,
} from "@/lib/types/model-connection";

export const PROTOCOL_PROFILE_LABELS: Record<
  ModelConnectionProtocolProfile,
  string
> = {
  openai_chat_completions: "Chat Completions-compatible",
  openai_responses: "Responses-compatible",
};

export const PROTOCOL_PROFILE_DESCRIPTIONS: Record<
  ModelConnectionProtocolProfile,
  string
> = {
  openai_chat_completions:
    "Use a Chat Completions-compatible request and response shape.",
  openai_responses: "Use a Responses-compatible request and response shape.",
};
export const CAPABILITY_STATUS_LABELS: Record<
  ModelConnectionCapabilityStatus,
  string
> = {
  notApplicable: "Not applicable",
  supported: "Supported",
  unknown: "Unknown",
  unsupported: "Unsupported",
};

export const CAPABILITY_DEFINITIONS = [
  { key: "textGeneration", label: "Text generation" },
  { key: "chatCompletions", label: "Chat Completions protocol" },
  { key: "responsesApi", label: "Responses protocol" },
  { key: "streaming", label: "Streaming responses" },
  { key: "nativeToolCalls", label: "Native tool calls" },
  { key: "parallelToolCalls", label: "Parallel tool calls" },
  { key: "jsonObjectOutput", label: "JSON object output" },
  { key: "strictJsonSchemaOutput", label: "Strict JSON schema output" },
  { key: "reasoningHints", label: "Reasoning hints" },
  { key: "usageReporting", label: "Usage reporting" },
  { key: "systemMessages", label: "System messages" },
] as const satisfies readonly {
  key: keyof ModelConnectionCapabilities;
  label: string;
}[];

export const CAPABILITY_LABEL_BY_KEY = Object.fromEntries(
  CAPABILITY_DEFINITIONS.map(({ key, label }) => [key, label]),
) as Record<keyof ModelConnectionCapabilities, string>;

export const SUMMARY_CAPABILITY_KEYS = [
  "strictJsonSchemaOutput",
  "nativeToolCalls",
  "jsonObjectOutput",
  "reasoningHints",
  "streaming",
  "usageReporting",
] as const satisfies readonly (keyof ModelConnectionCapabilities)[];

export const PROBE_CAPABILITY_KEYS = CAPABILITY_DEFINITIONS.map(
  (definition) => definition.key,
);
export const OUTPUT_STRATEGY_POLICY_LABELS: Record<
  ModelConnectionOutputStrategyPolicy,
  string
> = {
  allow_json_object_validation: "Allow JSON-object validation fallback",
  allow_plain_text: "Allow plain text",
  prefer_strict_schema: "Prefer strict schema",
  require_strict_schema: "Require strict schema",
};

export const PARALLEL_TOOL_CALLS_POLICY_LABELS: Record<
  ModelConnectionParallelToolCallsPolicy,
  string
> = {
  allow: "Allow parallel calls",
  forbid: "Forbid tool calls",
  serialize: "Serialize tool calls",
};

export const REASONING_POLICY_LABELS: Record<
  ModelConnectionReasoningPolicy,
  string
> = {
  allow: "Allow reasoning hints",
  forbid: "Forbid reasoning hints",
};
export const STREAMING_POLICY_LABELS: Record<
  ModelConnectionStreamingPolicy,
  string
> = {
  allow: "Allow streaming",
  forbid: "Forbid streaming",
};

export function defaultCapabilityState(
  status: ModelConnectionCapabilityStatus = "unknown",
): ModelConnectionCapabilityState {
  return { detail: null, lastProbedAt: null, status };
}

export function createDefaultCapabilities(
  protocolProfile: ModelConnectionProtocolProfile,
): ModelConnectionCapabilities {
  const chatStatus =
    protocolProfile === "openai_chat_completions" ? "supported" : "notApplicable";
  const responsesStatus =
    protocolProfile === "openai_responses" ? "supported" : "notApplicable";

  return {
    chatCompletions: defaultCapabilityState(chatStatus),
    jsonObjectOutput: defaultCapabilityState(),
    nativeToolCalls: defaultCapabilityState(),
    parallelToolCalls: defaultCapabilityState(),
    reasoningHints: defaultCapabilityState(),
    responsesApi: defaultCapabilityState(responsesStatus),
    strictJsonSchemaOutput: defaultCapabilityState(),
    streaming: defaultCapabilityState(),
    systemMessages: defaultCapabilityState(),
    textGeneration: defaultCapabilityState("supported"),
    usageReporting: defaultCapabilityState(),
  };
}

export function normalizeCapabilities(
  protocolProfile: ModelConnectionProtocolProfile,
  capabilities?: Partial<ModelConnectionCapabilities>,
): ModelConnectionCapabilities {
  const defaults = createDefaultCapabilities(protocolProfile);
  const normalized = Object.fromEntries(
    CAPABILITY_DEFINITIONS.map(({ key }) => [
      key,
      {
        ...defaults[key],
        ...(capabilities?.[key] ?? {}),
      },
    ]),
  );

  return normalized as unknown as ModelConnectionCapabilities;
}

export function capabilitiesForProtocolProfile(
  current: ModelConnectionCapabilities,
  protocolProfile: ModelConnectionProtocolProfile,
): ModelConnectionCapabilities {
  const defaults = createDefaultCapabilities(protocolProfile);

  return {
    ...current,
    chatCompletions: defaults.chatCompletions,
    responsesApi: defaults.responsesApi,
  };
}

export function getCapabilityCounts(capabilities: ModelConnectionCapabilities) {
  return CAPABILITY_DEFINITIONS.reduce(
    (counts, { key }) => {
      counts[capabilities[key].status] += 1;
      return counts;
    },
    { notApplicable: 0, supported: 0, unknown: 0, unsupported: 0 } satisfies Record<
      ModelConnectionCapabilityStatus,
      number
    >,
  );
}
export function formatCapabilitySummary(
  capabilities: ModelConnectionCapabilities,
): string {
  const counts = getCapabilityCounts(capabilities);
  return [
    `${counts.supported} supported`,
    `${counts.unsupported} unsupported`,
    `${counts.unknown} unknown`,
  ].join(" · ");
}
