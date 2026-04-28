import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, PlugZap, Plus, Save, Trash2, XCircle } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { ExactJsonPreview } from "@/components/platform-authoring/inspectors/exact-json-preview";
import {
  useActivateMcpServer,
  useCreateMcpServer,
  useMcpServer,
  useTestMcpServerConnection,
  useUpdateMcpServer,
} from "@/hooks/use-mcp-servers";
import type {
  McpServerConfig,
  McpServerCreateInput,
  McpServerRead,
  McpServerUpdateInput,
} from "@/lib/types/mcp-server";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

import {
  parseJsonValue,
  parseRequiredText,
  PlatformResourceBadges,
  stringifyJson,
} from "../platform-resource-shared";

type ConnectionFeedback = {
  message: string;
  title: string;
  variant: "default" | "destructive";
};

type KeyValueEntry = {
  id: string;
  key: string;
  value: string;
};

let keyValueEntryCounter = 0;

function createKeyValueEntry(key = "", value = ""): KeyValueEntry {
  keyValueEntryCounter += 1;
  return {
    id: `mcp-server-entry-${keyValueEntryCounter}`,
    key,
    value,
  };
}

function buildKeyValueEntries(record: Record<string, string> | null | undefined): KeyValueEntry[] {
  const entries = Object.entries(record ?? {});
  return entries.length > 0
    ? entries.map(([key, value]) => createKeyValueEntry(key, value))
    : [createKeyValueEntry()];
}

function buildKeyValueRecord(entries: KeyValueEntry[]): Record<string, string> {
  const record: Record<string, string> = {};

  for (const entry of entries) {
    const trimmedKey = entry.key.trim();

    if (!trimmedKey) {
      continue;
    }

    record[trimmedKey] = entry.value;
  }

  return record;
}

function buildStructuredConfigValues(values: McpServerEditorValues) {
  return {
    args: parseJsonValue<string[]>("Args", values.args, []),
    env: buildKeyValueRecord(values.env),
    headers: buildKeyValueRecord(values.headers),
  };
}

function KeyValueObjectEditor(props: {
  addLabel: string;
  description: string;
  disabled: boolean;
  emptyKeyLabel: string;
  keyLabelPrefix: string;
  previewAriaLabel: string;
  previewTestId: string;
  previewValue: string;
  rows: KeyValueEntry[];
  title: string;
  valueLabelPrefix: string;
  onAdd: () => void;
  onChange: (entryId: string, field: "key" | "value", value: string) => void;
  onRemove: (entryId: string) => void;
}) {
  const {
    addLabel,
    description,
    disabled,
    emptyKeyLabel,
    keyLabelPrefix,
    previewAriaLabel,
    previewTestId,
    previewValue,
    rows,
    title,
    valueLabelPrefix,
    onAdd,
    onChange,
    onRemove,
  } = props;

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <div className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <Label>{title}</Label>
            <p className="text-sm text-muted-foreground">{description}</p>
          </div>
          <Button disabled={disabled} size="sm" type="button" variant="outline" onClick={onAdd}>
            <Plus data-icon="inline-start" />
            {addLabel}
          </Button>
        </div>
        <div className="grid gap-3">
          {rows.map((entry, index) => (
            <div key={entry.id} className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end">
              <div className="space-y-2">
                <Label htmlFor={`${entry.id}-key`}>{index === 0 ? emptyKeyLabel : `${emptyKeyLabel} ${index + 1}`}</Label>
                <Input
                  id={`${entry.id}-key`}
                  aria-label={`${keyLabelPrefix} ${index + 1}`}
                  disabled={disabled}
                  value={entry.key}
                  onChange={(event) => onChange(entry.id, "key", event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor={`${entry.id}-value`}>Value</Label>
                <Input
                  id={`${entry.id}-value`}
                  aria-label={`${valueLabelPrefix} ${index + 1}`}
                  disabled={disabled}
                  value={entry.value}
                  onChange={(event) => onChange(entry.id, "value", event.target.value)}
                />
              </div>
              <Button
                aria-label={`Remove ${keyLabelPrefix.toLowerCase()} row ${index + 1}`}
                className="md:self-end"
                disabled={disabled}
                size="icon"
                type="button"
                variant="outline"
                onClick={() => onRemove(entry.id)}
              >
                <Trash2 />
              </Button>
            </div>
          ))}
        </div>
      </div>
      <div className="space-y-2">
        <Label>{previewAriaLabel}</Label>
        <ExactJsonPreview ariaLabel={previewAriaLabel} data-testid={previewTestId} value={previewValue} />
      </div>
    </div>
  );
}

type McpServerEditorValues = {
  args: string;
  command: string;
  description: string;
  enabled: boolean;
  env: KeyValueEntry[];
  headers: KeyValueEntry[];
  key: string;
  jsonError: string | null;
  name: string;
  transport: "stdio" | "http-sse";
  url: string;
};

const initialValues: McpServerEditorValues = {
  args: stringifyJson([]),
  command: "",
  description: "",
  enabled: true,
  env: buildKeyValueEntries({}),
  headers: buildKeyValueEntries({}),
  jsonError: null,
  key: "",
  name: "",
  transport: "stdio",
  url: "",
};

function buildConfigFromValues(values: McpServerEditorValues): McpServerConfig {
  const structuredValues = buildStructuredConfigValues(values);
  const common = {
    description: values.description.trim(),
    enabled: values.enabled,
    name: parseRequiredText("Name", values.name),
  };

  if (values.transport === "stdio") {
    return {
      ...common,
      args: structuredValues.args,
      command: parseRequiredText("Command", values.command),
      env: structuredValues.env,
      transport: "stdio",
    };
  }

  return {
    ...common,
    headers: structuredValues.headers,
    transport: "http-sse",
    url: parseRequiredText("URL", values.url),
  };
}

function buildValuesFromServer(server: McpServerRead): McpServerEditorValues {
  return {
    args: stringifyJson(server.transport === "stdio" ? server.args ?? [] : []),
    command: server.transport === "stdio" ? server.command ?? "" : "",
    description: server.description ?? "",
    enabled: server.enabled,
    env: buildKeyValueEntries(server.transport === "stdio" ? server.env ?? {} : {}),
    headers: buildKeyValueEntries(server.transport === "http-sse" ? server.headers ?? {} : {}),
    jsonError: null,
    key: server.key,
    name: server.name,
    transport: server.transport,
    url: server.transport === "http-sse" ? server.url ?? "" : "",
  };
}

export function McpServersEditorPage() {
  const { serverId } = useParams<{ serverId: string }>();
  const navigate = useNavigate();
  const isEditing = Boolean(serverId);
  const serverQuery = useMcpServer(serverId);
  const createMutation = useCreateMcpServer();
  const updateMutation = useUpdateMcpServer();
  const activateMutation = useActivateMcpServer();
  const testConnectionMutation = useTestMcpServerConnection(serverId);
  const [values, setValues] = useState<McpServerEditorValues>(initialValues);
  const [connectionFeedback, setConnectionFeedback] = useState<ConnectionFeedback | null>(null);
  const rawEnvJson = useMemo(() => stringifyJson(buildKeyValueRecord(values.env)), [values.env]);
  const rawHeadersJson = useMemo(() => stringifyJson(buildKeyValueRecord(values.headers)), [values.headers]);

  useEffect(() => {
    if (!serverQuery.data) {
      return;
    }
    setValues(buildValuesFromServer(serverQuery.data));
    setConnectionFeedback(null);
  }, [serverQuery.data]);

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const isBusy = isSaving || activateMutation.isPending || testConnectionMutation.isPending;
  const canActivate = Boolean(isEditing && serverQuery.data?.status === "draft");

  const updateValue = <Key extends keyof McpServerEditorValues>(
    key: Key,
    value: McpServerEditorValues[Key],
  ) => {
    setValues((current) => {
      const nextValues = { ...current, [key]: value };
      try {
        buildConfigFromValues(nextValues);
        return { ...nextValues, jsonError: null };
      } catch {
        return { ...nextValues, jsonError: null };
      }
    });
  };

  const updateObjectRows = (field: "env" | "headers", nextRows: KeyValueEntry[]) => {
    setValues((current) => ({
      ...current,
      [field]: nextRows,
      jsonError: null,
    }));
  };

  const handleObjectRowChange = (
    field: "env" | "headers",
    entryId: string,
    entryField: "key" | "value",
    value: string,
  ) => {
    setValues((current) => ({
      ...current,
      [field]: current[field].map((entry) =>
        entry.id === entryId ? { ...entry, [entryField]: value } : entry,
      ),
      jsonError: null,
    }));
  };

  const handleAddObjectRow = (field: "env" | "headers") => {
    updateObjectRows(field, [...values[field], createKeyValueEntry()]);
  };

  const handleRemoveObjectRow = (field: "env" | "headers", entryId: string) => {
    setValues((current) => {
      const nextRows = current[field].filter((entry) => entry.id !== entryId);
      return {
        ...current,
        [field]: nextRows.length > 0 ? nextRows : [createKeyValueEntry()],
        jsonError: null,
      };
    });
  };

  const parsePayloadForSubmit = (): McpServerCreateInput | McpServerUpdateInput => {
    if (values.jsonError) {
      throw new Error(values.jsonError);
    }

    const config = buildConfigFromValues(values);
    const key = parseRequiredText("Key", values.key).toLowerCase();
    return isEditing ? (config as McpServerUpdateInput) : ({ ...config, key } as McpServerCreateInput);
  };

  const handleSave = async () => {
    try {
      if (isEditing && serverId) {
        const payload = parsePayloadForSubmit() as McpServerUpdateInput;
        const updated = await updateMutation.mutateAsync({ payload, serverId });
        toast.success("MCP server updated");
        navigate(`/mcp-servers/${updated.id}/edit`);
        return;
      }
      const payload = parsePayloadForSubmit() as McpServerCreateInput;
      const created = await createMutation.mutateAsync(payload);
      toast.success("MCP server created");
      navigate(`/mcp-servers/${created.id}/edit`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save MCP server");
    }
  };

  const handleTestConnection = async () => {
    if (!serverId) {
      setConnectionFeedback({
        message: "Save the MCP server before testing its connection.",
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
      const message = error instanceof Error ? error.message : "Failed to test MCP server connection";
      setConnectionFeedback({
        message,
        title: "Connection test failed",
        variant: "destructive",
      });
      toast.error(message);
    }
  };

  const handleActivate = async () => {
    if (!serverId) {
      return;
    }
    try {
      await activateMutation.mutateAsync(serverId);
      toast.success("MCP server activated");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to activate MCP server");
    }
  };

  if (isEditing && serverQuery.isPending) {
    return <div className="p-4 text-sm text-muted-foreground">Loading MCP server details...</div>;
  }
  if (isEditing && serverQuery.isError) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        {serverQuery.error instanceof Error ? serverQuery.error.message : "MCP server not found."}
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4" data-testid="mcp-servers-editor">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">
            {isEditing ? "Edit MCP Server" : "Create MCP Server"}
          </h1>
          <p className="text-sm text-muted-foreground">
            Configure how the workspace reaches an external MCP server and validate the current connection.
          </p>
          {serverQuery.data ? (
            <PlatformResourceBadges status={serverQuery.data.status} version={serverQuery.data.version} />
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {canActivate ? (
            <Button data-testid="mcp-server-activate" disabled={isBusy} size="sm" variant="outline" onClick={() => void handleActivate()}>
              Activate MCP Server
            </Button>
          ) : null}
          <Button data-testid="mcp-server-test-connection" disabled={testConnectionMutation.isPending} size="sm" variant="outline" onClick={() => void handleTestConnection()}>
            <PlugZap data-icon="inline-start" />
            Test Connection
          </Button>
          <Button disabled={isSaving} size="sm" onClick={handleSave}>
            <Save data-icon="inline-start" />
            Save MCP Server
          </Button>
        </div>
      </div>

      {connectionFeedback ? (
        <Alert data-testid="mcp-server-connection-feedback" variant={connectionFeedback.variant}>
          {connectionFeedback.variant === "default" ? <CheckCircle2 /> : <XCircle />}
          <AlertTitle>{connectionFeedback.title}</AlertTitle>
          <AlertDescription>{connectionFeedback.message}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>MCP server details</CardTitle>
          <CardDescription>
            Form edits update the flat resource fields directly.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="mcp-server-key">Key</Label>
              <Input id="mcp-server-key" aria-label="Key" disabled={isEditing || isSaving} value={values.key} onChange={(event) => updateValue("key", event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="mcp-server-name">Name</Label>
              <Input id="mcp-server-name" aria-label="Name" disabled={isSaving} value={values.name} onChange={(event) => updateValue("name", event.target.value)} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="mcp-server-description">Description</Label>
            <Textarea id="mcp-server-description" aria-label="Description" disabled={isSaving} rows={3} value={values.description} onChange={(event) => updateValue("description", event.target.value)} />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="mcp-server-transport">Transport</Label>
              <Select value={values.transport} disabled={isSaving} onValueChange={(value: "stdio" | "http-sse") => updateValue("transport", value)}>
                <SelectTrigger id="mcp-server-transport" aria-label="Transport">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="stdio">stdio</SelectItem>
                  <SelectItem value="http-sse">http-sse</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between rounded-md border p-4">
              <div className="space-y-1">
                <Label htmlFor="mcp-server-enabled">Enabled</Label>
                <p className="text-sm text-muted-foreground">Disable a server without removing its configuration.</p>
              </div>
              <Switch id="mcp-server-enabled" aria-label="Enabled" checked={values.enabled} disabled={isSaving} onCheckedChange={(checked) => updateValue("enabled", checked)} />
            </div>
          </div>

          {values.transport === "stdio" ? (
            <>
              <div className="space-y-2">
                <Label htmlFor="mcp-server-command">Command</Label>
                <Input id="mcp-server-command" aria-label="Command" disabled={isSaving} value={values.command} onChange={(event) => updateValue("command", event.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="mcp-server-args">Args JSON</Label>
                <Textarea id="mcp-server-args" aria-label="Args JSON" disabled={isSaving} rows={5} value={values.args} onChange={(event) => updateValue("args", event.target.value)} />
              </div>
              <KeyValueObjectEditor
                addLabel="Add env row"
                description="Edit environment variables as structured key/value rows. Blank keys stay local and are omitted from the submitted payload."
                disabled={isSaving}
                emptyKeyLabel="Env key"
                keyLabelPrefix="Env key"
                previewAriaLabel="Exact raw env JSON"
                previewTestId="mcp-server-env-raw-json"
                previewValue={rawEnvJson}
                rows={values.env}
                title="Env variables"
                valueLabelPrefix="Env value"
                onAdd={() => handleAddObjectRow("env")}
                onChange={(entryId, field, value) => handleObjectRowChange("env", entryId, field, value)}
                onRemove={(entryId) => handleRemoveObjectRow("env", entryId)}
              />
            </>
          ) : (
            <>
              <div className="space-y-2">
                <Label htmlFor="mcp-server-url">URL</Label>
                <Input id="mcp-server-url" aria-label="URL" disabled={isSaving} value={values.url} onChange={(event) => updateValue("url", event.target.value)} />
              </div>
              <KeyValueObjectEditor
                addLabel="Add header row"
                description="Edit request headers as structured key/value rows. Blank keys stay local and are omitted from the submitted payload."
                disabled={isSaving}
                emptyKeyLabel="Header key"
                keyLabelPrefix="Header key"
                previewAriaLabel="Exact raw headers JSON"
                previewTestId="mcp-server-headers-raw-json"
                previewValue={rawHeadersJson}
                rows={values.headers}
                title="Headers"
                valueLabelPrefix="Header value"
                onAdd={() => handleAddObjectRow("headers")}
                onChange={(entryId, field, value) => handleObjectRowChange("headers", entryId, field, value)}
                onRemove={(entryId) => handleRemoveObjectRow("headers", entryId)}
              />
            </>
          )}

          {values.jsonError ? <p className="text-sm text-destructive">{values.jsonError}</p> : null}
        </CardContent>
      </Card>
    </div>
  );
}
