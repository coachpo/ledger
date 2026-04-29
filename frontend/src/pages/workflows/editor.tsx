import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  Braces,
  CheckCircle2,
  Code2,
  FileText,
  Keyboard,
  Loader2,
  PlayCircle,
  Save,
  ShieldCheck,
  Wand2,
} from "lucide-react";
import { useNavigate, useParams } from "react-router";
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
  useCreateWorkflow,
  useCreateWorkflowRun,
  useUpdateWorkflow,
  useValidateWorkflowManifest,
  useWorkflow,
} from "@/hooks/use-workflows";
import { ApiRequestError } from "@/lib/api-client";
import { stringifyJson } from "@/lib/platform-authoring/common/serialization";
import { parseSchemaJsonText } from "@/lib/platform-authoring/schema/codec";
import { createDefaultSchemaNode } from "@/lib/platform-authoring/schema/factories";
import { buildPreviewValue } from "@/lib/platform-authoring/schema/preview";
import type { SchemaIRNode } from "@/lib/platform-authoring/schema/types";
import { encodeValueEntry, validateAndDecodeValueEntry } from "@/lib/platform-authoring/values/codec";
import type { ValueEntry } from "@/lib/platform-authoring/values/types";
import {
  createWorkflowManifestScaffold,
  extractWorkflowManifestOutline,
  formatWorkflowManifestYaml,
  mapWorkflowManifestDiagnosticsForEditor,
  parseWorkflowManifestLocallyForEditor,
  type WorkflowManifestOutlineSection,
} from "@/lib/platform-authoring/workflows/manifest";
import type { UnknownRecord } from "@/lib/types/common";
import type { WorkflowManifestValidationRead } from "@/lib/types/workflow";

type WorkflowSnippet = {
  description: string;
  id: string;
  label: string;
  shortcut: string;
  text: string;
};

type RunLaunchFeedback = {
  message: string;
  title: string;
  variant: "default" | "destructive";
};

const WORKFLOW_SNIPPETS: WorkflowSnippet[] = [
  {
    description: "Adds a string property for inputSchema.properties.",
    id: "input-property",
    label: "Input property",
    shortcut: "input",
    text: "newField:\n  type: string\n  description: Describe this workflow input.\n",
  },
  {
    description: "Adds an agent slot entry for a step agents list.",
    id: "agent-slot",
    label: "Step agent slot",
    shortcut: "agent",
    text: "- slot: analysis\n  uses: research_agent@1\n  with:\n    ticker: ${{ inputs.ticker }}\n",
  },
  {
    description: "Adds a reference to a previous step output.",
    id: "step-output-ref",
    label: "Step output reference",
    shortcut: "ref",
    text: "${{ steps.research.outputs.analysis }}",
  },
  {
    description: "Adds a workflow output mapping from a step slot.",
    id: "output-from",
    label: "Output mapping",
    shortcut: "output",
    text: "from: ${{ steps.research.outputs.analysis }}\n",
  },
];

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function createDefaultRunInputValue(schema: SchemaIRNode): ValueEntry {
  const previewValue = buildPreviewValue(schema);

  if (isRecord(previewValue) && typeof previewValue.ticker === "string") {
    return encodeValueEntry({ ...previewValue, ticker: "AAPL" });
  }

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

function getSectionDescription(section: WorkflowManifestOutlineSection) {
  if (!section.present) {
    return "Missing";
  }

  return formatLocation(section.line, section.column);
}

export function WorkflowsEditorPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const navigate = useNavigate();
  const isEditing = Boolean(workflowId);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const [manifestSource, setManifestSource] = useState(() => createWorkflowManifestScaffold());
  const [cleanManifestSource, setCleanManifestSource] = useState(manifestSource);
  const [isSnippetPaletteOpen, setIsSnippetPaletteOpen] = useState(false);
  const [validationResult, setValidationResult] = useState<WorkflowManifestValidationRead | null>(null);
  const [validatedManifestSource, setValidatedManifestSource] = useState<string | null>(null);
  const { data: workflow, error: workflowError, isError, isPending } = useWorkflow(workflowId);
  const createWorkflow = useCreateWorkflow();
  const updateWorkflow = useUpdateWorkflow();
  const createWorkflowRun = useCreateWorkflowRun();
  const validateWorkflowManifest = useValidateWorkflowManifest();
  const [runInput, setRunInput] = useState<ValueEntry>(() =>
    createDefaultRunInputValue(createDefaultSchemaNode("object")),
  );
  const [runLaunchFeedback, setRunLaunchFeedback] = useState<RunLaunchFeedback | null>(null);

  useEffect(() => {
    if (workflow?.manifestSource) {
      setManifestSource(workflow.manifestSource);
      setCleanManifestSource(workflow.manifestSource);
      setValidationResult(null);
      setValidatedManifestSource(null);
    }
  }, [workflow?.manifestSource]);

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

  const localParse = useMemo(
    () => parseWorkflowManifestLocallyForEditor(manifestSource),
    [manifestSource],
  );
  const outlineResult = useMemo(
    () => extractWorkflowManifestOutline(manifestSource),
    [manifestSource],
  );
  const diagnostics = useMemo(
    () =>
      mapWorkflowManifestDiagnosticsForEditor(localParse.diagnostics, {
        manifestSource,
        origin: "local",
      }),
    [localParse.diagnostics, manifestSource],
  );
  const metadata = useMemo(() => getManifestMetadata(localParse.value), [localParse.value]);
  const lineCount = useMemo(() => manifestSource.split(/\r\n|\r|\n/).length, [manifestSource]);
  const hasErrors = diagnostics.some((diagnostic) => diagnostic.severity === "error");
  const validationDiagnostics = useMemo(
    () =>
      validationResult
        ? mapWorkflowManifestDiagnosticsForEditor(validationResult.diagnostics, {
            manifestSource: validatedManifestSource ?? manifestSource,
            origin: "backend",
          })
        : [],
    [manifestSource, validatedManifestSource, validationResult],
  );
  const hasBackendErrors = validationDiagnostics.some((diagnostic) => diagnostic.severity === "error");
  const hasBackendWarnings = validationDiagnostics.some((diagnostic) => diagnostic.severity === "warning");
  const isValidationStale = Boolean(validationResult && validatedManifestSource !== manifestSource);
  const compiledPayloadJson = useMemo(
    () => stringifyJson(validationResult?.compiledPayload),
    [validationResult?.compiledPayload],
  );
  const activeRunInputSchema = validationResult?.runInputSchema ?? workflow?.inputSchema ?? null;
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
  const isSaving = createWorkflow.isPending || updateWorkflow.isPending;
  const isValidating = validateWorkflowManifest.isPending;
  const isLaunchingRun = createWorkflowRun.isPending;

  useEffect(() => {
    setRunInput(createDefaultRunInputValue(activeRunInputSchemaBuilder));
  }, [activeRunInputSchemaBuilder]);

  const handleClose = () => navigate("/workflows");

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
    const result = formatWorkflowManifestYaml(manifestSource);
    if (!result.formatted) {
      toast.error(result.diagnostics[0]?.message ?? "Fix YAML errors before formatting");
      return;
    }

    if (result.formatted === manifestSource) {
      toast.success("Workflow manifest already formatted");
      return;
    }

    setManifestSource(result.formatted);
    toast.success("Workflow manifest formatted");
  };

  const handleValidate = async () => {
    if (!manifestSource.trim()) {
      toast.error("Workflow manifest is required");
      return;
    }

    try {
      const result = await validateWorkflowManifest.mutateAsync({ manifestSource });
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
      const message = error instanceof ApiRequestError ? error.message : "Failed to validate workflow manifest";
      toast.error(message);
    }
  };

  const insertSnippet = (snippet: WorkflowSnippet) => {
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

  const handleSave = async () => {
    if (!manifestSource.trim()) {
      toast.error("Workflow manifest is required");
      return;
    }

    try {
      if (isEditing && workflowId) {
        const updatedWorkflow = await updateWorkflow.mutateAsync({
          payload: { manifestSource },
          workflowId,
        });
        setCleanManifestSource(manifestSource);
        toast.success("Workflow manifest saved");
        if (String(updatedWorkflow.id) !== workflowId) {
          navigate(`/workflows/${updatedWorkflow.id}/edit`, { replace: true });
        }
        return;
      }

      const createdWorkflow = await createWorkflow.mutateAsync({ manifestSource });
      setCleanManifestSource(manifestSource);
      toast.success("Workflow created from manifest");
      navigate(`/workflows/${createdWorkflow.id}/edit`);
    } catch (error) {
      const message = error instanceof ApiRequestError ? error.message : "Failed to save workflow manifest";
      toast.error(message);
    }
  };

  const handleLaunchRun = async () => {
    if (!workflowId) {
      setRunLaunchFeedback({
        message: "Save the workflow before launching a run.",
        title: "Run launch unavailable",
        variant: "destructive",
      });
      return;
    }

    try {
      const run = await createWorkflowRun.mutateAsync({
        payload: runInputPayload,
        version: workflow?.version,
        workflowId,
      });
      toast.success("Workflow run started");
      navigate(`/runs/${run.id}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to start workflow run";
      setRunLaunchFeedback({
        message,
        title: "Run launch failed",
        variant: "destructive",
      });
    }
  };

  if (isEditing && isPending) {
    return (
      <div className="flex h-full items-center justify-center bg-background" data-testid="workflow-yaml-editor-shell">
        <Loader2 className="size-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isEditing && isError) {
    return (
      <div className="flex h-full items-center justify-center bg-background p-6" data-testid="workflow-yaml-editor-shell">
        <Alert variant="destructive" className="max-w-xl">
          <AlertCircle />
          <AlertTitle>Unable to load workflow</AlertTitle>
          <AlertDescription>
            {workflowError instanceof Error ? workflowError.message : "The workflow could not be loaded."}
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-background" data-testid="workflow-yaml-editor-shell">
      <div
        className="sticky top-0 border-b border-border bg-card px-4 py-3"
        data-testid="workflow-command-bar"
      >
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
          <div className="flex min-w-0 flex-wrap items-center gap-2 xl:flex-1">
            <Button aria-label="Back to workflows" onClick={handleClose} size="icon" variant="ghost">
              <ArrowLeft data-icon="inline-start" />
            </Button>
            <Separator className="hidden h-5 sm:block" orientation="vertical" />
            <Badge variant="secondary">YAML manifest</Badge>
            {isDirty ? (
              <Badge data-testid="workflow-dirty-indicator" variant="outline">
                Unsaved changes
              </Badge>
            ) : (
              <Badge data-testid="workflow-dirty-indicator" variant="secondary">
                Saved baseline
              </Badge>
            )}
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">
                {metadata.name || workflow?.name || (isEditing ? "Workflow manifest" : "New Workflow")}
              </p>
              <p className="truncate text-xs text-muted-foreground">
                {metadata.key || workflow?.key || "metadata.key will identify this workflow"}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 border-t border-border/60 pt-3 sm:justify-end xl:ml-auto xl:border-t-0 xl:pt-0">
            <Button data-testid="workflow-open-snippets" onClick={() => setIsSnippetPaletteOpen(true)} size="sm" variant="outline">
              <Keyboard data-icon="inline-start" />
              Snippets
            </Button>
            <Button data-testid="workflow-format-manifest" onClick={handleFormat} size="sm" variant="ghost">
              <Wand2 data-icon="inline-start" />
              Format
            </Button>
            <Button data-testid="workflow-validate-manifest" disabled={isValidating} onClick={() => void handleValidate()} size="sm" variant="outline">
              {isValidating ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <ShieldCheck data-icon="inline-start" />}
              Validate
            </Button>
            <Button data-testid="workflow-cancel" onClick={handleClose} size="sm" variant="outline">
              Cancel
            </Button>
            <Button data-testid="workflow-save" disabled={isSaving} onClick={handleSave} size="sm">
              {isSaving ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <Save data-icon="inline-start" />}
              Save manifest
            </Button>
          </div>
        </div>
      </div>

      <CommandDialog
        description="Insert small YAML snippets at the current cursor without switching away from source editing."
        onOpenChange={setIsSnippetPaletteOpen}
        open={isSnippetPaletteOpen}
        title="Workflow YAML snippets"
      >
        <CommandInput placeholder="Search workflow snippets..." />
        <CommandList>
          <CommandEmpty>No snippets found.</CommandEmpty>
          <CommandGroup heading="Insert at cursor">
            {WORKFLOW_SNIPPETS.map((snippet) => (
              <CommandItem
                data-testid={`workflow-snippet-${snippet.id}`}
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
          <aside
            className="flex h-full min-h-0 flex-col border-r border-border bg-muted/20"
            data-testid="workflow-outline-rail"
          >
            <div className="flex items-center gap-2 border-b border-border px-4 py-3">
              <Braces className="size-4 text-muted-foreground" />
              <div className="min-w-0">
                <p className="text-sm font-medium">Manifest outline</p>
                <p className="text-xs text-muted-foreground">Jump by source section</p>
              </div>
            </div>
            <ScrollArea className="min-h-0 flex-1">
              <div className="flex flex-col gap-4 p-3">
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
                        <span className="shrink-0 text-xs text-muted-foreground">
                          {getSectionDescription(section)}
                        </span>
                      </button>
                    ))}
                  </CardContent>
                </Card>

                <Card className="gap-3">
                  <CardHeader className="px-3 pt-3">
                    <CardTitle className="text-sm">Execution path</CardTitle>
                    <CardDescription>Steps and published agent pins</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-2 px-3 pb-3">
                    {outlineResult.outline.steps.length ? (
                      outlineResult.outline.steps.map((step) => (
                        <div className="rounded-md border border-border bg-background p-2" key={step.path}>
                          <button
                            className="flex w-full items-center justify-between gap-2 text-left text-sm font-medium"
                            onClick={() => jumpToLine(step.line)}
                            type="button"
                          >
                            <span className="truncate">{step.id}</span>
                            <span className="text-xs text-muted-foreground">Step {step.index + 1}</span>
                          </button>
                          <div className="mt-2 flex flex-col gap-1">
                            {step.agentSlots.map((slot) => (
                              <button
                                className="flex items-center justify-between gap-2 rounded px-2 py-1 text-left text-xs hover:bg-accent hover:text-accent-foreground"
                                key={slot.path}
                                onClick={() => jumpToLine(slot.line)}
                                type="button"
                              >
                                <span className="truncate">{slot.slot}</span>
                                <span className="truncate text-muted-foreground">{slot.uses ?? "Unpinned"}</span>
                              </button>
                            ))}
                          </div>
                        </div>
                      ))
                    ) : (
                      <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
                        Add a steps list to populate the execution outline.
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
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Source editor
              </span>
              <span className="ml-auto text-xs text-muted-foreground">{lineCount} lines</span>
            </div>
            <div className="min-h-0 flex-1 p-3">
              <Textarea
                aria-label="Workflow manifest YAML"
                className="h-full min-h-0 resize-none rounded-lg border-border bg-background font-mono text-sm leading-6 shadow-none focus-visible:ring-1"
                data-testid="workflow-yaml-editor"
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
          <aside className="flex h-full min-h-0 flex-col border-l border-border bg-muted/20" data-testid="workflow-inspector-shell">
            <div className="flex items-center gap-2 border-b border-border px-4 py-3">
              <FileText className="size-4 text-muted-foreground" />
              <div className="min-w-0">
                <p className="text-sm font-medium">Inspector</p>
                <p className="text-xs text-muted-foreground">Local YAML structure only</p>
              </div>
            </div>
            <ScrollArea className="min-h-0 flex-1">
              <div className="flex flex-col gap-4 p-3">
                <Alert variant={hasErrors ? "destructive" : "default"} data-testid="workflow-local-parse-status">
                  {hasErrors ? <AlertCircle /> : <CheckCircle2 />}
                  <AlertTitle>{hasErrors ? "Local parse needs attention" : "Local parse ready"}</AlertTitle>
                  <AlertDescription>
                    {hasErrors
                      ? "Fix local YAML errors before relying on outline details. Backend validation remains authoritative for persisted workflow rules."
                      : "YAML is locally parseable. Use Validate for backend-authoritative workflow checks."}
                  </AlertDescription>
                </Alert>

                <Alert
                  data-testid="workflow-backend-validation-status"
                  variant={validationResult && hasBackendErrors ? "destructive" : "default"}
                >
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
                      ? "Run Validate to resolve agents, schemas, wiring, and compiled workflow output against the backend."
                      : isValidationStale
                        ? "The YAML changed after the last backend response. Validate again before trusting these results."
                        : hasBackendErrors
                          ? "Backend diagnostics must be resolved before this manifest can compile cleanly."
                          : hasBackendWarnings
                            ? "The backend returned warnings; review them before saving or running this workflow."
                            : "The backend returned a compiled payload and run input schema for this manifest."}
                  </AlertDescription>
                </Alert>

                <Card className="gap-3">
                  <CardHeader className="px-3 pt-3">
                    <CardTitle className="text-sm">Workflow metadata</CardTitle>
                    <CardDescription>Read from the manifest source</CardDescription>
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
                      <p className="break-words text-muted-foreground">
                        {metadata.description || "Not available"}
                      </p>
                    </div>
                  </CardContent>
                </Card>

                <Card className="gap-3">
                  <CardHeader className="px-3 pt-3">
                    <CardTitle className="text-sm">Local diagnostics</CardTitle>
                    <CardDescription>Local YAML parser feedback</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-2 px-3 pb-3" data-testid="workflow-validation-feedback">
                    {diagnostics.length ? (
                      diagnostics.map((diagnostic) => (
                        <button
                          className="rounded-md border border-border bg-background p-2 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground"
                          key={diagnostic.id}
                          onClick={() => jumpToLine(diagnostic.line)}
                          type="button"
                        >
                          <span className="flex items-center gap-2">
                            <Badge variant={diagnostic.severity === "error" ? "destructive" : "secondary"}>
                              {diagnostic.severity}
                            </Badge>
                            <span className="text-xs text-muted-foreground">{diagnostic.locationLabel}</span>
                          </span>
                          <span className="mt-2 block">{diagnostic.message}</span>
                        </button>
                      ))
                    ) : (
                      <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
                        No local diagnostics.
                      </p>
                    )}
                  </CardContent>
                </Card>

                <Card className="gap-3">
                  <CardHeader className="px-3 pt-3">
                    <CardTitle className="text-sm">Backend validation</CardTitle>
                    <CardDescription>Authoritative manifest validation response</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-2 px-3 pb-3" data-testid="workflow-backend-validation-feedback">
                    {!validationResult ? (
                      <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
                        Run Validate to populate backend diagnostics.
                      </p>
                    ) : validationDiagnostics.length ? (
                      validationDiagnostics.map((diagnostic) => (
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
                            <span className="text-xs text-muted-foreground">{diagnostic.locationLabel}</span>
                            {diagnostic.path ? (
                              <span className="break-all font-mono text-xs text-muted-foreground">
                                {diagnostic.path}
                              </span>
                            ) : null}
                          </span>
                          <span className="mt-2 block">{diagnostic.message}</span>
                        </button>
                      ))
                    ) : (
                      <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
                        No backend diagnostics.
                      </p>
                    )}
                  </CardContent>
                </Card>

                {validationResult ? (
                  <Card className="gap-3">
                    <CardHeader className="px-3 pt-3">
                      <CardTitle className="text-sm">Compiled workflow preview</CardTitle>
                      <CardDescription>Exact raw JSON returned by backend validation</CardDescription>
                    </CardHeader>
                    <CardContent className="px-3 pb-3">
                      {validationResult.compiledPayload ? (
                        <ExactJsonPreview
                          ariaLabel="Exact raw compiled workflow JSON"
                          data-testid="workflow-compiled-preview"
                          textareaClassName="min-h-52"
                          value={compiledPayloadJson}
                        />
                      ) : (
                        <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
                          Backend validation did not return a compiled payload.
                        </p>
                      )}
                    </CardContent>
                  </Card>
                ) : null}

                {validationResult ? (
                  <Card className="gap-3">
                    <CardHeader className="px-3 pt-3">
                      <CardTitle className="text-sm">Run input schema preview</CardTitle>
                      <CardDescription>Exact raw JSON schema returned by backend validation</CardDescription>
                    </CardHeader>
                    <CardContent className="px-3 pb-3">
                      {validationResult.runInputSchema ? (
                        <ExactJsonPreview
                          ariaLabel="Exact raw workflow run input schema JSON"
                          data-testid="workflow-run-input-preview"
                          textareaClassName="min-h-52"
                          value={runInputSchemaJson}
                        />
                      ) : (
                        <p className="rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
                          Backend validation did not return a run input schema.
                        </p>
                      )}
                    </CardContent>
                  </Card>
                ) : null}

                <Card className="gap-3" data-testid="workflow-run-panel">
                  <CardHeader className="px-3 pt-3">
                    <CardTitle className="text-sm">Launch run</CardTitle>
                    <CardDescription>Submit a saved workflow run through the compiled input schema.</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-3 px-3 pb-3">
                    {!isEditing ? (
                      <Alert data-testid="workflow-run-unavailable" variant="destructive">
                        <AlertTitle>Run launch unavailable</AlertTitle>
                        <AlertDescription>Save the workflow before launching a run.</AlertDescription>
                      </Alert>
                    ) : null}
                    {runLaunchFeedback ? (
                      <Alert data-testid="workflow-run-feedback" variant={runLaunchFeedback.variant}>
                        <AlertTitle>{runLaunchFeedback.title}</AlertTitle>
                        <AlertDescription>{runLaunchFeedback.message}</AlertDescription>
                      </Alert>
                    ) : null}
                    <div data-testid="workflow-run-input-form">
                      <SchemaForm
                        description="Fill the workflow run input through the shared schema-driven form instead of editing JSON directly."
                        disabled={!isEditing || isLaunchingRun}
                        label="Run input"
                        schema={activeRunInputSchemaBuilder}
                        value={runInput}
                        onChange={setRunInput}
                      />
                    </div>
                    <ExactJsonPreview
                      ariaLabel="Exact raw workflow run-input JSON"
                      data-testid="workflow-run-input-raw-json"
                      textareaClassName="min-h-32"
                      value={rawRunInputJson}
                    />
                    <Button
                      data-testid="workflow-run-now"
                      disabled={!isEditing || isLaunchingRun}
                      onClick={() => void handleLaunchRun()}
                      size="sm"
                      variant="outline"
                    >
                      {isLaunchingRun ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <PlayCircle data-icon="inline-start" />}
                      Launch Run
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
