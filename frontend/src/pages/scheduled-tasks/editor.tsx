import { AlertCircle, CalendarClock, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateScheduledTask,
  usePreviewUnsavedScheduledTask,
} from "@/hooks/use-scheduled-tasks";
import { formatDateTime } from "@/lib/format";
import { stringifyJson } from "@/lib/platform-authoring/common/serialization";
import { buildRuntimeInputs, createRuntimeInputRow, type RuntimeInputRow } from "@/lib/runtime-inputs";
import type { UnknownRecord } from "@/lib/types/common";
import type { ScheduleCreateRequest, SchedulePreviewRead } from "@/lib/types/schedule";

function parseJsonObject(value: string): UnknownRecord {
  const parsed = JSON.parse(value) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Scheduled input template JSON must be an object.");
  }
  return parsed as UnknownRecord;
}

function serializeDateTimeLocal(value: string): string {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) {
    throw new Error("Choose a valid preview scheduled-for date and time.");
  }
  return date.toISOString();
}

function buildCreatePayload(draft: NewScheduleDraft): ScheduleCreateRequest {
  const packageId = Number.parseInt(draft.packageId, 10);
  if (!Number.isInteger(packageId) || packageId <= 0) {
    throw new Error("Package id must be a positive number.");
  }
  const workflowKey = draft.workflowKey.trim();
  const name = draft.name.trim();
  const timezone = draft.timezone.trim();
  if (!workflowKey || !name || !timezone) {
    throw new Error("Name, workflow key, and timezone are required.");
  }
  return {
    description: draft.description.trim() || null,
    inputTemplate: parseJsonObject(draft.inputTemplateText),
    misfireGraceSeconds: Number.parseInt(draft.misfireGraceSeconds, 10) || 86_400,
    misfirePolicy: "catchUpOne",
    name,
    overlapPolicy: "skip",
    packageId,
    recurrence: { atLocalTime: draft.atLocalTime, type: "daily" },
    status: "enabled",
    templateVars: buildRuntimeInputs(draft.templateVarRows),
    timezone,
    workflowKey,
  };
}

type NewScheduleDraft = {
  atLocalTime: string;
  description: string;
  inputTemplateText: string;
  misfireGraceSeconds: string;
  name: string;
  packageId: string;
  previewScheduledFor: string;
  templateVarRows: RuntimeInputRow[];
  timezone: string;
  workflowKey: string;
};

function defaultInputTemplateText() {
  return stringifyJson({});
}

function ScheduleInputPreview({ preview }: { preview: SchedulePreviewRead | null }) {
  if (!preview) {
    return (
      <div className="rounded-lg border border-dashed bg-muted/20 p-3 text-xs text-muted-foreground" data-testid="schedule-input-preview-empty">
        Preview the scheduled fire to prove placeholder substitution before saving.
      </div>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-3 rounded-lg border bg-background/60 p-3" data-testid="schedule-input-preview">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <Badge variant={preview.ready ? "secondary" : "destructive"}>{preview.ready ? "Ready" : "Not ready"}</Badge>
        <span className="text-xs text-muted-foreground">Scheduled for {preview.scheduledFor ? formatDateTime(preview.scheduledFor) : "not available"}</span>
      </div>
      <div className="grid min-w-0 gap-3 lg:grid-cols-2">
        <div className="min-w-0">
          <p className="mb-1 text-xs font-medium text-muted-foreground">Rendered parameters</p>
          <pre className="max-h-72 overflow-auto rounded-md bg-muted/40 p-3 text-xs">{stringifyJson(preview.renderedParameters)}</pre>
        </div>
        <div className="min-w-0">
          <p className="mb-1 text-xs font-medium text-muted-foreground">Template context</p>
          <pre className="max-h-72 overflow-auto rounded-md bg-muted/40 p-3 text-xs">{stringifyJson(preview.templateContext)}</pre>
        </div>
      </div>
    </div>
  );
}

function TemplateVariableRows({ rows, onRowsChange }: { rows: RuntimeInputRow[]; onRowsChange: (rows: RuntimeInputRow[]) => void }) {
  const updateRow = (rowId: string, field: "key" | "value", value: string) => {
    onRowsChange(rows.map((row) => (row.id === rowId ? { ...row, [field]: value } : row)));
  };

  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-lg border bg-muted/20 p-3" data-testid="scheduled-task-new-template-vars">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-medium">Template variables</h3>
          <p className="text-xs text-muted-foreground">Rows become vars.&lt;key&gt; values during preview and materialization.</p>
        </div>
        <Button size="sm" type="button" variant="outline" onClick={() => onRowsChange([...rows, createRuntimeInputRow("scheduled-template-vars")])}>
          Add variable
        </Button>
      </div>
      {rows.map((row) => (
        <div className="grid min-w-0 gap-2 sm:grid-cols-[minmax(8rem,14rem)_minmax(0,1fr)]" key={row.id}>
          <Input aria-label={`Template variable key ${row.key || row.id}`} className="h-8 text-xs" placeholder="portfolioSlug" value={row.key} onChange={(event) => updateRow(row.id, "key", event.target.value)} />
          <Input aria-label={`Template variable value ${row.key || row.id}`} className="h-8 text-xs" placeholder="core_portfolio" value={row.value} onChange={(event) => updateRow(row.id, "value", event.target.value)} />
        </div>
      ))}
    </div>
  );
}

export function ScheduledTaskEditorPage() {
  const navigate = useNavigate();
  const createSchedule = useCreateScheduledTask();
  const previewSchedule = usePreviewUnsavedScheduledTask();
  const [preview, setPreview] = useState<SchedulePreviewRead | null>(null);
  const [draft, setDraft] = useState<NewScheduleDraft>(() => ({
    atLocalTime: "09:00",
    description: "",
    inputTemplateText: defaultInputTemplateText(),
    misfireGraceSeconds: "86400",
    name: "",
    packageId: "",
    previewScheduledFor: "",
    templateVarRows: [],
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    workflowKey: "",
  }));
  const isPending = createSchedule.isPending || previewSchedule.isPending;
  const inputTemplateError = useMemo(() => {
    try {
      parseJsonObject(draft.inputTemplateText);
      return null;
    } catch (error) {
      return error instanceof Error ? error.message : "Scheduled input template JSON is invalid.";
    }
  }, [draft.inputTemplateText]);

  const updateDraft = (updates: Partial<NewScheduleDraft>) => {
    setDraft((current) => ({ ...current, ...updates }));
    setPreview(null);
  };

  const previewCurrentDraft = async () => {
    try {
      const payload = buildCreatePayload(draft);
      const result = await previewSchedule.mutateAsync({
        inputTemplate: payload.inputTemplate,
        packageId: payload.packageId,
        recurrence: payload.recurrence,
        scheduledFor: serializeDateTimeLocal(draft.previewScheduledFor),
        templateVars: payload.templateVars,
        timezone: payload.timezone,
        workflowKey: payload.workflowKey,
      });
      setPreview(result);
      toast.success(result.ready ? "Scheduled input preview rendered" : "Preview returned validation errors");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Scheduled input preview failed.");
    }
  };

  const saveSchedule = async () => {
    try {
      const created = await createSchedule.mutateAsync(buildCreatePayload(draft));
      toast.success("Scheduled task saved");
      navigate(`/scheduled-tasks/${created.id}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save scheduled task.");
    }
  };

  return (
    <section className="flex h-full min-w-0 flex-col gap-4 overflow-y-auto p-4" data-testid="scheduled-task-new-page">
      <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">New Scheduled Task</h1>
          <p className="max-w-2xl text-sm text-muted-foreground">Create a backend-backed Workflow Package schedule, preview scheduled input substitution, then save into the Scheduled Tasks route family.</p>
        </div>
        <Button asChild size="sm" variant="outline"><Link to="/scheduled-tasks">Back to Scheduled Tasks</Link></Button>
      </div>
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base"><CalendarClock className="size-4" /> Schedule target</CardTitle>
          <CardDescription>Use a saved Workflow Package id and workflow key. The schedule targets the current package artifact at fire time.</CardDescription>
        </CardHeader>
        <CardContent className="grid min-w-0 gap-4 lg:grid-cols-2">
          <div className="flex flex-col gap-2"><Label htmlFor="schedule-package-id">Package id</Label><Input id="schedule-package-id" data-testid="schedule-package-id" inputMode="numeric" value={draft.packageId} onChange={(event) => updateDraft({ packageId: event.target.value })} /></div>
          <div className="flex flex-col gap-2"><Label htmlFor="schedule-workflow-key">Workflow key</Label><Input id="schedule-workflow-key" data-testid="schedule-workflow-key" value={draft.workflowKey} onChange={(event) => updateDraft({ workflowKey: event.target.value })} /></div>
          <div className="flex flex-col gap-2"><Label htmlFor="schedule-name">Schedule name</Label><Input id="schedule-name" data-testid="schedule-name" value={draft.name} onChange={(event) => updateDraft({ name: event.target.value })} /></div>
          <div className="flex flex-col gap-2"><Label htmlFor="schedule-timezone">Timezone</Label><Input id="schedule-timezone" value={draft.timezone} onChange={(event) => updateDraft({ timezone: event.target.value })} /></div>
          <div className="flex flex-col gap-2"><Label htmlFor="schedule-at-local-time">Daily local time</Label><Input id="schedule-at-local-time" type="time" value={draft.atLocalTime} onChange={(event) => updateDraft({ atLocalTime: event.target.value })} /></div>
          <div className="flex flex-col gap-2"><Label htmlFor="schedule-preview-scheduled-for">Preview scheduled for</Label><Input id="schedule-preview-scheduled-for" data-testid="schedule-preview-scheduled-for" type="datetime-local" value={draft.previewScheduledFor} onChange={(event) => updateDraft({ previewScheduledFor: event.target.value })} /></div>
          <div className="flex flex-col gap-2 lg:col-span-2"><Label htmlFor="schedule-description">Description</Label><Input id="schedule-description" value={draft.description} onChange={(event) => updateDraft({ description: event.target.value })} /></div>
        </CardContent>
      </Card>
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle className="text-base">Scheduled inputs</CardTitle>
          <CardDescription>JSON placeholders support schedule.*, fire.*, window.*, lastRun.*, and vars.&lt;key&gt; namespaces.</CardDescription>
        </CardHeader>
        <CardContent className="flex min-w-0 flex-col gap-4">
          {inputTemplateError ? <Alert variant="destructive"><AlertCircle /><AlertTitle>Input template needs attention</AlertTitle><AlertDescription>{inputTemplateError}</AlertDescription></Alert> : null}
          <div className="flex min-w-0 flex-col gap-2"><Label htmlFor="schedule-input-template-json">Scheduled input template JSON</Label><Textarea id="schedule-input-template-json" aria-label="Scheduled input template JSON" className="min-h-56 font-mono text-xs" data-testid="schedule-input-template-json" value={draft.inputTemplateText} onChange={(event) => updateDraft({ inputTemplateText: event.target.value })} /></div>
          <TemplateVariableRows rows={draft.templateVarRows} onRowsChange={(rows) => updateDraft({ templateVarRows: rows })} />
          <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
            <Button data-testid="schedule-input-preview-trigger" disabled={isPending || Boolean(inputTemplateError)} type="button" variant="outline" onClick={() => void previewCurrentDraft()}>{previewSchedule.isPending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : null} Preview next fire</Button>
            <Button data-testid="schedule-save" disabled={isPending || Boolean(inputTemplateError)} type="button" onClick={() => void saveSchedule()}>{createSchedule.isPending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : null} Save schedule</Button>
          </div>
          <ScheduleInputPreview preview={preview} />
        </CardContent>
      </Card>
    </section>
  );
}
