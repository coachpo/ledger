import type { ModelConnectionCapabilities } from "@/lib/types/model-connection";

export const CAPABILITY_ORDER: (keyof ModelConnectionCapabilities)[] = [
  "textGeneration",
  "chatCompletions",
  "responsesApi",
  "streaming",
  "nativeToolCalls",
  "parallelToolCalls",
  "jsonObjectOutput",
  "strictJsonSchemaOutput",
  "reasoningHints",
  "usageReporting",
  "systemMessages",
];

export const CAPABILITY_LABELS: Record<keyof ModelConnectionCapabilities, string> = {
  textGeneration: "Text generation",
  chatCompletions: "Chat completions",
  responsesApi: "Responses API",
  streaming: "Streaming",
  nativeToolCalls: "Native tool calls",
  parallelToolCalls: "Parallel tool calls",
  jsonObjectOutput: "JSON object output",
  strictJsonSchemaOutput: "Strict JSON schema output",
  reasoningHints: "Reasoning hints",
  usageReporting: "Usage reporting",
  systemMessages: "System messages",
};
