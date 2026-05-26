import { useEffect, useState } from "react";
import { CheckCircle2, PlugZap, Radar, Save, XCircle } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import {
  useCreateModelConnection,
  useModelConnection,
  useProbeModelConnectionCapabilities,
  useTestModelConnection,
  useUpdateModelConnection,
} from "@/hooks/use-model-connections";
import { SecretInput } from "@/components/forms/secret-input";
import { ConsoleSection } from "@/components/shared/console-section";
import {
  EvidenceCluster,
  type EvidenceClusterItem,
  type EvidenceClusterTone,
} from "@/components/shared/evidence-cluster";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { formatDateTime } from "@/lib/format";
import type {
  ModelConnectionCapabilities,
  ModelConnectionCapabilityStatus,
  ModelConnectionCreateInput,
  ModelConnectionKind,
  ModelConnectionOutputStrategyPolicy,
  ModelConnectionParallelToolCallsPolicy,
  ModelConnectionProtocolProfile,
  ModelConnectionRead,
  ModelConnectionReasoningEffort,
  ModelConnectionReasoningPolicy,
  ModelConnectionStreamingPolicy,
  ModelConnectionUpdateInput,
} from "@/lib/types/model-connection";

import {
  parseOptionalNumber,
  parseRequiredText,
} from "../platform-resource-helpers";
import {
  CAPABILITY_DEFINITIONS,
  CAPABILITY_LABEL_BY_KEY,
  CAPABILITY_STATUS_LABELS,
  OUTPUT_STRATEGY_POLICY_LABELS,
  PARALLEL_TOOL_CALLS_POLICY_LABELS,
  PROBE_CAPABILITY_KEYS,
  PROTOCOL_PROFILE_DESCRIPTIONS,
  PROTOCOL_PROFILE_LABELS,
  REASONING_POLICY_LABELS,
  STREAMING_POLICY_LABELS,
  SUMMARY_CAPABILITY_KEYS,
  capabilitiesForProtocolProfile,
  createDefaultCapabilities,
  formatCapabilitySummary,
  normalizeCapabilities,
} from "./model-connection-ui";

type ConnectionFeedback = {
  message: string;
  title: string;
  variant: "default" | "destructive";
};

const REASONING_EFFORT_OMIT_VALUE = "__omit__";
const REASONING_EFFORT_CUSTOM_VALUE = "__custom__";
const REASONING_EFFORT_PRESETS = [
  "none",
  "minimal",
  "low",
  "medium",
  "high",
  "xhigh",
] as const;
const CUSTOM_REASONING_EFFORT_MAX_LENGTH = 128;

type ReasoningEffortPreset = (typeof REASONING_EFFORT_PRESETS)[number];
type ReasoningEffortSelection =
  | typeof REASONING_EFFORT_OMIT_VALUE
  | typeof REASONING_EFFORT_CUSTOM_VALUE
  | ReasoningEffortPreset;

type ModelConnectionEditorValues = {
  apiKey: string;
  baseUrl: string;
  capabilities: ModelConnectionCapabilities;
  customReasoningEffort: string;
  description: string;
  key: string;
  modelId: string;
  name: string;
  lastProbedAt: string | null;
  outputStrategyPolicy: ModelConnectionOutputStrategyPolicy;
  parallelToolCallsPolicy: ModelConnectionParallelToolCallsPolicy;
  probeCacheTtlSeconds: number;
  protocolProfile: ModelConnectionProtocolProfile;
  reasoningEffort: ReasoningEffortSelection;
  reasoningPolicy: ModelConnectionReasoningPolicy;
  streamingPolicy: ModelConnectionStreamingPolicy;
  timeoutSeconds: string;
};

const DEFAULT_PROTOCOL_PROFILE: ModelConnectionProtocolProfile =
  "openai_responses";

const initialValues: ModelConnectionEditorValues = {
  apiKey: "",
  baseUrl: "https://model-endpoint.example/v1",
  capabilities: createDefaultCapabilities(DEFAULT_PROTOCOL_PROFILE),
  customReasoningEffort: "",
  description: "",
  key: "",
  modelId: "",
  name: "",
  lastProbedAt: null,
  outputStrategyPolicy: "prefer_strict_schema",
  parallelToolCallsPolicy: "serialize",
  probeCacheTtlSeconds: 900,
  protocolProfile: DEFAULT_PROTOCOL_PROFILE,
  reasoningEffort: "medium",
  reasoningPolicy: "allow",
  streamingPolicy: "allow",
  timeoutSeconds: "60",
};

function isReasoningEffortPreset(
  value: string | null,
): value is ReasoningEffortPreset {
  return REASONING_EFFORT_PRESETS.includes(value as ReasoningEffortPreset);
}

function getReasoningEffortSelection(
  value: ModelConnectionReasoningEffort | null,
): ReasoningEffortSelection {
  if (value === null) {
    return REASONING_EFFORT_OMIT_VALUE;
  }

  return isReasoningEffortPreset(value) ? value : REASONING_EFFORT_CUSTOM_VALUE;
}

function getCustomReasoningEffort(
  value: ModelConnectionReasoningEffort | null,
) {
  return value !== null && !isReasoningEffortPreset(value) ? value : "";
}

function buildValuesFromConnection(
  connection: ModelConnectionRead,
): ModelConnectionEditorValues {
  return {
    apiKey: "",
    baseUrl: connection.baseUrl,
    capabilities: normalizeCapabilities(
      connection.protocolProfile,
      connection.capabilities,
    ),
    customReasoningEffort: getCustomReasoningEffort(connection.reasoningEffort),
    description: connection.description ?? "",
    key: connection.key,
    modelId: connection.modelId,
    name: connection.name,
    lastProbedAt: connection.lastProbedAt ?? null,
    outputStrategyPolicy: connection.outputStrategyPolicy,
    parallelToolCallsPolicy: connection.parallelToolCallsPolicy,
    probeCacheTtlSeconds: connection.probeCacheTtlSeconds,
    protocolProfile: connection.protocolProfile,
    reasoningEffort: getReasoningEffortSelection(connection.reasoningEffort),
    reasoningPolicy: connection.reasoningPolicy,
    streamingPolicy: connection.streamingPolicy,
    timeoutSeconds: String(connection.timeoutSeconds),
  };
}

function parsePositiveInteger(fieldName: string, value: string) {
  const parsedValue = parseOptionalNumber(fieldName, value, {
    integer: true,
    min: 1,
  });

  if (parsedValue === undefined) {
    throw new Error(`${fieldName} is required.`);
  }

  return parsedValue;
}

function parseTimeoutSeconds(value: string) {
  return parsePositiveInteger("Timeout seconds", value);
}

function getFeedbackTone(variant: ConnectionFeedback["variant"]): EvidenceClusterTone {
  return variant === "default" ? "verified" : "danger";
}

function getCapabilityEvidenceTone(
  status: ModelConnectionCapabilityStatus,
): EvidenceClusterTone {
  if (status === "supported") {
    return "verified";
  }

  if (status === "unsupported") {
    return "danger";
  }

  return status === "unknown" ? "warning" : "neutral";
}

function getStoredReachabilityTone(
  connection: ModelConnectionRead | undefined,
): EvidenceClusterTone {
  if (connection?.lastTestOk === true) {
    return "verified";
  }

  if (connection?.lastTestOk === false) {
    return "danger";
  }

  return "warning";
}

function getStoredReachabilityValue(connection: ModelConnectionRead | undefined) {
  if (connection?.lastTestOk === true) {
    return "Last reachability test passed";
  }

  if (connection?.lastTestOk === false) {
    return "Last reachability test failed";
  }

  return "No reachability test recorded";
}

function getCredentialEvidence(connectionKind: ModelConnectionKind) {
  if (connectionKind === "deterministic_smoke") {
    return {
      description:
        "Deterministic smoke connections can run offline fixtures without an API key.",
      value: "API key optional",
    };
  }

  return {
    description:
      "Saved provider credentials stay write-only and can only be rotated from this editor.",
    value: "Write-only secret",
  };
}

function buildConnectionEvidenceItems({
  connection,
  connectionFeedback,
  connectionKind,
  probeFeedback,
  values,
}: {
  connection?: ModelConnectionRead;
  connectionFeedback: ConnectionFeedback | null;
  connectionKind: ModelConnectionKind;
  probeFeedback: ConnectionFeedback | null;
  values: ModelConnectionEditorValues;
}): EvidenceClusterItem[] {
  const credentialEvidence = getCredentialEvidence(connectionKind);
  const lastTestDescription = connection?.lastTestedAt
    ? `${formatDateTime(connection.lastTestedAt)}${
        connection.lastTestMessage ? ` · ${connection.lastTestMessage}` : ""
      }`
    : "Test Connection checks reachability on the saved endpoint only.";

  return [
    {
      description: `${PROTOCOL_PROFILE_DESCRIPTIONS[values.protocolProfile]} Timeout ${values.timeoutSeconds}s against ${values.baseUrl}.`,
      label: "Protocol profile",
      tone: "neutral",
      value: PROTOCOL_PROFILE_LABELS[values.protocolProfile],
    },
    {
      description: connectionFeedback?.message ?? lastTestDescription,
      label: "Test state",
      tone: connectionFeedback
        ? getFeedbackTone(connectionFeedback.variant)
        : getStoredReachabilityTone(connection),
      value: connectionFeedback?.title ?? getStoredReachabilityValue(connection),
    },
    {
      description:
        probeFeedback?.message ??
        (values.lastProbedAt
          ? `Last capability probe recorded ${formatDateTime(values.lastProbedAt)}.`
          : "Probe Required Capabilities records backend-owned support evidence after save."),
      label: "Capability support",
      tone: probeFeedback ? getFeedbackTone(probeFeedback.variant) : "warning",
      value: probeFeedback?.title ?? formatCapabilitySummary(values.capabilities),
    },
    {
      description: `Reasoning effort: ${getReasoningEffortValue(values) ?? "Omitted"}.`,
      label: "Runtime policy",
      tone: "neutral",
      value: [
        OUTPUT_STRATEGY_POLICY_LABELS[values.outputStrategyPolicy],
        PARALLEL_TOOL_CALLS_POLICY_LABELS[values.parallelToolCallsPolicy],
        REASONING_POLICY_LABELS[values.reasoningPolicy],
        STREAMING_POLICY_LABELS[values.streamingPolicy],
      ].join(" · "),
    },
    {
      description: credentialEvidence.description,
      label: "Credential state",
      tone: connectionKind === "deterministic_smoke" ? "verified" : "neutral",
      value: credentialEvidence.value,
    },
  ];
}

function buildCapabilityEvidenceItems(
  values: ModelConnectionEditorValues,
  capabilityKeys: readonly (keyof ModelConnectionCapabilities)[],
): EvidenceClusterItem[] {
  return capabilityKeys.map((capabilityKey) => {
    const capability = values.capabilities[capabilityKey];
    const lastProbedAt = capability.lastProbedAt ?? values.lastProbedAt;

    return {
      description: [
        capability.detail,
        lastProbedAt ? `Probed ${formatDateTime(lastProbedAt)}.` : null,
      ]
        .filter(Boolean)
        .join(" "),
      label: CAPABILITY_LABEL_BY_KEY[capabilityKey],
      tone: getCapabilityEvidenceTone(capability.status),
      value: CAPABILITY_STATUS_LABELS[capability.status],
    };
  });
}

function buildRuntimePolicyEvidenceItems(
  values: ModelConnectionEditorValues,
): EvidenceClusterItem[] {
  return [
    {
      label: "Output strategy policy",
      tone: "neutral",
      value: OUTPUT_STRATEGY_POLICY_LABELS[values.outputStrategyPolicy],
    },
    {
      label: "Parallel tool calls policy",
      tone: "neutral",
      value: PARALLEL_TOOL_CALLS_POLICY_LABELS[values.parallelToolCallsPolicy],
    },
    {
      label: "Reasoning policy",
      tone: "neutral",
      value: REASONING_POLICY_LABELS[values.reasoningPolicy],
    },
    {
      label: "Streaming policy",
      tone: "neutral",
      value: STREAMING_POLICY_LABELS[values.streamingPolicy],
    },
    {
      label: "Probe cache TTL",
      tone: "neutral",
      value: `${values.probeCacheTtlSeconds}s`,
    },
    {
      label: "Last capability probe",
      tone: values.lastProbedAt ? "verified" : "warning",
      value: values.lastProbedAt
        ? formatDateTime(values.lastProbedAt)
        : "No capability probe recorded.",
    },
  ];
}

function getReasoningEffortValue(
  values: ModelConnectionEditorValues,
): string | null {
  if (values.reasoningEffort === REASONING_EFFORT_OMIT_VALUE) {
    return null;
  }

  if (values.reasoningEffort === REASONING_EFFORT_CUSTOM_VALUE) {
    return values.customReasoningEffort;
  }

  return values.reasoningEffort;
}

function parseReasoningEffort(value: string | null): string | null {
  if (value === null) {
    return null;
  }

  const trimmedValue = value.trim();
  if (!trimmedValue) {
    throw new Error("Reasoning effort is required when Custom is selected.");
  }

  if (trimmedValue.length > CUSTOM_REASONING_EFFORT_MAX_LENGTH) {
    throw new Error("Reasoning effort must be 128 characters or fewer.");
  }

  return trimmedValue;
}

function buildCreatePayload(
  values: ModelConnectionEditorValues,
): ModelConnectionCreateInput {
  const apiKey = values.apiKey.trim();

  return {
    key: parseRequiredText("Key", values.key).toLowerCase(),
    name: parseRequiredText("Name", values.name),
    description: values.description.trim() || undefined,
    protocolProfile: values.protocolProfile,
    baseUrl: parseRequiredText("Base URL", values.baseUrl),
    modelId: parseRequiredText("Model ID", values.modelId),
    reasoningEffort: parseReasoningEffort(getReasoningEffortValue(values)),
    timeoutSeconds: parseTimeoutSeconds(values.timeoutSeconds),
    ...(apiKey ? { apiKey } : {}),
  };
}

function buildUpdatePayload(
  values: ModelConnectionEditorValues,
): ModelConnectionUpdateInput {
  const apiKey = values.apiKey.trim();

  return {
    name: parseRequiredText("Name", values.name),
    description: values.description.trim(),
    protocolProfile: values.protocolProfile,
    baseUrl: parseRequiredText("Base URL", values.baseUrl),
    modelId: parseRequiredText("Model ID", values.modelId),
    reasoningEffort: parseReasoningEffort(getReasoningEffortValue(values)),
    timeoutSeconds: parseTimeoutSeconds(values.timeoutSeconds),
    ...(apiKey ? { apiKey } : {}),
  };
}

export function ModelConnectionsEditorPage() {
  const { modelConnectionId } = useParams<{ modelConnectionId: string }>();
  const navigate = useNavigate();
  const isEditing = Boolean(modelConnectionId);
  const connectionQuery = useModelConnection(modelConnectionId);
  const createMutation = useCreateModelConnection();
  const updateMutation = useUpdateModelConnection();
  const testConnectionMutation = useTestModelConnection(modelConnectionId);
  const probeCapabilitiesMutation =
    useProbeModelConnectionCapabilities(modelConnectionId);
  const [values, setValues] =
    useState<ModelConnectionEditorValues>(initialValues);
  const [connectionFeedback, setConnectionFeedback] =
    useState<ConnectionFeedback | null>(null);
  const [probeFeedback, setProbeFeedback] = useState<ConnectionFeedback | null>(
    null,
  );

  useEffect(() => {
    if (!connectionQuery.data) {
      return;
    }

    setValues(buildValuesFromConnection(connectionQuery.data));
    setConnectionFeedback(null);
    setProbeFeedback(null);
  }, [connectionQuery.data]);

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const isBusy =
    isSaving ||
    testConnectionMutation.isPending ||
    probeCapabilitiesMutation.isPending;
  const currentConnectionKind =
    connectionQuery.data?.connectionKind ?? "provider";

  const updateValue = <Key extends keyof ModelConnectionEditorValues>(
    key: Key,
    value: ModelConnectionEditorValues[Key],
  ) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const handleProtocolProfileChange = (
    protocolProfile: ModelConnectionProtocolProfile,
  ) => {
    setValues((current) => ({
      ...current,
      capabilities: capabilitiesForProtocolProfile(
        current.capabilities,
        protocolProfile,
      ),
      lastProbedAt: null,
      outputStrategyPolicy: "prefer_strict_schema",
      parallelToolCallsPolicy: "serialize",
      probeCacheTtlSeconds: 900,
      protocolProfile,
      reasoningPolicy: "allow",
      streamingPolicy: "allow",
    }));
  };

  const handleSave = async () => {
    try {
      if (isEditing && modelConnectionId) {
        const updated = await updateMutation.mutateAsync({
          modelConnectionId,
          payload: buildUpdatePayload(values),
        });
        toast.success("Model connection updated");
        navigate(`/model-connections/${updated.id}/edit`);
        return;
      }

      const created = await createMutation.mutateAsync(
        buildCreatePayload(values),
      );
      toast.success("Model connection created");
      navigate(`/model-connections/${created.id}/edit`);
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Failed to save model connection",
      );
    }
  };

  const handleTestConnection = async () => {
    if (!modelConnectionId) {
      setConnectionFeedback({
        message: "Save the model connection before testing reachability.",
        title: "Reachability test unavailable",
        variant: "destructive",
      });
      return;
    }

    try {
      const result = await testConnectionMutation.mutateAsync();
      setConnectionFeedback({
        message: result.message,
        title: result.ok ? "Reachability succeeded" : "Reachability failed",
        variant: result.ok ? "default" : "destructive",
      });
      toast[result.ok ? "success" : "error"](result.message);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to test model connection reachability";
      setConnectionFeedback({
        message,
        title: "Reachability test failed",
        variant: "destructive",
      });
      toast.error(message);
    }
  };

  const handleProbeCapabilities = async () => {
    if (!modelConnectionId) {
      setProbeFeedback({
        message: "Save the model connection before probing capabilities.",
        title: "Capability probe unavailable",
        variant: "destructive",
      });
      return;
    }

    try {
      const result = await probeCapabilitiesMutation.mutateAsync({
        capabilityKeys: [...PROBE_CAPABILITY_KEYS],
        refresh: true,
      });
      setValues((current) => ({
        ...current,
        capabilities: normalizeCapabilities(
          current.protocolProfile,
          result.capabilities,
        ),
        lastProbedAt: result.lastProbedAt,
        probeCacheTtlSeconds: result.probeCacheTtlSeconds,
      }));
      setProbeFeedback({
        message: `${formatCapabilitySummary(result.capabilities)} · ${
          result.cached ? "served from probe cache" : "fresh probe recorded"
        }`,
        title: "Capability probe completed",
        variant: "default",
      });
      toast.success("Capability probe completed");
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to probe model capabilities";
      setProbeFeedback({
        message,
        title: "Capability probe failed",
        variant: "destructive",
      });
      toast.error(message);
    }
  };

  if (isEditing && connectionQuery.isPending) {
    return (
      <div className="flex h-full items-center p-4 text-sm text-muted-foreground">
        Loading model connection details...
      </div>
    );
  }

  if (isEditing && connectionQuery.isError) {
    return (
      <div className="flex h-full items-center p-4 text-sm text-muted-foreground">
        {connectionQuery.error instanceof Error
          ? connectionQuery.error.message
          : "Model connection not found."}
      </div>
    );
  }

  const apiKeyHelpText =
    currentConnectionKind === "deterministic_smoke"
      ? "Optional for deterministic smoke."
      : isEditing
        ? "Leave blank to keep the current key."
        : "Optional; add or rotate it later.";
  const connectionEvidenceItems = buildConnectionEvidenceItems({
    connection: connectionQuery.data,
    connectionFeedback,
    connectionKind: currentConnectionKind,
    probeFeedback,
    values,
  });
  const summaryCapabilityItems = buildCapabilityEvidenceItems(
    values,
    SUMMARY_CAPABILITY_KEYS,
  );
  const capabilityEvidenceItems = buildCapabilityEvidenceItems(
    values,
    CAPABILITY_DEFINITIONS.map(({ key }) => key),
  );
  const runtimePolicyEvidenceItems = buildRuntimePolicyEvidenceItems(values);

  return (
    <WorkspacePageShell
      bodyAriaLabel="Model connection editor workspace"
      bodyClassName="gap-4"
      contextBar={
        <PageContextBar
          density="compact"
          title={
            <span id="model-connection-editor-title">
              {isEditing ? "Edit Model Connection" : "Create Model Connection"}
            </span>
          }
          description="Save endpoint settings and credentials. Backend evidence stays read-only and refreshes through saved-record actions."
          meta={
            <span>
              Test Connection checks reachability on the saved endpoint only.
              Probe Required Capabilities refreshes backend-owned capability
              evidence separately.
            </span>
          }
          status={
            <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span>
                Stable key: <span className="font-medium text-foreground">{values.key || "unsaved"}</span>
              </span>
              <span>
                Model: <span className="font-medium text-foreground">{values.modelId || "not set"}</span>
              </span>
            </span>
          }
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <Button
                data-testid="model-connection-test"
                disabled={isBusy}
                size="sm"
                variant="outline"
                onClick={() => void handleTestConnection()}
              >
                <PlugZap data-icon="inline-start" />
                Test Connection
              </Button>
              <Button
                data-testid="model-connection-probe"
                disabled={isBusy}
                size="sm"
                variant="outline"
                onClick={() => void handleProbeCapabilities()}
              >
                <Radar data-icon="inline-start" />
                Probe Required Capabilities
              </Button>
              <Button
                data-testid="model-connection-save"
                disabled={isSaving}
                size="sm"
                onClick={handleSave}
              >
                <Save data-icon="inline-start" />
                Save Model Connection
              </Button>
            </div>
          }
        />
      }
      testId="model-connections-editor"
    >
      <div className="grid min-h-0 min-w-0 gap-4 xl:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-4">
          <ConsoleSection
            title="Editable connection details"
            description="Keep the saved key stable, then edit the provider endpoint fields that feed create/update payloads."
          >
            <div className="grid gap-4 md:grid-cols-2">
              <div className="flex min-w-0 flex-col gap-2">
                <Label htmlFor="model-connection-key">Key</Label>
                <Input
                  id="model-connection-key"
                  aria-label="Key"
                  disabled={isSaving || isEditing}
                  value={values.key}
                  onChange={(event) => updateValue("key", event.target.value)}
                />
              </div>
              <div className="flex min-w-0 flex-col gap-2">
                <Label htmlFor="model-connection-name">Name</Label>
                <Input
                  id="model-connection-name"
                  aria-label="Name"
                  disabled={isSaving}
                  value={values.name}
                  onChange={(event) => updateValue("name", event.target.value)}
                />
              </div>
              <div className="flex min-w-0 flex-col gap-2">
                <Label htmlFor="model-connection-model-id">Model ID</Label>
                <Input
                  id="model-connection-model-id"
                  aria-label="Model ID"
                  disabled={isSaving}
                  value={values.modelId}
                  onChange={(event) => updateValue("modelId", event.target.value)}
                />
              </div>
              <div className="flex min-w-0 flex-col gap-2">
                <Label htmlFor="model-connection-base-url">Base URL</Label>
                <Input
                  id="model-connection-base-url"
                  aria-label="Base URL"
                  disabled={isSaving}
                  value={values.baseUrl}
                  onChange={(event) => updateValue("baseUrl", event.target.value)}
                />
              </div>
              <div className="flex min-w-0 flex-col gap-2 md:col-span-2">
                <Label htmlFor="model-connection-description">Description</Label>
                <Textarea
                  id="model-connection-description"
                  aria-label="Description"
                  disabled={isSaving}
                  rows={3}
                  value={values.description}
                  onChange={(event) =>
                    updateValue("description", event.target.value)
                  }
                />
              </div>
            </div>
          </ConsoleSection>

          <ConsoleSection
            title="Protocol and runtime defaults"
            description="Base URL stays at the provider /v1 root; protocol profile carries Responses versus Chat Completions semantics."
          >
            <div className="grid gap-4 md:grid-cols-2">
              <div className="flex min-w-0 flex-col gap-2">
                <Label htmlFor="model-connection-protocol-profile">
                  Protocol Profile
                </Label>
                <Select
                  value={values.protocolProfile}
                  disabled={isSaving}
                  onValueChange={(value: ModelConnectionProtocolProfile) =>
                    handleProtocolProfileChange(value)
                  }
                >
                  <SelectTrigger
                    id="model-connection-protocol-profile"
                    aria-label="Protocol Profile"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem value="openai_responses">
                        {PROTOCOL_PROFILE_LABELS.openai_responses}
                      </SelectItem>
                      <SelectItem value="openai_chat_completions">
                        {PROTOCOL_PROFILE_LABELS.openai_chat_completions}
                      </SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {PROTOCOL_PROFILE_DESCRIPTIONS[values.protocolProfile]}
                </p>
              </div>
              <div className="flex min-w-0 flex-col gap-2">
                <Label htmlFor="model-connection-timeout-seconds">
                  Timeout Seconds
                </Label>
                <Input
                  id="model-connection-timeout-seconds"
                  aria-label="Timeout Seconds"
                  disabled={isSaving}
                  inputMode="numeric"
                  value={values.timeoutSeconds}
                  onChange={(event) =>
                    updateValue("timeoutSeconds", event.target.value)
                  }
                />
              </div>
              <div className="flex min-w-0 flex-col gap-2 md:col-span-2">
                <Label htmlFor="model-connection-reasoning-effort">
                  Reasoning Effort
                </Label>
                <Select
                  value={values.reasoningEffort}
                  disabled={isSaving}
                  onValueChange={(value) =>
                    updateValue(
                      "reasoningEffort",
                      value as ReasoningEffortSelection,
                    )
                  }
                >
                  <SelectTrigger
                    id="model-connection-reasoning-effort"
                    aria-label="Reasoning Effort"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem value={REASONING_EFFORT_OMIT_VALUE}>
                        Omit reasoning parameter
                      </SelectItem>
                      {REASONING_EFFORT_PRESETS.map((preset) => (
                        <SelectItem key={preset} value={preset}>
                          {preset}
                        </SelectItem>
                      ))}
                      <SelectItem value={REASONING_EFFORT_CUSTOM_VALUE}>
                        Custom...
                      </SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
                {values.reasoningEffort === REASONING_EFFORT_CUSTOM_VALUE ? (
                  <div className="flex min-w-0 flex-col gap-2">
                    <Label htmlFor="model-connection-custom-reasoning-effort">
                      Custom Reasoning Effort
                    </Label>
                    <Input
                      id="model-connection-custom-reasoning-effort"
                      aria-label="Custom Reasoning Effort"
                      disabled={isSaving}
                      maxLength={CUSTOM_REASONING_EFFORT_MAX_LENGTH + 1}
                      value={values.customReasoningEffort}
                      onChange={(event) =>
                        updateValue("customReasoningEffort", event.target.value)
                      }
                    />
                  </div>
                ) : null}
                <p className="text-xs text-muted-foreground">
                  Choose Omit for providers that reject reasoning.
                </p>
              </div>
            </div>
          </ConsoleSection>

          <ConsoleSection
            title="Credential rotation"
            description={
              currentConnectionKind === "deterministic_smoke"
                ? "Deterministic smoke connections run offline; provider API keys remain optional and hidden."
                : "Existing secrets are never shown again. Save a new value only when you want to rotate it."
            }
          >
            <SecretInput
              aria-label="API Key"
              disabled={isSaving}
              helperText={apiKeyHelpText}
              id="model-connection-api-key"
              label="API Key"
              placeholder={
                isEditing ? "Enter a new key to rotate it" : "Enter an API key"
              }
              value={values.apiKey}
              onValueChange={(value) => updateValue("apiKey", value)}
            />
          </ConsoleSection>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          {connectionFeedback || probeFeedback ? (
            <div className="flex flex-col gap-2">
              {connectionFeedback ? (
                <Alert
                  data-testid="model-connection-feedback"
                  variant={connectionFeedback.variant}
                >
                  {connectionFeedback.variant === "default" ? (
                    <CheckCircle2 />
                  ) : (
                    <XCircle />
                  )}
                  <AlertTitle>{connectionFeedback.title}</AlertTitle>
                  <AlertDescription>{connectionFeedback.message}</AlertDescription>
                </Alert>
              ) : null}

              {probeFeedback ? (
                <Alert
                  data-testid="model-connection-probe-feedback"
                  variant={probeFeedback.variant}
                >
                  {probeFeedback.variant === "default" ? (
                    <CheckCircle2 />
                  ) : (
                    <XCircle />
                  )}
                  <AlertTitle>{probeFeedback.title}</AlertTitle>
                  <AlertDescription>{probeFeedback.message}</AlertDescription>
                </Alert>
              ) : null}
            </div>
          ) : null}

          <ConsoleSection
            title="Compatibility evidence"
            description="Read-only test, probe, credential, and runtime evidence resolved by the backend. Save before refreshing it."
          >
            <div className="flex min-w-0 flex-col gap-3">
              <EvidenceCluster items={connectionEvidenceItems} layout="grid" />
              <EvidenceCluster items={summaryCapabilityItems} layout="grid" />
            </div>
          </ConsoleSection>

          <ConsoleSection
            title="Capability matrix"
            description="Backend-owned capability support is displayed here but never submitted from the editor form."
          >
            <EvidenceCluster items={capabilityEvidenceItems} layout="grid" />
          </ConsoleSection>

          <ConsoleSection
            title="Backend runtime policies"
            description="Policy truth remains server-derived and is excluded from create/edit payloads."
          >
            <EvidenceCluster items={runtimePolicyEvidenceItems} layout="grid" />
          </ConsoleSection>
        </div>
      </div>
    </WorkspacePageShell>
  );
}
