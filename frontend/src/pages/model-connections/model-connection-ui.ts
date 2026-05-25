import type {
  EvidenceClusterItem,
  EvidenceClusterTone,
} from "@/components/shared/evidence-cluster";
import type {
  ResourceStatusStripItem,
  ResourceStatusTone,
} from "@/components/shared/resource-status-strip";
import { formatDateTime } from "@/lib/format";
import type {
  ModelConnectionCapabilities,
  ModelConnectionCapabilityState,
  ModelConnectionCapabilityStatus,
  ModelConnectionListItemRead,
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

export function formatLastTestStatus(
  connection: ModelConnectionListItemRead,
): string {
  if (connection.lastTestOk === true) {
    return "Passed";
  }

  if (connection.lastTestOk === false) {
    return "Failed";
  }

  return "Not tested";
}

export function formatReasoningEffort(
  value: ModelConnectionListItemRead["reasoningEffort"],
): string {
  return value ?? "Omitted";
}

export function formatRuntimePolicyEvidence(
  connection: ModelConnectionListItemRead,
): string {
  return [
    OUTPUT_STRATEGY_POLICY_LABELS[connection.outputStrategyPolicy],
    PARALLEL_TOOL_CALLS_POLICY_LABELS[connection.parallelToolCallsPolicy],
    REASONING_POLICY_LABELS[connection.reasoningPolicy],
    STREAMING_POLICY_LABELS[connection.streamingPolicy],
  ].join(" · ");
}

export function formatCapabilityDetails(
  connection: ModelConnectionListItemRead,
): string {
  return SUMMARY_CAPABILITY_KEYS.map((capabilityKey) => {
    const capability = connection.capabilities[capabilityKey];
    return `${CAPABILITY_LABEL_BY_KEY[capabilityKey]}: ${
      CAPABILITY_STATUS_LABELS[capability.status]
    }`;
  }).join(" · ");
}

function getLastTestEvidenceTone(
  connection: ModelConnectionListItemRead,
): EvidenceClusterTone {
  if (connection.lastTestOk === true) {
    return "verified";
  }

  if (connection.lastTestOk === false) {
    return "danger";
  }

  return "warning";
}

function getLastTestStatusTone(
  connection: ModelConnectionListItemRead,
): ResourceStatusTone {
  if (connection.lastTestOk === true) {
    return "success";
  }

  if (connection.lastTestOk === false) {
    return "danger";
  }

  return "warning";
}

function getCapabilityEvidenceTone(
  capabilities: ModelConnectionCapabilities,
): EvidenceClusterTone {
  const counts = getCapabilityCounts(capabilities);
  return counts.unsupported > 0 || counts.unknown > 0 ? "warning" : "verified";
}

function getCapabilityStatusTone(
  capabilities: ModelConnectionCapabilities,
): ResourceStatusTone {
  const counts = getCapabilityCounts(capabilities);
  return counts.unsupported > 0 || counts.unknown > 0 ? "warning" : "success";
}

function formatReachabilityValue(connection: ModelConnectionListItemRead): string {
  return connection.lastTestedAt
    ? formatDateTime(connection.lastTestedAt)
    : "No reachability test recorded";
}

function getCredentialState(connection: ModelConnectionListItemRead) {
  if (connection.connectionKind === "deterministic_smoke") {
    return {
      description:
        "Deterministic smoke connections can run offline fixtures without an API key.",
      label: "API key optional",
      tone: "verified" as const,
    };
  }

  return {
    description:
      "Saved provider credentials stay write-only and can only be rotated from the editor.",
    label: "Write-only secret",
    tone: "neutral" as const,
  };
}

export function getModelConnectionStatusItems(
  connection: ModelConnectionListItemRead,
): ResourceStatusStripItem[] {
  return [
    {
      label: "Test",
      tone: getLastTestStatusTone(connection),
      value: formatLastTestStatus(connection),
    },
    {
      label: "Profile",
      tone: "neutral",
      value: PROTOCOL_PROFILE_LABELS[connection.protocolProfile],
    },
    {
      label: "Capabilities",
      tone: getCapabilityStatusTone(connection.capabilities),
      value: formatCapabilitySummary(connection.capabilities),
    },
  ];
}

export function getModelConnectionEvidenceItems(
  connection: ModelConnectionListItemRead,
): EvidenceClusterItem[] {
  const credentialState = getCredentialState(connection);

  return [
    {
      description: `${PROTOCOL_PROFILE_DESCRIPTIONS[connection.protocolProfile]} Timeout ${connection.timeoutSeconds}s against ${connection.baseUrl}.`,
      label: "Protocol profile",
      tone: "neutral",
      value: PROTOCOL_PROFILE_LABELS[connection.protocolProfile],
    },
    {
      description: connection.lastTestMessage ?? "Backend connection test has not reported a provider message.",
      label: "Test state",
      tone: getLastTestEvidenceTone(connection),
      value: formatLastTestStatus(connection),
    },
    {
      description: formatCapabilityDetails(connection),
      label: "Capability support",
      tone: getCapabilityEvidenceTone(connection.capabilities),
      value: formatCapabilitySummary(connection.capabilities),
    },
    {
      description: `Reasoning effort: ${formatReasoningEffort(connection.reasoningEffort)}.`,
      label: "Runtime policy",
      tone: "neutral",
      value: formatRuntimePolicyEvidence(connection),
    },
    {
      description: connection.lastTestMessage ?? "Run a saved backend connection test to refresh reachability.",
      label: "Reachability",
      tone: getLastTestEvidenceTone(connection),
      value: formatReachabilityValue(connection),
    },
    {
      description: credentialState.description,
      label: "Credential state",
      tone: credentialState.tone,
      value: credentialState.label,
    },
  ];
}
