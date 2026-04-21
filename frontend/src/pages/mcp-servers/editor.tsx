import { useEffect, useState } from "react";
import { CheckCircle2, PlugZap, Save, XCircle } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

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

type McpServerEditorValues = {
  args: string;
  command: string;
  description: string;
  enabled: boolean;
  env: string;
  headers: string;
  key: string;
  jsonError: string | null;
  name: string;
  transport: "stdio" | "http-sse";
  url: string;
};

const initialValues: McpServerEditorValues = {
  args: "[\n  \"-m\",\n  \"app.agents.mcp.stock_analysis_reference_server\"\n]",
  command: "python3",
  description: "",
  enabled: true,
  env: "{}",
  headers: "{}",
  jsonError: null,
  key: "",
  name: "",
  transport: "stdio",
  url: "",
};

function buildConfigFromValues(values: McpServerEditorValues): McpServerConfig {
  const common = {
    description: values.description.trim(),
    enabled: values.enabled,
    name: parseRequiredText("Name", values.name),
  };

  if (values.transport === "stdio") {
    return {
      ...common,
      args: parseJsonValue<string[]>("Args", values.args, []),
      command: parseRequiredText("Command", values.command),
      env: parseJsonValue<Record<string, string>>("Env", values.env, {}),
      transport: "stdio",
    };
  }

  return {
    ...common,
    headers: parseJsonValue<Record<string, string>>("Headers", values.headers, {}),
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
    env: stringifyJson(server.transport === "stdio" ? server.env ?? {} : {}),
    headers: stringifyJson(server.transport === "http-sse" ? server.headers ?? {} : {}),
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
              <div className="space-y-2">
                <Label htmlFor="mcp-server-env">Env JSON</Label>
                <Textarea id="mcp-server-env" aria-label="Env JSON" disabled={isSaving} rows={5} value={values.env} onChange={(event) => updateValue("env", event.target.value)} />
              </div>
            </>
          ) : (
            <>
              <div className="space-y-2">
                <Label htmlFor="mcp-server-url">URL</Label>
                <Input id="mcp-server-url" aria-label="URL" disabled={isSaving} value={values.url} onChange={(event) => updateValue("url", event.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="mcp-server-headers">Headers JSON</Label>
                <Textarea id="mcp-server-headers" aria-label="Headers JSON" disabled={isSaving} rows={5} value={values.headers} onChange={(event) => updateValue("headers", event.target.value)} />
              </div>
            </>
          )}

          {values.jsonError ? <p className="text-sm text-destructive">{values.jsonError}</p> : null}
        </CardContent>
      </Card>
    </div>
  );
}
