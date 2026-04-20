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
import type { McpServerCreateInput, McpServerUpdateInput } from "@/lib/types/mcp-server";
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
} from "../platform-resource-shared";

type ConnectionFeedback = {
  message: string;
  title: string;
  variant: "default" | "destructive";
};

type McpServerEditorValues = {
  auth: string;
  command: string;
  description: string;
  enabled: boolean;
  key: string;
  name: string;
  transport: "stdio" | "http-sse";
  url: string;
};

const initialValues: McpServerEditorValues = {
  auth: "{}",
  command: "",
  description: "",
  enabled: true,
  key: "",
  name: "",
  transport: "stdio",
  url: "",
};

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

    setValues({
      auth: JSON.stringify(serverQuery.data.auth ?? {}, null, 2),
      command: serverQuery.data.command ?? "",
      description: serverQuery.data.description ?? "",
      enabled: serverQuery.data.enabled,
      key: serverQuery.data.key,
      name: serverQuery.data.name,
      transport: serverQuery.data.transport,
      url: serverQuery.data.url ?? "",
    });
    setConnectionFeedback(null);
  }, [serverQuery.data]);

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const isBusy = isSaving || activateMutation.isPending || testConnectionMutation.isPending;
  const canActivate = Boolean(isEditing && serverQuery.data?.status === "draft");

  const updateValue = <Key extends keyof McpServerEditorValues>(
    key: Key,
    value: McpServerEditorValues[Key],
  ) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const buildPayload = (): McpServerCreateInput | McpServerUpdateInput => {
    const payload = {
      auth: parseJsonValue("Auth", values.auth, {}),
      command: values.command.trim() || null,
      description: values.description.trim() || undefined,
      enabled: values.enabled,
      key: parseRequiredText("Key", values.key).toLowerCase(),
      name: parseRequiredText("Name", values.name),
      transport: values.transport,
      url: values.url.trim() || null,
    };

    if (payload.transport === "stdio" && !payload.command) {
      throw new Error("Command is required for stdio servers.");
    }

    if (payload.transport === "http-sse" && !payload.url) {
      throw new Error("URL is required for HTTP SSE servers.");
    }

    return payload;
  };

  const handleSave = async () => {
    try {
      const payload = buildPayload();

      if (isEditing && serverId) {
        const { key: _ignored, ...updatePayload } = payload as McpServerCreateInput;
        const updated = await updateMutation.mutateAsync({ payload: updatePayload, serverId });
        toast.success("MCP server updated");
        navigate(`/mcp-servers/${updated.id}/edit`);
        return;
      }

      const created = await createMutation.mutateAsync(payload as McpServerCreateInput);
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
          <Button
            data-testid="mcp-server-test-connection"
            disabled={testConnectionMutation.isPending}
            size="sm"
            variant="outline"
            onClick={() => void handleTestConnection()}
          >
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
        <Alert
          data-testid="mcp-server-connection-feedback"
          variant={connectionFeedback.variant}
        >
          {connectionFeedback.variant === "default" ? <CheckCircle2 /> : <XCircle />}
          <AlertTitle>{connectionFeedback.title}</AlertTitle>
          <AlertDescription>{connectionFeedback.message}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>MCP server details</CardTitle>
          <CardDescription>
            Keys are immutable after creation. Choose a transport and provide the matching connection settings.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="mcp-server-key">Key</Label>
              <Input
                id="mcp-server-key"
                aria-label="Key"
                disabled={isEditing || isSaving}
                value={values.key}
                onChange={(event) => updateValue("key", event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="mcp-server-name">Name</Label>
              <Input
                id="mcp-server-name"
                aria-label="Name"
                disabled={isSaving}
                value={values.name}
                onChange={(event) => updateValue("name", event.target.value)}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="mcp-server-description">Description</Label>
            <Textarea
              id="mcp-server-description"
              aria-label="Description"
              disabled={isSaving}
              rows={3}
              value={values.description}
              onChange={(event) => updateValue("description", event.target.value)}
            />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="mcp-server-transport">Transport</Label>
              <Select
                value={values.transport}
                disabled={isSaving}
                onValueChange={(value: "stdio" | "http-sse") => updateValue("transport", value)}
              >
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
              <Switch
                id="mcp-server-enabled"
                aria-label="Enabled"
                checked={values.enabled}
                disabled={isSaving}
                onCheckedChange={(checked) => updateValue("enabled", checked)}
              />
            </div>
          </div>

          {values.transport === "stdio" ? (
            <div className="space-y-2">
              <Label htmlFor="mcp-server-command">Command</Label>
              <Input
                id="mcp-server-command"
                aria-label="Command"
                disabled={isSaving}
                value={values.command}
                onChange={(event) => updateValue("command", event.target.value)}
              />
            </div>
          ) : (
            <div className="space-y-2">
              <Label htmlFor="mcp-server-url">URL</Label>
              <Input
                id="mcp-server-url"
                aria-label="URL"
                disabled={isSaving}
                value={values.url}
                onChange={(event) => updateValue("url", event.target.value)}
              />
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="mcp-server-auth">Auth JSON</Label>
            <Textarea
              id="mcp-server-auth"
              aria-label="Auth JSON"
              disabled={isSaving}
              rows={8}
              value={values.auth}
              onChange={(event) => updateValue("auth", event.target.value)}
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
