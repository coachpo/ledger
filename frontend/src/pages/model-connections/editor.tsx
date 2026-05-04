import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, PlugZap, Save, XCircle } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { ExactJsonPreview } from "@/components/platform-authoring/inspectors/exact-json-preview";
import {
  useCreateModelConnection,
  useModelConnection,
  useTestModelConnection,
  useUpdateModelConnection,
} from "@/hooks/use-model-connections";
import { SecretInput } from "@/components/forms/secret-input";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import { stringifyJson } from "@/lib/platform-authoring/common/serialization";
import type {
  ModelConnectionApiStyle,
  ModelConnectionCreateInput,
  ModelConnectionRead,
  ModelConnectionReasoningEffort,
  ModelConnectionUpdateInput,
} from "@/lib/types/model-connection";

import {
  parseOptionalNumber,
  parseRequiredText,
  PlatformResourceBadges,
} from "../platform-resource-shared";

type ConnectionFeedback = {
  message: string;
  title: string;
  variant: "default" | "destructive";
};

const API_STYLE_LABELS: Record<ModelConnectionApiStyle, string> = {
  chat_completions: "Chat Completions API - legacy / OpenAI-compatible",
  responses: "Responses API",
};

const REASONING_EFFORT_OMIT_VALUE = "__omit__";
const REASONING_EFFORT_CUSTOM_VALUE = "__custom__";
const REASONING_EFFORT_PRESETS = ["none", "minimal", "low", "medium", "high", "xhigh"] as const;
const CUSTOM_REASONING_EFFORT_MAX_LENGTH = 128;

type ReasoningEffortPreset = (typeof REASONING_EFFORT_PRESETS)[number];
type ReasoningEffortSelection =
  | typeof REASONING_EFFORT_OMIT_VALUE
  | typeof REASONING_EFFORT_CUSTOM_VALUE
  | ReasoningEffortPreset;

type ModelConnectionEditorValues = {
  apiKey: string;
  apiStyle: ModelConnectionApiStyle;
  baseUrl: string;
  customReasoningEffort: string;
  description: string;
  key: string;
  modelId: string;
  name: string;
  organization: string;
  project: string;
  reasoningEffort: ReasoningEffortSelection;
  timeoutSeconds: string;
};

const initialValues: ModelConnectionEditorValues = {
  apiKey: "",
  apiStyle: "responses",
  baseUrl: "https://api.openai.com/v1",
  customReasoningEffort: "",
  description: "",
  key: "",
  modelId: "",
  name: "",
  organization: "",
  project: "",
  reasoningEffort: "medium",
  timeoutSeconds: "60",
};

const MASKED_SECRET_VALUE = "••••••••";

function isReasoningEffortPreset(value: string | null): value is ReasoningEffortPreset {
  return REASONING_EFFORT_PRESETS.includes(value as ReasoningEffortPreset);
}

function getReasoningEffortSelection(value: ModelConnectionReasoningEffort | null): ReasoningEffortSelection {
  if (value === null) {
    return REASONING_EFFORT_OMIT_VALUE;
  }

  return isReasoningEffortPreset(value) ? value : REASONING_EFFORT_CUSTOM_VALUE;
}

function getCustomReasoningEffort(value: ModelConnectionReasoningEffort | null) {
  return value !== null && !isReasoningEffortPreset(value) ? value : "";
}

function buildValuesFromConnection(connection: ModelConnectionRead): ModelConnectionEditorValues {
  return {
    apiKey: "",
    apiStyle: connection.apiStyle,
    baseUrl: connection.baseUrl,
    customReasoningEffort: getCustomReasoningEffort(connection.reasoningEffort),
    description: connection.description ?? "",
    key: connection.key,
    modelId: connection.modelId,
    name: connection.name,
    organization: connection.organization ?? "",
    project: connection.project ?? "",
    reasoningEffort: getReasoningEffortSelection(connection.reasoningEffort),
    timeoutSeconds: String(connection.timeoutSeconds),
  };
}

function parseTimeoutSeconds(value: string) {
  const timeoutSeconds = parseOptionalNumber("Timeout seconds", value, {
    integer: true,
    min: 1,
  });

  if (timeoutSeconds === undefined) {
    throw new Error("Timeout seconds is required.");
  }

  return timeoutSeconds;
}

function getReasoningEffortValue(values: ModelConnectionEditorValues): string | null {
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

function buildCreatePayload(values: ModelConnectionEditorValues): ModelConnectionCreateInput {
  const apiKey = values.apiKey.trim();

  return {
    key: parseRequiredText("Key", values.key).toLowerCase(),
    name: parseRequiredText("Name", values.name),
    description: values.description.trim() || undefined,
    apiStyle: values.apiStyle,
    baseUrl: parseRequiredText("Base URL", values.baseUrl),
    organization: values.organization.trim() || undefined,
    project: values.project.trim() || undefined,
    modelId: parseRequiredText("Model ID", values.modelId),
    reasoningEffort: parseReasoningEffort(getReasoningEffortValue(values)),
    timeoutSeconds: parseTimeoutSeconds(values.timeoutSeconds),
    ...(apiKey ? { apiKey } : {}),
  };
}

function buildUpdatePayload(values: ModelConnectionEditorValues): ModelConnectionUpdateInput {
  const apiKey = values.apiKey.trim();

  return {
    name: parseRequiredText("Name", values.name),
    description: values.description.trim(),
    apiStyle: values.apiStyle,
    baseUrl: parseRequiredText("Base URL", values.baseUrl),
    organization: values.organization.trim(),
    project: values.project.trim(),
    modelId: parseRequiredText("Model ID", values.modelId),
    reasoningEffort: parseReasoningEffort(getReasoningEffortValue(values)),
    timeoutSeconds: parseTimeoutSeconds(values.timeoutSeconds),
    ...(apiKey ? { apiKey } : {}),
  };
}

function buildPreviewPayload(
  values: ModelConnectionEditorValues,
  isEditing: boolean,
): ModelConnectionCreateInput | ModelConnectionUpdateInput {
  const payload = isEditing ? buildUpdatePayload(values) : buildCreatePayload(values);

  if (!payload.apiKey) {
    return payload;
  }

  return {
    ...payload,
    apiKey: MASKED_SECRET_VALUE,
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
  const [values, setValues] = useState<ModelConnectionEditorValues>(initialValues);
  const [connectionFeedback, setConnectionFeedback] = useState<ConnectionFeedback | null>(null);

  useEffect(() => {
    if (!connectionQuery.data) {
      return;
    }

    setValues(buildValuesFromConnection(connectionQuery.data));
    setConnectionFeedback(null);
  }, [connectionQuery.data]);

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const isBusy = isSaving || testConnectionMutation.isPending;
  const exactConfigJson = useMemo(() => {
    try {
      return stringifyJson(buildPreviewPayload(values, isEditing));
    } catch {
      return "";
    }
  }, [isEditing, values]);

  const updateValue = <Key extends keyof ModelConnectionEditorValues>(
    key: Key,
    value: ModelConnectionEditorValues[Key],
  ) => {
    setValues((current) => ({ ...current, [key]: value }));
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

      const created = await createMutation.mutateAsync(buildCreatePayload(values));
      toast.success("Model connection created");
      navigate(`/model-connections/${created.id}/edit`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save model connection");
    }
  };

  const handleTestConnection = async () => {
    if (!modelConnectionId) {
      setConnectionFeedback({
        message: "Save the model connection before testing it.",
        title: "Connection unavailable",
        variant: "destructive",
      });
      return;
    }

    try {
      const result = await testConnectionMutation.mutateAsync();
      setConnectionFeedback({
        message: result.message,
        title: result.ok ? "Connection succeeded" : "Connection failed",
        variant: result.ok ? "default" : "destructive",
      });
      toast[result.ok ? "success" : "error"](result.message);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to test model connection";
      setConnectionFeedback({
        message,
        title: "Connection test failed",
        variant: "destructive",
      });
      toast.error(message);
    }
  };

  if (isEditing && connectionQuery.isPending) {
    return <div className="p-4 text-sm text-muted-foreground">Loading model connection details...</div>;
  }

  if (isEditing && connectionQuery.isError) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        {connectionQuery.error instanceof Error
          ? connectionQuery.error.message
          : "Model connection not found."}
      </div>
    );
  }

  const apiKeyHelpText = connectionQuery.data?.apiKeyLast4
    ? `Leave blank to keep current key ending in ••••${connectionQuery.data.apiKeyLast4}.`
    : isEditing
      ? "Leave blank to keep current key."
      : "Optional for create; you can add or rotate it later.";

  return (
    <div className="space-y-4 p-4" data-testid="model-connections-editor">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">
            {isEditing ? "Edit Model Connection" : "Create Model Connection"}
          </h1>
          <p className="text-sm text-muted-foreground">
            Save an OpenAI-family endpoint, credentials, and runtime defaults for reuse across agents.
          </p>
          {connectionQuery.data ? (
            <PlatformResourceBadges
              status={connectionQuery.data.status}
              extra={
                <Badge variant={connectionQuery.data.hasApiKey ? "secondary" : "outline"}>
                  {connectionQuery.data.hasApiKey ? "API key configured" : "No API key"}
                </Badge>
              }
            />
          ) : null}
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
          <Button data-testid="model-connection-save" disabled={isSaving} size="sm" onClick={handleSave}>
            <Save data-icon="inline-start" />
            Save Model Connection
          </Button>
        </div>
      </div>

      {connectionFeedback ? (
        <Alert data-testid="model-connection-feedback" variant={connectionFeedback.variant}>
          {connectionFeedback.variant === "default" ? <CheckCircle2 /> : <XCircle />}
          <AlertTitle>{connectionFeedback.title}</AlertTitle>
          <AlertDescription>{connectionFeedback.message}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Connection details</CardTitle>
          <CardDescription>
            Base URL should stay at the provider&apos;s `/v1` root. Archived connections remain editable for historical references.
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
              onChange={(event) => updateValue("description", event.target.value)}
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
              <Label htmlFor="model-connection-api-style">API Style</Label>
              <Select
                value={values.apiStyle}
                disabled={isSaving}
                onValueChange={(value: ModelConnectionApiStyle) => updateValue("apiStyle", value)}
              >
                <SelectTrigger id="model-connection-api-style" aria-label="API Style">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="responses">{API_STYLE_LABELS.responses}</SelectItem>
                    <SelectItem value="chat_completions">
                      {API_STYLE_LABELS.chat_completions}
                    </SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
              <p className="text-sm text-muted-foreground">
                Keep <code>baseUrl</code> at the provider&apos;s `/v1` root. Chat Completions is for
                legacy/OpenAI-compatible third-party models.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="model-connection-timeout-seconds">Timeout Seconds</Label>
              <Input
                id="model-connection-timeout-seconds"
                aria-label="Timeout Seconds"
                disabled={isSaving}
                inputMode="numeric"
                value={values.timeoutSeconds}
                onChange={(event) => updateValue("timeoutSeconds", event.target.value)}
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="model-connection-organization">Organization</Label>
              <Input
                id="model-connection-organization"
                aria-label="Organization"
                disabled={isSaving}
                value={values.organization}
                onChange={(event) => updateValue("organization", event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="model-connection-project">Project</Label>
              <Input
                id="model-connection-project"
                aria-label="Project"
                disabled={isSaving}
                value={values.project}
                onChange={(event) => updateValue("project", event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="model-connection-reasoning-effort">Reasoning Effort</Label>
              <Select
                value={values.reasoningEffort}
                disabled={isSaving}
                onValueChange={(value) => updateValue("reasoningEffort", value as ReasoningEffortSelection)}
              >
                <SelectTrigger id="model-connection-reasoning-effort" aria-label="Reasoning Effort">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value={REASONING_EFFORT_OMIT_VALUE}>Omit reasoning parameter</SelectItem>
                    {REASONING_EFFORT_PRESETS.map((preset) => (
                      <SelectItem key={preset} value={preset}>{preset}</SelectItem>
                    ))}
                    <SelectItem value={REASONING_EFFORT_CUSTOM_VALUE}>Custom...</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
              {values.reasoningEffort === REASONING_EFFORT_CUSTOM_VALUE ? (
                <div className="space-y-2">
                  <Label htmlFor="model-connection-custom-reasoning-effort">Custom Reasoning Effort</Label>
                  <Input
                    id="model-connection-custom-reasoning-effort"
                    aria-label="Custom Reasoning Effort"
                    disabled={isSaving}
                    maxLength={CUSTOM_REASONING_EFFORT_MAX_LENGTH + 1}
                    value={values.customReasoningEffort}
                    onChange={(event) => updateValue("customReasoningEffort", event.target.value)}
                  />
                </div>
              ) : null}
              <p className="text-sm text-muted-foreground">
                Only sent for Responses API. Choose Omit for providers that reject reasoning. The literal value "none" is sent as a string; Omit sends no reasoning parameter.
                Existing agent versions keep saved model-connection snapshots; re-save the agent to pick up changed model-connection settings.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Credentials & health</CardTitle>
          <CardDescription>
            Existing secrets are never shown again. Save a new value only when you want to rotate it.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <SecretInput
            aria-label="API Key"
            disabled={isSaving}
            helperText={apiKeyHelpText}
            id="model-connection-api-key"
            label="API Key"
            placeholder={isEditing ? "Enter a new key to rotate it" : "Enter an API key"}
            value={values.apiKey}
            onValueChange={(value) => updateValue("apiKey", value)}
          />

          {connectionQuery.data?.lastTestedAt ? (
            <div className="rounded-lg border bg-muted/30 p-4 text-sm text-muted-foreground">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={connectionQuery.data.lastTestOk ? "secondary" : "destructive"}>
                  {connectionQuery.data.lastTestOk ? "Last test passed" : "Last test failed"}
                </Badge>
                <span>{formatDateTime(connectionQuery.data.lastTestedAt)}</span>
              </div>
              {connectionQuery.data.lastTestMessage ? (
                <p className="mt-2">{connectionQuery.data.lastTestMessage}</p>
              ) : null}
            </div>
          ) : (
            <div className="rounded-lg border bg-muted/30 p-4 text-sm text-muted-foreground">
              No connection test has been recorded yet.
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Exact config JSON</CardTitle>
          <CardDescription>
            Read-only canonical JSON derived from the same create or update payload used on save. API keys stay masked.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ExactJsonPreview
            ariaLabel="Exact config JSON"
            data-testid="model-connection-exact-config-json"
            value={exactConfigJson}
          />
        </CardContent>
      </Card>
    </div>
  );
}
