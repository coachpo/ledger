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
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
  CAPABILITY_STATUS_OPTIONS,
  OUTPUT_STRATEGY_POLICY_LABELS,
  OUTPUT_STRATEGY_POLICY_OPTIONS,
  PARALLEL_TOOL_CALLS_POLICY_LABELS,
  PARALLEL_TOOL_CALLS_POLICY_OPTIONS,
  PROBE_CAPABILITY_KEYS,
  PROTOCOL_PROFILE_DESCRIPTIONS,
  PROTOCOL_PROFILE_LABELS,
  REASONING_POLICY_LABELS,
  REASONING_POLICY_OPTIONS,
  STREAMING_POLICY_LABELS,
  STREAMING_POLICY_OPTIONS,
  SUMMARY_CAPABILITY_KEYS,
  capabilitiesForProtocolProfile,
  createDefaultCapabilities,
  formatCapabilitySummary,
  normalizeCapabilities,
  toCapabilityWritePayload,
  validatePolicyCompatibility,
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
  outputStrategyPolicy: ModelConnectionOutputStrategyPolicy;
  parallelToolCallsPolicy: ModelConnectionParallelToolCallsPolicy;
  probeCacheTtlSeconds: string;
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
  outputStrategyPolicy: "prefer_strict_schema",
  parallelToolCallsPolicy: "serialize",
  probeCacheTtlSeconds: "900",
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
    outputStrategyPolicy: connection.outputStrategyPolicy,
    parallelToolCallsPolicy: connection.parallelToolCallsPolicy,
    probeCacheTtlSeconds: String(connection.probeCacheTtlSeconds),
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

function parseProbeCacheTtlSeconds(value: string) {
  return parsePositiveInteger("Probe cache TTL seconds", value);
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

function assertPolicyCompatibility(values: ModelConnectionEditorValues) {
  const policyError = validatePolicyCompatibility(
    values.capabilities,
    values.outputStrategyPolicy,
  );

  if (policyError) {
    throw new Error(policyError);
  }
}

function buildCreatePayload(
  values: ModelConnectionEditorValues,
): ModelConnectionCreateInput {
  const apiKey = values.apiKey.trim();
  assertPolicyCompatibility(values);

  return {
    key: parseRequiredText("Key", values.key).toLowerCase(),
    name: parseRequiredText("Name", values.name),
    description: values.description.trim() || undefined,
    protocolProfile: values.protocolProfile,
    baseUrl: parseRequiredText("Base URL", values.baseUrl),
    modelId: parseRequiredText("Model ID", values.modelId),
    reasoningEffort: parseReasoningEffort(getReasoningEffortValue(values)),
    capabilities: toCapabilityWritePayload(values.capabilities),
    outputStrategyPolicy: values.outputStrategyPolicy,
    parallelToolCallsPolicy: values.parallelToolCallsPolicy,
    reasoningPolicy: values.reasoningPolicy,
    streamingPolicy: values.streamingPolicy,
    probeCacheTtlSeconds: parseProbeCacheTtlSeconds(values.probeCacheTtlSeconds),
    timeoutSeconds: parseTimeoutSeconds(values.timeoutSeconds),
    ...(apiKey ? { apiKey } : {}),
  };
}

function buildUpdatePayload(
  values: ModelConnectionEditorValues,
): ModelConnectionUpdateInput {
  const apiKey = values.apiKey.trim();
  assertPolicyCompatibility(values);

  return {
    name: parseRequiredText("Name", values.name),
    description: values.description.trim(),
    protocolProfile: values.protocolProfile,
    baseUrl: parseRequiredText("Base URL", values.baseUrl),
    modelId: parseRequiredText("Model ID", values.modelId),
    reasoningEffort: parseReasoningEffort(getReasoningEffortValue(values)),
    capabilities: toCapabilityWritePayload(values.capabilities),
    outputStrategyPolicy: values.outputStrategyPolicy,
    parallelToolCallsPolicy: values.parallelToolCallsPolicy,
    reasoningPolicy: values.reasoningPolicy,
    streamingPolicy: values.streamingPolicy,
    probeCacheTtlSeconds: parseProbeCacheTtlSeconds(values.probeCacheTtlSeconds),
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
      protocolProfile,
    }));
  };

  const updateCapabilityStatus = (
    capabilityKey: keyof ModelConnectionCapabilities,
    status: ModelConnectionCapabilityStatus,
  ) => {
    setValues((current) => ({
      ...current,
      capabilities: {
        ...current.capabilities,
        [capabilityKey]: {
          ...current.capabilities[capabilityKey],
          status,
        },
      },
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
        probeCacheTtlSeconds: String(result.probeCacheTtlSeconds),
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

  return (
    <div
      aria-labelledby="model-connection-editor-title"
      className="flex h-full min-h-0 min-w-0 flex-col gap-4 overflow-y-auto overflow-x-hidden p-4 font-sans"
      data-testid="model-connections-editor"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1
            id="model-connection-editor-title"
            className="text-xl font-semibold tracking-tight"
          >
            {isEditing ? "Edit Model Connection" : "Create Model Connection"}
          </h1>
          <p className="text-sm text-muted-foreground">
            Save protocol profiles, capability declarations, and runtime
            policies for workflow packages.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
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
        <p className="max-w-3xl text-sm text-muted-foreground">
          Test Connection checks reachability on the saved endpoint only.
          Probe Required Capabilities refreshes the capability summary and
          policy readiness separately.
        </p>
      </div>

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
          {probeFeedback.variant === "default" ? <CheckCircle2 /> : <XCircle />}
          <AlertTitle>{probeFeedback.title}</AlertTitle>
          <AlertDescription>{probeFeedback.message}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Connection details</CardTitle>
          <CardDescription>
            Enter the model endpoint identity and protocol-compatible base URL.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="model-connection-key">Key</Label>
              <Input
                id="model-connection-key"
                aria-label="Key"
                disabled={isSaving || isEditing}
                value={values.key}
                onChange={(event) => updateValue("key", event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="model-connection-name">Name</Label>
              <Input
                id="model-connection-name"
                aria-label="Name"
                disabled={isSaving}
                value={values.name}
                onChange={(event) => updateValue("name", event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="model-connection-model-id">Model ID</Label>
              <Input
                id="model-connection-model-id"
                aria-label="Model ID"
                disabled={isSaving}
                value={values.modelId}
                onChange={(event) => updateValue("modelId", event.target.value)}
              />
            </div>
          </div>

          <div className="space-y-2">
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

          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="model-connection-base-url">Base URL</Label>
              <Input
                id="model-connection-base-url"
                aria-label="Base URL"
                disabled={isSaving}
                value={values.baseUrl}
                onChange={(event) => updateValue("baseUrl", event.target.value)}
              />
            </div>
            <div className="space-y-2">
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
              <p className="text-sm text-muted-foreground">
                {PROTOCOL_PROFILE_DESCRIPTIONS[values.protocolProfile]}
              </p>
            </div>
            <div className="space-y-2">
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
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
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
                <div className="space-y-2">
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
              <p className="text-sm text-muted-foreground">
                Choose Omit for providers that reject reasoning.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Capability summary</CardTitle>
          <CardDescription>
            Summarize what this endpoint can support. Probe results and manual
            overrides stay separate from the reachability test.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-3 md:grid-cols-3">
            {SUMMARY_CAPABILITY_KEYS.map((capabilityKey) => {
              const capability = values.capabilities[capabilityKey];

              return (
                <div
                  key={capabilityKey}
                  className="rounded-lg border bg-muted/30 p-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-foreground">
                      {CAPABILITY_LABEL_BY_KEY[capabilityKey]}
                    </p>
                    <Badge
                      variant={
                        capability.status === "unsupported"
                          ? "destructive"
                          : "secondary"
                      }
                    >
                      {CAPABILITY_STATUS_LABELS[capability.status]}
                    </Badge>
                  </div>
                  {capability.detail ? (
                    <p className="mt-2 text-xs text-muted-foreground">
                      {capability.detail}
                    </p>
                  ) : null}
                </div>
              );
            })}
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {CAPABILITY_DEFINITIONS.map(({ key, label }) => (
              <div key={key} className="space-y-2">
                <Label htmlFor={`model-connection-capability-${key}`}>
                  {label}
                </Label>
                <Select
                  value={values.capabilities[key].status}
                  disabled={isSaving}
                  onValueChange={(status: ModelConnectionCapabilityStatus) =>
                    updateCapabilityStatus(key, status)
                  }
                >
                  <SelectTrigger
                    id={`model-connection-capability-${key}`}
                    aria-label={`${label} capability`}
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {CAPABILITY_STATUS_OPTIONS.map((status) => (
                        <SelectItem key={status} value={status}>
                          {CAPABILITY_STATUS_LABELS[status]}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Policy controls</CardTitle>
          <CardDescription>
            Choose how strictly runtime should require structured output, tools,
            reasoning hints, and streaming support.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="model-connection-output-policy">
              Output Strategy Policy
            </Label>
            <Select
              value={values.outputStrategyPolicy}
              disabled={isSaving}
              onValueChange={(value: ModelConnectionOutputStrategyPolicy) =>
                updateValue("outputStrategyPolicy", value)
              }
            >
              <SelectTrigger
                id="model-connection-output-policy"
                aria-label="Output Strategy Policy"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {OUTPUT_STRATEGY_POLICY_OPTIONS.map((policy) => (
                    <SelectItem key={policy} value={policy}>
                      {OUTPUT_STRATEGY_POLICY_LABELS[policy]}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="model-connection-parallel-tools-policy">
              Parallel Tool Calls Policy
            </Label>
            <Select
              value={values.parallelToolCallsPolicy}
              disabled={isSaving}
              onValueChange={(value: ModelConnectionParallelToolCallsPolicy) =>
                updateValue("parallelToolCallsPolicy", value)
              }
            >
              <SelectTrigger
                id="model-connection-parallel-tools-policy"
                aria-label="Parallel Tool Calls Policy"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {PARALLEL_TOOL_CALLS_POLICY_OPTIONS.map((policy) => (
                    <SelectItem key={policy} value={policy}>
                      {PARALLEL_TOOL_CALLS_POLICY_LABELS[policy]}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="model-connection-reasoning-policy">
              Reasoning Policy
            </Label>
            <Select
              value={values.reasoningPolicy}
              disabled={isSaving}
              onValueChange={(value: ModelConnectionReasoningPolicy) =>
                updateValue("reasoningPolicy", value)
              }
            >
              <SelectTrigger
                id="model-connection-reasoning-policy"
                aria-label="Reasoning Policy"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {REASONING_POLICY_OPTIONS.map((policy) => (
                    <SelectItem key={policy} value={policy}>
                      {REASONING_POLICY_LABELS[policy]}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="model-connection-streaming-policy">
              Streaming Policy
            </Label>
            <Select
              value={values.streamingPolicy}
              disabled={isSaving}
              onValueChange={(value: ModelConnectionStreamingPolicy) =>
                updateValue("streamingPolicy", value)
              }
            >
              <SelectTrigger
                id="model-connection-streaming-policy"
                aria-label="Streaming Policy"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {STREAMING_POLICY_OPTIONS.map((policy) => (
                    <SelectItem key={policy} value={policy}>
                      {STREAMING_POLICY_LABELS[policy]}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="model-connection-probe-cache-ttl">
              Probe Cache TTL Seconds
            </Label>
            <Input
              id="model-connection-probe-cache-ttl"
              aria-label="Probe Cache TTL Seconds"
              disabled={isSaving}
              inputMode="numeric"
              value={values.probeCacheTtlSeconds}
              onChange={(event) =>
                updateValue("probeCacheTtlSeconds", event.target.value)
              }
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Credentials & health</CardTitle>
          <CardDescription>
            {currentConnectionKind === "deterministic_smoke"
              ? "Deterministic smoke connections run offline; provider API keys remain optional and hidden."
              : "Existing secrets are never shown again. Save a new value only when you want to rotate it."}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
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

          {connectionQuery.data?.lastTestedAt ? (
            <div className="rounded-lg border bg-muted/30 p-4 text-sm text-muted-foreground">
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  variant={
                    connectionQuery.data.lastTestOk
                      ? "secondary"
                      : "destructive"
                  }
                >
                  {connectionQuery.data.lastTestOk
                    ? "Last reachability test passed"
                    : "Last reachability test failed"}
                </Badge>
                <span>{formatDateTime(connectionQuery.data.lastTestedAt)}</span>
              </div>
              {connectionQuery.data.lastTestMessage ? (
                <p className="mt-2">{connectionQuery.data.lastTestMessage}</p>
              ) : null}
            </div>
          ) : (
            <div className="rounded-lg border bg-muted/30 p-4 text-sm text-muted-foreground">
              No reachability test has been recorded yet.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
