import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  PlayCircle,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import { useLocation, useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { SchemaForm } from "@/components/platform-authoring/generated-form/schema-form";
import { ExactJsonPreview } from "@/components/platform-authoring/inspectors/exact-json-preview";
import { StructuredValueInspector } from "@/components/platform-authoring/inspectors/structured-value-inspector";
import { SchemaComposer } from "@/components/platform-authoring/schema-composer/schema-composer";
import { useAgents } from "@/hooks/use-agents";
import {
  useCreateWorkflow,
  useCreateWorkflowRun,
  useUpdateWorkflow,
  useWorkflow,
} from "@/hooks/use-workflows";
import { ApiRequestError } from "@/lib/api-client";
import { parseSchemaJsonText, schemaBuilderToJsonSchema } from "@/lib/platform-authoring/schema/codec";
import { createDefaultSchemaNode } from "@/lib/platform-authoring/schema/factories";
import { buildPreviewValue } from "@/lib/platform-authoring/schema/preview";
import type { SchemaIRNode } from "@/lib/platform-authoring/schema/types";
import {
  encodeValueEntry,
  validateAndDecodeValueEntry,
} from "@/lib/platform-authoring/values/codec";
import type { ValueEntry } from "@/lib/platform-authoring/values/types";
import type { AgentRead } from "@/lib/types/agent";
import type { UnknownRecord } from "@/lib/types/common";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

import { PlatformResourceBadges, stringifyJson } from "../platform-resource-shared";
import {
  buildWorkflowPayload,
  createEmptyWorkflowAgent,
  createEmptyWorkflowStep,
  createInitialWorkflowDraft,
  findAgentByKey,
  getSchemaFieldNames,
  type WiringSourceDraft,
  type WorkflowDraft,
  type WorkflowDraftAgent,
  type WorkflowDraftOutput,
  type WorkflowSection,
  type WorkflowValidationIssue,
  validateWorkflowDraft,
  workflowDraftFromRead,
  WORKFLOW_SECTIONS,
} from "./shared";

const NONE_OPTION = "__none__";
const DEFAULT_WORKFLOW_INPUT_SCHEMA_BUILDER =
  parseSchemaJsonText(createInitialWorkflowDraft().inputSchemaText).builder ??
  createDefaultSchemaNode("object");

function createEmptySourceDraft(): WiringSourceDraft {
  return { from: "none", path: "", slot: "", stepIndex: "" };
}

function stringifyWorkflowInputSchema(builder: SchemaIRNode): string {
  return stringifyJson(schemaBuilderToJsonSchema(builder));
}

function sortAgents(agents: readonly AgentRead[]): AgentRead[] {
  return [...agents].sort((left, right) => left.key.localeCompare(right.key));
}

function sectionForIssue(field: string): WorkflowSection {
  if (field === "key" || field === "name" || field.startsWith("inputSchema")) {
    return "input";
  }

  if (field.startsWith("steps")) {
    return "steps";
  }

  if (field.startsWith("outputSpec")) {
    return "output";
  }

  return "review";
}

function isUnknownRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function createDefaultRunInputValue(schema: SchemaIRNode): ValueEntry {
  const previewValue = buildPreviewValue(schema);

  if (isUnknownRecord(previewValue) && typeof previewValue.ticker === "string") {
    return encodeValueEntry({ ...previewValue, ticker: "AAPL" });
  }

  if (isUnknownRecord(previewValue)) {
    return encodeValueEntry(previewValue);
  }

  return encodeValueEntry({});
}

function parseRunInputValue(value: ValueEntry): UnknownRecord {
  const decoded = validateAndDecodeValueEntry(value);
  if (!decoded.ok || !isUnknownRecord(decoded.value)) {
    throw new Error("Run input must be a JSON object.");
  }

  return decoded.value;
}

type StepSlotOption = {
  optional: boolean;
  slot: string;
  stepNumber: number;
};

function collectPreviousStepSlots(
  draft: WorkflowDraft,
  currentStepNumber: number,
): StepSlotOption[] {
  const options: StepSlotOption[] = [];

  draft.steps.slice(0, Math.max(0, currentStepNumber - 1)).forEach((step, index) => {
    step.agents.forEach((agent) => {
      const slot = agent.slot.trim();
      if (slot) {
        options.push({
          optional: agent.optional,
          slot,
          stepNumber: index + 1,
        });
      }
    });
  });

  return options;
}

function getStepOptions(draft: WorkflowDraft): string[] {
  return draft.steps.map((_, index) => String(index + 1));
}

type WiringFieldEditorProps = {
  currentStepNumber: number;
  fieldName: string;
  onChange: (nextSource: WiringSourceDraft) => void;
  source: WiringSourceDraft;
  workflowDraft: WorkflowDraft;
};

function WiringFieldEditor(props: WiringFieldEditorProps) {
  const { currentStepNumber, fieldName, onChange, source, workflowDraft } = props;
  const stepSlots = collectPreviousStepSlots(workflowDraft, currentStepNumber);
  const stepNumbers = Array.from(new Set(stepSlots.map((entry) => String(entry.stepNumber))));
  const slotOptions = source.stepIndex
    ? stepSlots.filter((entry) => String(entry.stepNumber) === source.stepIndex)
    : [];

  const updateSource = (patch: Partial<WiringSourceDraft>) => {
    onChange({ ...source, ...patch });
  };

  return (
    <div className="rounded-md border p-4">
      <div className="grid gap-4 md:grid-cols-4">
        <div className="flex flex-col gap-2">
          <Label>{fieldName}</Label>
          <Select
            value={source.from}
            onValueChange={(value: WiringSourceDraft["from"]) => {
              if (value === "none") {
                onChange(createEmptySourceDraft());
                return;
              }

              if (value === "input") {
                onChange({ from: "input", path: source.path || fieldName, slot: "", stepIndex: "" });
                return;
              }

              onChange({
                from: "step",
                path: source.path,
                slot: "",
                stepIndex: stepNumbers[stepNumbers.length - 1] ?? "",
              });
            }}
          >
            <SelectTrigger aria-label={`${fieldName} source`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="none">Not wired</SelectItem>
                <SelectItem value="input">Workflow input</SelectItem>
                <SelectItem value="step">Previous step slot</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>
        {source.from === "input" ? (
          <div className="flex flex-col gap-2 md:col-span-3">
            <Label htmlFor={`${fieldName}-input-path`}>Input path</Label>
            <Input
              id={`${fieldName}-input-path`}
              aria-label={`${fieldName} input path`}
              placeholder={fieldName}
              value={source.path}
              onChange={(event) => updateSource({ path: event.target.value })}
            />
          </div>
        ) : null}

        {source.from === "step" ? (
          <>
            <div className="flex flex-col gap-2">
              <Label htmlFor={`${fieldName}-step-index`}>Step</Label>
              <Select
                value={source.stepIndex || NONE_OPTION}
                onValueChange={(value) => {
                  updateSource({ slot: "", stepIndex: value === NONE_OPTION ? "" : value });
                }}
              >
                <SelectTrigger aria-label={`${fieldName} step`} id={`${fieldName}-step-index`}>
                  <SelectValue placeholder="Select step" />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value={NONE_OPTION}>Select step</SelectItem>
                    {stepNumbers.map((stepNumber) => (
                      <SelectItem key={`${fieldName}-${stepNumber}`} value={stepNumber}>
                        Step {stepNumber}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor={`${fieldName}-slot-name`}>Slot</Label>
              <Select
                value={source.slot || NONE_OPTION}
                onValueChange={(value) => updateSource({ slot: value === NONE_OPTION ? "" : value })}
              >
                <SelectTrigger aria-label={`${fieldName} slot`} id={`${fieldName}-slot-name`}>
                  <SelectValue placeholder="Select slot" />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value={NONE_OPTION}>Select slot</SelectItem>
                    {slotOptions.map((option) => (
                      <SelectItem
                        key={`${fieldName}-${option.stepNumber}-${option.slot}`}
                        value={option.slot}
                      >
                        {option.slot}{option.optional ? " (optional)" : ""}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-2 md:col-span-2">
              <Label htmlFor={`${fieldName}-slot-path`}>Slot path</Label>
              <Input
                id={`${fieldName}-slot-path`}
                aria-label={`${fieldName} slot path`}
                placeholder="summary"
                value={source.path}
                onChange={(event) => updateSource({ path: event.target.value })}
              />
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}

type AgentEditorCardProps = {
  currentStepNumber: number;
  draftAgent: WorkflowDraftAgent;
  heading: string;
  onChange: (nextAgent: WorkflowDraftAgent) => void;
  onRemove?: () => void;
  workflowAgents: readonly AgentRead[];
  workflowDraft: WorkflowDraft;
};

function AgentEditorCard(props: AgentEditorCardProps) {
  const {
    currentStepNumber,
    draftAgent,
    heading,
    onChange,
    onRemove,
    workflowAgents,
    workflowDraft,
  } = props;
  const resolvedAgent = findAgentByKey(workflowAgents, draftAgent.agentKey);
  const fieldNames = getSchemaFieldNames(resolvedAgent?.inputSchema, draftAgent.wiring);

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex flex-col gap-1">
            <CardTitle className="text-base">{heading}</CardTitle>
            <CardDescription>
              Pin an agent version, assign its slot name, and map every required input field.
            </CardDescription>
          </div>
          {onRemove ? (
            <Button size="sm" variant="outline" onClick={onRemove}>
              <Trash2 data-icon="inline-start" />
              Remove Agent
            </Button>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-4 md:grid-cols-4">
          <div className="flex flex-col gap-2 md:col-span-2">
            <Label>Agent</Label>
            <Select
              value={draftAgent.agentKey || NONE_OPTION}
              onValueChange={(value) =>
                onChange({
                  ...draftAgent,
                  agentKey: value === NONE_OPTION ? "" : value,
                })
              }
            >
              <SelectTrigger aria-label={`${heading} agent`}>
                <SelectValue placeholder="Select agent" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value={NONE_OPTION}>Select agent</SelectItem>
                  {workflowAgents.map((agent) => (
                    <SelectItem key={agent.id} value={agent.key}>
                      {agent.name} ({agent.key}@{agent.version})
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${heading}-version`}>Pinned version</Label>
            <Input
              id={`${heading}-version`}
              aria-label={`${heading} version`}
              placeholder={resolvedAgent ? String(resolvedAgent.version) : "1"}
              value={draftAgent.agentVersion}
              onChange={(event) => onChange({ ...draftAgent, agentVersion: event.target.value })}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${heading}-slot`}>Slot</Label>
            <Input
              id={`${heading}-slot`}
              aria-label={`${heading} slot`}
              placeholder="analysis"
              value={draftAgent.slot}
              onChange={(event) => onChange({ ...draftAgent, slot: event.target.value })}
            />
          </div>
        </div>

        <div className="flex items-center justify-between rounded-md border p-4">
          <div className="flex flex-col gap-1">
            <Label htmlFor={`${heading}-optional`}>Optional slot</Label>
            <p className="text-sm text-muted-foreground">
              Optional agents may fail and provide a null slot for downstream wiring.
            </p>
          </div>
          <Switch
            id={`${heading}-optional`}
            checked={draftAgent.optional}
            onCheckedChange={(checked) => onChange({ ...draftAgent, optional: checked })}
          />
        </div>

        {!resolvedAgent && draftAgent.agentKey.trim() ? (
          <Alert variant="destructive">
            <AlertCircle />
            <AlertTitle>Agent not found</AlertTitle>
            <AlertDescription>
              The saved workflow references `{draftAgent.agentKey}`, but that agent is not in the
              current latest-version catalog.
            </AlertDescription>
          </Alert>
        ) : null}

        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div className="flex flex-col gap-1">
              <h3 className="text-sm font-medium">Slot wiring</h3>
              <p className="text-sm text-muted-foreground">
                Map each agent input field from the workflow input or an earlier slot.
              </p>
            </div>
            {resolvedAgent ? (
              <Badge variant="outline">{fieldNames.length} mapped field(s)</Badge>
            ) : null}
          </div>

          {fieldNames.length === 0 ? (
            <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
              Select an agent with an object input schema to configure slot wiring controls.
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {fieldNames.map((fieldName) => (
                <WiringFieldEditor
                  currentStepNumber={currentStepNumber}
                  fieldName={fieldName}
                  key={`${heading}-${fieldName}`}
                  onChange={(nextSource) =>
                    onChange({
                      ...draftAgent,
                      wiring: { ...draftAgent.wiring, [fieldName]: nextSource },
                    })
                  }
                  source={draftAgent.wiring[fieldName] ?? createEmptySourceDraft()}
                  workflowDraft={workflowDraft}
                />
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

type OutputEditorProps = {
  onChange: (nextOutput: WorkflowDraftOutput) => void;
  workflowAgents: readonly AgentRead[];
  workflowDraft: WorkflowDraft;
};

function OutputEditor(props: OutputEditorProps) {
  const { onChange, workflowAgents, workflowDraft } = props;
  const stepOptions = getStepOptions(workflowDraft);
  const output = workflowDraft.output;

  if (output.kind === "slot") {
    const slots = collectPreviousStepSlots(workflowDraft, workflowDraft.steps.length + 1).filter(
      (entry) => String(entry.stepNumber) === output.stepIndex,
    );

    return (
      <Card>
        <CardHeader>
          <CardTitle>Final output slot</CardTitle>
          <CardDescription>
            Choose which step slot becomes the workflow result and optionally pick a nested path.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          <div className="flex flex-col gap-2">
            <Label>Output kind</Label>
            <Select value="slot" onValueChange={() => void 0}>
              <SelectTrigger aria-label="Output kind">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="slot">Slot</SelectItem>
                  <SelectItem value="agent" onSelect={() => void 0}>Agent</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label>Step</Label>
            <Select
              value={output.stepIndex || NONE_OPTION}
              onValueChange={(value) =>
                onChange({
                  kind: "slot",
                  path: output.path,
                  slot: "",
                  stepIndex: value === NONE_OPTION ? "" : value,
                })
              }
            >
              <SelectTrigger aria-label="Output step">
                <SelectValue placeholder="Select step" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value={NONE_OPTION}>Select step</SelectItem>
                  {stepOptions.map((stepValue) => (
                    <SelectItem key={`output-step-${stepValue}`} value={stepValue}>
                      Step {stepValue}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label>Slot</Label>
            <Select
              value={output.slot || NONE_OPTION}
              onValueChange={(value) =>
                onChange({
                  kind: "slot",
                  path: output.path,
                  slot: value === NONE_OPTION ? "" : value,
                  stepIndex: output.stepIndex,
                })
              }
            >
              <SelectTrigger aria-label="Output slot">
                <SelectValue placeholder="Select slot" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value={NONE_OPTION}>Select slot</SelectItem>
                  {slots.map((slotOption) => (
                    <SelectItem key={`output-slot-${slotOption.slot}`} value={slotOption.slot}>
                      {slotOption.slot}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2 md:col-span-3">
            <Label htmlFor="workflow-output-path">Output path</Label>
            <Input
              id="workflow-output-path"
              aria-label="Output path"
              placeholder="summary"
              value={output.path}
              onChange={(event) =>
                onChange({
                  kind: "slot",
                  path: event.target.value,
                  slot: output.slot,
                  stepIndex: output.stepIndex,
                })
              }
            />
          </div>
          <Button
            className="md:col-span-3 md:w-fit"
            size="sm"
            variant="outline"
            onClick={() =>
              onChange({ agentKey: "", agentVersion: "", kind: "agent", wiring: {} })
            }
          >
            Switch to Output Agent
          </Button>
        </CardContent>
      </Card>
    );
  }

  const resolvedAgent = findAgentByKey(workflowAgents, output.agentKey);
  const fieldNames = getSchemaFieldNames(resolvedAgent?.inputSchema, output.wiring);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Final output agent</CardTitle>
        <CardDescription>
          Run a pinned agent after all steps and map its inputs from earlier slots or the workflow input.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-4 md:grid-cols-3">
          <div className="flex flex-col gap-2">
            <Label>Output kind</Label>
            <Input aria-label="Output kind" disabled value="agent" />
          </div>
          <div className="flex flex-col gap-2 md:col-span-2">
            <Label>Agent</Label>
            <Select
              value={output.agentKey || NONE_OPTION}
              onValueChange={(value) =>
                onChange({
                  agentKey: value === NONE_OPTION ? "" : value,
                  agentVersion: output.agentVersion,
                  kind: "agent",
                  wiring: output.wiring,
                })
              }
            >
              <SelectTrigger aria-label="Output agent">
                <SelectValue placeholder="Select agent" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value={NONE_OPTION}>Select agent</SelectItem>
                  {workflowAgents.map((agent) => (
                    <SelectItem key={`output-agent-${agent.id}`} value={agent.key}>
                      {agent.name} ({agent.key}@{agent.version})
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="workflow-output-agent-version">Pinned version</Label>
            <Input
              id="workflow-output-agent-version"
              aria-label="Output agent version"
              placeholder={resolvedAgent ? String(resolvedAgent.version) : "1"}
              value={output.agentVersion}
              onChange={(event) =>
                onChange({
                  agentKey: output.agentKey,
                  agentVersion: event.target.value,
                  kind: "agent",
                  wiring: output.wiring,
                })
              }
            />
          </div>
        </div>

        {fieldNames.length === 0 ? (
          <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
            Select an output agent with an object input schema to configure its wiring.
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {fieldNames.map((fieldName) => (
              <WiringFieldEditor
                currentStepNumber={workflowDraft.steps.length + 1}
                fieldName={fieldName}
                key={`output-${fieldName}`}
                onChange={(nextSource) =>
                  onChange({
                    agentKey: output.agentKey,
                    agentVersion: output.agentVersion,
                    kind: "agent",
                    wiring: { ...output.wiring, [fieldName]: nextSource },
                  })
                }
                source={output.wiring[fieldName] ?? createEmptySourceDraft()}
                workflowDraft={workflowDraft}
              />
            ))}
          </div>
        )}

        <Button
          className="w-fit"
          size="sm"
          variant="outline"
          onClick={() => onChange({ kind: "slot", path: "", slot: "", stepIndex: "1" })}
        >
          Switch to Output Slot
        </Button>
      </CardContent>
    </Card>
  );
}

export function WorkflowsEditorPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const isEditing = Boolean(workflowId);
  const workflowQuery = useWorkflow(workflowId);
  const agentsQuery = useAgents();
  const createMutation = useCreateWorkflow();
  const updateMutation = useUpdateWorkflow();
  const createRunMutation = useCreateWorkflowRun();
  const workflowAgents = useMemo(() => sortAgents(agentsQuery.data?.items ?? []), [agentsQuery.data?.items]);
  const [activeSection, setActiveSection] = useState<WorkflowSection>("input");
  const [draft, setDraft] = useState<WorkflowDraft>(createInitialWorkflowDraft);
  const [inputSchemaBuilder, setInputSchemaBuilder] =
    useState<SchemaIRNode>(DEFAULT_WORKFLOW_INPUT_SCHEMA_BUILDER);
  const [runInputValue, setRunInputValue] = useState<ValueEntry>(() =>
    createDefaultRunInputValue(DEFAULT_WORKFLOW_INPUT_SCHEMA_BUILDER),
  );
  const [validationIssues, setValidationIssues] = useState<WorkflowValidationIssue[]>([]);

  useEffect(() => {
    if (!workflowQuery.data) {
      return;
    }

    const nextDraft = workflowDraftFromRead(workflowQuery.data);
    const decodedSchema = parseSchemaJsonText(nextDraft.inputSchemaText);

    const nextInputSchemaBuilder = decodedSchema.builder ?? createDefaultSchemaNode("object");

    setDraft(nextDraft);
    setInputSchemaBuilder(nextInputSchemaBuilder);
    setRunInputValue(createDefaultRunInputValue(nextInputSchemaBuilder));
    setValidationIssues([]);
  }, [workflowQuery.data]);

  useEffect(() => {
    if (location.hash === "#review") {
      setActiveSection("review");
    }
  }, [location.hash]);

  const activeIndex = WORKFLOW_SECTIONS.findIndex((section) => section.value === activeSection);
  const progressValue = ((activeIndex + 1) / WORKFLOW_SECTIONS.length) * 100;
  const isSaving = createMutation.isPending || updateMutation.isPending;
  const canRunNow = Boolean(isEditing && workflowQuery.data);
  const derivedInputSchema = useMemo(
    () => schemaBuilderToJsonSchema(inputSchemaBuilder),
    [inputSchemaBuilder],
  );
  const rawInputSchemaJson = useMemo(
    () => stringifyJson(derivedInputSchema),
    [derivedInputSchema],
  );
  const inputSchemaPreviewValue = useMemo(
    () => buildPreviewValue(inputSchemaBuilder),
    [inputSchemaBuilder],
  );
  const parsedRunInputPayload = useMemo(() => {
    try {
      return parseRunInputValue(runInputValue);
    } catch {
      return null;
    }
  }, [runInputValue]);
  const rawRunInputJson = useMemo(
    () => stringifyJson(parsedRunInputPayload),
    [parsedRunInputPayload],
  );

  const reviewPayload = useMemo(() => {
    try {
      return buildWorkflowPayload(draft);
    } catch {
      return null;
    }
  }, [draft]);

  const handleInputSchemaBuilderChange = (nextBuilder: SchemaIRNode) => {
    setInputSchemaBuilder(nextBuilder);
    setRunInputValue(createDefaultRunInputValue(nextBuilder));
    setDraft((current) => ({
      ...current,
      inputSchemaText: stringifyWorkflowInputSchema(nextBuilder),
    }));
  };

  const setIssueState = (issues: WorkflowValidationIssue[]) => {
    setValidationIssues(issues);
    if (issues.length > 0) {
      setActiveSection(sectionForIssue(issues[0].field));
    }
  };

  const applyApiIssues = (error: unknown) => {
    if (error instanceof ApiRequestError && error.details.length > 0) {
      const issues = error.details.map((detail) => ({ field: detail.field, issue: detail.issue }));
      setIssueState(issues);
    }
  };

  const validateCurrentDraft = () => {
    const issues = validateWorkflowDraft(draft, workflowAgents);
    setIssueState(issues);
    return issues;
  };

  const saveWorkflow = async () => {
    const issues = validateCurrentDraft();
    if (issues.length > 0) {
      throw new Error("Resolve workflow validation issues before saving.");
    }

    const payload = buildWorkflowPayload(draft);
    if (isEditing && workflowId) {
      const { key: _ignored, ...updatePayload } = payload;
      const updated = await updateMutation.mutateAsync({ payload: updatePayload, workflowId });
      toast.success("Workflow updated");
      navigate(`/workflows/${updated.id}/edit`);
      return updated;
    }

    const created = await createMutation.mutateAsync(payload);
    toast.success("Workflow created");
    navigate(`/workflows/${created.id}/edit`);
    return created;
  };

  const handleSave = async () => {
    try {
      await saveWorkflow();
    } catch (error) {
      applyApiIssues(error);
      toast.error(error instanceof Error ? error.message : "Failed to save workflow");
    }
  };

  const handleRunNow = async () => {
    if (!workflowQuery.data) {
      toast.error("Save the workflow before running it.");
      return;
    }

    try {
      const issues = validateCurrentDraft();
      if (issues.length > 0) {
        throw new Error("Resolve workflow validation issues before running.");
      }

      if (!parsedRunInputPayload) {
        throw new Error("Run input must be a JSON object.");
      }

      const run = await createRunMutation.mutateAsync({
        payload: parsedRunInputPayload,
        version: workflowQuery.data.version,
        workflowId: workflowQuery.data.id,
      });
      toast.success("Workflow run started");
      navigate(`/runs/${run.id}`);
    } catch (error) {
      applyApiIssues(error);
      toast.error(error instanceof Error ? error.message : "Failed to start workflow run");
    }
  };

  if (isEditing && workflowQuery.isPending) {
    return <div className="p-4 text-sm text-muted-foreground">Loading workflow details...</div>;
  }

  if (isEditing && workflowQuery.isError) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        {workflowQuery.error instanceof Error ? workflowQuery.error.message : "Workflow not found."}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4" data-testid="workflows-editor">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-2">
          <div className="flex flex-col gap-1">
            <h1 className="text-xl font-semibold tracking-tight">
              {isEditing ? "Edit Workflow" : "Create Workflow"}
            </h1>
            <p className="text-sm text-muted-foreground">
              Build a version-pinned workflow through four sections: Input, Steps, Output,
              and Review.
            </p>
          </div>
          {workflowQuery.data ? (
            <PlatformResourceBadges
              status={workflowQuery.data.status}
              version={workflowQuery.data.version}
            />
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button data-testid="workflow-save" disabled={isSaving} size="sm" onClick={() => void handleSave()}>
            <Save data-icon="inline-start" />
            Save Workflow
          </Button>
          <Button
            data-testid="workflow-run-now"
            disabled={!canRunNow || createRunMutation.isPending}
            size="sm"
            variant="outline"
            onClick={() => void handleRunNow()}
          >
            <PlayCircle data-icon="inline-start" />
            Run Now
          </Button>
        </div>
      </div>

      {validationIssues.length > 0 ? (
        <Alert data-testid="workflow-validation-feedback" variant="destructive">
          <AlertCircle />
          <AlertTitle>Workflow validation needs attention</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-5">
              {validationIssues.map((issue) => (
                <li key={`${issue.field}-${issue.issue}`}>{`${issue.field}: ${issue.issue}`}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardContent className="flex flex-col gap-4 pt-6">
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>
                Step {activeIndex + 1} of {WORKFLOW_SECTIONS.length}
              </span>
              <span>{WORKFLOW_SECTIONS[activeIndex]?.title}</span>
            </div>
            <Progress value={progressValue} />
          </div>
          <Tabs value={activeSection} onValueChange={(value) => setActiveSection(value as WorkflowSection)}>
            <TabsList className="w-full justify-start">
              {WORKFLOW_SECTIONS.map((section) => (
                <TabsTrigger key={section.value} value={section.value}>
                  {section.title}
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent forceMount value="input">
              <Card>
                <CardHeader>
                  <CardTitle>Input</CardTitle>
                  <CardDescription>
                    Set the workflow identity and define the request schema that step wiring can reference.
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-4">
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="flex flex-col gap-2">
                      <Label htmlFor="workflow-key">Workflow Key</Label>
                      <Input
                        id="workflow-key"
                        aria-label="Workflow Key"
                        disabled={isEditing || isSaving}
                        value={draft.key}
                        onChange={(event) => setDraft((current) => ({ ...current, key: event.target.value }))}
                      />
                    </div>
                    <div className="flex flex-col gap-2">
                      <Label htmlFor="workflow-name">Workflow Name</Label>
                      <Input
                        id="workflow-name"
                        aria-label="Workflow Name"
                        value={draft.name}
                        onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
                      />
                    </div>
                  </div>

                  <div className="flex flex-col gap-2">
                    <Label htmlFor="workflow-description">Description</Label>
                    <Textarea
                      id="workflow-description"
                      aria-label="Workflow Description"
                      rows={3}
                      value={draft.description}
                      onChange={(event) =>
                        setDraft((current) => ({ ...current, description: event.target.value }))
                      }
                    />
                  </div>
                  <div className="flex flex-col gap-3">
                    <div className="flex flex-col gap-1">
                      <Label>Workflow Input Schema</Label>
                      <p className="text-sm text-muted-foreground">
                        Define the workflow request shape with the shared schema builder instead of editing JSON directly.
                      </p>
                    </div>
                    <SchemaComposer
                      label="Workflow input schema"
                      node={inputSchemaBuilder}
                      onChange={handleInputSchemaBuilderChange}
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
                            data-testid="workflow-input-schema-raw-json"
                            value={rawInputSchemaJson}
                          />
                        </CardContent>
                      </Card>
                      <Card>
                        <CardHeader>
                          <CardTitle>Sample run input</CardTitle>
                          <CardDescription>
                            Derived companion data from the current schema state.
                          </CardDescription>
                        </CardHeader>
                        <CardContent>
                          <StructuredValueInspector
                            data-testid="workflow-input-schema-preview"
                            label="Derived sample run input"
                            value={inputSchemaPreviewValue}
                          />
                        </CardContent>
                      </Card>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent forceMount value="steps">
              <div className="flex flex-col gap-4">
                {draft.steps.map((step, stepIndex) => (
                  <Card key={step.id}>
                    <CardHeader>
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div className="flex flex-col gap-1">
                          <CardTitle>Step {stepIndex + 1}</CardTitle>
                          <CardDescription>
                            Agents in the same step run together and publish their outputs to named slots.
                          </CardDescription>
                        </div>
                        {draft.steps.length > 1 ? (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              setDraft((current) => ({
                                ...current,
                                steps: current.steps.filter((_, index) => index !== stepIndex),
                              }))
                            }
                          >
                            <Trash2 data-icon="inline-start" />
                            Remove Step
                          </Button>
                        ) : null}
                      </div>
                    </CardHeader>
                    <CardContent className="flex flex-col gap-4">
                      {step.agents.map((agentDraft, agentIndex) => (
                        <AgentEditorCard
                          currentStepNumber={stepIndex + 1}
                          draftAgent={agentDraft}
                          heading={`Step ${stepIndex + 1} Agent ${agentIndex + 1}`}
                          key={agentDraft.id}
                          onChange={(nextAgent) =>
                            setDraft((current) => ({
                              ...current,
                              steps: current.steps.map((item, index) =>
                                index === stepIndex
                                  ? {
                                      ...item,
                                      agents: item.agents.map((agent, currentAgentIndex) =>
                                        currentAgentIndex === agentIndex ? nextAgent : agent,
                                      ),
                                    }
                                  : item,
                              ),
                            }))
                          }
                          onRemove={
                            step.agents.length > 1
                              ? () =>
                                  setDraft((current) => ({
                                    ...current,
                                    steps: current.steps.map((item, index) =>
                                      index === stepIndex
                                        ? {
                                            ...item,
                                            agents: item.agents.filter(
                                              (_, currentAgentIndex) => currentAgentIndex !== agentIndex,
                                            ),
                                          }
                                        : item,
                                    ),
                                  }))
                              : undefined
                          }
                          workflowAgents={workflowAgents}
                          workflowDraft={draft}
                        />
                      ))}

                      <Button
                        className="w-fit"
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          setDraft((current) => ({
                            ...current,
                            steps: current.steps.map((item, index) =>
                              index === stepIndex
                                ? { ...item, agents: [...item.agents, createEmptyWorkflowAgent()] }
                                : item,
                            ),
                          }))
                        }
                      >
                        <Plus data-icon="inline-start" />
                        Add Agent
                      </Button>
                    </CardContent>
                  </Card>
                ))}

                <Button
                  className="w-fit"
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    setDraft((current) => ({
                      ...current,
                      steps: [...current.steps, createEmptyWorkflowStep()],
                    }))
                  }
                >
                  <Plus data-icon="inline-start" />
                  Add Step
                </Button>
              </div>
            </TabsContent>

            <TabsContent forceMount value="output">
              <OutputEditor onChange={(nextOutput) => setDraft((current) => ({ ...current, output: nextOutput }))} workflowAgents={workflowAgents} workflowDraft={draft} />
            </TabsContent>

            <TabsContent forceMount value="review">
              <div className="flex flex-col gap-4">
                <div className="grid gap-3 md:grid-cols-3">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Input</CardTitle>
                      <CardDescription>Request contract and identity.</CardDescription>
                    </CardHeader>
                    <CardContent className="text-sm text-muted-foreground">
                      <p>{draft.key || "unsaved_workflow"}</p>
                      <p>{draft.name || "Workflow name pending"}</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Steps</CardTitle>
                      <CardDescription>Parallel groups and pinned agent refs.</CardDescription>
                    </CardHeader>
                    <CardContent className="text-sm text-muted-foreground">
                      <p>{draft.steps.length} step(s)</p>
                      <p>
                        {draft.steps.reduce((count, step) => count + step.agents.length, 0)} agent placement(s)
                      </p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Output</CardTitle>
                      <CardDescription>Final slot or synthesized agent result.</CardDescription>
                    </CardHeader>
                    <CardContent className="text-sm text-muted-foreground">
                      <p>{draft.output.kind === "slot" ? "Slot output" : "Agent output"}</p>
                      <p>
                        {draft.output.kind === "slot"
                          ? `Step ${draft.output.stepIndex || "?"} · ${draft.output.slot || "slot pending"}`
                          : draft.output.agentKey || "Output agent pending"}
                      </p>
                    </CardContent>
                  </Card>
                </div>

                <Card>
                  <CardHeader>
                    <CardTitle>Run input</CardTitle>
                    <CardDescription>
                      Save the workflow, then run the currently saved version with structured inputs derived from the workflow request schema.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-4">
                    {!canRunNow ? (
                      <Alert>
                        <AlertCircle />
                        <AlertTitle>Run now becomes available after the first save</AlertTitle>
                        <AlertDescription>
                          Create the workflow once, then the Review step can launch real runs into `/runs/:runId`.
                        </AlertDescription>
                      </Alert>
                    ) : null}
                    <div className="grid gap-4 xl:grid-cols-2">
                      <div data-testid="workflow-review-run-input-form">
                        <SchemaForm
                          description="Enter the run payload through the shared schema-driven form instead of authoring JSON."
                          label="Run input"
                          onChange={setRunInputValue}
                          schema={inputSchemaBuilder}
                          value={runInputValue}
                        />
                      </div>
                      <Card>
                        <CardHeader>
                          <CardTitle>Exact raw run-input JSON</CardTitle>
                          <CardDescription>
                            Read-only canonical JSON from the same parsed payload used when creating a run.
                          </CardDescription>
                        </CardHeader>
                        <CardContent>
                          <ExactJsonPreview
                            ariaLabel="Exact raw run-input JSON"
                            data-testid="workflow-review-run-input-raw-json"
                            value={rawRunInputJson}
                          />
                        </CardContent>
                      </Card>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Workflow summary</CardTitle>
                    <CardDescription>
                      Review the structured workflow payload produced by the current builder state.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-4">
                    {reviewPayload ? (
                      <StructuredValueInspector
                        data-testid="workflow-review-summary"
                        label="Workflow payload"
                        value={reviewPayload}
                      />
                    ) : (
                      <div className="rounded-md border border-dashed bg-muted/20 px-3 py-2 text-sm text-muted-foreground">
                        Resolve validation issues to preview the workflow summary.
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            </TabsContent>
          </Tabs>

          <Separator />

          <div className="flex flex-wrap items-center justify-between gap-3">
            <Button
              disabled={activeIndex === 0}
              size="sm"
              variant="outline"
              onClick={() => setActiveSection(WORKFLOW_SECTIONS[Math.max(0, activeIndex - 1)].value)}
            >
              <ArrowLeft data-icon="inline-start" />
              Back
            </Button>
            {activeSection !== "review" ? (
              <Button
                data-testid="workflow-wizard-next"
                size="sm"
                onClick={() => setActiveSection(WORKFLOW_SECTIONS[Math.min(WORKFLOW_SECTIONS.length - 1, activeIndex + 1)].value)}
              >
                Next
                <ArrowRight data-icon="inline-end" />
              </Button>
            ) : (
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => void handleSave()}>
                  <Save data-icon="inline-start" />
                  Save Workflow
                </Button>
                <Button
                  disabled={!canRunNow || createRunMutation.isPending}
                  size="sm"
                  onClick={() => void handleRunNow()}
                >
                  <PlayCircle data-icon="inline-start" />
                  Run Now
                </Button>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
