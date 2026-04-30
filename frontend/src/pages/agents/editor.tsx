import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Archive,
  ArrowLeft,
  Braces,
  CheckCircle2,
  Code2,
  Copy,
  FileText,
  Keyboard,
  Loader2,
  PlayCircle,
  Save,
  ShieldCheck,
  Wand2,
} from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";

import { ExactJsonPreview } from "@/components/platform-authoring/inspectors/exact-json-preview";
import { SchemaForm } from "@/components/platform-authoring/generated-form/schema-form";
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
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
} from "@/components/ui/command";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import {
  useAgent,
  useArchiveAgent,
  useCreateAgent,
  useCreateAgentRun,
  useUpdateAgent,
  useValidateAgentManifest,
} from "@/hooks/use-agents";
import { ApiRequestError } from "@/lib/api-client";
import {
  createAgentManifestScaffold,
  createAgentManifestSource,
  extractAgentManifestOutline,
  formatAgentManifestYaml,
  mapAgentManifestDiagnosticsForEditor,
  parseAgentManifestLocallyForEditor,
  type AgentManifestOutlineSection,
} from "@/lib/platform-authoring/agents/manifest";
import { stringifyJson } from "@/lib/platform-authoring/common/serialization";
import { parseSchemaJsonText } from "@/lib/platform-authoring/schema/codec";
import { createDefaultSchemaNode } from "@/lib/platform-authoring/schema/factories";
import { buildPreviewValue } from "@/lib/platform-authoring/schema/preview";
import type { SchemaIRNode } from "@/lib/platform-authoring/schema/types";
import { encodeValueEntry, validateAndDecodeValueEntry } from "@/lib/platform-authoring/values/codec";
import type { ValueEntry } from "@/lib/platform-authoring/values/types";
import type { AgentManifestValidationRead, AgentRead } from "@/lib/types/agent";
import type { UnknownRecord } from "@/lib/types/common";

import { PlatformResourceBadges } from "../platform-resource-shared";

type RunLaunchFeedback = {
  message: string;
  title: string;
  variant: "default" | "destructive";
};

type AgentSnippet = {
  description: string;
  id: string;
  label: string;
  shortcut: string;
  text: string;
};

const AGENT_SNIPPETS: AgentSnippet[] = [
  {
    description: "Adds the manifest metadata block with key, name, and description.",
    id: "metadata",
    label: "Metadata block",
    shortcut: "meta",
    text: "metadata:\n  key: new_agent\n  name: New Agent\n  description: Describe what this agent does.\n",
  },
  {
    description: "Adds a block-style system prompt under spec.",
    id: "prompt",
    label: "System prompt",
    shortcut: "prompt",
    text: "systemPrompt: |\n  You are a concise portfolio research assistant.\n",
  },
  {
    description: "Adds a string property for spec.inputSchema.properties.",
    id: "input-schema-field",
    label: "Input schema field",
    shortcut: "input",
    text: "newField:\n  type: string\n  description: Describe this agent input.\n",
  },
  {
    description: "Pins a published output schema by key and version.",
    id: "output-schema-pin",
    label: "Output schema pin",
    shortcut: "schema",
    text: "outputSchema: summary_schema@1\n",
  },
  {
    description: "Adds a published capability pin to spec.capabilities.",
    id: "capability-pin",
    label: "Capability pin",
    shortcut: "capability",
    text: "- summarize_capability@1\n",
  },
  {
    description: "Adds a published MCP server pin to spec.mcpServers.",
    id: "mcp-pin",
    label: "MCP server pin",
    shortcut: "mcp",
    text: "- quotes_mcp@1\n",
  },
];

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function getManifestMetadata(value: unknown) {
  if (!isRecord(value) || !isRecord(value.metadata)) {
    return { description: "", key: "", name: "" };
  }

  return {
    description: typeof value.metadata.description === "string" ? value.metadata.description : "",
    key: typeof value.metadata.key === "string" ? value.metadata.key : "",
    name: typeof value.metadata.name === "string" ? value.metadata.name : "",
  };
}

function formatLocation(line: number | null, column: number | null) {
  if (line === null) {
    return "No source location";
  }

  return column === null ? `Line ${line}` : `Line ${line}, column ${column}`;
}

function getSectionDescription(section: AgentManifestOutlineSection) {
  if (!section.present) {
    return "Missing";
  }

  return formatLocation(section.line, section.column);
}

function readOptionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function readString(value: unknown, fallback: string): string {
  return readOptionalString(value) ?? fallback;
}

function readStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function createDefaultRunInputValue(schema: SchemaIRNode): ValueEntry {
  const previewValue = buildPreviewValue(schema);

  if (isRecord(previewValue)) {
    return encodeValueEntry(previewValue);
  }

  return encodeValueEntry({});
}

function decodeRunInputValue(value: ValueEntry): UnknownRecord {
  const decoded = validateAndDecodeValueEntry(value);

  if (!decoded.ok || !isRecord(decoded.value)) {
    return {};
  }

  return decoded.value;
}

function getConfirmNavigationMessage() {
  return "You have unsaved agent YAML changes. Leave this editor and discard them?";
}

function createDuplicateAgentManifestScaffold(agent: AgentRead): string {
  const parsed = parseAgentManifestLocallyForEditor(agent.manifestSource);
  const manifest = parsed.value;

  if (parsed.isValidYaml && isRecord(manifest) && isRecord(manifest.metadata) && isRecord(manifest.spec)) {
    return createAgentManifestSource({
      budgetUsd: readOptionalString(manifest.spec.budgetUsd),
      description: readOptionalString(manifest.metadata.description),
      inputSchema: manifest.spec.inputSchema ?? { additionalProperties: false, properties: {}, type: "object" },
      key: "new_agent",
      mcpServers: readStringList(manifest.spec.mcpServers),
      modelConnection: readString(manifest.spec.modelConnection, "primary_model_connection"),
      name: `${readString(manifest.metadata.name, agent.name)} Copy`,
      outputSchema: readString(manifest.spec.outputSchema, "summary_schema@1"),
      capabilities: readStringList(manifest.spec.capabilities),
      systemPrompt: readString(manifest.spec.systemPrompt, "You are a concise portfolio research assistant."),
    });
  }

  return createAgentManifestScaffold({ key: "new_agent", name: "New Agent Copy" });
}

export function AgentsEditorPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const duplicateFromId = !agentId ? searchParams.get("duplicateFrom") ?? undefined : undefined;
  const isEditing = Boolean(agentId);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const initializedSourceRef = useRef<string | null>(duplicateFromId || isEditing ? null : "new");

  const [manifestSource, setManifestSource] = useState(() => createAgentManifestScaffold());
  const [cleanManifestSource, setCleanManifestSource] = useState(manifestSource);
  const [isSnippetPaletteOpen, setIsSnippetPaletteOpen] = useState(false);
  const [validationResult, setValidationResult] = useState<AgentManifestValidationRead | null>(null);
  const [validatedManifestSource, setValidatedManifestSource] = useState<string | null>(null);
  const [runInput, setRunInput] = useState<ValueEntry>(() => createDefaultRunInputValue(createDefaultSchemaNode("object")));
  const [runLaunchFeedback, setRunLaunchFeedback] = useState<RunLaunchFeedback | null>(null);

  const agentQuery = useAgent(agentId);
  const duplicateQuery = useAgent(duplicateFromId);
  const createMutation = useCreateAgent();
  const updateMutation = useUpdateAgent();
  const archiveMutation = useArchiveAgent();
  const createAgentRun = useCreateAgentRun();
  const validateAgentManifest = useValidateAgentManifest();

  useEffect(() => {
    if (!isEditing || !agentQuery.data?.manifestSource) {
      return;
    }

    const sourceKey = `edit:${agentQuery.data.id}:${agentQuery.data.manifestHash}`;
    if (initializedSourceRef.current === sourceKey) {
      return;
    }

    initializedSourceRef.current = sourceKey;
    setManifestSource(agentQuery.data.manifestSource);
    setCleanManifestSource(agentQuery.data.manifestSource);
    setValidationResult(null);
    setValidatedManifestSource(null);
  }, [agentQuery.data?.id, agentQuery.data?.manifestHash, agentQuery.data?.manifestSource, isEditing]);

  useEffect(() => {
    if (isEditing || !duplicateFromId || !duplicateQuery.data?.manifestSource) {
      return;
    }

    const sourceKey = `duplicate:${duplicateQuery.data.id}:${duplicateQuery.data.manifestHash}`;
    if (initializedSourceRef.current === sourceKey) {
      return;
    }

    const duplicateManifestSource = createDuplicateAgentManifestScaffold(duplicateQuery.data);
    initializedSourceRef.current = sourceKey;
    setManifestSource(duplicateManifestSource);
    setCleanManifestSource(duplicateManifestSource);
    setValidationResult(null);
    setValidatedManifestSource(null);
  }, [duplicateFromId, duplicateQuery.data, isEditing]);

  const isDirty = manifestSource !== cleanManifestSource;

  useEffect(() => {
    if (!isDirty) {
      return;
    }

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      const legacyReturnValueKey = "returnValue";
      event.preventDefault();
      Object.assign(event, { [legacyReturnValueKey]: "" });
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isDirty]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setIsSnippetPaletteOpen((isOpen) => !isOpen);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const localParse = useMemo(() => parseAgentManifestLocallyForEditor(manifestSource), [manifestSource]);
  const outlineResult = useMemo(() => extractAgentManifestOutline(manifestSource), [manifestSource]);
  const diagnostics = useMemo(
    () =>
      mapAgentManifestDiagnosticsForEditor(localParse.diagnostics, {
        manifestSource,
        origin: "local",
      }),
    [localParse.diagnostics, manifestSource],
  );
  const validationDiagnostics = useMemo(
    () =>
      validationResult
        ? mapAgentManifestDiagnosticsForEditor(validationResult.diagnostics, {
            manifestSource: validatedManifestSource ?? manifestSource,
            origin: "backend",
          })
        : [],
    [manifestSource, validatedManifestSource, validationResult],
  );
  const metadata = useMemo(() => getManifestMetadata(localParse.value), [localParse.value]);
  const lineCount = useMemo(() => manifestSource.split(/\r\n|\r|\n/).length, [manifestSource]);
  const compiledPayloadJson = useMemo(
    () => stringifyJson(validationResult?.compiledPayload),
    [validationResult?.compiledPayload],
  );
  const activeRunInputSchema = validationResult?.runInputSchema ?? agentQuery.data?.inputSchema ?? null;
  const activeRunInputSchemaJson = useMemo(
    () => stringifyJson(activeRunInputSchema ?? { additionalProperties: false, properties: {}, type: "object" }),
    [activeRunInputSchema],
  );
  const activeRunInputSchemaBuilder = useMemo(() => {
    const parsedSchema = parseSchemaJsonText(activeRunInputSchemaJson);
    return parsedSchema.builder ?? createDefaultSchemaNode("object");
  }, [activeRunInputSchemaJson]);
  const runInputPayload = useMemo(() => decodeRunInputValue(runInput), [runInput]);
  const rawRunInputJson = useMemo(() => stringifyJson(runInputPayload), [runInputPayload]);
  const runInputSchemaJson = useMemo(
    () => stringifyJson(validationResult?.runInputSchema),
    [validationResult?.runInputSchema],
  );
  const isSaving = createMutation.isPending || updateMutation.isPending;
  const isValidating = validateAgentManifest.isPending;
  const isLaunchingRun = createAgentRun.isPending;
  const hasLocalErrors = diagnostics.some((diagnostic) => diagnostic.severity === "error");
  const hasBackendErrors = validationDiagnostics.some((diagnostic) => diagnostic.severity === "error");
  const hasBackendWarnings = validationDiagnostics.some((diagnostic) => diagnostic.severity === "warning");
  const isValidationStale = Boolean(validationResult && validatedManifestSource !== manifestSource);

  useEffect(() => {
    setRunInput(createDefaultRunInputValue(activeRunInputSchemaBuilder));
  }, [activeRunInputSchemaBuilder]);

  const confirmDiscardIfDirty = () => !isDirty || window.confirm(getConfirmNavigationMessage());

  const handleClose = () => {
    if (!confirmDiscardIfDirty()) {
      return;
    }

    navigate("/agents");
  };

  const jumpToLine = (line: number | null) => {
    if (!line || !textareaRef.current) {
      return;
    }

    const lines = manifestSource.split(/\r\n|\r|\n/);
    const offset = lines.slice(0, Math.max(0, line - 1)).join("\n").length + (line > 1 ? 1 : 0);
    textareaRef.current.focus();
    textareaRef.current.setSelectionRange(offset, offset);
  };

  const handleFormat = () => {
    const result = formatAgentManifestYaml(manifestSource);
    if (!result.formatted) {
      toast.error(result.diagnostics[0]?.message ?? "Fix YAML errors before formatting");
      return;
    }

    if (result.formatted === manifestSource) {
      toast.success("Agent manifest already formatted");
      return;
    }

    setManifestSource(result.formatted);
    toast.success("Agent manifest formatted");
  };

  const insertSnippet = (snippet: AgentSnippet) => {
    const textarea = textareaRef.current;
    const selectionStart = textarea?.selectionStart ?? manifestSource.length;
    const selectionEnd = textarea?.selectionEnd ?? manifestSource.length;
    const beforeSelection = manifestSource.slice(0, selectionStart);
    const afterSelection = manifestSource.slice(selectionEnd);
    const leadingBreak = beforeSelection && !beforeSelection.endsWith("\n") ? "\n" : "";
    const trailingBreak = afterSelection && snippet.text && !snippet.text.endsWith("\n") ? "\n" : "";
    const insertion = `${leadingBreak}${snippet.text}${trailingBreak}`;
    const nextSource = `${beforeSelection}${insertion}${afterSelection}`;
    const nextCursor = beforeSelection.length + insertion.length;

    setManifestSource(nextSource);
    setIsSnippetPaletteOpen(false);

    const scheduleSelection = window.requestAnimationFrame ?? ((callback: FrameRequestCallback) => window.setTimeout(callback, 0));
    scheduleSelection(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(nextCursor, nextCursor);
    });
  };

  const handleValidate = async () => {
    if (!manifestSource.trim()) {
      toast.error("Agent manifest is required");
      return;
    }

    try {
      const result = await validateAgentManifest.mutateAsync({ manifestSource });
      setValidationResult(result);
      setValidatedManifestSource(manifestSource);

      if (result.diagnostics.some((diagnostic) => diagnostic.severity === "error")) {
        toast.error("Backend validation found manifest errors");
        return;
      }

      if (result.diagnostics.some((diagnostic) => diagnostic.severity === "warning")) {
        toast.success("Backend validation completed with warnings");
        return;
      }

      toast.success("Backend validation passed");
    } catch (error) {
      const message = error instanceof ApiRequestError ? error.message : "Failed to validate agent manifest";
      toast.error(message);
    }
  };

  const handleSave = async () => {
    if (!manifestSource.trim()) {
      toast.error("Agent manifest is required");
      return;
    }

    try {
      if (isEditing && agentId) {
        const updatedAgent = await updateMutation.mutateAsync({
          agentId,
          payload: { manifestSource },
        });
        setCleanManifestSource(manifestSource);
        toast.success("Agent manifest saved");
        if (String(updatedAgent.id) !== agentId) {
          navigate(`/agents/${updatedAgent.id}/edit`, { replace: true });
        }
        return;
      }

      const createdAgent = await createMutation.mutateAsync({ manifestSource });
      setCleanManifestSource(manifestSource);
      toast.success("Agent created from manifest");
      navigate(`/agents/${createdAgent.id}/edit`);
    } catch (error) {
      const message = error instanceof ApiRequestError ? error.message : "Failed to save agent manifest";
      toast.error(message);
    }
  };

  const handleDuplicate = () => {
    if (!agentId) {
      return;
    }

    if (!confirmDiscardIfDirty()) {
      return;
    }

    navigate(`/agents/new?duplicateFrom=${agentId}`);
  };

  const handleArchive = async () => {
    if (!agentId) {
      return;
    }

    if (!confirmDiscardIfDirty()) {
      return;
    }

    try {
      await archiveMutation.mutateAsync(agentId);
      toast.success("Agent archived");
      navigate("/agents");
    } catch (error) {
      const message = error instanceof ApiRequestError ? error.message : "Failed to archive agent";
      toast.error(message);
    }
  };

  const handleLaunchRun = async () => {
    if (!agentId || !agentQuery.data) {
      setRunLaunchFeedback({
        message: "Save the agent before launching a run.",
        title: "Run launch unavailable",
        variant: "destructive",
      });
      return;
    }

    if (isDirty) {
      setRunLaunchFeedback({
        message: "Save the YAML first. Runs always launch the last saved agent version, not unsaved editor text.",
        title: "Save required before run",
        variant: "destructive",
      });
      return;
    }

    try {
      const run = await createAgentRun.mutateAsync({
        agentId,
        payload: runInputPayload,
        version: agentQuery.data.version,
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
    return (
      <div className="flex h-full items-center justify-center bg-background" data-testid="agent-yaml-editor-shell">
        <Loader2 className="size-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isEditing && agentQuery.isError) {
    return (
      <div className="flex h-full items-center justify-center bg-background p-6" data-testid="agent-yaml-editor-shell">
        <Alert variant="destructive" className="max-w-xl">
          <AlertCircle />
          <AlertTitle>Unable to load agent</AlertTitle>
          <AlertDescription>
            {agentQuery.error instanceof Error ? agentQuery.error.message : "The agent could not be loaded."}
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-background" data-testid="agent-yaml-editor-shell">
      <div className="sticky top-0 border-b border-border bg-card px-4 py-3" data-testid="agent-command-bar">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
          <div className="flex min-w-0 flex-wrap items-center gap-2 xl:flex-1">
            <Button aria-label="Back to agents" onClick={handleClose} size="icon" variant="ghost">
              <ArrowLeft data-icon="inline-start" />
            </Button>
            <Separator className="hidden h-5 sm:block" orientation="vertical" />
            <Badge variant="secondary">YAML manifest</Badge>
            {duplicateFromId ? <Badge variant="outline">Duplicate source</Badge> : null}
            {agentQuery.data ? (
              <PlatformResourceBadges status={agentQuery.data.status} version={agentQuery.data.version} />
            ) : null}
            {isDirty ? (
              <Badge data-testid="agent-dirty-indicator" variant="outline">
                Unsaved changes
              </Badge>
            ) : (
              <Badge data-testid="agent-dirty-indicator" variant="secondary">
                Saved baseline
              </Badge>
            )}
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">
                {metadata.name || agentQuery.data?.name || (duplicateFromId ? "Duplicate Agent" : isEditing ? "Agent manifest" : "New Agent")}
              </p>
              <p className="truncate text-xs text-muted-foreground">
                {metadata.key || agentQuery.data?.key || "metadata.key will identify this agent"}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 border-t border-border/60 pt-3 sm:justify-end xl:ml-auto xl:border-t-0 xl:pt-0">
            <Button data-testid="agents-open-snippets" onClick={() => setIsSnippetPaletteOpen(true)} size="sm" variant="outline">
              <Keyboard data-icon="inline-start" />
              Snippets
            </Button>
            <Button data-testid="agents-format-manifest" onClick={handleFormat} size="sm" variant="ghost">
              <Wand2 data-icon="inline-start" />
              Format YAML
            </Button>
            <Button data-testid="agents-validate-manifest" disabled={isValidating} onClick={() => void handleValidate()} size="sm" variant="outline">
              {isValidating ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <ShieldCheck data-icon="inline-start" />}
              Validate
            </Button>
            <Button data-testid="agents-save" disabled={isSaving} onClick={() => void handleSave()} size="sm">
              {isSaving ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <Save data-icon="inline-start" />}
              Save Agent
            </Button>
            <Button data-testid="agents-duplicate" disabled={!agentId} onClick={handleDuplicate} size="sm" variant="outline">
              <Copy data-icon="inline-start" />
              Duplicate Agent
            </Button>
            <Button
              data-testid="agents-archive"
              disabled={!agentId || archiveMutation.isPending || agentQuery.data?.status === "archived"}
              onClick={() => void handleArchive()}
              size="sm"
              variant="outline"
            >
              {archiveMutation.isPending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <Archive data-icon="inline-start" />}
              Archive Agent
            </Button>
          </div>
        </div>
      </div>

      <CommandDialog
        description="Insert small YAML snippets at the current cursor without replacing the manifest source."
        onOpenChange={setIsSnippetPaletteOpen}
        open={isSnippetPaletteOpen}
        title="Agent YAML snippets"
      >
        <CommandInput placeholder="Search agent snippets..." />
        <CommandList>
          <CommandEmpty>No snippets found.</CommandEmpty>
          <CommandGroup heading="Insert at cursor">
            {AGENT_SNIPPETS.map((snippet) => (
              <CommandItem
                data-testid={`agent-snippet-${snippet.id}`}
                key={snippet.id}
                onSelect={() => insertSnippet(snippet)}
                value={`${snippet.label} ${snippet.description} ${snippet.shortcut}`}
              >
                <Code2 />
                <div className="min-w-0">
                  <p className="truncate">{snippet.label}</p>
                  <p className="truncate text-xs text-muted-foreground">{snippet.description}</p>
                </div>
                <CommandShortcut>{snippet.shortcut}</CommandShortcut>
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>

      <ResizablePanelGroup className="min-h-0 flex-1" direction="horizontal">
        <ResizablePanel defaultSize={20} minSize={16}>
          <aside className="flex h-full min-h-0 flex-col border-r border-border bg-muted/20" data-testid="agent-outline-rail">
            <div className="flex items-center gap-2 border-b border-border px-4 py-3">
              <Braces className="size-4 text-muted-foreground" />
              <div className="min-w-0">
                <p className="text-sm font-medium">Manifest outline</p>
                <p className="text-xs text-muted-foreground">Jump by source section</p>
              </div>
            </div>
            <ScrollArea className="min-h-0 flex-1">
              <div className="flex flex-col gap-4 p-3">
                <Card className="gap-3" data-testid="agent-manifest-101">
                  <CardHeader className="px-3 pt-3">
                    <CardTitle className="text-sm">Agent Manifest 101</CardTitle>
                    <CardDescription>Describe one runnable agent, then pin the resources it needs.</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-2 px-3 pb-3">
                    <div className="flex flex-col gap-1 rounded-md border border-border bg-background p-2 text-sm">
                      <Badge className="w-fit" variant="outline">apiVersion + kind</Badge>
                      <p className="text-xs text-muted-foreground">Use ledger.agent/v1 and kind: Agent.</p>
                    </div>
                    <div className="flex flex-col gap-1 rounded-md border border-border bg-background p-2 text-sm">
                      <Badge className="w-fit" variant="outline">metadata</Badge>
                      <p className="text-xs text-muted-foreground">Set the key, name, and short purpose users will recognize.</p>
                    </div>
                    <div className="flex flex-col gap-1 rounded-md border border-border bg-background p-2 text-sm">
                      <Badge className="w-fit" variant="outline">spec.systemPrompt</Badge>
                      <p className="text-xs text-muted-foreground">Tell the model how this agent should behave during a run.</p>
                    </div>
                    <div className="flex flex-col gap-1 rounded-md border border-border bg-background p-2 text-sm">
                      <Badge className="w-fit" variant="outline">spec.inputSchema</Badge>
                      <p className="text-xs text-muted-foreground">Define the structured input fields the agent can receive.</p>
                    </div>
                    <div className="flex flex-col gap-1 rounded-md border border-border bg-background p-2 text-sm">
                      <Badge className="w-fit" variant="outline">refs</Badge>
                      <p className="text-xs text-muted-foreground">Pin outputSchema as &lt;key&gt;@&lt;version&gt;, then add capabilities and mcpServers as needed.</p>
                    </div>
                    <p className="text-xs font-medium text-muted-foreground">Validate before Save.</p>
                  </CardContent>
                </Card>

                <Card className="gap-3">
                  <CardHeader className="px-3 pt-3">
                    <CardTitle className="text-sm">Sections</CardTitle>
                    <CardDescription>Required v1 manifest blocks</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-1 px-3 pb-3">
                    {outlineResult.outline.sections.map((section) => (
                      <button
                        className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground disabled:cursor-not-allowed disabled:opacity-60"
                        disabled={!section.present}
                        key={section.id}
                        onClick={() => jumpToLine(section.line)}
                        type="button"
                      >
                        <span className="truncate">{section.label}</span>
                        <span className="shrink-0 text-xs text-muted-foreground">{getSectionDescription(section)}</span>
                      </button>
                    ))}
                  </CardContent>
                </Card>

                <Card className="gap-3">
                  <CardHeader className="px-3 pt-3">
                    <CardTitle className="text-sm">References</CardTitle>
                    <CardDescription>Stable model, schema, capability, and MCP pins</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-2 px-3 pb-3">
                    {outlineResult.outline.refs.length ? (
                      outlineResult.outline.refs.map((ref) => (
                        <button
                          className="rounded-md border border-border bg-background p-2 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground"
                          key={ref.path}
                          onClick={() => jumpToLine(ref.line)}
                          type="button"
                        >
                          <span className="flex items-center justify-between gap-2">
                            <span className="truncate font-medium">{ref.label}</span>
                            <span className="shrink-0 text-xs text-muted-foreground">{formatLocation(ref.line, ref.column)}</span>
                          </span>
                          <span className="mt-1 block truncate font-mono text-xs text-muted-foreground">{ref.ref || "Unpinned"}</span>
                        </button>
                      ))
                    ) : (
                      <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
                        Add spec references to populate the outline.
                      </p>
                    )}
                  </CardContent>
                </Card>
              </div>
            </ScrollArea>
          </aside>
        </ResizablePanel>

        <ResizableHandle withHandle />

        <ResizablePanel defaultSize={55} minSize={34}>
          <section className="flex h-full min-h-0 flex-col bg-background">
            <div className="flex items-center gap-2 border-b border-border bg-muted/40 px-4 py-2">
              <Code2 className="size-4 text-muted-foreground" />
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Source editor</span>
              <span className="ml-auto text-xs text-muted-foreground">{lineCount} lines</span>
            </div>
            <div className="min-h-0 flex-1 p-3">
              <Textarea
                aria-label="Agent manifest YAML"
                className="h-full min-h-0 resize-none rounded-lg border-border bg-background font-mono text-sm leading-6 shadow-none focus-visible:ring-1"
                data-testid="agent-yaml-editor"
                onChange={(event) => setManifestSource(event.target.value)}
                ref={textareaRef}
                spellCheck={false}
                value={manifestSource}
              />
            </div>
          </section>
        </ResizablePanel>

        <ResizableHandle withHandle />

        <ResizablePanel defaultSize={25} minSize={20}>
          <aside className="flex h-full min-h-0 flex-col border-l border-border bg-muted/20" data-testid="agent-inspector-shell">
            <div className="flex items-center gap-2 border-b border-border px-4 py-3">
              <FileText className="size-4 text-muted-foreground" />
              <div className="min-w-0">
                <p className="text-sm font-medium">Inspector</p>
                <p className="text-xs text-muted-foreground">YAML-only agent authoring</p>
              </div>
            </div>
            <ScrollArea className="min-h-0 flex-1">
              <div className="flex flex-col gap-4 p-3">
                <Alert variant={hasLocalErrors ? "destructive" : "default"} data-testid="agent-local-parse-status">
                  {hasLocalErrors ? <AlertCircle /> : <CheckCircle2 />}
                  <AlertTitle>{hasLocalErrors ? "Local parse needs attention" : "Local parse ready"}</AlertTitle>
                  <AlertDescription>
                    {hasLocalErrors
                      ? "Fix local YAML errors before relying on outline details. Backend validation remains authoritative for saved agent rules."
                      : "YAML is locally parseable. Use Validate for backend-authoritative agent checks."}
                  </AlertDescription>
                </Alert>

                <Card className="gap-3" data-testid="agent-validation-panel">
                  <CardHeader className="px-3 pt-3">
                    <CardTitle className="text-sm">Validation</CardTitle>
                    <CardDescription>Local parser feedback and backend diagnostics</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-3 px-3 pb-3">
                    <Alert data-testid="agent-backend-validation-status" variant={validationResult && hasBackendErrors ? "destructive" : "default"}>
                      {validationResult && hasBackendErrors ? <AlertCircle /> : <ShieldCheck />}
                      <AlertTitle>
                        {!validationResult
                          ? "Backend validation not run"
                          : isValidationStale
                            ? "Backend validation is stale"
                            : hasBackendErrors
                              ? "Backend validation found errors"
                              : hasBackendWarnings
                                ? "Backend validation has warnings"
                                : "Backend validation passed"}
                      </AlertTitle>
                      <AlertDescription>
                        {!validationResult
                          ? "Run Validate to resolve model connections, schema pins, capabilities, MCP servers, and compiled agent output against the backend."
                          : isValidationStale
                            ? "The YAML changed after the last backend response. Validate again before trusting these results."
                            : hasBackendErrors
                              ? "Backend diagnostics must be resolved before this manifest can compile cleanly."
                              : hasBackendWarnings
                                ? "The backend returned warnings; review them before saving or running this agent."
                                : "The backend returned a compiled payload and run input schema for this manifest."}
                      </AlertDescription>
                    </Alert>

                    <div className="flex flex-col gap-2" data-testid="agent-validation-feedback">
                      {[...diagnostics, ...validationDiagnostics].length ? (
                        [...diagnostics, ...validationDiagnostics].map((diagnostic) => (
                          <button
                            className="rounded-md border border-border bg-background p-2 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground"
                            key={diagnostic.id}
                            onClick={() => jumpToLine(diagnostic.line)}
                            type="button"
                          >
                            <span className="flex flex-wrap items-center gap-2">
                              <Badge variant={diagnostic.severity === "error" ? "destructive" : "secondary"}>
                                {diagnostic.severity}
                              </Badge>
                              <Badge variant="outline">{diagnostic.origin}</Badge>
                              <span className="text-xs text-muted-foreground">{diagnostic.locationLabel}</span>
                              {diagnostic.path ? <span className="break-all font-mono text-xs text-muted-foreground">{diagnostic.path}</span> : null}
                            </span>
                            <span className="mt-2 block">{diagnostic.message}</span>
                          </button>
                        ))
                      ) : (
                        <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
                          No diagnostics yet.
                        </p>
                      )}
                    </div>
                  </CardContent>
                </Card>

                <Card className="gap-3">
                  <CardHeader className="px-3 pt-3">
                    <CardTitle className="text-sm">Agent metadata</CardTitle>
                    <CardDescription>Read locally and from backend validation</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-3 px-3 pb-3 text-sm">
                    <div>
                      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Key</p>
                      <p className="break-words font-mono">{metadata.key || "Not available"}</p>
                    </div>
                    <div>
                      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Name</p>
                      <p className="break-words">{metadata.name || "Not available"}</p>
                    </div>
                    <div>
                      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Description</p>
                      <p className="break-words text-muted-foreground">{metadata.description || "Not available"}</p>
                    </div>
                    {validationResult?.metadata ? (
                      <div className="rounded-md border border-border bg-background p-2" data-testid="agent-validation-metadata">
                        <div className="mb-2 flex items-center gap-2">
                          <Badge variant="secondary">backend</Badge>
                          {isValidationStale ? <Badge variant="outline">stale</Badge> : null}
                        </div>
                        <div className="flex flex-col gap-2">
                          <div>
                            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">API version</p>
                            <p className="break-words font-mono">{validationResult.metadata.apiVersion}</p>
                          </div>
                          <div>
                            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Key</p>
                            <p className="break-words font-mono">{validationResult.metadata.key}</p>
                          </div>
                          <div>
                            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Name</p>
                            <p className="break-words">{validationResult.metadata.name}</p>
                          </div>
                          <div>
                            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Description</p>
                            <p className="break-words text-muted-foreground">{validationResult.metadata.description || "Not available"}</p>
                          </div>
                        </div>
                      </div>
                    ) : null}
                  </CardContent>
                </Card>

                <Card className="gap-3" data-testid="agent-compiled-panel">
                  <CardHeader className="px-3 pt-3">
                    <CardTitle className="text-sm">Compiled</CardTitle>
                    <CardDescription>Exact raw JSON returned by backend validation</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-3 px-3 pb-3">
                    {isValidationStale ? (
                      <Alert data-testid="agent-compiled-stale" variant="default">
                        <AlertTitle>Compiled preview is stale</AlertTitle>
                        <AlertDescription>Validate again to refresh the backend compiled payload for the edited YAML.</AlertDescription>
                      </Alert>
                    ) : null}
                    {validationResult?.compiledPayload ? (
                      <ExactJsonPreview
                        ariaLabel="Exact raw compiled agent JSON"
                        data-testid="agent-compiled-preview"
                        textareaClassName="min-h-52"
                        value={compiledPayloadJson}
                      />
                    ) : (
                      <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
                        Run Validate to populate the compiled agent preview.
                      </p>
                    )}
                  </CardContent>
                </Card>

                <Card className="gap-3" data-testid="agent-run-input-panel">
                  <CardHeader className="px-3 pt-3">
                    <CardTitle className="text-sm">Launch run</CardTitle>
                    <CardDescription>Submit only the persisted agent version through the compiled input schema.</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-3 px-3 pb-3">
                    {!agentId ? (
                      <Alert data-testid="agent-run-unavailable" variant="destructive">
                        <PlayCircle />
                        <AlertTitle>Run launch unavailable</AlertTitle>
                        <AlertDescription>Save the agent before launching a run.</AlertDescription>
                      </Alert>
                    ) : null}
                    {agentId && isDirty ? (
                      <Alert data-testid="agent-run-unsaved-blocked" variant="destructive">
                        <AlertTitle>Save required before run</AlertTitle>
                        <AlertDescription>
                          Runs always launch the saved agent version. Save the YAML first so the run cannot drift from the persisted manifest.
                        </AlertDescription>
                      </Alert>
                    ) : null}
                    {isValidationStale ? (
                      <Alert data-testid="agent-run-input-stale" variant="default">
                        <AlertTitle>Run input schema preview is stale</AlertTitle>
                        <AlertDescription>Validate again to refresh the backend run input schema for the edited YAML.</AlertDescription>
                      </Alert>
                    ) : null}
                    {validationResult?.runInputSchema ? (
                      <ExactJsonPreview
                        ariaLabel="Exact raw agent run input schema JSON"
                        data-testid="agent-run-input-preview"
                        textareaClassName="min-h-52"
                        value={runInputSchemaJson}
                      />
                    ) : (
                      <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
                        Run Validate to preview the run input schema returned by the backend, or use the saved agent schema below for existing agents.
                      </p>
                    )}
                    {runLaunchFeedback ? (
                      <Alert data-testid="agent-run-feedback" variant={runLaunchFeedback.variant}>
                        <AlertTitle>{runLaunchFeedback.title}</AlertTitle>
                        <AlertDescription>{runLaunchFeedback.message}</AlertDescription>
                      </Alert>
                    ) : null}
                    <div data-testid="agent-run-panel-input-form">
                      <SchemaForm
                        description="Fill the agent run input through the shared schema-driven form instead of editing JSON directly."
                        disabled={!agentId || isDirty || isLaunchingRun}
                        label="Run input"
                        schema={activeRunInputSchemaBuilder}
                        value={runInput}
                        onChange={setRunInput}
                      />
                    </div>
                    <ExactJsonPreview
                      ariaLabel="Exact raw agent run-input JSON"
                      data-testid="agent-run-panel-input-raw-json"
                      textareaClassName="min-h-32"
                      value={rawRunInputJson}
                    />
                    <Button
                      data-testid="agent-run-panel-launch"
                      disabled={!agentId || isDirty || isLaunchingRun}
                      onClick={() => void handleLaunchRun()}
                      size="sm"
                      variant="outline"
                    >
                      {isLaunchingRun ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <PlayCircle data-icon="inline-start" />}
                      Launch saved version {agentQuery.data ? `v${agentQuery.data.version}` : ""}
                    </Button>
                  </CardContent>
                </Card>
              </div>
            </ScrollArea>
          </aside>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
