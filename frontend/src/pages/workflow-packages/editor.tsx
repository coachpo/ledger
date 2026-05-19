import {
  AlertCircle,
  Boxes,
  Braces,
  Cable,
  CheckCircle2,
  Code2,
  Download,
  FileCheck2,
  KeyRound,
  Loader2,
  PlayCircle,
  Plus,
  Save,
  ShieldCheck,
  Trash2,
  Workflow,
} from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useLocation, useNavigate, useParams } from "react-router";
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
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useModelConnections } from "@/hooks/use-model-connections";
import {
  useCreateWorkflowPackage,
  useCreateWorkflowPackageLaunch,
  useCreateWorkflowPackageRuntimeInputPersonalEntry,
  useDeleteWorkflowPackageRuntimeInputPersonalEntry,
  useDeleteWorkflowPackageSecretBinding,
  useImportWorkflowPackage,
  usePreflightWorkflowPackage,
  useTools,
  useUpdateWorkflowPackage,
  useUpdateWorkflowPackageRuntimeInputPersonalEntry,
  useUpsertWorkflowPackageSecretBinding,
  useValidateWorkflowPackageManifest,
  useWorkflowPackage,
  useWorkflowPackageLaunch,
  useWorkflowPackageManifest,
  useWorkflowPackageRuntimeInputRegistry,
  useWorkflowPackageSecretBindings,
} from "@/hooks/use-workflow-packages";
import { ApiRequestError } from "@/lib/api-client";
import { exportWorkflowPackageUrl } from "@/lib/api/workflow-packages";
import { formatDateTime } from "@/lib/format";
import {
  createPackageAgentDraft,
  createPackageCapabilityProfileDraft,
  createPackageMcpServerDraft,
  createPackageOutputSchemaDraft,
  createWorkflowPackageDraft,
  diagnosticToEditorTarget,
  mapBackendDiagnostics,
  packageDraftFromManifestSource,
  validateWorkflowPackageDraft,
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
import { stringifyJson } from "@/lib/platform-authoring/common/serialization";
import {
  createLaunchParametersTemplate,
  parseLaunchParametersJson,
  resetLaunchParametersTemplate,
} from "@/lib/platform-authoring/schema/schema-template";
import type { ApiErrorDetail, UnknownRecord } from "@/lib/types/common";
import type { ModelConnectionKind } from "@/lib/types/model-connection";
import type {
  WorkflowPackageImportRequest,
  WorkflowPackageLaunchRead,
  WorkflowPackageManifestRead,
  WorkflowPackageRead,
  WorkflowPackageRuntimeInputEntryRead,
  WorkflowPackageSecretBindingRead,
} from "@/lib/types/workflow-package";
import { WorkflowPackageImportDialog } from "./workflow-package-import-dialog";

type WorkflowPackageEditorTab =
  | "overview"
  | "agents"
  | "output-schemas"
  | "capability-profiles"
  | "private-mcp"
  | "workflow-yaml"
  | "secret-bindings"
  | "preflight"
  | "launch"
  | "exports";

type WorkflowPackageEditorTabDefinition = {
  description: string;
  icon: typeof Workflow;
  label: string;
  value: WorkflowPackageEditorTab;
};


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

type DiagnosticTarget = {
  field: string;
  tab: WorkflowPackageEditorTab;
} | null;

function agentIndexFromPath(path: string): number | null {
  const match = /^spec\.agents\[(\d+)]/.exec(path);
  return match ? Number.parseInt(match[1], 10) : null;
}

function issueMessageForField(issues: readonly WorkflowPackageEditorIssue[], field: string) {
  return issues.find((issue) => issue.field === field)?.issue ?? null;
}

function issueMessagesForPrefix(issues: readonly WorkflowPackageEditorIssue[], prefix: string) {
  return issues.filter((issue) => issue.field === prefix || issue.field.startsWith(`${prefix}.`) || issue.field.startsWith(`${prefix}[`));
}

function fieldNameFromAgentPath(field: string): keyof AgentFormValues | null {
  const match = /^spec\.agents\[\d+]\.(?<name>[A-Za-z][A-Za-z0-9]*)/.exec(field);
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

const editorTabs: WorkflowPackageEditorTabDefinition[] = [
  { description: "Package metadata, manifest identity, current hashes, and local edit state.", icon: Workflow, label: "Overview", value: "overview" },
  { description: "Package-private agent definitions stay local to this package shell.", icon: Boxes, label: "Agents", value: "agents" },
  { description: "Local output contracts are authored inside the package boundary.", icon: Braces, label: "Output Schemas", value: "output-schemas" },
  { description: "Capability profiles collect server-declared tool keys for local agents.", icon: ShieldCheck, label: "Capability Profiles", value: "capability-profiles" },
  { description: "Private MCP server bindings stay portable and secret-reference driven.", icon: Cable, label: "Private MCP", value: "private-mcp" },
  { description: "Author workflow graphs as raw YAML, including kind:http operation nodes.", icon: Code2, label: "Workflow YAML", value: "workflow-yaml" },
  { description: "Bind package-local secret references without exposing stored values.", icon: KeyRound, label: "Secret Bindings", value: "secret-bindings" },
  { description: "Run package readiness checks before launch without mutating runtime state.", icon: FileCheck2, label: "Preflight", value: "preflight" },
  { description: "Launch a selected package workflow after preflight readiness passes.", icon: PlayCircle, label: "Launch", value: "launch" },
  { description: "Import or export clean package YAML without database ids or secret values.", icon: Download, label: "Import / Export", value: "exports" },
];

function routeTab(pathname: string): WorkflowPackageEditorTab {
  return pathname.endsWith("/run") ? "launch" : "overview";
}

function packageTitle(workflowPackage: WorkflowPackageRead | undefined, isNew: boolean) {
  return workflowPackage ? workflowPackage.name : isNew ? "New Workflow Package" : "Workflow Package";
}

function packageSubtitle(workflowPackage: WorkflowPackageRead | undefined, isNew: boolean) {
  if (workflowPackage) {
    return workflowPackage.key;
  }
  return isNew ? "Draft manifest shell" : "Loading package identity";
}

function manifestIdentity(manifest: WorkflowPackageManifestRead) {
  return `package:${manifest.packageId}:${manifest.manifestHash}`;
}

type PackageDiagnostic = {
  connectionKind?: ModelConnectionKind;
  field: string;
  issue: string;
  severity: "error" | "warning";
};

function diagnosticFromRecord(value: unknown, severity: "error" | "warning"): PackageDiagnostic {
  const record = isUnknownRecord(value) ? value : {};
  const field = stringValue(record.field) || stringValue(record.path) || "$";
  const connectionKind = modelConnectionKindValue(record.connectionKind);
  return {
    ...(connectionKind ? { connectionKind } : {}),
    field,
    issue: stringValue(record.issue) || stringValue(record.message) || "Review this package diagnostic.",
    severity,
  };
}

function diagnosticsFromLaunch(read: WorkflowPackageLaunchRead | undefined): PackageDiagnostic[] {
  if (!read) {
    return [];
  }
  const blockingErrors = Array.isArray(read.blockingErrors) ? read.blockingErrors : [];
  const warnings = Array.isArray(read.warnings) ? read.warnings : [];
  return [
    ...blockingErrors.map((diagnostic) => diagnosticFromRecord(diagnostic, "error")),
    ...warnings.map((diagnostic) => diagnosticFromRecord(diagnostic, "warning")),
  ];
}

function diagnosticBadge(diagnostic: PackageDiagnostic) {
  return diagnostic.severity === "error" ? (
    <Badge variant="destructive">Blocking</Badge>
  ) : (
    <Badge className="border-chart-3/30 bg-chart-3/10 text-chart-3" variant="outline">Warning</Badge>
  );
}

const CONNECTION_KIND_LABELS: Record<ModelConnectionKind, string> = {
  deterministic_smoke: "Deterministic smoke",
  provider: "Provider-backed",
};

function connectionKindLabel(value: ModelConnectionKind | null | undefined): string {
  return CONNECTION_KIND_LABELS[value ?? "provider"];
}

function modelConnectionKindValue(value: unknown): ModelConnectionKind | null {
  return value === "provider" || value === "deterministic_smoke" ? value : null;
}

function isSmokeDiagnostic(diagnostic: PackageDiagnostic): boolean {
  return diagnostic.connectionKind === "deterministic_smoke";
}

function isUnknownRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function collectSecretReferenceKeys(value: unknown): string[] {
  const matches = JSON.stringify(value).matchAll(/\$\{\{\s*secrets\.([a-z][a-z0-9_]*)\s*}}/g);
  return [...new Set([...matches].map((match) => match[1]).filter(Boolean))].sort((left, right) => left.localeCompare(right));
}

function sortedSecretBindings(bindings: readonly WorkflowPackageSecretBindingRead[]): WorkflowPackageSecretBindingRead[] {
  return [...bindings].sort((left, right) => left.key.localeCompare(right.key));
}

function EditorSkeleton() {
  return (
    <div className="space-y-4 p-4">
      <Skeleton className="h-28 w-full" />
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-72 w-full" />
    </div>
  );
}

function ManifestBlockingState({ errors, loading, onRetry, title }: { errors: readonly string[]; loading: boolean; onRetry: () => void; title: string }) {
  return (
    <Card className="border-destructive/30 bg-destructive/5 shadow-sm" data-testid="workflow-package-manifest-blocker">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-destructive"><AlertCircle className="size-5" />{title}</CardTitle>
        <CardDescription>Manifest content must load and parse cleanly before package resources can be edited.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Alert variant="destructive" role="alert">
          <AlertCircle />
          <AlertTitle>Editor locked</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-5">
              {errors.map((error, index) => <li key={`${index}-${error}`}>{error}</li>)}
            </ul>
          </AlertDescription>
        </Alert>
        <Button disabled={loading} type="button" variant="outline" onClick={onRetry}>
          {loading ? <Loader2 className="animate-spin" data-icon="inline-start" /> : null}
          Retry manifest load
        </Button>
      </CardContent>
    </Card>
  );
}

function issueForField(issues: readonly WorkflowPackageEditorIssue[], field: string) {
  return issues.find((issue) => issue.field === field)?.issue ?? null;
}

function FieldMessage({ message }: { message: string | null }) {
  return message ? <p className="text-sm text-destructive" role="alert">{message}</p> : null;
}

function ResourceChecks({ issues, tab }: { issues: readonly WorkflowPackageEditorIssue[]; tab: WorkflowPackageEditorTab }) {
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
            <li key={`${issue.field}-${issue.issue}`}>{issue.field}: {issue.issue}</li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

function updateArrayItem<T>(items: readonly T[], index: number, updater: (item: T) => T): T[] {
  return items.map((item, itemIndex) => itemIndex === index ? updater(item) : item);
}

function toggleString(values: readonly string[], value: string, checked: boolean) {
  if (checked) {
    return values.includes(value) ? [...values] : [...values, value];
  }
  return values.filter((entry) => entry !== value);
}

function OverviewEditor({ draft, issues, isNew, onChange }: { draft: WorkflowPackageDraft; issues: readonly WorkflowPackageEditorIssue[]; isNew: boolean; onChange: (draft: WorkflowPackageDraft) => void }) {
  const setMetadata = (key: keyof WorkflowPackageDraft["metadata"], value: string) => {
    onChange({ ...draft, metadata: { ...draft.metadata, [key]: value } });
  };
  return (
    <Card className="border-border/70 bg-card/80 shadow-sm backdrop-blur">
      <CardHeader>
        <CardTitle>Package overview</CardTitle>
        <CardDescription>Author the portable package identity that wraps all package-local resources.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="metadata-key">Local package key</Label>
          <Input id="metadata-key" data-field="metadata.key" aria-label="Package key" readOnly={!isNew} value={draft.metadata.key} onChange={isNew ? (event) => setMetadata("key", event.target.value) : undefined} />
          <FieldMessage message={issueForField(issues, "metadata.key")} />
          {isNew ? null : <p className="text-sm text-muted-foreground">Existing package keys are immutable and must stay aligned with the package identity.</p>}
        </div>
        <div className="space-y-2">
          <Label htmlFor="metadata-name">Name</Label>
          <Input id="metadata-name" data-field="metadata.name" aria-label="Package name" value={draft.metadata.name} onChange={(event) => setMetadata("name", event.target.value)} />
          <FieldMessage message={issueForField(issues, "metadata.name")} />
        </div>
        <div className="space-y-2 md:col-span-2">
          <Label htmlFor="metadata-description">Description</Label>
          <Textarea id="metadata-description" aria-label="Package description" rows={3} value={draft.metadata.description} onChange={(event) => setMetadata("description", event.target.value)} />
        </div>
        <div className="space-y-2 md:col-span-2">
          <Label>Package input schema</Label>
          <SchemaComposer label="Package inputs" node={draft.spec.inputs} onChange={(inputs) => onChange({ ...draft, spec: { ...draft.spec, inputs } })} />
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
  modelConnectionOptions: { description?: string; label: string; value: string }[];
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
      document.querySelector<HTMLElement>(`[data-field="${CSS.escape(targetField)}"]`)?.focus();
    }, 75);
  }, [open, targetField]);

  if (!agent || agentIndex === null) {
    return null;
  }

  const fieldPath = (field: keyof AgentFormValues) => `spec.agents[${agentIndex}].${field}`;
  const setAgent = <Key extends keyof PackageAgentDraft>(key: Key, value: PackageAgentDraft[Key]) => {
    onChange({ ...agent, [key]: value });
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-3xl" data-testid={`package-agent-sheet-${agentIndex}`}>
        <SheetHeader>
          <SheetTitle>Agent editor</SheetTitle>
          <SheetDescription>Save model, schema, profile, MCP, timeout, and prompt fields into this package manifest only.</SheetDescription>
        </SheetHeader>
        <Form {...form}>
          <form className="grid gap-4 px-4 pb-4" onSubmit={(event) => event.preventDefault()}>
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
                      <div data-field={fieldPath("modelConnection")} tabIndex={-1}>
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
                    <FormDescription>Global model connections stay outside the package and are referenced by stable key.</FormDescription>
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
                        <SelectTrigger data-field={fieldPath("outputSchema")} aria-label="Output schema local key">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__none__">Select local schema</SelectItem>
                          {outputSchemaKeys.map((key) => <SelectItem key={key} value={key}>{key}</SelectItem>)}
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
                    <FormDescription>Launch planning only; this value is not serialized by the current package manifest contract.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <MultiKeyPicker label="Capability profile local keys" keys={capabilityProfileKeys} selectedKeys={agent.capabilityProfiles} onChange={(nextKeys) => setAgent("capabilityProfiles", nextKeys)} />
              <MultiKeyPicker label="Private MCP local keys" keys={mcpServerKeys} selectedKeys={agent.mcpServers} onChange={(nextKeys) => setAgent("mcpServers", nextKeys)} />
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
            <div className="space-y-2" data-field={`spec.agents[${agentIndex}].inputSchema`} tabIndex={-1}>
              <Label>Input schema</Label>
              <SchemaComposer label="Agent input schema" node={agent.inputSchema} onChange={(inputSchema) => setAgent("inputSchema", inputSchema)} />
              <FieldMessage message={issueMessageForField(issues, `spec.agents[${agentIndex}].inputSchema`)} />
            </div>
          </form>
        </Form>
        <SheetFooter>
          <Button type="button" onClick={() => onOpenChange(false)}>Close agent editor</Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

function MultiKeyPicker({ keys, label, onChange, selectedKeys }: { keys: string[]; label: string; onChange: (keys: string[]) => void; selectedKeys: string[] }) {
  return (
    <div className="space-y-2 rounded-lg border p-3">
      <Label>{label}</Label>
      {keys.length === 0 ? <p className="text-sm text-muted-foreground">Create local resources before binding them.</p> : null}
      <div className="grid gap-2">
        {keys.map((key) => (
          <label key={key} className="flex cursor-pointer items-center gap-2 text-sm">
            <Checkbox checked={selectedKeys.includes(key)} onCheckedChange={(checked) => onChange(toggleString(selectedKeys, key, checked === true))} />
            <span className="font-['Fira_Code',ui-monospace,monospace] text-xs">{key}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

function AgentsTab(props: {
  diagnosticTarget: DiagnosticTarget;
  draft: WorkflowPackageDraft;
  issues: readonly WorkflowPackageEditorIssue[];
  modelConnectionOptions: { description?: string; label: string; value: string }[];
  onChange: (draft: WorkflowPackageDraft) => void;
}) {
  const { diagnosticTarget, draft, issues, modelConnectionOptions, onChange } = props;
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const outputSchemaKeys = draft.spec.outputSchemas.map((schema) => schema.key).filter(Boolean);
  const capabilityProfileKeys = draft.spec.capabilityProfiles.map((profile) => profile.key).filter(Boolean);
  const mcpServerKeys = draft.spec.mcpServers.map((server) => server.key).filter(Boolean);
  const editingAgent = editingIndex === null ? null : draft.spec.agents[editingIndex] ?? null;
  const updateAgents = (agents: PackageAgentDraft[]) => onChange({ ...draft, spec: { ...draft.spec, agents } });

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
    <Card className="border-border/70 bg-card/80 shadow-sm backdrop-blur" data-testid="workflow-package-agents-tab">
      <CardHeader className="border-b pb-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle>Package-local agents</CardTitle>
            <CardDescription>Agents save as local manifest entries and never call retired global agent APIs.</CardDescription>
          </div>
          <Button type="button" size="sm" onClick={() => { updateAgents([...draft.spec.agents, createPackageAgentDraft({ outputSchema: outputSchemaKeys[0] ?? "" })]); setEditingIndex(draft.spec.agents.length); }}>
            <Plus data-icon="inline-start" />Add Agent
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        <ResourceChecks issues={issues} tab="agents" />
        {draft.spec.agents.length === 0 ? <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">No package-local agents yet.</div> : null}
        <div className="grid gap-3">
          {draft.spec.agents.map((agent, index) => (
            <div key={`${agent.key}-${index}`} className="flex flex-col gap-3 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between" data-testid={`package-agent-row-${agent.key}`}>
              <div className="min-w-0 space-y-1">
                <p className="font-medium">{agent.name || "Untitled agent"}</p>
                <p className="break-all font-['Fira_Code',ui-monospace,monospace] text-xs text-muted-foreground">{agent.key || "missing_key"}</p>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">model: {agent.modelConnection || "missing"}</Badge>
                  <Badge variant="outline">schema: {agent.outputSchema || "missing"}</Badge>
                  <Badge variant="secondary">{agent.capabilityProfiles.length} profiles</Badge>
                  <Badge variant="secondary">{agent.mcpServers.length} MCP</Badge>
                </div>
              </div>
              <div className="flex gap-2">
                <Button type="button" size="sm" variant="outline" aria-label={`Edit agent ${agent.name}`} onClick={() => setEditingIndex(index)}>Edit</Button>
                <Button type="button" size="icon" variant="outline" aria-label={`Remove agent ${agent.name}`} onClick={() => updateAgents(draft.spec.agents.filter((_, itemIndex) => itemIndex !== index))}><Trash2 /></Button>
              </div>
            </div>
          ))}
        </div>
        <AgentSheet agent={editingAgent} agentIndex={editingIndex} capabilityProfileKeys={capabilityProfileKeys} issues={issues} mcpServerKeys={mcpServerKeys} modelConnectionOptions={modelConnectionOptions} open={editingIndex !== null} outputSchemaKeys={outputSchemaKeys} targetField={diagnosticTarget?.tab === "agents" ? diagnosticTarget.field : null} onOpenChange={(open) => !open ? setEditingIndex(null) : undefined} onChange={(agent) => editingIndex !== null ? updateAgents(updateArrayItem(draft.spec.agents, editingIndex, () => agent)) : undefined} />
      </CardContent>
    </Card>
  );
}

function OutputSchemasTab({ draft, issues, onChange }: { draft: WorkflowPackageDraft; issues: readonly WorkflowPackageEditorIssue[]; onChange: (draft: WorkflowPackageDraft) => void }) {
  const updateSchemas = (outputSchemas: PackageOutputSchemaDraft[]) => onChange({ ...draft, spec: { ...draft.spec, outputSchemas } });
  return (
    <Card className="border-border/70 bg-card/80 shadow-sm backdrop-blur" data-testid="workflow-package-output-schemas-tab">
      <CardHeader className="border-b pb-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle>Package-local output schemas</CardTitle>
            <CardDescription>Cards and accordions use the shared schema composer scoped to local schema keys.</CardDescription>
          </div>
          <Button type="button" size="sm" onClick={() => updateSchemas([...draft.spec.outputSchemas, createPackageOutputSchemaDraft()])}><Plus data-icon="inline-start" />Add Schema</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        <ResourceChecks issues={issues} tab="output-schemas" />
        {draft.spec.outputSchemas.length === 0 ? <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">No package-local output schemas yet.</div> : null}
        <div className="grid gap-4 xl:grid-cols-2">
          {draft.spec.outputSchemas.map((schema, index) => (
            <Card key={`${schema.key}-${index}`} className="bg-background/60" data-field={`spec.outputSchemas[${index}]`} tabIndex={-1} data-testid={`package-output-schema-card-${schema.key}`}>
              <CardHeader>
                <CardTitle>{schema.name || "Untitled schema"}</CardTitle>
                <CardDescription className="font-['Fira_Code',ui-monospace,monospace] text-xs">{schema.key || "missing_key"}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="space-y-2"><Label>Local key</Label><Input aria-label={`Output schema ${index + 1} local key`} data-field={`spec.outputSchemas[${index}].key`} value={schema.key} onChange={(event) => updateSchemas(updateArrayItem(draft.spec.outputSchemas, index, (item) => ({ ...item, key: event.target.value })))} /><FieldMessage message={issueMessageForField(issues, `spec.outputSchemas[${index}].key`) ?? issueMessageForField(issues, `spec.outputSchemas[${index}]`)} /></div>
                  <div className="space-y-2"><Label>Name</Label><Input aria-label={`Output schema ${index + 1} name`} value={schema.name} onChange={(event) => updateSchemas(updateArrayItem(draft.spec.outputSchemas, index, (item) => ({ ...item, name: event.target.value })))} /></div>
                </div>
                <div className="space-y-2"><Label>Description</Label><Input aria-label={`Output schema ${index + 1} description`} value={schema.description} onChange={(event) => updateSchemas(updateArrayItem(draft.spec.outputSchemas, index, (item) => ({ ...item, description: event.target.value })))} /></div>
                <SchemaComposer label="Output schema root" node={schema.jsonSchema} onChange={(jsonSchema) => updateSchemas(updateArrayItem(draft.spec.outputSchemas, index, (item) => ({ ...item, jsonSchema })))} />
                <Button type="button" size="sm" variant="outline" onClick={() => updateSchemas(draft.spec.outputSchemas.filter((_, itemIndex) => itemIndex !== index))}>Remove schema</Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function CapabilityProfilesTab(props: { draft: WorkflowPackageDraft; issues: readonly WorkflowPackageEditorIssue[]; onChange: (draft: WorkflowPackageDraft) => void; tools: { description: string; displayName: string; key: string }[]; toolsError: string | null; toolsLoading: boolean }) {
  const { draft, issues, onChange, tools, toolsError, toolsLoading } = props;
  const updateProfiles = (capabilityProfiles: PackageCapabilityProfileDraft[]) => onChange({ ...draft, spec: { ...draft.spec, capabilityProfiles } });
  return (
    <Card className="border-border/70 bg-card/80 shadow-sm backdrop-blur" data-testid="workflow-package-capability-profiles-tab">
      <CardHeader className="border-b pb-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div><CardTitle>Capability profiles</CardTitle><CardDescription>Search the global tool catalog with Command and store only local profile keys plus tool keys.</CardDescription></div>
          <Button type="button" size="sm" onClick={() => updateProfiles([...draft.spec.capabilityProfiles, createPackageCapabilityProfileDraft()])}><Plus data-icon="inline-start" />Add Profile</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        <ResourceChecks issues={issues} tab="capability-profiles" />
        {toolsError ? <Alert variant="destructive"><AlertTitle>Tool catalog unavailable</AlertTitle><AlertDescription>{toolsError}</AlertDescription></Alert> : null}
        {draft.spec.capabilityProfiles.map((profile, index) => (
          <Card key={`${profile.key}-${index}`} className="bg-background/60" data-field={`spec.capabilityProfiles[${index}]`} tabIndex={-1} data-testid={`package-capability-profile-card-${profile.key}`}>
            <CardHeader><CardTitle>{profile.name || "Untitled profile"}</CardTitle><CardDescription className="font-['Fira_Code',ui-monospace,monospace] text-xs">{profile.key || "missing_key"}</CardDescription></CardHeader>
            <CardContent className="grid gap-4 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
              <div className="space-y-3">
                <div className="space-y-2"><Label>Local key</Label><Input aria-label={`Capability profile ${index + 1} local key`} data-field={`spec.capabilityProfiles[${index}].key`} value={profile.key} onChange={(event) => updateProfiles(updateArrayItem(draft.spec.capabilityProfiles, index, (item) => ({ ...item, key: event.target.value })))} /><FieldMessage message={issueMessageForField(issues, `spec.capabilityProfiles[${index}].key`)} /></div>
                <div className="space-y-2"><Label>Name</Label><Input aria-label={`Capability profile ${index + 1} name`} value={profile.name} onChange={(event) => updateProfiles(updateArrayItem(draft.spec.capabilityProfiles, index, (item) => ({ ...item, name: event.target.value })))} /></div>
                <div className="space-y-2"><Label>Description</Label><Textarea aria-label={`Capability profile ${index + 1} description`} rows={3} value={profile.description} onChange={(event) => updateProfiles(updateArrayItem(draft.spec.capabilityProfiles, index, (item) => ({ ...item, description: event.target.value })))} /></div>
                <Button type="button" size="sm" variant="outline" onClick={() => updateProfiles(draft.spec.capabilityProfiles.filter((_, itemIndex) => itemIndex !== index))}>Remove profile</Button>
              </div>
              <div className="space-y-2">
                <Label>Global tool catalog</Label>
                <div data-field={`spec.capabilityProfiles[${index}].toolKeys[0]`} tabIndex={-1}><Command className="rounded-lg border" data-testid="capability-tool-command">
                  <CommandInput placeholder="Search server-declared tools..." />
                  <CommandList>
                    <CommandEmpty>{toolsLoading ? "Loading tools..." : "No catalog tools match."}</CommandEmpty>
                    <CommandGroup>
                      {tools.map((tool) => (
                        <CommandItem className="data-[selected=true]:bg-transparent data-[selected=true]:text-foreground data-[selected=true]:hover:bg-accent data-[selected=true]:hover:text-accent-foreground" key={tool.key} value={`${tool.displayName} ${tool.key} ${tool.description}`} onSelect={() => updateProfiles(updateArrayItem(draft.spec.capabilityProfiles, index, (item) => ({ ...item, toolKeys: toggleString(item.toolKeys, tool.key, !item.toolKeys.includes(tool.key)) })))}>
                          <Checkbox aria-label={`Select tool ${tool.displayName}`} checked={profile.toolKeys.includes(tool.key)} onCheckedChange={(checked) => updateProfiles(updateArrayItem(draft.spec.capabilityProfiles, index, (item) => ({ ...item, toolKeys: toggleString(item.toolKeys, tool.key, checked === true) })))} />
                          <div className="min-w-0"><p className="truncate text-sm">{tool.displayName}</p><p className="break-all text-xs text-muted-foreground">{tool.key}</p></div>
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                </Command></div>
                <FieldMessage message={issueMessagesForPrefix(issues, `spec.capabilityProfiles[${index}].toolKeys`)[0]?.issue ?? issueMessagesForPrefix(issues, `spec.capabilityProfiles.${profile.key}.toolKeys`)[0]?.issue ?? null} />
                <div className="flex flex-wrap gap-2">{profile.toolKeys.map((key) => <Badge key={key} variant="secondary">{key}</Badge>)}</div>
              </div>
            </CardContent>
          </Card>
        ))}
        {draft.spec.capabilityProfiles.length === 0 ? <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">No local capability profiles yet.</div> : null}
      </CardContent>
    </Card>
  );
}

function PrivateMcpTab({ draft, issues, onChange }: { draft: WorkflowPackageDraft; issues: readonly WorkflowPackageEditorIssue[]; onChange: (draft: WorkflowPackageDraft) => void }) {
  const updateServers = (mcpServers: PackageMcpServerDraft[]) => onChange({ ...draft, spec: { ...draft.spec, mcpServers } });
  return (
    <Card className="border-border/70 bg-card/80 shadow-sm backdrop-blur" data-testid="workflow-package-private-mcp-tab">
      <CardHeader className="border-b pb-4"><div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><CardTitle>Private MCP servers</CardTitle><CardDescription>Configure package-local MCP transport values inline for the selected transport.</CardDescription></div><Button type="button" size="sm" onClick={() => updateServers([...draft.spec.mcpServers, createPackageMcpServerDraft()])}><Plus data-icon="inline-start" />Add Private MCP</Button></div></CardHeader>
      <CardContent className="space-y-4 p-4">
        <ResourceChecks issues={issues} tab="private-mcp" />
        {draft.spec.mcpServers.map((server, index) => (
          <Card key={`${server.key}-${index}`} className="bg-background/60" data-field={`spec.mcpServers[${index}]`} tabIndex={-1} data-testid={`package-private-mcp-card-${server.key}`}>
            <CardHeader><CardTitle>{server.name || "Untitled MCP"}</CardTitle><CardDescription className="font-['Fira_Code',ui-monospace,monospace] text-xs">{server.key || "missing_key"}</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3"><div className="space-y-2"><Label>Local key</Label><Input aria-label={`Private MCP ${index + 1} local key`} data-field={`spec.mcpServers[${index}].key`} value={server.key} onChange={(event) => updateServers(updateArrayItem(draft.spec.mcpServers, index, (item) => ({ ...item, key: event.target.value })))} /></div><div className="space-y-2"><Label>Name</Label><Input aria-label={`Private MCP ${index + 1} name`} value={server.name} onChange={(event) => updateServers(updateArrayItem(draft.spec.mcpServers, index, (item) => ({ ...item, name: event.target.value })))} /></div><div className="space-y-2"><Label>Transport</Label><Select value={server.transport} onValueChange={(transport: "stdio" | "http-sse") => updateServers(updateArrayItem(draft.spec.mcpServers, index, (item) => ({ ...item, transport })))}><SelectTrigger aria-label={`Private MCP ${index + 1} transport`}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="stdio">stdio</SelectItem><SelectItem value="http-sse">http-sse</SelectItem></SelectContent></Select></div></div>
              <div className="space-y-2"><Label>Description</Label><Input aria-label={`Private MCP ${index + 1} description`} value={server.description} onChange={(event) => updateServers(updateArrayItem(draft.spec.mcpServers, index, (item) => ({ ...item, description: event.target.value })))} /></div>
              {server.transport === "stdio" ? <div className="grid gap-3 md:grid-cols-2"><div className="space-y-2"><Label>Command</Label><Input aria-label={`Private MCP ${index + 1} command`} value={server.command} onChange={(event) => updateServers(updateArrayItem(draft.spec.mcpServers, index, (item) => ({ ...item, command: event.target.value })))} /></div><div className="space-y-2"><Label>Args JSON array</Label><Textarea aria-label={`Private MCP ${index + 1} args`} rows={3} value={server.argsText} onChange={(event) => updateServers(updateArrayItem(draft.spec.mcpServers, index, (item) => ({ ...item, argsText: event.target.value })))} /></div></div> : <div className="space-y-2"><Label>URL</Label><Input aria-label={`Private MCP ${index + 1} URL`} value={server.url} onChange={(event) => updateServers(updateArrayItem(draft.spec.mcpServers, index, (item) => ({ ...item, url: event.target.value })))} /></div>}
              {server.transport === "stdio" ? (
                <StringMapEditor
                  addLabel="Add Env"
                  emptyLabel="No environment values configured."
                  issues={issues}
                  label="Environment values"
                  map={server.env}
                  name="env"
                  onChange={(env) => updateServers(updateArrayItem(draft.spec.mcpServers, index, (item) => ({ ...item, env })))}
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
                    onChange={(headers) => updateServers(updateArrayItem(draft.spec.mcpServers, index, (item) => ({ ...item, headers })))}
                    serverIndex={index}
                  />
                  <StringMapEditor
                    addLabel="Add Query"
                    emptyLabel="No query values configured."
                    issues={issues}
                    label="Query values"
                    map={server.query}
                    name="query"
                    onChange={(query) => updateServers(updateArrayItem(draft.spec.mcpServers, index, (item) => ({ ...item, query })))}
                    serverIndex={index}
                  />
                </div>
              )}
              <Button type="button" size="sm" variant="outline" onClick={() => updateServers(draft.spec.mcpServers.filter((_, itemIndex) => itemIndex !== index))}>Remove private MCP</Button>
            </CardContent>
          </Card>
        ))}
        {draft.spec.mcpServers.length === 0 ? <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">No package-private MCP servers yet.</div> : null}
      </CardContent>
    </Card>
  );
}

type PrivateMcpMapName = "env" | "headers" | "query";

function replaceStringMapEntry(map: Record<string, string>, currentKey: string, nextKey: string, nextValue: string): Record<string, string> {
  const entries = Object.entries(map);
  const nextEntries = entries.map(([key, value]) => key === currentKey ? [nextKey, nextValue] : [key, value]);
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
    <div className="space-y-3 rounded-lg border p-3" data-testid={`private-mcp-${name}-values`}>
      <div className="flex items-center justify-between gap-3"><Label>{label}</Label><Button type="button" size="sm" variant="outline" onClick={() => onChange({ ...map, "": "" })}>{addLabel}</Button></div>
      {entries.length === 0 ? <p className="text-sm text-muted-foreground">{emptyLabel}</p> : null}
      {entries.map(([key, value], index) => {
        const field = `spec.mcpServers[${serverIndex}].${name}.${key}`;
        return (
          <div key={`${name}-${index}-${key}`} className="grid gap-2 md:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)_auto]">
            <Input
              aria-label={`Private MCP ${serverIndex + 1} ${displayName} key ${index + 1}`}
              data-field={field}
              placeholder={name === "env" ? "MARKET_DATA_API_KEY" : name === "headers" ? "Authorization" : "apiKey"}
              value={key}
              onChange={(event) => onChange(replaceStringMapEntry(map, key, event.target.value, value))}
            />
            <Input
              aria-label={`Private MCP ${serverIndex + 1} ${displayName} value ${index + 1}`}
              data-field={field}
              placeholder={name === "headers" ? "Bearer ${TOKEN}" : "${VALUE}"}
              value={value}
              onChange={(event) => onChange(replaceStringMapEntry(map, key, key, event.target.value))}
            />
            <Button type="button" size="icon" variant="outline" aria-label={`Remove Private MCP ${serverIndex + 1} ${displayName} ${index + 1}`} onClick={() => onChange(Object.fromEntries(entries.filter((_, itemIndex) => itemIndex !== index)))}><Trash2 /></Button>
            <FieldMessage message={issueMessageForField(issues, field)} />
          </div>
        );
      })}
    </div>
  );
}

function WorkflowYamlTab({ draft, issues, onChange }: { draft: WorkflowPackageDraft; issues: readonly WorkflowPackageEditorIssue[]; onChange: (draft: WorkflowPackageDraft) => void }) {
  const [workflowYaml, setWorkflowYaml] = useState(() => workflowPackageWorkflowsToYaml(draft.spec.workflows));
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
      onChange({ ...draft, spec: { ...draft.spec, workflows: parsed.workflows } });
    }
  };

  return (
    <Card className="border-border/70 bg-card/80 shadow-sm backdrop-blur" data-testid="workflow-package-workflow-yaml-tab">
      <CardHeader className="border-b pb-4">
        <CardTitle id="workflow-yaml-title">Workflow YAML</CardTitle>
        <CardDescription>Author workflow graph nodes directly in YAML. HTTP operations stay in kind:http manifest nodes and validate through the backend manifest flow.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        <ResourceChecks issues={issues} tab="workflow-yaml" />
        {parseErrors.length > 0 ? (
          <Alert variant="destructive">
            <AlertCircle />
            <AlertTitle>Workflow YAML could not be parsed</AlertTitle>
            <AlertDescription><ul className="list-disc pl-5">{parseErrors.map((error) => <li key={error}>{error}</li>)}</ul></AlertDescription>
          </Alert>
        ) : null}
        <div className="space-y-2" data-field="spec.workflows" tabIndex={-1}>
          <Textarea id="workflow-yaml" aria-labelledby="workflow-yaml-title" className="min-h-96 font-mono text-xs" spellCheck={false} value={workflowYaml} onChange={(event) => updateWorkflowYaml(event.target.value)} />
          <p className="text-xs text-muted-foreground">Use an array of workflow objects. Keep HTTP nodes as YAML with kind: http; there is intentionally no visual node editor.</p>
        </div>
      </CardContent>
    </Card>
  );
}

function SecretBindingsTab(props: {
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
  const { bindings, bindingsError, bindingsLoading, deleting, onDelete, onSave, packageId, referencedSecretKeys, saving } = props;
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
    <Card className="border-border/70 bg-card/80 shadow-sm backdrop-blur" data-testid="workflow-package-secret-bindings-tab">
      <CardHeader className="border-b pb-4">
        <CardTitle>Secret bindings</CardTitle>
        <CardDescription>Bind package-local <code className="rounded bg-muted/40 px-1">{"${{ secrets.* }}"}</code> references. Stored secret values are never returned or echoed by the UI.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        {!packageId ? <Alert><AlertCircle /><AlertTitle>Save the package first</AlertTitle><AlertDescription>Secret bindings are stored against a saved package id, outside the YAML manifest.</AlertDescription></Alert> : null}
        {bindingsError ? <Alert variant="destructive"><AlertCircle /><AlertTitle>Secret bindings unavailable</AlertTitle><AlertDescription>{bindingsError}</AlertDescription></Alert> : null}
        <div className="rounded-lg border bg-muted/20 p-3 text-sm">
          <p className="font-medium">Referenced by workflow YAML</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {referencedSecretKeys.length === 0 ? <span className="text-muted-foreground">No {"${{ secrets.* }}"} references found in workflows.</span> : null}
            {referencedSecretKeys.map((key) => <Badge key={key} variant={configuredKeys.has(key) ? "secondary" : "outline"}>{key}{configuredKeys.has(key) ? " bound" : " missing"}</Badge>)}
          </div>
        </div>
        <div className="grid gap-3 rounded-lg border p-3 md:grid-cols-[minmax(0,0.8fr)_minmax(0,1fr)_auto]">
          <div className="space-y-2"><Label htmlFor="secret-binding-key">Secret binding key</Label><Input id="secret-binding-key" aria-label="Secret binding key" placeholder="slack_webhook_token" value={secretKey} onChange={(event) => setSecretKey(event.target.value)} /></div>
          <div className="space-y-2"><Label htmlFor="secret-binding-value">Secret binding value</Label><Input id="secret-binding-value" aria-label="Secret binding value" placeholder="Paste new value; never echoed" type="password" value={secretValue} onChange={(event) => setSecretValue(event.target.value)} /></div>
          <div className="flex items-end"><Button disabled={!packageId || saving} type="button" onClick={() => void submit()}>{saving ? <Loader2 className="animate-spin" data-icon="inline-start" /> : null}Save secret binding</Button></div>
        </div>
        <div className="grid gap-2">
          {bindingsLoading ? <div className="rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground">Loading secret bindings...</div> : null}
          {sortedBindings.length === 0 && !bindingsLoading ? <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">No package secret bindings configured.</div> : null}
          {sortedBindings.map((binding) => (
            <div key={binding.key} className="flex flex-col gap-3 rounded-md border bg-muted/20 p-3 text-sm sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0"><p className="font-medium">{binding.key}</p><p className="text-xs text-muted-foreground">{binding.hasValue ? "Stored value redacted" : "No value stored"} · updated {formatDateTime(binding.updatedAt)}</p></div>
              <Button disabled={deleting} size="sm" type="button" variant="outline" aria-label={`Delete secret binding ${binding.key}`} onClick={() => void onDelete(binding.key)}>Delete</Button>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function DiagnosticRows({ diagnostics, onOpenField }: { diagnostics: PackageDiagnostic[]; onOpenField: (diagnostic: PackageDiagnostic) => void }) {
  if (diagnostics.length === 0) {
    return <div className="rounded-xl border border-dashed bg-background/50 p-4 text-sm text-muted-foreground">No diagnostics returned for this package selection.</div>;
  }
  return (
    <div className="overflow-hidden rounded-xl border">
      <div className="grid grid-cols-[auto_minmax(0,0.8fr)_minmax(0,1.2fr)_auto] gap-3 bg-muted/40 px-3 py-2 text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
        <span>Severity</span><span>Field</span><span>Diagnostic</span><span>Action</span>
      </div>
      {diagnostics.map((diagnostic, index) => (
        <div className="grid grid-cols-[auto_minmax(0,0.8fr)_minmax(0,1.2fr)_auto] items-center gap-3 border-t px-3 py-3 text-sm" key={`${diagnostic.field}-${diagnostic.issue}-${index}`}>
          <div className="flex flex-wrap items-center gap-2">
            {diagnosticBadge(diagnostic)}
            {diagnostic.connectionKind ? (
              <Badge variant={diagnostic.connectionKind === "deterministic_smoke" ? "secondary" : "outline"}>
                {connectionKindLabel(diagnostic.connectionKind)}
              </Badge>
            ) : null}
          </div>
          <code className="break-all rounded bg-muted/40 px-2 py-1 text-xs">{diagnostic.field}</code>
          <span className="break-words text-muted-foreground">{diagnostic.issue}</span>
          <Button size="sm" type="button" variant="outline" onClick={() => onOpenField(diagnostic)}>Open field</Button>
        </div>
      ))}
    </div>
  );
}

function ModelConnectionModeSummary({ diagnostics, read }: { diagnostics: PackageDiagnostic[]; read: WorkflowPackageLaunchRead | undefined }) {
  if (!read) {
    return null;
  }

  const smokeCount = diagnostics.filter(isSmokeDiagnostic).length;
  return (
    <div className="rounded-lg border bg-muted/30 p-4 text-sm text-muted-foreground" data-testid="workflow-package-model-connection-modes">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-foreground">Model connection modes:</span>
        <Badge variant="outline">{connectionKindLabel("provider")}</Badge>
        {smokeCount > 0 ? <Badge variant="secondary">{connectionKindLabel("deterministic_smoke")}</Badge> : null}
      </div>
      <p className="mt-2">
        {smokeCount > 0
          ? `${smokeCount} deterministic smoke connection${smokeCount === 1 ? "" : "s"} will run offline; remaining saved model connections stay provider-backed.`
          : "No deterministic smoke warnings were reported; saved model connections are provider-backed for this launch metadata."}
      </p>
    </div>
  );
}

function RuntimeInputValidationAlert({ errors }: { errors: readonly ApiErrorDetail[] }) {
  if (errors.length === 0) {
    return null;
  }

  return (
    <Alert data-testid="runtime-input-validation-feedback" variant="destructive">
      <AlertCircle />
      <AlertTitle>Runtime inputs need attention</AlertTitle>
      <AlertDescription>
        <ul className="list-disc space-y-1 pl-5">
          {errors.map((error) => (
            <li key={`${error.field}-${error.issue}`}>
              <code className="rounded bg-muted/40 px-1 py-0.5 text-xs">{error.field}</code>: {error.issue}
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

function PreflightTab(props: {
  diagnostics: PackageDiagnostic[];
  launchRead: WorkflowPackageLaunchRead | undefined;
  loading: boolean;
  onOpenField: (diagnostic: PackageDiagnostic) => void;
  onRunPreflight: () => void;
  preflightRead: WorkflowPackageLaunchRead | undefined;
  workflowPackage: WorkflowPackageRead | undefined;
}) {
  const { diagnostics, launchRead, loading, onOpenField, onRunPreflight, preflightRead, workflowPackage } = props;
  const read = preflightRead ?? launchRead;
  const blockingCount = diagnostics.filter((diagnostic) => diagnostic.severity === "error").length;
  const warningCount = diagnostics.filter((diagnostic) => diagnostic.severity === "warning").length;
  const ready = read?.ready === true && blockingCount === 0;
  return (
    <Card className="border-border/70 bg-card/80 shadow-sm backdrop-blur" data-testid="workflow-package-preflight-tab">
      <CardHeader className="border-b pb-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <CardTitle>Package preflight</CardTitle>
            <CardDescription>Run launch readiness checks and deep-link diagnostics back into package-local editor fields.</CardDescription>
          </div>
          <Button disabled={!workflowPackage || loading} size="sm" type="button" variant="outline" onClick={onRunPreflight}>
            {loading ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <FileCheck2 data-icon="inline-start" />}
            Run preflight
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        <Alert className={ready ? "border-positive/30 bg-positive/10" : blockingCount > 0 ? "border-destructive/30" : "border-chart-3/30 bg-chart-3/10"} variant={blockingCount > 0 ? "destructive" : "default"}>
          {ready ? <CheckCircle2 /> : <AlertCircle />}
          <AlertTitle>{ready ? "Ready to launch" : "Needs attention"}</AlertTitle>
          <AlertDescription>
            {read ? `${blockingCount} blocking issue${blockingCount === 1 ? "" : "s"} and ${warningCount} warning${warningCount === 1 ? "" : "s"} for ${read.packageKey}.` : "Run preflight to check current package readiness."}
          </AlertDescription>
        </Alert>
        <ModelConnectionModeSummary diagnostics={diagnostics} read={read} />
        <DiagnosticRows diagnostics={diagnostics} onOpenField={onOpenField} />
      </CardContent>
    </Card>
  );
}

const SAVED_INPUT_ENTRY_LIMIT = 20;

type SavedInputEntryMode = "history" | "personal";

function newestRuntimeInputEntries(
  entries: readonly WorkflowPackageRuntimeInputEntryRead[],
  timestampKey: "createdAt" | "updatedAt",
): WorkflowPackageRuntimeInputEntryRead[] {
  return [...entries].sort((left, right) => {
    const timestampDelta = Date.parse(right[timestampKey]) - Date.parse(left[timestampKey]);
    return timestampDelta === 0 ? right.id - left.id : timestampDelta;
  });
}

function savedInputEntryLabel(entry: WorkflowPackageRuntimeInputEntryRead, mode: SavedInputEntryMode) {
  const name = entry.name?.trim();
  if (name) {
    return name;
  }
  if (mode === "history" && entry.sourceRunId) {
    return `Run #${entry.sourceRunId}`;
  }
  return mode === "history" ? `History #${entry.id}` : `Preset #${entry.id}`;
}

function SavedInputEntryRow(props: {
  deletePending: boolean;
  entry: WorkflowPackageRuntimeInputEntryRead;
  mode: SavedInputEntryMode;
  updatePending: boolean;
  onDelete: (entry: WorkflowPackageRuntimeInputEntryRead) => void;
  onLoad: (entry: WorkflowPackageRuntimeInputEntryRead) => void;
  onUpdate: (entry: WorkflowPackageRuntimeInputEntryRead) => void;
}) {
  const { deletePending, entry, mode, onDelete, onLoad, onUpdate, updatePending } = props;
  const label = savedInputEntryLabel(entry, mode);
  const timestamp = mode === "history" ? entry.createdAt : entry.updatedAt;
  const staleReasons = entry.stale.reasons;

  return (
    <div className="space-y-2 rounded-lg border bg-background/60 p-3" data-testid={`saved-input-${mode}-${entry.id}`}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium">{label}</p>
            {entry.stale.stale ? <Badge className="border-chart-3/30 bg-chart-3/10 text-chart-3" variant="outline">Stale</Badge> : null}
          </div>
          <p className="text-xs text-muted-foreground">{mode === "history" ? "Captured" : "Updated"} {formatDateTime(timestamp)}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button className="h-7 px-2 text-xs" size="sm" type="button" variant="outline" aria-label={`Load ${mode} input ${label}`} onClick={() => onLoad(entry)}>
            Load
          </Button>
          {mode === "personal" ? (
            <>
              <Button className="h-7 px-2 text-xs" disabled={updatePending} size="sm" type="button" variant="outline" aria-label={`Overwrite personal input ${label}`} onClick={() => onUpdate(entry)}>
                {updatePending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : null}
                Overwrite
              </Button>
              <Button className="h-7 px-2 text-xs" disabled={deletePending} size="sm" type="button" variant="ghost" aria-label={`Delete personal input ${label}`} onClick={() => onDelete(entry)}>
                {deletePending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <Trash2 className="size-3" data-icon="inline-start" />}
                Delete
              </Button>
            </>
          ) : null}
        </div>
      </div>
      {entry.stale.stale ? (
        <div className="rounded-md border border-chart-3/30 bg-chart-3/10 px-2 py-1 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">Saved against older workflow metadata.</p>
          {staleReasons.length > 0 ? (
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {staleReasons.map((reason) => (
                <li key={`${entry.id}-${reason.field}-${reason.issue}`}>{reason.field}: {reason.issue}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function SavedInputsHelper(props: {
  createDisabled: boolean;
  createPending: boolean;
  deletePending: boolean;
  error: Error | null;
  historyEntries: readonly WorkflowPackageRuntimeInputEntryRead[];
  loading: boolean;
  personalEntries: readonly WorkflowPackageRuntimeInputEntryRead[];
  presetName: string;
  updatePending: boolean;
  workflowKey: string;
  onCreate: () => void;
  onDelete: (entry: WorkflowPackageRuntimeInputEntryRead) => void;
  onLoad: (entry: WorkflowPackageRuntimeInputEntryRead) => void;
  onPresetNameChange: (value: string) => void;
  onUpdate: (entry: WorkflowPackageRuntimeInputEntryRead) => void;
}) {
  const {
    createDisabled,
    createPending,
    deletePending,
    error,
    historyEntries,
    loading,
    onCreate,
    onDelete,
    onLoad,
    onPresetNameChange,
    onUpdate,
    personalEntries,
    presetName,
    updatePending,
    workflowKey,
  } = props;
  const personalLimitReached = personalEntries.length >= SAVED_INPUT_ENTRY_LIMIT;
  const sortedPersonal = newestRuntimeInputEntries(personalEntries, "updatedAt");
  const sortedHistory = newestRuntimeInputEntries(historyEntries, "createdAt");

  return (
    <div className="space-y-3 rounded-xl border bg-muted/20 p-3" data-testid="runtime-input-saved-inputs-helper">
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2">
          <h4 className="text-sm font-semibold">Saved Inputs</h4>
          <Badge variant="outline">{workflowKey || "workflow"}</Badge>
        </div>
        <p className="text-xs text-muted-foreground">Load presets or prior launch inputs into the raw JSON editor. Loading never queues a run.</p>
      </div>
      {loading ? (
        <div className="flex items-center gap-2 rounded-lg border bg-background/60 p-3 text-xs text-muted-foreground">
          <Loader2 className="size-3 animate-spin" />
          Loading saved inputs for {workflowKey || "this workflow"}...
        </div>
      ) : null}
      {error ? (
        <Alert variant="destructive">
          <AlertCircle />
          <AlertTitle>Saved inputs unavailable</AlertTitle>
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      ) : null}
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h5 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Personal</h5>
          <Badge variant="secondary">{personalEntries.length}/{SAVED_INPUT_ENTRY_LIMIT}</Badge>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input className="h-8 text-xs" aria-label="Personal preset name" placeholder="Preset name" value={presetName} onChange={(event) => onPresetNameChange(event.target.value)} />
          <Button className="h-8 text-xs" disabled={createDisabled || createPending || personalLimitReached} size="sm" type="button" onClick={onCreate}>
            {createPending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <Save data-icon="inline-start" />}
            Save current JSON
          </Button>
        </div>
        {personalLimitReached ? <p className="text-xs text-destructive">Personal presets are capped at 20 per workflow. Delete one before saving another.</p> : null}
        {sortedPersonal.length === 0 ? <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">No personal presets saved for this workflow.</p> : null}
        <div className="space-y-2">
          {sortedPersonal.map((entry) => (
            <SavedInputEntryRow key={entry.id} deletePending={deletePending} entry={entry} mode="personal" updatePending={updatePending} onDelete={onDelete} onLoad={onLoad} onUpdate={onUpdate} />
          ))}
        </div>
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h5 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">History</h5>
          <Badge variant="secondary">{historyEntries.length}/{SAVED_INPUT_ENTRY_LIMIT}</Badge>
        </div>
        {sortedHistory.length === 0 ? <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">No launch history captured for this workflow yet.</p> : null}
        <div className="space-y-2">
          {sortedHistory.map((entry) => (
            <SavedInputEntryRow key={entry.id} deletePending={false} entry={entry} mode="history" updatePending={false} onDelete={onDelete} onLoad={onLoad} onUpdate={onUpdate} />
          ))}
        </div>
      </div>
    </div>
  );
}

function LaunchTab(props: {
  createLaunch: ReturnType<typeof useCreateWorkflowPackageLaunch>;
  launchRead: WorkflowPackageLaunchRead | undefined;
  launchLoading: boolean;
  onRunPreflight: () => Promise<WorkflowPackageLaunchRead | null>;
  packageId: string | undefined;
  setWorkflowKey: (workflowKey: string) => void;
  workflowKey: string;
}) {
  const { createLaunch, launchRead, launchLoading, onRunPreflight, packageId, setWorkflowKey, workflowKey } = props;
  const navigate = useNavigate();
  const [parametersText, setParametersText] = useState(() => stringifyJson({}));
  const [runtimeInputErrors, setRuntimeInputErrors] = useState<ApiErrorDetail[]>([]);
  const [personalPresetName, setPersonalPresetName] = useState("");
  const resolvedWorkflowKey = workflowKey.trim();
  const runtimeInputRegistry = useWorkflowPackageRuntimeInputRegistry(packageId, resolvedWorkflowKey);
  const createPersonalEntry = useCreateWorkflowPackageRuntimeInputPersonalEntry();
  const updatePersonalEntry = useUpdateWorkflowPackageRuntimeInputPersonalEntry();
  const deletePersonalEntry = useDeleteWorkflowPackageRuntimeInputPersonalEntry();
  const inputSchemaFingerprint = useMemo(() => stringifyJson(launchRead?.inputSchema), [launchRead?.inputSchema]);
  const inputSchemaSnapshot = useMemo(() => inputSchemaFingerprint ? JSON.parse(inputSchemaFingerprint) as unknown : undefined, [inputSchemaFingerprint]);
  const inputTemplate = useMemo(() => createLaunchParametersTemplate(inputSchemaSnapshot), [inputSchemaSnapshot]);
  const launchDiagnostics = useMemo(() => diagnosticsFromLaunch(launchRead), [launchRead]);
  const launchFormIdentity = `${packageId ?? ""}:${workflowKey}:${inputSchemaFingerprint}`;

  useEffect(() => {
    setParametersText(resetLaunchParametersTemplate(inputTemplate));
    setRuntimeInputErrors([]);
  }, [inputTemplate, launchFormIdentity]);

  const resetParameters = () => {
    setParametersText(resetLaunchParametersTemplate(inputTemplate));
    setRuntimeInputErrors([]);
  };

  const parseCurrentRuntimeInputs = () => {
    setRuntimeInputErrors([]);
    try {
      return parseLaunchParametersJson(parametersText);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Runtime inputs JSON must be a valid object.";
      setRuntimeInputErrors([{ field: "parameters", issue: message }]);
      toast.error(message);
      return null;
    }
  };

  const loadSavedInput = (entry: WorkflowPackageRuntimeInputEntryRead) => {
    setParametersText(stringifyJson(entry.payload));
    setRuntimeInputErrors([]);
    toast.success("Saved input loaded into the JSON editor");
  };

  const savePersonalInput = async () => {
    if (!packageId || !resolvedWorkflowKey) {
      return;
    }
    const name = personalPresetName.trim();
    if (!name) {
      toast.error("Name this personal preset before saving it.");
      return;
    }
    const payload = parseCurrentRuntimeInputs();
    if (!payload) {
      return;
    }
    try {
      await createPersonalEntry.mutateAsync({
        packageId,
        payload: { name, payload },
        workflowKey: resolvedWorkflowKey,
      });
      setPersonalPresetName("");
      toast.success("Saved personal runtime input preset");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save personal runtime input preset.");
    }
  };

  const overwritePersonalInput = async (entry: WorkflowPackageRuntimeInputEntryRead) => {
    if (!packageId || !resolvedWorkflowKey) {
      return;
    }
    const payload = parseCurrentRuntimeInputs();
    if (!payload) {
      return;
    }
    const name = personalPresetName.trim() || entry.name;
    try {
      await updatePersonalEntry.mutateAsync({
        entryId: entry.id,
        packageId,
        payload: { name: name || null, payload },
        workflowKey: resolvedWorkflowKey,
      });
      setPersonalPresetName("");
      toast.success("Updated personal runtime input preset");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to update personal runtime input preset.");
    }
  };

  const deletePersonalInput = async (entry: WorkflowPackageRuntimeInputEntryRead) => {
    if (!packageId || !resolvedWorkflowKey) {
      return;
    }
    try {
      await deletePersonalEntry.mutateAsync({
        entryId: entry.id,
        packageId,
        workflowKey: resolvedWorkflowKey,
      });
      toast.success("Deleted personal runtime input preset");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to delete personal runtime input preset.");
    }
  };

  const launchPackage = async () => {
    if (!packageId) {
      return;
    }
    setRuntimeInputErrors([]);
    let parameters: UnknownRecord;
    try {
      parameters = parseLaunchParametersJson(parametersText);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Runtime inputs JSON must be a valid object.";
      setRuntimeInputErrors([{ field: "parameters", issue: message }]);
      toast.error(message);
      return;
    }
    try {
      const preflight = await onRunPreflight();
      if (preflight && !preflight.ready) {
        toast.error("Resolve blocking preflight diagnostics before launch.");
        return;
      }
      const run = await createLaunch.mutateAsync({
        packageId,
        payload: { parameters, workflowKey: workflowKey || null },
      });
      toast.success("Package run queued");
      navigate(`/runs/${run.id}`);
    } catch (error) {
      if (error instanceof ApiRequestError && error.details.length > 0) {
        setRuntimeInputErrors(error.details);
      }
      toast.error(error instanceof Error ? error.message : "Failed to launch workflow package.");
    }
  };

  return (
    <Card className="border-border/70 bg-card/80 shadow-sm backdrop-blur" data-testid="workflow-package-launch-tab">
      <CardHeader className="border-b pb-4">
        <CardTitle>Launch package run</CardTitle>
        <CardDescription>Select a workflow key, provide runtime inputs, preflight, then queue a run from the current package.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        <div className="space-y-2"><Label htmlFor="workflow-key">Workflow key</Label><Input id="workflow-key" aria-label="Workflow key" placeholder="Workflow key" value={workflowKey} onChange={(event) => setWorkflowKey(event.target.value)} /></div>
        {launchLoading ? <div className="rounded-xl border bg-muted/30 p-4 text-sm text-muted-foreground">Loading launch metadata...</div> : null}
        <ModelConnectionModeSummary diagnostics={launchDiagnostics} read={launchRead} />
        <Card className="bg-background/60">
          <CardHeader>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="space-y-1">
                <CardTitle className="text-base">Runtime inputs</CardTitle>
                <CardDescription>Edit the schema-derived template as raw JSON. Launch parameters must remain a JSON object.</CardDescription>
              </div>
              <Button size="sm" type="button" variant="outline" onClick={resetParameters}>Reset to template</Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {!inputTemplate.schemaSupported ? (
              <Alert className="border-chart-3/30 bg-chart-3/10">
                <AlertCircle />
                <AlertTitle>Schema template started empty</AlertTitle>
                <AlertDescription>
                  <p>{inputTemplate.reason}</p>
                  {inputTemplate.issues.length > 0 ? (
                    <ul className="list-disc pl-5">
                      {inputTemplate.issues.map((issue) => <li key={`${issue.field}-${issue.issue}`}>{issue.field}: {issue.issue}</li>)}
                    </ul>
                  ) : null}
                </AlertDescription>
              </Alert>
            ) : null}
            <RuntimeInputValidationAlert errors={runtimeInputErrors} />
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
              <div className="space-y-2">
                <Label htmlFor="runtime-json">Runtime inputs JSON</Label>
                <Textarea id="runtime-json" aria-label="Runtime inputs JSON" className="min-h-72 font-mono text-xs" rows={14} value={parametersText} onChange={(event) => setParametersText(event.target.value)} />
              </div>
              <SavedInputsHelper
                createDisabled={!packageId || !resolvedWorkflowKey || !personalPresetName.trim() || runtimeInputRegistry.isPending || runtimeInputRegistry.isFetching}
                createPending={createPersonalEntry.isPending}
                deletePending={deletePersonalEntry.isPending}
                error={runtimeInputRegistry.isError ? runtimeInputRegistry.error : null}
                historyEntries={runtimeInputRegistry.data?.history ?? []}
                loading={runtimeInputRegistry.isPending || runtimeInputRegistry.isFetching}
                personalEntries={runtimeInputRegistry.data?.personal ?? []}
                presetName={personalPresetName}
                updatePending={updatePersonalEntry.isPending}
                workflowKey={resolvedWorkflowKey}
                onCreate={() => void savePersonalInput()}
                onDelete={(entry) => void deletePersonalInput(entry)}
                onLoad={loadSavedInput}
                onPresetNameChange={setPersonalPresetName}
                onUpdate={(entry) => void overwritePersonalInput(entry)}
              />
            </div>
          </CardContent>
        </Card>
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
          <Button disabled={!packageId || launchLoading} type="button" variant="outline" onClick={() => void onRunPreflight()}><FileCheck2 data-icon="inline-start" />Run preflight</Button>
          <Button disabled={!packageId || createLaunch.isPending || launchLoading} type="button" onClick={() => void launchPackage()}>{createLaunch.isPending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <PlayCircle data-icon="inline-start" />}Launch Run</Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ExportsTab(props: {
  confirmDiscardChanges: (action: string) => boolean;
  draft: WorkflowPackageDraft;
  importPackage: ReturnType<typeof useImportWorkflowPackage>;
  onImportComplete: (imported: WorkflowPackageRead) => void;
  packageId: string | undefined;
}) {
  const { confirmDiscardChanges, draft, importPackage, onImportComplete, packageId } = props;
  const generatedManifestSource = useMemo(() => workflowPackageDraftToManifestSource(draft), [draft]);
  const [exportPreview, setExportPreview] = useState(generatedManifestSource);
  const exportHref = packageId ? exportWorkflowPackageUrl(packageId) : undefined;

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
          toast.error(error instanceof Error ? error.message : "Failed to load export preview.");
        }
      });

    return () => {
      active = false;
    };
  }, [exportHref, generatedManifestSource]);

  const importManifest = async (payload: WorkflowPackageImportRequest) => {
    if (!confirmDiscardChanges("import this package")) {
      return null;
    }
    try {
      const imported = await importPackage.mutateAsync(payload);
      onImportComplete(imported);
      toast.success("Imported package");
      return imported;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to import package.");
      return null;
    }
  };

  return (
    <Card className="border-border/70 bg-card/80 shadow-sm backdrop-blur" data-testid="workflow-package-exports-tab">
      <CardHeader className="border-b pb-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><CardTitle>Package import / export</CardTitle><CardDescription>Download and import package manifests as plain YAML. Package-private MCP inline values remain visible in the manifest.</CardDescription></div><div className="flex flex-wrap gap-2">{exportHref ? <Button asChild size="sm"><a href={exportHref} download><Download data-icon="inline-start" />Download YAML</a></Button> : null}<WorkflowPackageImportDialog isPending={importPackage.isPending} onImport={importManifest} /></div></div>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        <Textarea aria-label="Package YAML preview" className="min-h-96 font-mono text-xs" readOnly value={exportPreview} />
      </CardContent>
    </Card>
  );
}

export function WorkflowPackageEditorPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { packageId } = useParams<{ packageId: string }>();
  const isNew = location.pathname === "/workflow-packages/new";
  const packageQuery = useWorkflowPackage(isNew ? undefined : packageId);
  const manifestQuery = useWorkflowPackageManifest(isNew ? undefined : packageId);
  const workflowPackage = packageQuery.data;
  const editorShellRef = useRef<HTMLDivElement>(null);
  const pendingTabScrollTop = useRef<number | null>(null);
  const previousPathname = useRef(location.pathname);
  const [activeTab, setActiveTab] = useState<WorkflowPackageEditorTab>(() => routeTab(location.pathname));
  const [draft, setDraft] = useState<WorkflowPackageDraft>(() => createWorkflowPackageDraft());
  const [isDirty, setIsDirty] = useState(false);
  const [issues, setIssues] = useState<WorkflowPackageEditorIssue[]>([]);
  const [diagnosticTarget, setDiagnosticTarget] = useState<DiagnosticTarget>(null);
  const [initializedManifestIdentity, setInitializedManifestIdentity] = useState<string | null>(isNew ? "new" : null);
  const [workflowKey, setWorkflowKey] = useState("");
  const [preflightRead, setPreflightRead] = useState<WorkflowPackageLaunchRead | undefined>(undefined);
  const createPackage = useCreateWorkflowPackage();
  const updatePackage = useUpdateWorkflowPackage();
  const validatePackage = useValidateWorkflowPackageManifest();
  const preflightPackage = usePreflightWorkflowPackage();
  const createLaunch = useCreateWorkflowPackageLaunch();
  const importPackage = useImportWorkflowPackage();
  const launchQuery = useWorkflowPackageLaunch(isNew ? undefined : packageId, workflowKey.trim() || undefined);
  const modelConnectionsQuery = useModelConnections();
  const toolsQuery = useTools();
  const secretBindingsQuery = useWorkflowPackageSecretBindings(isNew ? undefined : packageId);
  const upsertSecretBinding = useUpsertWorkflowPackageSecretBinding();
  const deleteSecretBinding = useDeleteWorkflowPackageSecretBinding();

  const selectEditorTab = (tab: WorkflowPackageEditorTab) => {
    pendingTabScrollTop.current = editorShellRef.current?.scrollTop ?? null;
    setActiveTab(tab);
  };

  useLayoutEffect(() => {
    const scrollTop = pendingTabScrollTop.current;
    if (scrollTop === null) {
      return;
    }
    pendingTabScrollTop.current = null;
    const editorShell = editorShellRef.current;
    if (!editorShell) {
      return;
    }
    editorShell.scrollTop = scrollTop;
    const frame = window.requestAnimationFrame(() => {
      editorShell.scrollTop = scrollTop;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [activeTab]);

  useEffect(() => {
    if (previousPathname.current === location.pathname) {
      return;
    }
    previousPathname.current = location.pathname;
    setActiveTab(routeTab(location.pathname));
  }, [location.pathname]);

  const parsedManifest = useMemo(() => {
    if (isNew || !manifestQuery.data) {
      return null;
    }
    return packageDraftFromManifestSource(manifestQuery.data.manifestSource);
  }, [isNew, manifestQuery.data]);

  useEffect(() => {
    if (isNew) {
      if (initializedManifestIdentity !== "new") {
        setDraft(createWorkflowPackageDraft());
        setIssues([]);
        setDiagnosticTarget(null);
        setInitializedManifestIdentity("new");
        setIsDirty(false);
      }
      return;
    }
    if (!manifestQuery.data || !parsedManifest || parsedManifest.errors.length > 0) {
      return;
    }
    const nextIdentity = manifestIdentity(manifestQuery.data);
    if (initializedManifestIdentity === nextIdentity || (isDirty && initializedManifestIdentity !== null)) {
      return;
    }
    setDraft(parsedManifest.draft);
    setIssues([]);
    setDiagnosticTarget(null);
    setInitializedManifestIdentity(nextIdentity);
    setIsDirty(false);
  }, [initializedManifestIdentity, isDirty, isNew, manifestQuery.data, parsedManifest]);

  useEffect(() => {
    if (launchQuery.data?.workflowKey && !workflowKey) {
      setWorkflowKey(launchQuery.data.workflowKey);
    }
  }, [launchQuery.data?.workflowKey, workflowKey]);

  const headerDescription = workflowPackage?.description || (isNew ? "Create a package manifest shell before adding private agents, schemas, profiles, MCP bindings, and launch flows." : "Package-local authoring shell for resources that must not become standalone global pages.");
  const localIssues = useMemo(() => validateWorkflowPackageDraft(draft), [draft]);
  const combinedIssues = [...localIssues, ...issues];
  const modelConnectionOptions = (modelConnectionsQuery.data?.items ?? []).map((connection) => ({ description: `${connection.modelId} · ${connection.apiStyle} · ${connectionKindLabel(connection.connectionKind)}`, label: connection.name, value: connection.key }));
  const launchDiagnostics = diagnosticsFromLaunch(preflightRead ?? launchQuery.data);
  const referencedSecretKeys = useMemo(() => collectSecretReferenceKeys(draft.spec.workflows), [draft.spec.workflows]);
  const isSaving = createPackage.isPending || updatePackage.isPending;
  const manifestParseErrors = parsedManifest?.errors ?? [];
  const manifestLoadError = manifestQuery.error instanceof Error ? manifestQuery.error.message : "Failed to load package manifest.";
  const packageLoadError = packageQuery.error instanceof Error ? packageQuery.error.message : "Failed to load workflow package.";
  const editorBlocker = !isNew && packageQuery.isError
    ? { errors: [packageLoadError], title: "Package identity could not be loaded" }
    : !isNew && manifestQuery.isError
      ? { errors: [manifestLoadError], title: "Package manifest could not be loaded" }
      : !isNew && manifestParseErrors.length > 0
        ? { errors: manifestParseErrors, title: "Package manifest could not be parsed" }
        : null;
  const isEditorBlocked = editorBlocker !== null;

  const updateDraft = (nextDraft: WorkflowPackageDraft) => {
    setIsDirty(true);
    setDraft(nextDraft);
  };

  const clearTransientEditorState = () => {
    setPreflightRead(undefined);
    setIssues([]);
    setDiagnosticTarget(null);
    setIsDirty(false);
  };

  const discardLoadedDraftState = () => {
    clearTransientEditorState();
    setInitializedManifestIdentity(null);
  };

  const confirmDiscardUnsavedChanges = (action: string) => {
    if (!isDirty) {
      return true;
    }
    return window.confirm(`You have unsaved changes. Discard them and ${action}?`);
  };

  const retryManifestLoad = () => {
    if (!confirmDiscardUnsavedChanges("retry the manifest load")) {
      return;
    }
    if (isDirty) {
      discardLoadedDraftState();
    }
    if (packageQuery.isError) {
      void packageQuery.refetch();
    }
    void manifestQuery.refetch();
  };

  const handleImportSuccess = (imported: WorkflowPackageRead) => {
    clearTransientEditorState();
    setWorkflowKey("");
    navigate(`/workflow-packages/${imported.id}`);
  };

  const focusIssue = (issue: WorkflowPackageEditorIssue) => {
    const target = diagnosticToEditorTarget(issue.field);
    setDiagnosticTarget(target);
    setActiveTab(target.tab);
    window.setTimeout(() => {
      const field = document.querySelector<HTMLElement>(`[data-field="${CSS.escape(issue.field)}"]`) ?? document.querySelector<HTMLElement>(`[data-field="${CSS.escape(target.field)}"]`);
      field?.focus();
      field?.scrollIntoView({ block: "center", inline: "nearest" });
    }, 50);
  };

  const focusPackageDiagnostic = (diagnostic: PackageDiagnostic) => {
    focusIssue({ field: diagnostic.field, issue: diagnostic.issue, tab: diagnosticToEditorTarget(diagnostic.field).tab });
  };

  const saveSecretBinding = async (key: string, value: string) => {
    if (!packageId) {
      toast.error("Save the package before binding secrets.");
      return;
    }
    try {
      await upsertSecretBinding.mutateAsync({ key, packageId, payload: { value } });
      toast.success(`Secret binding ${key} saved`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Secret binding save failed.");
    }
  };

  const removeSecretBinding = async (key: string) => {
    if (!packageId) {
      return;
    }
    try {
      await deleteSecretBinding.mutateAsync({ key, packageId });
      toast.success(`Secret binding ${key} deleted`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Secret binding delete failed.");
    }
  };

  const runPackagePreflight = async (): Promise<WorkflowPackageLaunchRead | null> => {
    if (!packageId) {
      return null;
    }
    try {
      const result = await preflightPackage.mutateAsync({ packageId, payload: { workflowKey: workflowKey || null, parameters: {} } });
      setPreflightRead(result);
      const diagnostics = diagnosticsFromLaunch(result);
      const blockingIssue = diagnostics.find((diagnostic) => diagnostic.severity === "error");
      if (blockingIssue) {
        focusPackageDiagnostic(blockingIssue);
        toast.warning("Package preflight found blocking diagnostics");
      } else {
        toast.success(result.warnings.length > 0 ? "Package preflight passed with warnings" : "Package preflight passed");
      }
      return result;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Package preflight failed.");
      return null;
    }
  };

  const validateCurrentDraft = async () => {
    if (isEditorBlocked) {
      toast.error("Load a valid package manifest before validating.");
      return;
    }
    const manifestSource = workflowPackageDraftToManifestSource(draft);
    const result = await validatePackage.mutateAsync({ manifestSource });
    const backendIssues = mapBackendDiagnostics(result.diagnostics);
    setIssues(backendIssues);
    if (backendIssues[0]) {
      focusIssue(backendIssues[0]);
    }
    toast[backendIssues.some((issue) => issue.issue) ? "warning" : "success"](backendIssues.length > 0 ? "Package validation returned diagnostics" : "Package validation passed");
  };

  const savePackage = async () => {
    if (isEditorBlocked) {
      toast.error("Load a valid package manifest before saving.");
      return;
    }
    const nextIssues = validateWorkflowPackageDraft(draft);
    setIssues(nextIssues);
    if (nextIssues[0]) {
      focusIssue(nextIssues[0]);
      toast.error("Resolve package editor validation before saving.");
      return;
    }
    const manifestSource = workflowPackageDraftToManifestSource(draft);
    if (isNew) {
      const created = await createPackage.mutateAsync({ manifestSource });
      clearTransientEditorState();
      setWorkflowKey("");
      toast.success("Workflow package created");
      navigate(`/workflow-packages/${created.id}`);
      return;
    }
    if (packageId) {
      await updatePackage.mutateAsync({ packageId, payload: { manifestSource } });
      clearTransientEditorState();
      toast.success("Workflow package saved");
    }
  };

  if (!isNew && (packageQuery.isPending || manifestQuery.isPending)) {
    return <EditorSkeleton />;
  }

  return (
    <div ref={editorShellRef} className="flex h-full flex-col gap-4 overflow-y-auto p-4 font-['Fira_Sans',ui-sans-serif,system-ui,sans-serif]" data-testid="workflow-package-editor-shell">
      <Card className="border-border/70 bg-card/80 shadow-sm backdrop-blur">
        <CardContent className="flex flex-col gap-4 p-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 space-y-3"><div className="flex flex-wrap items-center gap-2">{location.pathname.endsWith("/run") ? <Badge variant="secondary">Launch route</Badge> : null}{combinedIssues.length > 0 ? <Badge variant="destructive">{combinedIssues.length} diagnostics</Badge> : null}</div><div className="space-y-1"><h1 className="text-xl font-semibold tracking-tight">{packageTitle(workflowPackage, isNew)}</h1><p className="font-['Fira_Code',ui-monospace,monospace] text-xs text-muted-foreground">{packageSubtitle(workflowPackage, isNew)}</p><p className="max-w-3xl text-sm text-muted-foreground">{headerDescription}</p></div></div>
          <div className="flex flex-col gap-2 sm:flex-row lg:justify-end"><Button aria-label="Save package" className="cursor-pointer" disabled={isSaving || isEditorBlocked} type="button" size="sm" variant="outline" onClick={() => void savePackage()}><Save data-icon="inline-start" />Save</Button><Button aria-label="Run package preflight" className="cursor-pointer" disabled={validatePackage.isPending || isEditorBlocked} type="button" size="sm" variant="outline" onClick={() => void validateCurrentDraft()}><FileCheck2 data-icon="inline-start" />Validate</Button><Button aria-label="Launch workflow package" className="cursor-pointer" disabled={isNew || isEditorBlocked} type="button" size="sm" onClick={() => packageId ? navigate(`/workflow-packages/${packageId}/run`) : undefined}><PlayCircle data-icon="inline-start" />Launch</Button></div>
        </CardContent>
      </Card>
      {editorBlocker ? (
        <ManifestBlockingState errors={editorBlocker.errors} loading={packageQuery.isFetching || manifestQuery.isFetching} onRetry={retryManifestLoad} title={editorBlocker.title} />
      ) : (
        <>
          {packageDraftFromManifestSource(workflowPackageDraftToManifestSource(draft)).errors.length > 0 ? <Alert variant="destructive"><AlertTitle>Generated manifest cannot be parsed</AlertTitle><AlertDescription>Review package-local resource fields before saving.</AlertDescription></Alert> : null}
          <Tabs orientation="vertical" value={activeTab} onValueChange={(value) => selectEditorTab(value as WorkflowPackageEditorTab)} className="min-h-0 flex-1 gap-4 lg:grid lg:grid-cols-[16rem_minmax(0,1fr)] lg:items-start">
            <div className="shrink-0">
              <TabsList aria-label="Workflow package editor sections" className="relative z-10 h-auto w-full justify-start bg-muted/60 p-1">
                {editorTabs.map((tab) => { const Icon = tab.icon; return <TabsTrigger key={tab.value} value={tab.value} aria-label={`${tab.label} tab`} className="px-3 py-2" onClick={() => selectEditorTab(tab.value)}><Icon className="size-4" aria-hidden="true" />{tab.label}</TabsTrigger>; })}
              </TabsList>
            </div>
            <div className="min-w-0">
              <TabsContent value="overview" className="mt-0"><OverviewEditor draft={draft} issues={combinedIssues} isNew={isNew} onChange={updateDraft} /></TabsContent>
              <TabsContent value="agents" className="mt-0"><AgentsTab diagnosticTarget={diagnosticTarget} draft={draft} issues={combinedIssues} modelConnectionOptions={modelConnectionOptions} onChange={updateDraft} /></TabsContent>
              <TabsContent value="output-schemas" className="mt-0"><OutputSchemasTab draft={draft} issues={combinedIssues} onChange={updateDraft} /></TabsContent>
              <TabsContent value="capability-profiles" className="mt-0"><CapabilityProfilesTab draft={draft} issues={combinedIssues} onChange={updateDraft} tools={(toolsQuery.data?.items ?? []).map((tool) => ({ description: tool.description, displayName: tool.displayName, key: tool.key }))} toolsError={toolsQuery.error instanceof Error ? toolsQuery.error.message : null} toolsLoading={toolsQuery.isPending} /></TabsContent>
              <TabsContent value="private-mcp" className="mt-0"><PrivateMcpTab draft={draft} issues={combinedIssues} onChange={updateDraft} /></TabsContent>
              <TabsContent value="workflow-yaml" className="mt-0"><WorkflowYamlTab draft={draft} issues={combinedIssues} onChange={updateDraft} /></TabsContent>
              <TabsContent value="secret-bindings" className="mt-0"><SecretBindingsTab bindings={secretBindingsQuery.data?.items ?? []} bindingsError={secretBindingsQuery.error instanceof Error ? secretBindingsQuery.error.message : null} bindingsLoading={secretBindingsQuery.isPending} deleting={deleteSecretBinding.isPending} onDelete={removeSecretBinding} onSave={saveSecretBinding} packageId={packageId} referencedSecretKeys={referencedSecretKeys} saving={upsertSecretBinding.isPending} /></TabsContent>
              <TabsContent value="preflight" className="mt-0"><PreflightTab diagnostics={launchDiagnostics} launchRead={launchQuery.data} loading={preflightPackage.isPending || launchQuery.isPending} onOpenField={focusPackageDiagnostic} onRunPreflight={() => void runPackagePreflight()} preflightRead={preflightRead} workflowPackage={workflowPackage} /></TabsContent>
              <TabsContent value="launch" className="mt-0"><LaunchTab createLaunch={createLaunch} launchRead={launchQuery.data} launchLoading={launchQuery.isPending} onRunPreflight={runPackagePreflight} packageId={packageId} setWorkflowKey={setWorkflowKey} workflowKey={workflowKey} /></TabsContent>
              <TabsContent value="exports" className="mt-0"><ExportsTab confirmDiscardChanges={confirmDiscardUnsavedChanges} draft={draft} importPackage={importPackage} onImportComplete={handleImportSuccess} packageId={packageId} /></TabsContent>
            </div>
          </Tabs>
        </>
      )}
    </div>
  );
}
