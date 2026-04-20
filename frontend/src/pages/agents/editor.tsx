import { useEffect, useMemo, useState } from "react";
import { Archive, Copy, FlaskConical, Save } from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";

import {
  useAgent,
  useArchiveAgent,
  useCreateAgent,
  useResolveAgentTestPanel,
  useUpdateAgent,
} from "@/hooks/use-agents";
import { useMcpServers } from "@/hooks/use-mcp-servers";
import { useOutputSchemas } from "@/hooks/use-output-schemas";
import { useSkills } from "@/hooks/use-skills";
import type { AgentCreateInput, AgentUpdateInput } from "@/lib/types/agent";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

import {
  parseJsonValue,
  parseOptionalNumber,
  parseRequiredText,
  parseVersionedRef,
  parseVersionedRefs,
  PlatformResourceBadges,
  sortByKey,
  stringifyJson,
  toVersionedRefValue,
} from "../platform-resource-shared";

type AgentEditorValues = {
  budgetUsd: string;
  description: string;
  inputSchema: string;
  key: string;
  maxToolRounds: string;
  mcpServers: string;
  model: string;
  name: string;
  outputSchemaRef: string;
  skills: string;
  streaming: boolean;
  systemPrompt: string;
  temperature: string;
};

const initialValues: AgentEditorValues = {
  budgetUsd: "",
  description: "",
  inputSchema: "{}",
  key: "",
  maxToolRounds: "",
  mcpServers: "",
  model: "",
  name: "",
  outputSchemaRef: "",
  skills: "",
  streaming: true,
  systemPrompt: "",
  temperature: "",
};

type TestPanelFeedback = {
  message: string;
  title: string;
  variant: "default" | "destructive";
};

export function AgentsEditorPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const duplicateFromId = !agentId ? searchParams.get("duplicateFrom") ?? undefined : undefined;
  const isEditing = Boolean(agentId);
  const agentQuery = useAgent(agentId);
  const duplicateQuery = useAgent(duplicateFromId);
  const createMutation = useCreateAgent();
  const updateMutation = useUpdateAgent();
  const archiveMutation = useArchiveAgent();
  const resolveTestPanelMutation = useResolveAgentTestPanel(agentId);
  const outputSchemasQuery = useOutputSchemas();
  const skillsQuery = useSkills();
  const mcpServersQuery = useMcpServers();
  const [values, setValues] = useState<AgentEditorValues>(initialValues);
  const [sampleInput, setSampleInput] = useState('{\n  "ticker": "AAPL"\n}');
  const [testPanelFeedback, setTestPanelFeedback] = useState<TestPanelFeedback | null>(null);
  const [testPanelResult, setTestPanelResult] = useState<string>("");

  const outputSchemas = useMemo(
    () => sortByKey(outputSchemasQuery.data?.items ?? []),
    [outputSchemasQuery.data?.items],
  );
  const skills = useMemo(() => sortByKey(skillsQuery.data?.items ?? []), [skillsQuery.data?.items]);
  const mcpServers = useMemo(
    () => sortByKey(mcpServersQuery.data?.items ?? []),
    [mcpServersQuery.data?.items],
  );

  useEffect(() => {
    if (!agentQuery.data) {
      return;
    }

    setValues({
      budgetUsd: agentQuery.data.budgetUsd,
      description: agentQuery.data.description ?? "",
      inputSchema: stringifyJson(agentQuery.data.inputSchema),
      key: agentQuery.data.key,
      maxToolRounds: String(agentQuery.data.maxToolRounds),
      mcpServers: agentQuery.data.mcpServers
        .map((server) => toVersionedRefValue(server.key, server.version))
        .join("\n"),
      model: agentQuery.data.model,
      name: agentQuery.data.name,
      outputSchemaRef: toVersionedRefValue(
        agentQuery.data.outputSchema.key,
        agentQuery.data.outputSchema.version,
      ),
      skills: agentQuery.data.skills
        .map((skill) => toVersionedRefValue(skill.key, skill.version))
        .join("\n"),
      streaming: agentQuery.data.streaming,
      systemPrompt: agentQuery.data.systemPrompt,
      temperature: String(agentQuery.data.temperature),
    });
  }, [agentQuery.data]);

  useEffect(() => {
    if (isEditing || !duplicateQuery.data) {
      return;
    }

    setValues({
      budgetUsd: duplicateQuery.data.budgetUsd,
      description: duplicateQuery.data.description ?? "",
      inputSchema: stringifyJson(duplicateQuery.data.inputSchema),
      key: "",
      maxToolRounds: String(duplicateQuery.data.maxToolRounds),
      mcpServers: duplicateQuery.data.mcpServers
        .map((server) => toVersionedRefValue(server.key, server.version))
        .join("\n"),
      model: duplicateQuery.data.model,
      name: `${duplicateQuery.data.name} Copy`,
      outputSchemaRef: toVersionedRefValue(
        duplicateQuery.data.outputSchema.key,
        duplicateQuery.data.outputSchema.version,
      ),
      skills: duplicateQuery.data.skills
        .map((skill) => toVersionedRefValue(skill.key, skill.version))
        .join("\n"),
      streaming: duplicateQuery.data.streaming,
      systemPrompt: duplicateQuery.data.systemPrompt,
      temperature: String(duplicateQuery.data.temperature),
    });
  }, [duplicateQuery.data, isEditing]);

  const isSaving = createMutation.isPending || updateMutation.isPending;

  const updateValue = <Key extends keyof AgentEditorValues>(key: Key, value: AgentEditorValues[Key]) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const buildPayload = (): AgentCreateInput | AgentUpdateInput => {
    const key = parseRequiredText("Key", values.key).toLowerCase();
    const name = parseRequiredText("Name", values.name);
    const model = parseRequiredText("Model", values.model);
    const systemPrompt = parseRequiredText("System prompt", values.systemPrompt);
    const outputSchema = parseVersionedRef("Output schema", values.outputSchemaRef);

    return {
      budgetUsd: values.budgetUsd.trim() || undefined,
      description: values.description.trim() || undefined,
      inputSchema: parseJsonValue("Input schema", values.inputSchema, {}),
      key,
      maxToolRounds: parseOptionalNumber("Max tool rounds", values.maxToolRounds, {
        integer: true,
        min: 1,
      }),
      mcpServers: parseVersionedRefs("MCP server", values.mcpServers).map((server) => ({
        mcpServerKey: server.key,
        mcpServerVersion: server.version ?? null,
      })),
      model,
      name,
      outputSchemaKey: outputSchema.key,
      outputSchemaVersion: outputSchema.version ?? null,
      skills: parseVersionedRefs("Skill", values.skills).map((skill) => ({
        skillKey: skill.key,
        skillVersion: skill.version ?? null,
      })),
      streaming: values.streaming,
      systemPrompt,
      temperature: parseOptionalNumber("Temperature", values.temperature, { min: 0 }),
    };
  };

  const handleSave = async () => {
    try {
      const payload = buildPayload();

      if (isEditing && agentId) {
        const { key: _ignored, ...updatePayload } = payload as AgentCreateInput;
        await updateMutation.mutateAsync({ agentId, payload: updatePayload });
        toast.success("Agent updated");
        return;
      }

      const created = await createMutation.mutateAsync(payload as AgentCreateInput);
      toast.success("Agent created");
      navigate(`/agents/${created.id}/edit`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save agent");
    }
  };

  const handleDuplicate = () => {
    if (!agentId) {
      return;
    }

    navigate(`/agents/new?duplicateFrom=${agentId}`);
  };

  const handleArchive = async () => {
    if (!agentId) {
      return;
    }

    try {
      await archiveMutation.mutateAsync(agentId);
      toast.success("Agent archived");
      navigate("/agents");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to archive agent");
    }
  };

  const handleRunTestPanel = async () => {
    if (!agentId) {
      setTestPanelFeedback({
        message: "Save the agent before using the test panel.",
        title: "Test panel unavailable",
        variant: "destructive",
      });
      return;
    }

    try {
      const result = await resolveTestPanelMutation.mutateAsync({
        sampleInput: parseJsonValue("Sample input", sampleInput, {}),
      });
      setTestPanelFeedback({
        message: "Resolved the current agent snapshot for the supplied sample input.",
        title: "Test panel ready",
        variant: "default",
      });
      setTestPanelResult(JSON.stringify(result, null, 2));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to resolve the test panel";
      setTestPanelFeedback({
        message,
        title: "Test panel failed",
        variant: "destructive",
      });
      setTestPanelResult("");
    }
  };

  if (isEditing && agentQuery.isPending) {
    return <div className="p-4 text-sm text-muted-foreground">Loading agent details...</div>;
  }

  if (isEditing && agentQuery.isError) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        {agentQuery.error instanceof Error ? agentQuery.error.message : "Agent not found."}
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4" data-testid="agents-editor">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">
            {isEditing ? "Edit Agent" : duplicateFromId ? "Duplicate Agent" : "Create Agent"}
          </h1>
          <p className="text-sm text-muted-foreground">
            Configure the core prompt, model policy, output schema, attached skill or MCP references, and a test-panel-ready sample input surface.
          </p>
          {agentQuery.data ? (
            <PlatformResourceBadges status={agentQuery.data.status} version={agentQuery.data.version} />
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {isEditing ? (
            <Button data-testid="agents-duplicate" size="sm" variant="outline" onClick={handleDuplicate}>
              <Copy data-icon="inline-start" />
              Duplicate Agent
            </Button>
          ) : null}
          {isEditing && agentQuery.data?.status !== "archived" ? (
            <Button data-testid="agents-archive" disabled={archiveMutation.isPending} size="sm" variant="outline" onClick={() => void handleArchive()}>
              <Archive data-icon="inline-start" />
              Archive Agent
            </Button>
          ) : null}
          <Button disabled={isSaving} size="sm" onClick={handleSave}>
            <Save data-icon="inline-start" />
            Save Agent
          </Button>
        </div>
      </div>
      <Tabs defaultValue="configuration" data-testid="agents-editor-tabs">
        <TabsList className="h-8">
          <TabsTrigger className="text-xs" value="configuration">Configuration</TabsTrigger>
          <TabsTrigger className="text-xs" value="test-panel">Test Panel</TabsTrigger>
        </TabsList>
        <TabsContent forceMount value="configuration">
          <Card>
        <CardHeader>
          <CardTitle>Agent details</CardTitle>
          <CardDescription>
            Keys are immutable after creation, while the model, prompt, and bindings remain editable.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="agent-key">Key</Label>
              <Input
                id="agent-key"
                aria-label="Key"
                disabled={isEditing || isSaving}
                value={values.key}
                onChange={(event) => updateValue("key", event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-name">Name</Label>
              <Input
                id="agent-name"
                aria-label="Name"
                disabled={isSaving}
                value={values.name}
                onChange={(event) => updateValue("name", event.target.value)}
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="agent-model">Model</Label>
              <Input
                id="agent-model"
                aria-label="Model"
                disabled={isSaving}
                value={values.model}
                onChange={(event) => updateValue("model", event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-output-schema">Output Schema</Label>
              <Select
                value={values.outputSchemaRef}
                disabled={isSaving || outputSchemas.length === 0}
                onValueChange={(value) => updateValue("outputSchemaRef", value)}
              >
                <SelectTrigger id="agent-output-schema" aria-label="Output Schema" data-testid="agent-output-schema-select">
                  <SelectValue placeholder="Select an output schema" />
                </SelectTrigger>
                <SelectContent>
                  {outputSchemas.map((schema) => (
                    <SelectItem key={schema.id} value={toVersionedRefValue(schema.key, schema.version)}>
                      {schema.name} ({schema.key}@{schema.version})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {outputSchemas.length === 0 ? (
                <p className="text-sm text-muted-foreground">Create an output schema before saving an agent.</p>
              ) : null}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="agent-description">Description</Label>
            <Textarea
              id="agent-description"
              aria-label="Description"
              disabled={isSaving}
              rows={3}
              value={values.description}
              onChange={(event) => updateValue("description", event.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="agent-system-prompt">System Prompt</Label>
            <Textarea
              id="agent-system-prompt"
              aria-label="System Prompt"
              disabled={isSaving}
              rows={10}
              value={values.systemPrompt}
              onChange={(event) => updateValue("systemPrompt", event.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="agent-input-schema">Input Schema JSON</Label>
            <Textarea
              id="agent-input-schema"
              aria-label="Input Schema JSON"
              disabled={isSaving}
              rows={8}
              value={values.inputSchema}
              onChange={(event) => updateValue("inputSchema", event.target.value)}
            />
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="agent-temperature">Temperature</Label>
              <Input
                id="agent-temperature"
                aria-label="Temperature"
                disabled={isSaving}
                value={values.temperature}
                onChange={(event) => updateValue("temperature", event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-max-tool-rounds">Max Tool Rounds</Label>
              <Input
                id="agent-max-tool-rounds"
                aria-label="Max Tool Rounds"
                disabled={isSaving}
                value={values.maxToolRounds}
                onChange={(event) => updateValue("maxToolRounds", event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-budget-usd">Budget USD</Label>
              <Input
                id="agent-budget-usd"
                aria-label="Budget USD"
                disabled={isSaving}
                value={values.budgetUsd}
                onChange={(event) => updateValue("budgetUsd", event.target.value)}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="agent-skills">Skills</Label>
            <Textarea
              id="agent-skills"
              aria-label="Skills"
              disabled={isSaving}
              rows={4}
              value={values.skills}
              onChange={(event) => updateValue("skills", event.target.value)}
            />
            {skills.length > 0 ? (
              <p className="text-sm text-muted-foreground">
                Available refs: {skills.map((skill) => toVersionedRefValue(skill.key, skill.version)).join(", ")}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="agent-mcp-servers">MCP Servers</Label>
            <Textarea
              id="agent-mcp-servers"
              aria-label="MCP Servers"
              disabled={isSaving}
              rows={4}
              value={values.mcpServers}
              onChange={(event) => updateValue("mcpServers", event.target.value)}
            />
            {mcpServers.length > 0 ? (
              <p className="text-sm text-muted-foreground">
                Available refs: {mcpServers.map((server) => toVersionedRefValue(server.key, server.version)).join(", ")}
              </p>
            ) : null}
          </div>

          <div className="flex items-center justify-between rounded-md border p-4">
            <div className="space-y-1">
              <Label htmlFor="agent-streaming">Streaming</Label>
              <p className="text-sm text-muted-foreground">
                Enable streaming responses for runtime callers that support partial output.
              </p>
            </div>
            <Switch
              id="agent-streaming"
              aria-label="Streaming"
              checked={values.streaming}
              disabled={isSaving}
              onCheckedChange={(checked) => updateValue("streaming", checked)}
            />
          </div>
        </CardContent>
      </Card>
    </TabsContent>
    <TabsContent forceMount value="test-panel">
      <Card data-testid="agent-test-panel">
        <CardHeader>
          <CardTitle>Test panel</CardTitle>
          <CardDescription>
            Resolve the current saved agent snapshot against a sample input before wiring it into broader workflows.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          {!isEditing ? (
            <Alert data-testid="agent-test-panel-unavailable" variant="destructive">
              <AlertTitle>Test panel unavailable</AlertTitle>
              <AlertDescription>Save the agent before using the test panel.</AlertDescription>
            </Alert>
          ) : null}
          {testPanelFeedback ? (
            <Alert data-testid="agent-test-panel-feedback" variant={testPanelFeedback.variant}>
              <AlertTitle>{testPanelFeedback.title}</AlertTitle>
              <AlertDescription>{testPanelFeedback.message}</AlertDescription>
            </Alert>
          ) : null}
          <div className="space-y-2">
            <Label htmlFor="agent-test-panel-sample-input">Sample Input JSON</Label>
            <Textarea
              id="agent-test-panel-sample-input"
              aria-label="Sample Input JSON"
              disabled={!isEditing || resolveTestPanelMutation.isPending}
              rows={8}
              value={sampleInput}
              onChange={(event) => setSampleInput(event.target.value)}
            />
          </div>
          <div className="flex justify-end">
            <Button
              data-testid="agent-test-panel-run"
              disabled={!isEditing || resolveTestPanelMutation.isPending}
              size="sm"
              variant="outline"
              onClick={() => void handleRunTestPanel()}
            >
              <FlaskConical data-icon="inline-start" />
              Run Test Panel
            </Button>
          </div>
          {testPanelResult ? (
            <div className="space-y-2" data-testid="agent-test-panel-result">
              <Label>Resolved Result JSON</Label>
              <pre className="overflow-x-auto rounded-md border bg-muted p-3 text-xs text-foreground whitespace-pre-wrap">
                {testPanelResult}
              </pre>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </TabsContent>
  </Tabs>
</div>
  );
}
