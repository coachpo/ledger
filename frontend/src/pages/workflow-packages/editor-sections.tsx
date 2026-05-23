import {
  AlertCircle,
  Download,
  FileCheck2,
  FileUp,
  Loader2,
  Plus,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";

import { SchemaComposer } from "@/components/platform-authoring/schema-composer/schema-composer";
import { SearchableSelect } from "@/components/shared/searchable-select";
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
import { Checkbox } from "@/components/ui/checkbox";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { exportWorkflowPackageUrl } from "@/lib/api/workflow-packages";
import { formatDateTime } from "@/lib/format";
import {
  createPackageAgentDraft,
  createPackageCapabilityProfileDraft,
  createPackageMcpServerDraft,
  createPackageOutputSchemaDraft,
  workflowPackageDraftToManifestSource,
  workflowPackageWorkflowsFromYaml,
  workflowPackageWorkflowsToYaml,
  type PackageAgentDraft,
  type PackageCapabilityProfileDraft,
  type PackageMcpServerDraft,
  type PackageOutputSchemaDraft,
  type WorkflowPackageDraft,
  type WorkflowPackageEditorIssue,
} from "@/lib/platform-authoring/workflow-packages/manifest";
import type { WorkflowPackageSecretBindingRead } from "@/lib/types/workflow-package";

import {
  issueMessagesForPrefix,
  type DiagnosticTarget,
  type WorkflowPackageEditorTab,
} from "./editor-sections.shared";

const agentFormSchema = z.object({
  description: z.string(),
  key: z.string().min(1, "Agent key is required."),
  modelConnection: z.string().min(1, "Model connection key is required."),
  name: z.string().min(1, "Agent name is required."),
  outputSchema: z.string().min(1, "Output schema key is required."),
  systemPrompt: z.string().min(1, "System prompt is required."),
  timeoutSeconds: z.string().min(1, "Timeout seconds is required."),
});

type AgentFormValues = z.infer<typeof agentFormSchema>;

function agentIndexFromPath(path: string): number | null {
  const match = /^spec\.agents\[(\d+)]/.exec(path);
  return match ? Number.parseInt(match[1], 10) : null;
}

function issueMessageForField(
  issues: readonly WorkflowPackageEditorIssue[],
  field: string,
) {
  return issues.find((issue) => issue.field === field)?.issue ?? null;
}

function fieldNameFromAgentPath(field: string): keyof AgentFormValues | null {
  const match = /^spec\.agents\[\d+]\.(?<name>[A-Za-z][A-Za-z0-9]*)/.exec(
    field,
  );
  const name = match?.groups?.name;
  if (
    name === "description" ||
    name === "key" ||
    name === "modelConnection" ||
    name === "name" ||
    name === "outputSchema" ||
    name === "systemPrompt" ||
    name === "timeoutSeconds"
  ) {
    return name;
  }
  return null;
}

function agentFormValues(agent: PackageAgentDraft): AgentFormValues {
  return {
    description: agent.description,
    key: agent.key,
    modelConnection: agent.modelConnection,
    name: agent.name,
    outputSchema: agent.outputSchema,
    systemPrompt: agent.systemPrompt,
    timeoutSeconds: agent.timeoutSeconds,
  };
}

function sortedSecretBindings(
  bindings: readonly WorkflowPackageSecretBindingRead[],
): WorkflowPackageSecretBindingRead[] {
  return [...bindings].sort((left, right) => left.key.localeCompare(right.key));
}

export function EditorSkeleton() {
  return (
    <div className="space-y-4 p-4">
      <Skeleton className="h-28 w-full" />
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-72 w-full" />
    </div>
  );
}

export function ManifestBlockingState({
  errors,
  loading,
  onRetry,
  title,
}: {
  errors: readonly string[];
  loading: boolean;
  onRetry: () => void;
  title: string;
}) {
  return (
    <Card
      className="border-destructive/30 bg-destructive/5 shadow-sm"
      data-testid="workflow-package-manifest-blocker"
    >
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-destructive">
          <AlertCircle className="size-5" />
          {title}
        </CardTitle>
        <CardDescription>
          Manifest content must load and parse cleanly before package resources
          can be edited.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Alert variant="destructive" role="alert">
          <AlertCircle />
          <AlertTitle>Editor locked</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-5">
              {errors.map((error, index) => (
                <li key={`${index}-${error}`}>{error}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
        <Button
          disabled={loading}
          type="button"
          variant="outline"
          onClick={onRetry}
        >
          {loading ? (
            <Loader2 className="animate-spin" data-icon="inline-start" />
          ) : null}
          Retry manifest load
        </Button>
      </CardContent>
    </Card>
  );
}

function issueForField(
  issues: readonly WorkflowPackageEditorIssue[],
  field: string,
) {
  return issues.find((issue) => issue.field === field)?.issue ?? null;
}

function FieldMessage({ message }: { message: string | null }) {
  return message ? (
    <p className="text-sm text-destructive" role="alert">
      {message}
    </p>
  ) : null;
}

function ResourceChecks({
  issues,
  tab,
}: {
  issues: readonly WorkflowPackageEditorIssue[];
  tab: WorkflowPackageEditorTab;
}) {
  const tabIssues = issues.filter((issue) => issue.tab === tab);
  if (tabIssues.length === 0) {
    return null;
  }
  return (
    <Alert variant="destructive" data-testid={`${tab}-validation-feedback`}>
      <FileCheck2 />
      <AlertTitle>Validation needs attention</AlertTitle>
      <AlertDescription>
        <ul className="list-disc pl-5">
          {tabIssues.map((issue) => (
            <li key={`${issue.field}-${issue.issue}`}>
              {issue.field}: {issue.issue}
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

function updateArrayItem<T>(
  items: readonly T[],
  index: number,
  updater: (item: T) => T,
): T[] {
  return items.map((item, itemIndex) =>
    itemIndex === index ? updater(item) : item,
  );
}

function toggleString(
  values: readonly string[],
  value: string,
  checked: boolean,
) {
  if (checked) {
    return values.includes(value) ? [...values] : [...values, value];
  }
  return values.filter((entry) => entry !== value);
}

export function OverviewEditor({
  draft,
  issues,
  isNew,
  onChange,
}: {
  draft: WorkflowPackageDraft;
  issues: readonly WorkflowPackageEditorIssue[];
  isNew: boolean;
  onChange: (draft: WorkflowPackageDraft) => void;
}) {
  const setMetadata = (
    key: keyof WorkflowPackageDraft["metadata"],
    value: string,
  ) => {
    onChange({ ...draft, metadata: { ...draft.metadata, [key]: value } });
  };
  return (
    <Card className="border-border/70 bg-card/80 shadow-sm backdrop-blur">
      <CardHeader>
        <CardTitle>Package overview</CardTitle>
        <CardDescription>Package identity and inputs.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="metadata-key">Local package key</Label>
          <Input
            id="metadata-key"
            data-field="metadata.key"
            aria-label="Package key"
            readOnly={!isNew}
            value={draft.metadata.key}
            onChange={
              isNew
                ? (event) => setMetadata("key", event.target.value)
                : undefined
            }
          />
          <FieldMessage message={issueForField(issues, "metadata.key")} />
          {isNew ? null : (
            <p className="text-sm text-muted-foreground">
              Existing package keys are immutable.
            </p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor="metadata-name">Name</Label>
          <Input
            id="metadata-name"
            data-field="metadata.name"
            aria-label="Package name"
            value={draft.metadata.name}
            onChange={(event) => setMetadata("name", event.target.value)}
          />
          <FieldMessage message={issueForField(issues, "metadata.name")} />
        </div>
        <div className="space-y-2 md:col-span-2">
          <Label htmlFor="metadata-description">Description</Label>
          <Textarea
            id="metadata-description"
            aria-label="Package description"
            rows={3}
            value={draft.metadata.description}
            onChange={(event) => setMetadata("description", event.target.value)}
          />
        </div>
        <div className="space-y-2 md:col-span-2">
          <Label>Package input schema</Label>
          <SchemaComposer
            label="Package inputs"
            node={draft.spec.inputs}
            onChange={(inputs) =>
              onChange({ ...draft, spec: { ...draft.spec, inputs } })
            }
          />
        </div>
      </CardContent>
    </Card>
  );
}

function AgentSheet(props: {
  agent: PackageAgentDraft | null;
  agentIndex: number | null;
  capabilityProfileKeys: string[];
  issues: readonly WorkflowPackageEditorIssue[];
  mcpServerKeys: string[];
  modelConnectionOptions: {
    description?: string;
    label: string;
    value: string;
  }[];
  open: boolean;
  outputSchemaKeys: string[];
  targetField: string | null;
  onChange: (agent: PackageAgentDraft) => void;
  onOpenChange: (open: boolean) => void;
}) {
  const {
    agent,
    agentIndex,
    capabilityProfileKeys,
    issues,
    mcpServerKeys,
    modelConnectionOptions,
    onChange,
    onOpenChange,
    open,
    outputSchemaKeys,
    targetField,
  } = props;
  const form = useForm<AgentFormValues>({
    resolver: zodResolver(agentFormSchema),
    values: agent ? agentFormValues(agent) : undefined,
  });

  useEffect(() => {
    form.clearErrors();
    if (agentIndex === null) {
      return;
    }
    for (const issue of issues) {
      const fieldName = fieldNameFromAgentPath(issue.field);
      if (fieldName && issue.field.startsWith(`spec.agents[${agentIndex}].`)) {
        form.setError(fieldName, { message: issue.issue, type: "manual" });
      }
    }
  }, [agentIndex, form, issues]);

  useEffect(() => {
    if (!open || !targetField) {
      return;
    }
    window.setTimeout(() => {
      document
        .querySelector<HTMLElement>(`[data-field="${CSS.escape(targetField)}"]`)
        ?.focus();
    }, 75);
  }, [open, targetField]);

  if (!agent || agentIndex === null) {
    return null;
  }

  const fieldPath = (field: keyof AgentFormValues) =>
    `spec.agents[${agentIndex}].${field}`;
  const setAgent = <Key extends keyof PackageAgentDraft>(
    key: Key,
    value: PackageAgentDraft[Key],
  ) => {
    onChange({ ...agent, [key]: value });
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        className="w-full overflow-y-auto sm:max-w-3xl"
        data-testid={`package-agent-sheet-${agentIndex}`}
      >
        <SheetHeader>
          <SheetTitle>Agent editor</SheetTitle>
          <SheetDescription>Edit this package manifest entry.</SheetDescription>
        </SheetHeader>
        <Form {...form}>
          <form
            className="grid gap-4 px-4 pb-4"
            onSubmit={(event) => event.preventDefault()}
          >
            <div className="grid gap-4 md:grid-cols-2">
              <FormField
                control={form.control}
                name="key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Local key</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        data-field={fieldPath("key")}
                        aria-label="Agent local key"
                        onChange={(event) => {
                          field.onChange(event);
                          setAgent("key", event.target.value);
                        }}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        data-field={fieldPath("name")}
                        aria-label="Agent name"
                        onChange={(event) => {
                          field.onChange(event);
                          setAgent("name", event.target.value);
                        }}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      data-field={fieldPath("description")}
                      aria-label="Agent description"
                      onChange={(event) => {
                        field.onChange(event);
                        setAgent("description", event.target.value);
                      }}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid gap-4 md:grid-cols-2">
              <FormField
                control={form.control}
                name="modelConnection"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Model connection key</FormLabel>
                    <FormControl>
                      <div
                        data-field={fieldPath("modelConnection")}
                        tabIndex={-1}
                      >
                        <SearchableSelect
                          options={modelConnectionOptions}
                          placeholder="Select global model connection"
                          searchPlaceholder="Search model connections..."
                          value={field.value}
                          onValueChange={(value) => {
                            field.onChange(value);
                            setAgent("modelConnection", value);
                          }}
                        />
                      </div>
                    </FormControl>
                    <FormDescription>Referenced by stable key.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="outputSchema"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Output schema local key</FormLabel>
                    <FormControl>
                      <Select
                        value={field.value || "__none__"}
                        onValueChange={(value) => {
                          const nextValue = value === "__none__" ? "" : value;
                          field.onChange(nextValue);
                          setAgent("outputSchema", nextValue);
                        }}
                      >
                        <SelectTrigger
                          data-field={fieldPath("outputSchema")}
                          aria-label="Output schema local key"
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__none__">
                            Select local schema
                          </SelectItem>
                          {outputSchemaKeys.map((key) => (
                            <SelectItem key={key} value={key}>
                              {key}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <FormField
                control={form.control}
                name="timeoutSeconds"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Timeout seconds</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        data-field={fieldPath("timeoutSeconds")}
                        aria-label="Timeout seconds"
                        onChange={(event) => {
                          field.onChange(event);
                          setAgent("timeoutSeconds", event.target.value);
                        }}
                      />
                    </FormControl>
                    <FormDescription>
                      Used for launch planning only.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <MultiKeyPicker
                label="Capability profile local keys"
                keys={capabilityProfileKeys}
                selectedKeys={agent.capabilityProfiles}
                onChange={(nextKeys) =>
                  setAgent("capabilityProfiles", nextKeys)
                }
              />
              <MultiKeyPicker
                label="Private MCP local keys"
                keys={mcpServerKeys}
                selectedKeys={agent.mcpServers}
                onChange={(nextKeys) => setAgent("mcpServers", nextKeys)}
              />
            </div>
            <FormField
              control={form.control}
              name="systemPrompt"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>System prompt</FormLabel>
                  <FormControl>
                    <Textarea
                      {...field}
                      data-field={fieldPath("systemPrompt")}
                      aria-label="System prompt"
                      rows={7}
                      onChange={(event) => {
                        field.onChange(event);
                        setAgent("systemPrompt", event.target.value);
                      }}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div
              className="space-y-2"
              data-field={`spec.agents[${agentIndex}].inputSchema`}
              tabIndex={-1}
            >
              <Label>Input schema</Label>
              <SchemaComposer
                label="Agent input schema"
                node={agent.inputSchema}
                onChange={(inputSchema) => setAgent("inputSchema", inputSchema)}
              />
              <FieldMessage
                message={issueMessageForField(
                  issues,
                  `spec.agents[${agentIndex}].inputSchema`,
                )}
              />
            </div>
          </form>
        </Form>
        <SheetFooter>
          <Button type="button" onClick={() => onOpenChange(false)}>
            Close agent editor
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

function MultiKeyPicker({
  keys,
  label,
  onChange,
  selectedKeys,
}: {
  keys: string[];
  label: string;
  onChange: (keys: string[]) => void;
  selectedKeys: string[];
}) {
  return (
    <div className="space-y-2 rounded-lg border p-3">
      <Label>{label}</Label>
      {keys.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Create local resources before binding them.
        </p>
      ) : null}
      <div className="grid gap-2">
        {keys.map((key) => (
          <label
            key={key}
            className="flex cursor-pointer items-center gap-2 text-sm"
          >
            <Checkbox
              checked={selectedKeys.includes(key)}
              onCheckedChange={(checked) =>
                onChange(toggleString(selectedKeys, key, checked === true))
              }
            />
            <span className="font-mono text-xs">{key}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

export function AgentsTab(props: {
  diagnosticTarget: DiagnosticTarget;
  draft: WorkflowPackageDraft;
  issues: readonly WorkflowPackageEditorIssue[];
  modelConnectionOptions: {
    description?: string;
    label: string;
    value: string;
  }[];
  onChange: (draft: WorkflowPackageDraft) => void;
}) {
  const { diagnosticTarget, draft, issues, modelConnectionOptions, onChange } =
    props;
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const outputSchemaKeys = draft.spec.outputSchemas
    .map((schema) => schema.key)
    .filter(Boolean);
  const capabilityProfileKeys = draft.spec.capabilityProfiles
    .map((profile) => profile.key)
    .filter(Boolean);
  const mcpServerKeys = draft.spec.mcpServers
    .map((server) => server.key)
    .filter(Boolean);
  const editingAgent =
    editingIndex === null ? null : (draft.spec.agents[editingIndex] ?? null);
  const updateAgents = (agents: PackageAgentDraft[]) =>
    onChange({ ...draft, spec: { ...draft.spec, agents } });

  useEffect(() => {
    if (diagnosticTarget?.tab !== "agents") {
      return;
    }
    const nextIndex = agentIndexFromPath(diagnosticTarget.field);
    if (nextIndex !== null && draft.spec.agents[nextIndex]) {
      setEditingIndex(nextIndex);
    }
  }, [diagnosticTarget, draft.spec.agents]);

  return (
    <Card
      className="border-border/70 bg-card/80 shadow-sm backdrop-blur"
      data-testid="workflow-package-agents-tab"
    >
      <CardHeader className="border-b pb-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle>Package-local agents</CardTitle>
            <CardDescription>Manifest-local agent entries.</CardDescription>
          </div>
          <Button
            type="button"
            size="sm"
            onClick={() => {
              updateAgents([
                ...draft.spec.agents,
                createPackageAgentDraft({
                  outputSchema: outputSchemaKeys[0] ?? "",
                }),
              ]);
              setEditingIndex(draft.spec.agents.length);
            }}
          >
            <Plus data-icon="inline-start" />
            Add Agent
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        <ResourceChecks issues={issues} tab="agents" />
        {draft.spec.agents.length === 0 ? (
          <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
            No package-local agents yet.
          </div>
        ) : null}
        <div className="grid gap-3">
          {draft.spec.agents.map((agent, index) => (
            <div
              key={`${agent.key}-${index}`}
              className="flex flex-col gap-3 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between"
              data-testid={`package-agent-row-${agent.key}`}
            >
              <div className="min-w-0 space-y-1">
                <p className="font-medium">{agent.name || "Untitled agent"}</p>
                <p className="break-all font-mono text-xs text-muted-foreground">
                  {agent.key || "missing_key"}
                </p>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">
                    model: {agent.modelConnection || "missing"}
                  </Badge>
                  <Badge variant="outline">
                    schema: {agent.outputSchema || "missing"}
                  </Badge>
                  <Badge variant="secondary">
                    {agent.capabilityProfiles.length} profiles
                  </Badge>
                  <Badge variant="secondary">
                    {agent.mcpServers.length} MCP
                  </Badge>
                </div>
              </div>
              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  aria-label={`Edit agent ${agent.name}`}
                  onClick={() => setEditingIndex(index)}
                >
                  Edit
                </Button>
                <Button
                  type="button"
                  size="icon"
                  variant="outline"
                  aria-label={`Remove agent ${agent.name}`}
                  onClick={() =>
                    updateAgents(
                      draft.spec.agents.filter(
                        (_, itemIndex) => itemIndex !== index,
                      ),
                    )
                  }
                >
                  <Trash2 />
                </Button>
              </div>
            </div>
          ))}
        </div>
        <AgentSheet
          agent={editingAgent}
          agentIndex={editingIndex}
          capabilityProfileKeys={capabilityProfileKeys}
          issues={issues}
          mcpServerKeys={mcpServerKeys}
          modelConnectionOptions={modelConnectionOptions}
          open={editingIndex !== null}
          outputSchemaKeys={outputSchemaKeys}
          targetField={
            diagnosticTarget?.tab === "agents" ? diagnosticTarget.field : null
          }
          onOpenChange={(open) => (!open ? setEditingIndex(null) : undefined)}
          onChange={(agent) =>
            editingIndex !== null
              ? updateAgents(
                  updateArrayItem(draft.spec.agents, editingIndex, () => agent),
                )
              : undefined
          }
        />
      </CardContent>
    </Card>
  );
}

export function OutputSchemasTab({
  draft,
  issues,
  onChange,
}: {
  draft: WorkflowPackageDraft;
  issues: readonly WorkflowPackageEditorIssue[];
  onChange: (draft: WorkflowPackageDraft) => void;
}) {
  const updateSchemas = (outputSchemas: PackageOutputSchemaDraft[]) =>
    onChange({ ...draft, spec: { ...draft.spec, outputSchemas } });
  return (
    <Card
      className="border-border/70 bg-card/80 shadow-sm backdrop-blur"
      data-testid="workflow-package-output-schemas-tab"
    >
      <CardHeader className="border-b pb-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle>Package-local output schemas</CardTitle>
            <CardDescription>Local schema keys and shapes.</CardDescription>
          </div>
          <Button
            type="button"
            size="sm"
            onClick={() =>
              updateSchemas([
                ...draft.spec.outputSchemas,
                createPackageOutputSchemaDraft(),
              ])
            }
          >
            <Plus data-icon="inline-start" />
            Add Schema
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        <ResourceChecks issues={issues} tab="output-schemas" />
        {draft.spec.outputSchemas.length === 0 ? (
          <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
            No package-local output schemas yet.
          </div>
        ) : null}
        <div className="grid gap-4 xl:grid-cols-2">
          {draft.spec.outputSchemas.map((schema, index) => (
            <Card
              key={`${schema.key}-${index}`}
              className="bg-background/60"
              data-field={`spec.outputSchemas[${index}]`}
              tabIndex={-1}
              data-testid={`package-output-schema-card-${schema.key}`}
            >
              <CardHeader>
                <CardTitle>{schema.name || "Untitled schema"}</CardTitle>
                <CardDescription className="font-mono text-xs">
                  {schema.key || "missing_key"}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label>Local key</Label>
                    <Input
                      aria-label={`Output schema ${index + 1} local key`}
                      data-field={`spec.outputSchemas[${index}].key`}
                      value={schema.key}
                      onChange={(event) =>
                        updateSchemas(
                          updateArrayItem(
                            draft.spec.outputSchemas,
                            index,
                            (item) => ({ ...item, key: event.target.value }),
                          ),
                        )
                      }
                    />
                    <FieldMessage
                      message={
                        issueMessageForField(
                          issues,
                          `spec.outputSchemas[${index}].key`,
                        ) ??
                        issueMessageForField(
                          issues,
                          `spec.outputSchemas[${index}]`,
                        )
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Name</Label>
                    <Input
                      aria-label={`Output schema ${index + 1} name`}
                      value={schema.name}
                      onChange={(event) =>
                        updateSchemas(
                          updateArrayItem(
                            draft.spec.outputSchemas,
                            index,
                            (item) => ({ ...item, name: event.target.value }),
                          ),
                        )
                      }
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>Description</Label>
                  <Input
                    aria-label={`Output schema ${index + 1} description`}
                    value={schema.description}
                    onChange={(event) =>
                      updateSchemas(
                        updateArrayItem(
                          draft.spec.outputSchemas,
                          index,
                          (item) => ({
                            ...item,
                            description: event.target.value,
                          }),
                        ),
                      )
                    }
                  />
                </div>
                <SchemaComposer
                  label="Output schema root"
                  node={schema.jsonSchema}
                  onChange={(jsonSchema) =>
                    updateSchemas(
                      updateArrayItem(
                        draft.spec.outputSchemas,
                        index,
                        (item) => ({ ...item, jsonSchema }),
                      ),
                    )
                  }
                />
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    updateSchemas(
                      draft.spec.outputSchemas.filter(
                        (_, itemIndex) => itemIndex !== index,
                      ),
                    )
                  }
                >
                  Remove schema
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export function CapabilityProfilesTab(props: {
  draft: WorkflowPackageDraft;
  issues: readonly WorkflowPackageEditorIssue[];
  onChange: (draft: WorkflowPackageDraft) => void;
  tools: { description: string; displayName: string; key: string }[];
  toolsError: string | null;
  toolsLoading: boolean;
}) {
  const { draft, issues, onChange, tools, toolsError, toolsLoading } = props;
  const updateProfiles = (
    capabilityProfiles: PackageCapabilityProfileDraft[],
  ) => onChange({ ...draft, spec: { ...draft.spec, capabilityProfiles } });
  return (
    <Card
      className="border-border/70 bg-card/80 shadow-sm backdrop-blur"
      data-testid="workflow-package-capability-profiles-tab"
    >
      <CardHeader className="border-b pb-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle>Capability profiles</CardTitle>
            <CardDescription>Local profiles and tool keys.</CardDescription>
          </div>
          <Button
            type="button"
            size="sm"
            onClick={() =>
              updateProfiles([
                ...draft.spec.capabilityProfiles,
                createPackageCapabilityProfileDraft(),
              ])
            }
          >
            <Plus data-icon="inline-start" />
            Add Profile
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        <ResourceChecks issues={issues} tab="capability-profiles" />
        {toolsError ? (
          <Alert variant="destructive">
            <AlertTitle>Tool catalog unavailable</AlertTitle>
            <AlertDescription>{toolsError}</AlertDescription>
          </Alert>
        ) : null}
        {draft.spec.capabilityProfiles.map((profile, index) => (
          <Card
            key={`${profile.key}-${index}`}
            className="bg-background/60"
            data-field={`spec.capabilityProfiles[${index}]`}
            tabIndex={-1}
            data-testid={`package-capability-profile-card-${profile.key}`}
          >
            <CardHeader>
              <CardTitle>{profile.name || "Untitled profile"}</CardTitle>
              <CardDescription className="font-mono text-xs">
                {profile.key || "missing_key"}
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
              <div className="space-y-3">
                <div className="space-y-2">
                  <Label>Local key</Label>
                  <Input
                    aria-label={`Capability profile ${index + 1} local key`}
                    data-field={`spec.capabilityProfiles[${index}].key`}
                    value={profile.key}
                    onChange={(event) =>
                      updateProfiles(
                        updateArrayItem(
                          draft.spec.capabilityProfiles,
                          index,
                          (item) => ({ ...item, key: event.target.value }),
                        ),
                      )
                    }
                  />
                  <FieldMessage
                    message={issueMessageForField(
                      issues,
                      `spec.capabilityProfiles[${index}].key`,
                    )}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Name</Label>
                  <Input
                    aria-label={`Capability profile ${index + 1} name`}
                    value={profile.name}
                    onChange={(event) =>
                      updateProfiles(
                        updateArrayItem(
                          draft.spec.capabilityProfiles,
                          index,
                          (item) => ({ ...item, name: event.target.value }),
                        ),
                      )
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label>Description</Label>
                  <Textarea
                    aria-label={`Capability profile ${index + 1} description`}
                    rows={3}
                    value={profile.description}
                    onChange={(event) =>
                      updateProfiles(
                        updateArrayItem(
                          draft.spec.capabilityProfiles,
                          index,
                          (item) => ({
                            ...item,
                            description: event.target.value,
                          }),
                        ),
                      )
                    }
                  />
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    updateProfiles(
                      draft.spec.capabilityProfiles.filter(
                        (_, itemIndex) => itemIndex !== index,
                      ),
                    )
                  }
                >
                  Remove profile
                </Button>
              </div>
              <div className="space-y-2">
                <Label>Global tool catalog</Label>
                <div
                  data-field={`spec.capabilityProfiles[${index}].toolKeys[0]`}
                  tabIndex={-1}
                >
                  <Command
                    className="rounded-lg border"
                    data-testid="capability-tool-command"
                  >
                    <CommandInput placeholder="Search server-declared tools..." />
                    <CommandList>
                      <CommandEmpty>
                        {toolsLoading
                          ? "Loading tools..."
                          : "No catalog tools match."}
                      </CommandEmpty>
                      <CommandGroup>
                        {tools.map((tool) => (
                          <CommandItem
                            className="data-[selected=true]:bg-transparent data-[selected=true]:text-foreground data-[selected=true]:hover:bg-accent data-[selected=true]:hover:text-accent-foreground"
                            key={tool.key}
                            value={`${tool.displayName} ${tool.key} ${tool.description}`}
                            onSelect={() =>
                              updateProfiles(
                                updateArrayItem(
                                  draft.spec.capabilityProfiles,
                                  index,
                                  (item) => ({
                                    ...item,
                                    toolKeys: toggleString(
                                      item.toolKeys,
                                      tool.key,
                                      !item.toolKeys.includes(tool.key),
                                    ),
                                  }),
                                ),
                              )
                            }
                          >
                            <Checkbox
                              aria-label={`Select tool ${tool.displayName}`}
                              checked={profile.toolKeys.includes(tool.key)}
                              onCheckedChange={(checked) =>
                                updateProfiles(
                                  updateArrayItem(
                                    draft.spec.capabilityProfiles,
                                    index,
                                    (item) => ({
                                      ...item,
                                      toolKeys: toggleString(
                                        item.toolKeys,
                                        tool.key,
                                        checked === true,
                                      ),
                                    }),
                                  ),
                                )
                              }
                            />
                            <div className="min-w-0">
                              <p className="truncate text-sm">
                                {tool.displayName}
                              </p>
                              <p className="break-all text-xs text-muted-foreground">
                                {tool.key}
                              </p>
                            </div>
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </div>
                <FieldMessage
                  message={
                    issueMessagesForPrefix(
                      issues,
                      `spec.capabilityProfiles[${index}].toolKeys`,
                    )[0]?.issue ??
                    issueMessagesForPrefix(
                      issues,
                      `spec.capabilityProfiles.${profile.key}.toolKeys`,
                    )[0]?.issue ??
                    null
                  }
                />
                <div className="flex flex-wrap gap-2">
                  {profile.toolKeys.map((key) => (
                    <Badge key={key} variant="secondary">
                      {key}
                    </Badge>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
        {draft.spec.capabilityProfiles.length === 0 ? (
          <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
            No local capability profiles yet.
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function PrivateMcpTab({
  draft,
  issues,
  onChange,
}: {
  draft: WorkflowPackageDraft;
  issues: readonly WorkflowPackageEditorIssue[];
  onChange: (draft: WorkflowPackageDraft) => void;
}) {
  const updateServers = (mcpServers: PackageMcpServerDraft[]) =>
    onChange({ ...draft, spec: { ...draft.spec, mcpServers } });
  return (
    <Card
      className="border-border/70 bg-card/80 shadow-sm backdrop-blur"
      data-testid="workflow-package-private-mcp-tab"
    >
      <CardHeader className="border-b pb-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle>Private MCP servers</CardTitle>
            <CardDescription>Package-local transport values.</CardDescription>
          </div>
          <Button
            type="button"
            size="sm"
            onClick={() =>
              updateServers([
                ...draft.spec.mcpServers,
                createPackageMcpServerDraft(),
              ])
            }
          >
            <Plus data-icon="inline-start" />
            Add Private MCP
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        <ResourceChecks issues={issues} tab="private-mcp" />
        {draft.spec.mcpServers.map((server, index) => (
          <Card
            key={`${server.key}-${index}`}
            className="bg-background/60"
            data-field={`spec.mcpServers[${index}]`}
            tabIndex={-1}
            data-testid={`package-private-mcp-card-${server.key}`}
          >
            <CardHeader>
              <CardTitle>{server.name || "Untitled MCP"}</CardTitle>
              <CardDescription className="font-mono text-xs">
                {server.key || "missing_key"}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <div className="space-y-2">
                  <Label>Local key</Label>
                  <Input
                    aria-label={`Private MCP ${index + 1} local key`}
                    data-field={`spec.mcpServers[${index}].key`}
                    value={server.key}
                    onChange={(event) =>
                      updateServers(
                        updateArrayItem(
                          draft.spec.mcpServers,
                          index,
                          (item) => ({ ...item, key: event.target.value }),
                        ),
                      )
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label>Name</Label>
                  <Input
                    aria-label={`Private MCP ${index + 1} name`}
                    value={server.name}
                    onChange={(event) =>
                      updateServers(
                        updateArrayItem(
                          draft.spec.mcpServers,
                          index,
                          (item) => ({ ...item, name: event.target.value }),
                        ),
                      )
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label>Transport</Label>
                  <Select
                    value={server.transport}
                    onValueChange={(transport: "stdio" | "http-sse") =>
                      updateServers(
                        updateArrayItem(
                          draft.spec.mcpServers,
                          index,
                          (item) => ({ ...item, transport }),
                        ),
                      )
                    }
                  >
                    <SelectTrigger
                      aria-label={`Private MCP ${index + 1} transport`}
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="stdio">stdio</SelectItem>
                      <SelectItem value="http-sse">http-sse</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-2">
                <Label>Description</Label>
                <Input
                  aria-label={`Private MCP ${index + 1} description`}
                  value={server.description}
                  onChange={(event) =>
                    updateServers(
                      updateArrayItem(draft.spec.mcpServers, index, (item) => ({
                        ...item,
                        description: event.target.value,
                      })),
                    )
                  }
                />
              </div>
              {server.transport === "stdio" ? (
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label>Command</Label>
                    <Input
                      aria-label={`Private MCP ${index + 1} command`}
                      value={server.command}
                      onChange={(event) =>
                        updateServers(
                          updateArrayItem(
                            draft.spec.mcpServers,
                            index,
                            (item) => ({
                              ...item,
                              command: event.target.value,
                            }),
                          ),
                        )
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Args JSON array</Label>
                    <Textarea
                      aria-label={`Private MCP ${index + 1} args`}
                      rows={3}
                      value={server.argsText}
                      onChange={(event) =>
                        updateServers(
                          updateArrayItem(
                            draft.spec.mcpServers,
                            index,
                            (item) => ({
                              ...item,
                              argsText: event.target.value,
                            }),
                          ),
                        )
                      }
                    />
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <Label>URL</Label>
                  <Input
                    aria-label={`Private MCP ${index + 1} URL`}
                    value={server.url}
                    onChange={(event) =>
                      updateServers(
                        updateArrayItem(
                          draft.spec.mcpServers,
                          index,
                          (item) => ({ ...item, url: event.target.value }),
                        ),
                      )
                    }
                  />
                </div>
              )}
              {server.transport === "stdio" ? (
                <StringMapEditor
                  addLabel="Add Env"
                  emptyLabel="No environment values configured."
                  issues={issues}
                  label="Environment values"
                  map={server.env}
                  name="env"
                  onChange={(env) =>
                    updateServers(
                      updateArrayItem(draft.spec.mcpServers, index, (item) => ({
                        ...item,
                        env,
                      })),
                    )
                  }
                  serverIndex={index}
                />
              ) : (
                <div className="grid gap-3 xl:grid-cols-2">
                  <StringMapEditor
                    addLabel="Add Header"
                    emptyLabel="No header values configured."
                    issues={issues}
                    label="Header values"
                    map={server.headers}
                    name="headers"
                    onChange={(headers) =>
                      updateServers(
                        updateArrayItem(
                          draft.spec.mcpServers,
                          index,
                          (item) => ({ ...item, headers }),
                        ),
                      )
                    }
                    serverIndex={index}
                  />
                  <StringMapEditor
                    addLabel="Add Query"
                    emptyLabel="No query values configured."
                    issues={issues}
                    label="Query values"
                    map={server.query}
                    name="query"
                    onChange={(query) =>
                      updateServers(
                        updateArrayItem(
                          draft.spec.mcpServers,
                          index,
                          (item) => ({ ...item, query }),
                        ),
                      )
                    }
                    serverIndex={index}
                  />
                </div>
              )}
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() =>
                  updateServers(
                    draft.spec.mcpServers.filter(
                      (_, itemIndex) => itemIndex !== index,
                    ),
                  )
                }
              >
                Remove private MCP
              </Button>
            </CardContent>
          </Card>
        ))}
        {draft.spec.mcpServers.length === 0 ? (
          <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
            No package-private MCP servers yet.
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

type PrivateMcpMapName = "env" | "headers" | "query";

function replaceStringMapEntry(
  map: Record<string, string>,
  currentKey: string,
  nextKey: string,
  nextValue: string,
): Record<string, string> {
  const entries = Object.entries(map);
  const nextEntries = entries.map(([key, value]) =>
    key === currentKey ? [nextKey, nextValue] : [key, value],
  );
  return Object.fromEntries(nextEntries);
}

function StringMapEditor({
  addLabel,
  emptyLabel,
  issues,
  label,
  map,
  name,
  onChange,
  serverIndex,
}: {
  addLabel: string;
  emptyLabel: string;
  issues: readonly WorkflowPackageEditorIssue[];
  label: string;
  map: Record<string, string>;
  name: PrivateMcpMapName;
  onChange: (map: Record<string, string>) => void;
  serverIndex: number;
}) {
  const entries = Object.entries(map);
  const displayName = name === "headers" ? "header" : name;
  return (
    <div
      className="space-y-3 rounded-lg border p-3"
      data-testid={`private-mcp-${name}-values`}
    >
      <div className="flex items-center justify-between gap-3">
        <Label>{label}</Label>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => onChange({ ...map, "": "" })}
        >
          {addLabel}
        </Button>
      </div>
      {entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">{emptyLabel}</p>
      ) : null}
      {entries.map(([key, value], index) => {
        const field = `spec.mcpServers[${serverIndex}].${name}.${key}`;
        return (
          <div
            key={`${name}-${index}-${key}`}
            className="grid gap-2 md:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)_auto]"
          >
            <Input
              aria-label={`Private MCP ${serverIndex + 1} ${displayName} key ${index + 1}`}
              data-field={field}
              placeholder={
                name === "env"
                  ? "MARKET_DATA_API_KEY"
                  : name === "headers"
                    ? "Authorization"
                    : "apiKey"
              }
              value={key}
              onChange={(event) =>
                onChange(
                  replaceStringMapEntry(map, key, event.target.value, value),
                )
              }
            />
            <Input
              aria-label={`Private MCP ${serverIndex + 1} ${displayName} value ${index + 1}`}
              data-field={field}
              placeholder={name === "headers" ? "Bearer ${TOKEN}" : "${VALUE}"}
              value={value}
              onChange={(event) =>
                onChange(
                  replaceStringMapEntry(map, key, key, event.target.value),
                )
              }
            />
            <Button
              type="button"
              size="icon"
              variant="outline"
              aria-label={`Remove Private MCP ${serverIndex + 1} ${displayName} ${index + 1}`}
              onClick={() =>
                onChange(
                  Object.fromEntries(
                    entries.filter((_, itemIndex) => itemIndex !== index),
                  ),
                )
              }
            >
              <Trash2 />
            </Button>
            <FieldMessage message={issueMessageForField(issues, field)} />
          </div>
        );
      })}
    </div>
  );
}

export function WorkflowYamlTab({
  draft,
  issues,
  onChange,
}: {
  draft: WorkflowPackageDraft;
  issues: readonly WorkflowPackageEditorIssue[];
  onChange: (draft: WorkflowPackageDraft) => void;
}) {
  const [workflowYaml, setWorkflowYaml] = useState(() =>
    workflowPackageWorkflowsToYaml(draft.spec.workflows),
  );
  const [parseErrors, setParseErrors] = useState<string[]>([]);

  useEffect(() => {
    setWorkflowYaml(workflowPackageWorkflowsToYaml(draft.spec.workflows));
    setParseErrors([]);
  }, [draft.spec.workflows]);

  const updateWorkflowYaml = (value: string) => {
    setWorkflowYaml(value);
    const parsed = workflowPackageWorkflowsFromYaml(value);
    setParseErrors(parsed.errors);
    if (parsed.errors.length === 0) {
      onChange({
        ...draft,
        spec: { ...draft.spec, workflows: parsed.workflows },
      });
    }
  };

  return (
    <Card
      className="border-border/70 bg-card/80 shadow-sm backdrop-blur"
      data-testid="workflow-package-workflow-yaml-tab"
    >
      <CardHeader className="border-b pb-4">
        <CardTitle id="workflow-yaml-title">Workflow YAML</CardTitle>
        <CardDescription>Workflow graph nodes in YAML.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        <ResourceChecks issues={issues} tab="workflow-yaml" />
        {parseErrors.length > 0 ? (
          <Alert variant="destructive">
            <AlertCircle />
            <AlertTitle>Workflow YAML could not be parsed</AlertTitle>
            <AlertDescription>
              <ul className="list-disc pl-5">
                {parseErrors.map((error) => (
                  <li key={error}>{error}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        ) : null}
        <div className="space-y-2" data-field="spec.workflows" tabIndex={-1}>
          <Textarea
            id="workflow-yaml"
            aria-labelledby="workflow-yaml-title"
            className="min-h-96 font-mono text-xs"
            spellCheck={false}
            value={workflowYaml}
            onChange={(event) => updateWorkflowYaml(event.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Use an array of workflow objects.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

export function SecretBindingsTab(props: {
  bindings: WorkflowPackageSecretBindingRead[];
  bindingsError: string | null;
  bindingsLoading: boolean;
  deleting: boolean;
  packageId: string | undefined;
  referencedSecretKeys: string[];
  saving: boolean;
  onDelete: (key: string) => Promise<void>;
  onSave: (key: string, value: string) => Promise<void>;
}) {
  const {
    bindings,
    bindingsError,
    bindingsLoading,
    deleting,
    onDelete,
    onSave,
    packageId,
    referencedSecretKeys,
    saving,
  } = props;
  const [secretKey, setSecretKey] = useState("");
  const [secretValue, setSecretValue] = useState("");
  const sortedBindings = sortedSecretBindings(bindings);
  const configuredKeys = new Set(sortedBindings.map((binding) => binding.key));

  const submit = async () => {
    const normalizedKey = secretKey.trim();
    if (!normalizedKey || !secretValue.trim()) {
      toast.error("Secret binding key and value are required.");
      return;
    }
    await onSave(normalizedKey, secretValue);
    setSecretKey("");
    setSecretValue("");
  };

  return (
    <Card
      className="border-border/70 bg-card/80 shadow-sm backdrop-blur"
      data-testid="workflow-package-secret-bindings-tab"
    >
      <CardHeader className="border-b pb-4">
        <CardTitle>Secret bindings</CardTitle>
        <CardDescription>
          Bind package-local{" "}
          <code className="rounded bg-muted/40 px-1">{"${{ secrets.* }}"}</code>{" "}
          references. Stored secret values are never returned or echoed by the
          UI.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        {!packageId ? (
          <Alert>
            <AlertCircle />
            <AlertTitle>Save the package first</AlertTitle>
            <AlertDescription>
              Secret bindings are stored against a saved package id, outside the
              YAML manifest.
            </AlertDescription>
          </Alert>
        ) : null}
        {bindingsError ? (
          <Alert variant="destructive">
            <AlertCircle />
            <AlertTitle>Secret bindings unavailable</AlertTitle>
            <AlertDescription>{bindingsError}</AlertDescription>
          </Alert>
        ) : null}
        <div className="rounded-lg border bg-muted/20 p-3 text-sm">
          <p className="font-medium">Referenced by workflow YAML</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {referencedSecretKeys.length === 0 ? (
              <span className="text-muted-foreground">
                No {"${{ secrets.* }}"} references found in workflows.
              </span>
            ) : null}
            {referencedSecretKeys.map((key) => (
              <Badge
                key={key}
                variant={configuredKeys.has(key) ? "secondary" : "outline"}
              >
                {key}
                {configuredKeys.has(key) ? " bound" : " missing"}
              </Badge>
            ))}
          </div>
        </div>
        <div className="grid gap-3 rounded-lg border p-3 md:grid-cols-[minmax(0,0.8fr)_minmax(0,1fr)_auto]">
          <div className="space-y-2">
            <Label htmlFor="secret-binding-key">Secret binding key</Label>
            <Input
              id="secret-binding-key"
              aria-label="Secret binding key"
              placeholder="slack_webhook_token"
              value={secretKey}
              onChange={(event) => setSecretKey(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="secret-binding-value">Secret binding value</Label>
            <Input
              id="secret-binding-value"
              aria-label="Secret binding value"
              placeholder="Paste new value; never echoed"
              type="password"
              value={secretValue}
              onChange={(event) => setSecretValue(event.target.value)}
            />
          </div>
          <div className="flex items-end">
            <Button
              disabled={!packageId || saving}
              type="button"
              onClick={() => void submit()}
            >
              {saving ? (
                <Loader2 className="animate-spin" data-icon="inline-start" />
              ) : null}
              Save secret binding
            </Button>
          </div>
        </div>
        <div className="grid gap-2">
          {bindingsLoading ? (
            <div className="rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground">
              Loading secret bindings...
            </div>
          ) : null}
          {sortedBindings.length === 0 && !bindingsLoading ? (
            <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
              No package secret bindings configured.
            </div>
          ) : null}
          {sortedBindings.map((binding) => (
            <div
              key={binding.key}
              className="flex flex-col gap-3 rounded-md border bg-muted/20 p-3 text-sm sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0">
                <p className="font-medium">{binding.key}</p>
                <p className="text-xs text-muted-foreground">
                  {binding.hasValue
                    ? "Stored value redacted"
                    : "No value stored"}{" "}
                  · updated {formatDateTime(binding.updatedAt)}
                </p>
              </div>
              <Button
                disabled={deleting}
                size="sm"
                type="button"
                variant="outline"
                aria-label={`Delete secret binding ${binding.key}`}
                onClick={() => void onDelete(binding.key)}
              >
                Delete
              </Button>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export function ExportsTab(props: {
  draft: WorkflowPackageDraft;
  onOpenImportWorkspace: () => void;
  packageId: string | undefined;
}) {
  const { draft, onOpenImportWorkspace, packageId } = props;
  const generatedManifestSource = useMemo(
    () => workflowPackageDraftToManifestSource(draft),
    [draft],
  );
  const [exportPreview, setExportPreview] = useState(generatedManifestSource);
  const exportHref = packageId
    ? exportWorkflowPackageUrl(packageId)
    : undefined;

  useEffect(() => {
    if (!exportHref) {
      setExportPreview(generatedManifestSource);
    }
  }, [exportHref, generatedManifestSource]);

  useEffect(() => {
    if (!exportHref) {
      return;
    }

    let active = true;
    setExportPreview("Loading package export preview...");
    void fetch(exportHref)
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("Failed to load export preview.");
        }
        return response.text();
      })
      .then((text) => {
        if (active) {
          setExportPreview(text);
        }
      })
      .catch((error) => {
        if (active) {
          setExportPreview(generatedManifestSource);
          toast.error(
            error instanceof Error
              ? error.message
              : "Failed to load export preview.",
          );
        }
      });

    return () => {
      active = false;
    };
  }, [exportHref, generatedManifestSource]);

  return (
    <Card
      className="border-border/70 bg-card/80 shadow-sm backdrop-blur"
      data-testid="workflow-package-exports-tab"
    >
      <CardHeader className="border-b pb-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle>Package import / export</CardTitle>
            <CardDescription>
              Download YAML or import a pasted manifest.
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            {exportHref ? (
              <Button asChild size="sm">
                <a href={exportHref} download>
                  <Download data-icon="inline-start" />
                  Download YAML
                </a>
              </Button>
            ) : null}
            <Button
              size="sm"
              type="button"
              variant="outline"
              onClick={onOpenImportWorkspace}
            >
              <FileUp data-icon="inline-start" />
              Import Package
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        <Textarea
          aria-label="Package YAML preview"
          className="min-h-96 font-mono text-xs"
          readOnly
          value={exportPreview}
        />
      </CardContent>
    </Card>
  );
}
