import { useEffect, useMemo, useState } from "react";
import { Archive, Copy, PlayCircle, Save } from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";

import { ResourceMultiRefSelect } from "@/components/platform-authoring/refs/resource-multi-ref-select";
import {
  ResourceRefSelect,
  type ResourceRefSelectOption,
} from "@/components/platform-authoring/refs/resource-ref-select";
import { SchemaForm } from "@/components/platform-authoring/generated-form/schema-form";
import { ExactJsonPreview } from "@/components/platform-authoring/inspectors/exact-json-preview";
import { SchemaComposer } from "@/components/platform-authoring/schema-composer/schema-composer";
import { useAgent, useArchiveAgent, useCreateAgent, useCreateAgentRun, useUpdateAgent } from "@/hooks/use-agents";
import { useMcpServers } from "@/hooks/use-mcp-servers";
import { useModelConnections } from "@/hooks/use-model-connections";
import { useOutputSchemas } from "@/hooks/use-output-schemas";
import { useSkills } from "@/hooks/use-skills";
import { agentBindingRefsFromRead } from "@/lib/platform-authoring/agents/codec";
import type { AgentAuthoringDraft } from "@/lib/platform-authoring/agents/types";
import { validateAgentDraft } from "@/lib/platform-authoring/agents/validation";
import { stringifyJson } from "@/lib/platform-authoring/common/serialization";
import {
  parseSchemaJsonText,
  schemaBuilderToJsonSchema,
  type SchemaCodecIssue,
} from "@/lib/platform-authoring/schema/codec";
import { createDefaultSchemaNode } from "@/lib/platform-authoring/schema/factories";
import { buildPreviewValue } from "@/lib/platform-authoring/schema/preview";
import type { SchemaIRNode } from "@/lib/platform-authoring/schema/types";
import { encodeValueEntry, validateAndDecodeValueEntry } from "@/lib/platform-authoring/values/codec";
import type { ValueEntry } from "@/lib/platform-authoring/values/types";
import type { ResourceRef } from "@/lib/platform-authoring/common/resource-ref";
import type { AgentCreateInput, AgentRead, AgentUpdateInput } from "@/lib/types/agent";
import type { UnknownRecord } from "@/lib/types/common";
import type { ModelConnectionListItemRead } from "@/lib/types/model-connection";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

import { parseOptionalNumber, parseRequiredText, PlatformResourceBadges, sortByKey } from "../platform-resource-shared";

type RunLaunchFeedback = {
  message: string;
  title: string;
  variant: "default" | "destructive";
};

type HydratedAgentEditorState = {
  draft: AgentAuthoringDraft;
  issues: SchemaCodecIssue[];
  sampleInput: ValueEntry;
};

const UNSELECTED_MODEL_CONNECTION = "__unselected_model_connection__";

function compareModelConnections(
  left: ModelConnectionListItemRead,
  right: ModelConnectionListItemRead,
): number {
  const nameComparison = left.name.localeCompare(right.name);
  if (nameComparison !== 0) {
    return nameComparison;
  }

  const modelComparison = left.modelId.localeCompare(right.modelId);
  if (modelComparison !== 0) {
    return modelComparison;
  }

  return left.id - right.id;
}

function formatModelConnectionLabel(connection: ModelConnectionListItemRead): string {
  return `${connection.name} · ${connection.modelId}`;
}

function formatModelConnectionMeta(connection: ModelConnectionListItemRead): string {
  return `${connection.baseUrl} · ${connection.reasoningEffort} reasoning`;
}

function parseModelConnectionId(value: string) {
  const modelConnectionId = parseOptionalNumber("Model connection", value, {
    integer: true,
    min: 1,
  });

  if (modelConnectionId === undefined) {
    throw new Error("Model connection is required.");
  }

  return modelConnectionId;
}

function createInitialDraft(): AgentAuthoringDraft {
  return {
    budgetUsd: "",
    description: "",
    inputSchema: createDefaultSchemaNode("object"),
    bindings: {
      outputSchema: { key: "", version: null },
      skills: [],
      mcpServers: [],
    },
    key: "",
    modelConnectionId: "",
    name: "",
    systemPrompt: "",
  };
}

function isUnknownRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function createDefaultSampleInputValue(schema: SchemaIRNode): ValueEntry {
  const previewValue = buildPreviewValue(schema);

  if (isUnknownRecord(previewValue) && typeof previewValue.ticker === "string") {
    return encodeValueEntry({ ...previewValue, ticker: "AAPL" });
  }

  if (isUnknownRecord(previewValue)) {
    return encodeValueEntry(previewValue);
  }

  return encodeValueEntry({});
}

function decodeSampleInputValue(value: ValueEntry): UnknownRecord {
  const decoded = validateAndDecodeValueEntry(value);

  if (!decoded.ok || !isUnknownRecord(decoded.value)) {
    throw new Error("Sample input must be a JSON object.");
  }

  return decoded.value;
}

function decodePersistedInputSchema(
  agent: AgentRead,
  options: { clearArchivedModelConnection?: boolean; clearKey?: boolean; duplicateName?: boolean } = {},
): HydratedAgentEditorState {
  const decoded = parseSchemaJsonText(stringifyJson(agent.inputSchema));
  const builder = decoded.builder ?? createDefaultSchemaNode("object");
  const shouldClearArchivedModelConnection =
    options.clearArchivedModelConnection && agent.modelConnection.status === "archived";

  return {
      draft: {
        budgetUsd: agent.budgetUsd,
        description: agent.description ?? "",
        inputSchema: builder,
        bindings: agentBindingRefsFromRead(agent),
        key: options.clearKey ? "" : agent.key,
        modelConnectionId: shouldClearArchivedModelConnection ? "" : String(agent.modelConnectionId),
        name: options.duplicateName ? `${agent.name} Copy` : agent.name,
        systemPrompt: agent.systemPrompt,
      },
    issues: decoded.issues,
    sampleInput: createDefaultSampleInputValue(builder),
  };
}

function toResourceRefOptions<T extends {
  description?: string | null;
  key: string;
  name: string;
  status?: string;
  version: number;
}>(items: readonly T[]): ResourceRefSelectOption[] {
  return items.map((item) => ({
    description: item.description ?? undefined,
    key: item.key,
    keywords: [item.key],
    label: item.name,
    status: item.status,
    version: item.version,
  }));
}

function cloneResourceRef(ref: ResourceRef): ResourceRef {
  return { key: ref.key, version: ref.version };
}

function cloneResourceRefs(refs: readonly ResourceRef[]): ResourceRef[] {
  return refs.map((ref) => cloneResourceRef(ref));
}

function buildPayload(
  draft: AgentAuthoringDraft,
  inputSchema = schemaBuilderToJsonSchema(draft.inputSchema),
): AgentCreateInput | AgentUpdateInput {
  const [issue] = validateAgentDraft(draft);

  if (issue) {
    throw new Error(issue.issue);
  }

  return {
    budgetUsd: draft.budgetUsd.trim() || undefined,
    description: draft.description.trim() || undefined,
    inputSchema,
    key: parseRequiredText("Key", draft.key).toLowerCase(),
    mcpServers: draft.bindings.mcpServers.map((server) => ({
      mcpServerKey: server.key.trim(),
      mcpServerVersion: server.version ?? null,
    })),
    modelConnectionId: parseModelConnectionId(draft.modelConnectionId),
    name: parseRequiredText("Name", draft.name),
    outputSchemaKey: draft.bindings.outputSchema.key.trim(),
    outputSchemaVersion: draft.bindings.outputSchema.version ?? null,
    skills: draft.bindings.skills.map((skill) => ({
      skillKey: skill.key.trim(),
      skillVersion: skill.version ?? null,
    })),
    systemPrompt: parseRequiredText("System prompt", draft.systemPrompt),
  };
}

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
  const createRunMutation = useCreateAgentRun();
  const outputSchemasQuery = useOutputSchemas();
  const skillsQuery = useSkills();
  const mcpServersQuery = useMcpServers();
  const modelConnectionsQuery = useModelConnections({ status: "active" });
  const [draft, setDraft] = useState<AgentAuthoringDraft>(() => createInitialDraft());
  const [sampleInput, setSampleInput] = useState<ValueEntry>(() =>
    createDefaultSampleInputValue(createInitialDraft().inputSchema),
  );
  const [unsupportedRecordIssues, setUnsupportedRecordIssues] = useState<SchemaCodecIssue[]>([]);
  const [runLaunchFeedback, setRunLaunchFeedback] = useState<RunLaunchFeedback | null>(null);

  const outputSchemas = useMemo(
    () => sortByKey(outputSchemasQuery.data?.items ?? []),
    [outputSchemasQuery.data?.items],
  );
  const skills = useMemo(() => sortByKey(skillsQuery.data?.items ?? []), [skillsQuery.data?.items]);
  const mcpServers = useMemo(
    () => sortByKey(mcpServersQuery.data?.items ?? []),
    [mcpServersQuery.data?.items],
  );
  const outputSchemaOptions = useMemo(() => toResourceRefOptions(outputSchemas), [outputSchemas]);
  const skillOptions = useMemo(() => toResourceRefOptions(skills), [skills]);
  const mcpServerOptions = useMemo(() => toResourceRefOptions(mcpServers), [mcpServers]);
  const activeModelConnections = useMemo(
    () => [...(modelConnectionsQuery.data?.items ?? [])].sort(compareModelConnections),
    [modelConnectionsQuery.data?.items],
  );
  const currentArchivedModelConnection = useMemo(() => {
    const currentAgent = isEditing ? agentQuery.data : null;
    if (!currentAgent || currentAgent.modelConnection.status !== "archived") {
      return null;
    }

    return currentAgent.modelConnection;
  }, [agentQuery.data, isEditing]);
  const selectedModelConnection = useMemo(() => {
    return (
      activeModelConnections.find((connection) => String(connection.id) === draft.modelConnectionId) ??
      (currentArchivedModelConnection &&
      String(currentArchivedModelConnection.id) === draft.modelConnectionId
        ? currentArchivedModelConnection
        : null)
    );
  }, [activeModelConnections, currentArchivedModelConnection, draft.modelConnectionId]);
  const selectedModelConnectionIsArchived = selectedModelConnection?.status === "archived";
  const derivedInputSchema = useMemo(
    () => schemaBuilderToJsonSchema(draft.inputSchema),
    [draft.inputSchema],
  );
  const rawInputSchemaJson = useMemo(
    () => stringifyJson(derivedInputSchema),
    [derivedInputSchema],
  );
  const sampleInputPayload = useMemo(() => decodeSampleInputValue(sampleInput), [sampleInput]);
  const rawSampleInputJson = useMemo(
    () => stringifyJson(sampleInputPayload),
    [sampleInputPayload],
  );

  useEffect(() => {
    if (!agentQuery.data) {
      return;
    }

    const hydrated = decodePersistedInputSchema(agentQuery.data);
    setDraft(hydrated.draft);
    setSampleInput(hydrated.sampleInput);
    setUnsupportedRecordIssues(hydrated.issues);
  }, [agentQuery.data]);

  useEffect(() => {
    if (isEditing || !duplicateQuery.data) {
      return;
    }

    const hydrated = decodePersistedInputSchema(duplicateQuery.data, {
      clearArchivedModelConnection: true,
      clearKey: true,
      duplicateName: true,
    });
    setDraft(hydrated.draft);
    setSampleInput(hydrated.sampleInput);
    setUnsupportedRecordIssues(hydrated.issues);
  }, [duplicateQuery.data, isEditing]);

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const hasUnsupportedPersistedRecord = unsupportedRecordIssues.length > 0;

  const updateDraft = <Key extends keyof AgentAuthoringDraft>(
    key: Key,
    value: AgentAuthoringDraft[Key],
  ) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const handleSave = async () => {
    try {
      if (hasUnsupportedPersistedRecord) {
        throw new Error("Unsupported retired input schema shape");
      }

      const payload = buildPayload(draft, derivedInputSchema);

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

  const handleLaunchRun = async () => {
    if (!agentId) {
      setRunLaunchFeedback({
        message: "Save the agent before launching a run.",
        title: "Run launch unavailable",
        variant: "destructive",
      });
      return;
    }

    if (hasUnsupportedPersistedRecord) {
      setRunLaunchFeedback({
        message: "This agent uses an unsupported retired input schema shape.",
        title: "Run launch unavailable",
        variant: "destructive",
      });
      return;
    }

    try {
      const run = await createRunMutation.mutateAsync({
        agentId,
        payload: sampleInputPayload,
        version: agentQuery.data?.version,
      });
      toast.success("Agent run started");
      navigate(`/runs/${run.id}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to start agent run";
      setRunLaunchFeedback({
        message,
        title: "Run launch failed",
        variant: "destructive",
      });
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
            Configure the core prompt, saved model connection, input schema, output schema binding, attached skills and MCP servers, and a structured run-launch input surface.
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
          <Button disabled={isSaving || hasUnsupportedPersistedRecord} size="sm" onClick={handleSave}>
            <Save data-icon="inline-start" />
            Save Agent
          </Button>
        </div>
      </div>

      {hasUnsupportedPersistedRecord ? (
        <Alert data-testid="agent-input-schema-unsupported-record" variant="destructive">
          <AlertTitle>Unsupported retired input schema shape</AlertTitle>
          <AlertDescription>
            <p>
              This persisted agent cannot be edited in the structured authoring flow because its
              input schema does not decode into the supported shared schema model.
            </p>
            <ul className="list-disc pl-5">
              {unsupportedRecordIssues.map((issue) => (
                <li key={`${issue.field}-${issue.issue}`}>{`${issue.field}: ${issue.issue}`}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}

      <Tabs defaultValue="configuration" data-testid="agents-editor-tabs">
        <TabsList className="h-8">
          <TabsTrigger className="text-xs" value="configuration">
            Configuration
          </TabsTrigger>
          <TabsTrigger className="text-xs" value="run">
            Run
          </TabsTrigger>
        </TabsList>

        <TabsContent forceMount value="configuration">
          <Card>
            <CardHeader>
              <CardTitle>Agent details</CardTitle>
              <CardDescription>
                Keys are immutable after creation, while the model connection, prompt, schema, and bindings remain editable.
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
                    value={draft.key}
                    onChange={(event) => updateDraft("key", event.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="agent-name">Name</Label>
                  <Input
                    id="agent-name"
                    aria-label="Name"
                    disabled={isSaving}
                    value={draft.name}
                    onChange={(event) => updateDraft("name", event.target.value)}
                  />
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="agent-model-connection">Model Connection</Label>
                  <Select
                    disabled={
                      isSaving ||
                      modelConnectionsQuery.isPending ||
                      (activeModelConnections.length === 0 && !currentArchivedModelConnection)
                    }
                    value={draft.modelConnectionId || UNSELECTED_MODEL_CONNECTION}
                    onValueChange={(value) =>
                      updateDraft(
                        "modelConnectionId",
                        value === UNSELECTED_MODEL_CONNECTION ? "" : value,
                      )
                    }
                  >
                    <SelectTrigger aria-label="Model Connection" id="agent-model-connection">
                      <SelectValue placeholder="Select a model connection" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        <SelectItem disabled value={UNSELECTED_MODEL_CONNECTION}>
                          Select a model connection
                        </SelectItem>
                        {currentArchivedModelConnection ? (
                          <SelectItem disabled value={String(currentArchivedModelConnection.id)}>
                            {formatModelConnectionLabel(currentArchivedModelConnection)} (archived current selection)
                          </SelectItem>
                        ) : null}
                        {activeModelConnections.map((connection) => (
                          <SelectItem key={connection.id} value={String(connection.id)}>
                            {formatModelConnectionLabel(connection)}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                  <p className="text-sm text-muted-foreground">
                    {modelConnectionsQuery.isError
                      ? modelConnectionsQuery.error instanceof Error
                        ? modelConnectionsQuery.error.message
                        : "Failed to load active model connections."
                      : selectedModelConnection
                        ? `${formatModelConnectionMeta(selectedModelConnection)}${selectedModelConnectionIsArchived ? " · archived" : ""}`
                        : activeModelConnections.length > 0
                          ? "Choose an active model connection for this agent."
                          : "No active model connections are available yet."}
                  </p>
                </div>
                <ResourceRefSelect
                  description="Bind the agent to one published output schema without typing a versioned ref string."
                  disabled={isSaving}
                  label="Output schema binding"
                  options={outputSchemaOptions}
                  resourceLabel="Output schema"
                  resourcePlaceholder="Select an output schema"
                  searchPlaceholder="Search output schemas..."
                  value={draft.bindings.outputSchema.key ? draft.bindings.outputSchema : null}
                  onChange={(nextValue) =>
                    setDraft((current) => ({
                      ...current,
                      bindings: {
                        ...current.bindings,
                        outputSchema: nextValue ? cloneResourceRef(nextValue) : { key: "", version: null },
                      },
                    }))
                  }
                />
              </div>

              {selectedModelConnectionIsArchived ? (
                <Alert>
                  <AlertTitle>Archived model connection in use</AlertTitle>
                  <AlertDescription>
                    This agent still points to an archived connection. You can keep the current binding on edit, but archived connections are not available as new selections.
                  </AlertDescription>
                </Alert>
              ) : null}

              <div className="space-y-2">
                <Label htmlFor="agent-description">Description</Label>
                <Textarea
                  id="agent-description"
                  aria-label="Description"
                  disabled={isSaving}
                  rows={3}
                  value={draft.description}
                  onChange={(event) => updateDraft("description", event.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="agent-system-prompt">System Prompt</Label>
                <Textarea
                  id="agent-system-prompt"
                  aria-label="System Prompt"
                  disabled={isSaving}
                  rows={10}
                  value={draft.systemPrompt}
                  onChange={(event) => updateDraft("systemPrompt", event.target.value)}
                />
              </div>

              {!hasUnsupportedPersistedRecord ? (
                <div className="flex flex-col gap-4">
                  <SchemaComposer
                    label="Input schema"
                    node={draft.inputSchema}
                    onChange={(nextSchema) => {
                      updateDraft("inputSchema", nextSchema);
                      setSampleInput(createDefaultSampleInputValue(nextSchema));
                    }}
                  />
                  <div className="grid gap-4 xl:grid-cols-2">
                    <Card>
                      <CardHeader>
                        <CardTitle>Exact raw schema JSON</CardTitle>
                        <CardDescription>
                          Read-only canonical JSON derived from the same schema object used in the save payload.
                        </CardDescription>
                      </CardHeader>
                      <CardContent>
                        <ExactJsonPreview
                          ariaLabel="Exact raw schema JSON"
                          data-testid="agent-input-schema-raw-json"
                          value={rawInputSchemaJson}
                        />
                      </CardContent>
                    </Card>
                    <Card>
                      <CardHeader>
                        <CardTitle>Sample input</CardTitle>
                        <CardDescription>
                          Derived sample input stays aligned with the current schema builder state.
                        </CardDescription>
                      </CardHeader>
                      <CardContent>
                        <ExactJsonPreview
                          ariaLabel="Sample input"
                          data-testid="agent-input-schema-preview"
                          value={rawSampleInputJson}
                        />
                      </CardContent>
                    </Card>
                  </div>
                </div>
              ) : null}

              <div className="space-y-2">
                <div className="space-y-2">
                  <Label htmlFor="agent-budget-usd">Budget USD</Label>
                  <Input
                    id="agent-budget-usd"
                    aria-label="Budget USD"
                    disabled={isSaving}
                    value={draft.budgetUsd}
                    onChange={(event) => updateDraft("budgetUsd", event.target.value)}
                  />
                </div>
              </div>

              <ResourceMultiRefSelect
                addLabel="Add skill binding"
                description="Attach one or more published skills without editing newline-delimited versioned ref text."
                disabled={isSaving}
                label="Skill bindings"
                options={skillOptions}
                resourceLabel="Skill"
                resourcePlaceholder="Select a skill"
                searchPlaceholder="Search skills..."
                value={draft.bindings.skills}
                onChange={(nextValue) =>
                  setDraft((current) => ({
                    ...current,
                    bindings: {
                      ...current.bindings,
                      skills: cloneResourceRefs(nextValue),
                    },
                  }))
                }
              />

              <ResourceMultiRefSelect
                addLabel="Add MCP server binding"
                description="Attach one or more MCP servers through structured bindings instead of raw versioned ref text."
                disabled={isSaving}
                label="MCP server bindings"
                options={mcpServerOptions}
                resourceLabel="MCP server"
                resourcePlaceholder="Select an MCP server"
                searchPlaceholder="Search MCP servers..."
                value={draft.bindings.mcpServers}
                onChange={(nextValue) =>
                  setDraft((current) => ({
                    ...current,
                    bindings: {
                      ...current.bindings,
                      mcpServers: cloneResourceRefs(nextValue),
                    },
                  }))
                }
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent forceMount value="run">
          <Card data-testid="agent-run-panel">
            <CardHeader>
              <CardTitle>Launch run</CardTitle>
              <CardDescription>
                Launch the current saved agent version with structured input, then continue in the shared run detail view.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4">
              {!isEditing ? (
                <Alert data-testid="agent-run-panel-unavailable" variant="destructive">
                  <AlertTitle>Run launch unavailable</AlertTitle>
                  <AlertDescription>Save the agent before launching a run.</AlertDescription>
                </Alert>
              ) : null}
              {runLaunchFeedback ? (
                <Alert data-testid="agent-run-panel-feedback" variant={runLaunchFeedback.variant}>
                  <AlertTitle>{runLaunchFeedback.title}</AlertTitle>
                  <AlertDescription>{runLaunchFeedback.message}</AlertDescription>
                </Alert>
              ) : null}

              {!hasUnsupportedPersistedRecord ? (
                <div className="grid gap-4 xl:grid-cols-2">
                  <div data-testid="agent-run-panel-input-form">
                    <SchemaForm
                      description="Fill the run input through the shared schema-driven form instead of editing JSON directly."
                      disabled={!isEditing || createRunMutation.isPending}
                      label="Run input"
                      schema={draft.inputSchema}
                      value={sampleInput}
                      onChange={setSampleInput}
                    />
                  </div>
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Exact raw run-input JSON</CardTitle>
                      <CardDescription>
                        Read-only canonical JSON from the same decoded payload used when launching the run.
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <ExactJsonPreview
                        ariaLabel="Exact raw run-input JSON"
                        data-testid="agent-run-panel-input-raw-json"
                        value={rawSampleInputJson}
                      />
                    </CardContent>
                  </Card>
                </div>
              ) : null}

              <div className="flex justify-end">
                <Button
                  data-testid="agent-run-panel-launch"
                  disabled={!isEditing || createRunMutation.isPending || hasUnsupportedPersistedRecord}
                  size="sm"
                  variant="outline"
                  onClick={() => void handleLaunchRun()}
                >
                  <PlayCircle data-icon="inline-start" />
                  Launch Run
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
