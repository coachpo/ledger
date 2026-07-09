import {
  AlertCircle,
  CalendarClock,
  ChevronDown,
  CopyPlus,
  ExternalLink,
  Loader2,
  PauseCircle,
  PlayCircle,
  RotateCcw,
  Trash2,
} from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { ConfirmDeleteDialog } from "@/components/shared/confirm-delete-dialog";
import { ConsoleSection } from "@/components/shared/console-section";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { ResourceActionsMenu } from "@/components/shared/resource-actions-menu";
import {
  ResourceStatusStrip,
  type ResourceStatusStripItem,
} from "@/components/shared/resource-status-strip";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
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
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
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
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  useDeleteScheduledTask,
  usePreviewUnsavedScheduledTask,
  useRunScheduledTaskNow,
  useScheduledTask,
  useScheduledTaskFires,
  useUpdateScheduledTask,
} from "@/hooks/use-scheduled-tasks";
import {
  useWorkflowPackageManifest,
} from "@/hooks/use-workflow-packages";
import { ApiRequestError } from "@/lib/api-client";
import { formatDateTime, formatDateTimeInTimeZone } from "@/lib/format";
import { getWorkflowOptions } from "@/lib/workflow-options";
import { stringifyJson } from "@/lib/platform-authoring/common/serialization";
import {
  createLaunchParametersTemplate,
  resetLaunchParametersTemplate,
} from "@/lib/platform-authoring/schema/schema-template";
import {
  buildRuntimeInputs,
  createRuntimeInputRow,
  createRuntimeInputRows,
  type RuntimeInputRow,
} from "@/lib/runtime-inputs";
import type { ApiErrorDetail, UnknownRecord } from "@/lib/types/common";
import type {
  ScheduleDayOfWeek,
  ScheduleFireListRead,
  ScheduleFireRead,
  ScheduleFireStatus,
  ScheduleIntervalUnit,
  ScheduleMisfirePolicy,
  ScheduleOverlapPolicy,
  SchedulePreviewRead,
  ScheduleRead,
  ScheduleRecurrence,
  ScheduleRecurrenceType,
  ScheduleStatus,
  ScheduleUpdateRequest,
  ScheduleValidationError,
  ScheduleWriteStatus,
} from "@/lib/types/schedule";

import { ScheduleDateTimePicker, ScheduleTimePicker } from "./pickers";
import { buildTimeZoneOptions, resolveBrowserTimeZone } from "./time-zones";

type DiagnosticSeverity = "error" | "warning" | "info";

type ScheduleDiagnostic = {
  message: string;
  severity: DiagnosticSeverity;
  title: string;
};

type FireHistoryState = {
  error: Error | null;
  fires: readonly ScheduleFireRead[];
  isError: boolean;
  isPending: boolean;
  totalCount: number;
};

type RunNowFeedback = {
  fireId: number;
  message: string;
  runId: number;
  severity: DiagnosticSeverity;
  title: string;
};

type ScheduleEditorDraft = {
  atLocalTime: string;
  daysOfMonth: number[];
  daysOfWeek: ScheduleDayOfWeek[];
  description: string;
  endsAt: string;
  every: number;
  intervalUnit: ScheduleIntervalUnit;
  misfireGraceSeconds: number;
  misfirePolicy: ScheduleMisfirePolicy;
  name: string;
  overlapPolicy: ScheduleOverlapPolicy;
  recurrenceType: ScheduleRecurrenceType;
  startsAt: string;
  status: ScheduleWriteStatus;
  timezone: string;
};

type ScheduleInputDraft = {
  inputTemplate: UnknownRecord;
  templateVars: UnknownRecord;
};
const FIRE_HISTORY_ROW_DEFERRED_CLASS_NAME =
  "[content-visibility:auto] [contain-intrinsic-size:auto_320px]";

const SCHEDULE_PLACEHOLDER_GROUPS = [
  {
    items: [
      "schedule.id",
      "schedule.name",
      "schedule.timezone",
      "schedule.packageKey",
      "schedule.workflowKey",
    ],
    title: "Schedule",
  },
  {
    items: [
      "fire.id",
      "fire.reason",
      "fire.scheduledFor",
      "fire.scheduledLocalDate",
      "fire.scheduledLocalTime",
      "fire.scheduledLocalDateTime",
      "fire.materializedAt",
    ],
    title: "Fire",
  },
  {
    items: ["window.start", "window.end", "window.startDate", "window.endDate"],
    title: "Window",
  },
  {
    items: ["lastRun.id", "lastRun.status", "lastRun.completedAt"],
    title: "Last run",
  },
  {
    items: ["vars.<key>"],
    title: "Vars",
  },
] as const;

const EXACT_SCHEDULE_PLACEHOLDER_EXPRESSIONS = new Set([
  "schedule.id",
  "schedule.name",
  "schedule.timezone",
  "schedule.packageKey",
  "schedule.workflowKey",
  "fire.id",
  "fire.reason",
  "fire.scheduledFor",
  "fire.scheduledLocalDate",
  "fire.scheduledLocalTime",
  "fire.scheduledLocalDateTime",
  "fire.materializedAt",
  "window.start",
  "window.end",
  "window.startDate",
  "window.endDate",
  "lastRun.id",
  "lastRun.status",
  "lastRun.completedAt",
]);

const PLACEHOLDER_PATTERN = /{{\s*([^{}]+?)\s*}}/g;
const TEMPLATE_VAR_KEY_PATTERN = /^[A-Za-z0-9_.-]+$/;

const DAY_OF_WEEK_OPTIONS: Array<{ label: string; value: ScheduleDayOfWeek }> =
  [
    { label: "Monday", value: "mon" },
    { label: "Tuesday", value: "tue" },
    { label: "Wednesday", value: "wed" },
    { label: "Thursday", value: "thu" },
    { label: "Friday", value: "fri" },
    { label: "Saturday", value: "sat" },
    { label: "Sunday", value: "sun" },
  ];

const MONTH_DAY_OPTIONS = Array.from({ length: 31 }, (_, index) => index + 1);

const STALE_WORKFLOW_RUNTIME_INPUTS_UNAVAILABLE_MESSAGE =
  "Runtime inputs are unavailable because this schedule references a workflow that is no longer in the package manifest.";
const PENDING_WORKFLOW_RUNTIME_INPUTS_UNAVAILABLE_MESSAGE =
  "Runtime inputs are unavailable until the current package manifest finishes loading.";
const ERROR_WORKFLOW_RUNTIME_INPUTS_UNAVAILABLE_MESSAGE =
  "Runtime inputs are unavailable until the current package manifest can be loaded.";
const MISSING_WORKFLOW_RUNTIME_INPUTS_UNAVAILABLE_MESSAGE =
  "Runtime inputs are unavailable until this schedule resolves to a current manifest workflow.";

type ScheduleWorkflowState = {
  activeWorkflowKey: string;
  inputSchema: UnknownRecord | null;
  isStale: boolean;
  packageDisplayLabel: string;
  workflowDisplayLabel: string;
};

function resolveScheduleWorkflowState(
  schedule: ScheduleRead,
  manifest: unknown,
): ScheduleWorkflowState {
  const persistedWorkflowKey = schedule.workflowKey.trim();
  const fallbackPackageLabel = schedule.packageKey.trim() || "package";
  if (!manifest) {
    return {
      activeWorkflowKey: "",
      inputSchema: null,
      isStale: false,
      packageDisplayLabel: fallbackPackageLabel,
      workflowDisplayLabel: persistedWorkflowKey || "workflow",
    };
  }

  const manifestRecord =
    manifest && typeof manifest === "object" && !Array.isArray(manifest)
      ? (manifest as UnknownRecord)
      : null;
  const packageDefinition =
    manifestRecord && isUnknownRecord(manifestRecord.packageDefinition)
      ? manifestRecord.packageDefinition
      : null;
  const metadata =
    packageDefinition && isUnknownRecord(packageDefinition.metadata)
      ? packageDefinition.metadata
      : null;
  const packageDisplayLabel =
    typeof metadata?.name === "string" && metadata.name.trim().length > 0
      ? metadata.name.trim()
      : fallbackPackageLabel;
  const workflowOptions = getWorkflowOptions(
    manifest as Parameters<typeof getWorkflowOptions>[0],
    persistedWorkflowKey || null,
  );
  const displayWorkflowLabel =
    workflowOptions.find((option) => option.key === persistedWorkflowKey)
      ?.label ??
    persistedWorkflowKey ??
    "workflow";
  const manifestWorkflow = getWorkflowOptions(
    manifest as Parameters<typeof getWorkflowOptions>[0],
  ).find((option) => option.key === persistedWorkflowKey);
  const inputSchema =
    manifestWorkflow &&
    typeof manifestWorkflow.inputSchema === "object" &&
    manifestWorkflow.inputSchema &&
    !Array.isArray(manifestWorkflow.inputSchema)
      ? (manifestWorkflow.inputSchema as UnknownRecord)
      : null;

  return {
    activeWorkflowKey: manifestWorkflow?.key ?? "",
    inputSchema,
    isStale: Boolean(persistedWorkflowKey) && !manifestWorkflow,
    packageDisplayLabel,
    workflowDisplayLabel: displayWorkflowLabel || "workflow",
  };
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function isNotFoundError(error: unknown): boolean {
  return error instanceof ApiRequestError && error.status === 404;
}

function isUnknownRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function parseScheduleInputTemplateJson(value: string): UnknownRecord {
  const trimmed = value.trim();
  if (!trimmed) {
    return {};
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed) as unknown;
  } catch {
    throw new Error("Scheduled input template JSON must be valid JSON.");
  }
  if (!isUnknownRecord(parsed)) {
    throw new Error("Scheduled input template JSON must be a valid object.");
  }
  return parsed;
}

function isSupportedPlaceholderExpression(expression: string): boolean {
  if (EXACT_SCHEDULE_PLACEHOLDER_EXPRESSIONS.has(expression)) {
    return true;
  }
  if (!expression.startsWith("vars.")) {
    return false;
  }
  const key = expression.slice("vars.".length);
  return Boolean(key) && TEMPLATE_VAR_KEY_PATTERN.test(key);
}

function collectUnsupportedPlaceholders(
  value: unknown,
  field = "inputTemplate",
): ScheduleValidationError[] {
  if (typeof value === "string") {
    const issues: ScheduleValidationError[] = [];
    for (const match of value.matchAll(PLACEHOLDER_PATTERN)) {
      const expression = match[1]?.trim() ?? "";
      if (!expression || !isSupportedPlaceholderExpression(expression)) {
        issues.push({
          field,
          issue: `Unsupported placeholder "${expression || match[0]}". Use only schedule.*, fire.*, window.*, lastRun.*, or vars.<key>.`,
        });
      }
    }
    return issues;
  }
  if (Array.isArray(value)) {
    return value.flatMap((item, index) =>
      collectUnsupportedPlaceholders(item, `${field}[${index}]`),
    );
  }
  if (isUnknownRecord(value)) {
    return Object.entries(value).flatMap(([key, nestedValue]) =>
      collectUnsupportedPlaceholders(nestedValue, `${field}.${key}`),
    );
  }
  return [];
}

function scheduleInputDraftErrors(
  inputTemplateText: string,
): ScheduleValidationError[] {
  try {
    const inputTemplate = parseScheduleInputTemplateJson(inputTemplateText);
    return collectUnsupportedPlaceholders(inputTemplate);
  } catch (error) {
    return [
      {
        field: "inputTemplate",
        issue:
          error instanceof Error
            ? error.message
            : "Scheduled input template JSON must be valid.",
      },
    ];
  }
}

function summarizeRenderedParameterValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (value === null) {
    return "null";
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return "[]";
    }
    const preview = value
      .slice(0, 2)
      .map(summarizeRenderedParameterValue)
      .join(", ");
    return value.length > 2 ? `[${preview}, ...]` : `[${preview}]`;
  }
  if (isUnknownRecord(value)) {
    const keys = Object.keys(value);
    if (keys.length === 0) {
      return "{}";
    }
    return keys.length > 2
      ? `{${keys.slice(0, 2).join(", ")}, ...}`
      : `{${keys.join(", ")}}`;
  }
  return String(value);
}

function summarizeRenderedParameters(value: unknown): string[] {
  if (isUnknownRecord(value)) {
    const entries = Object.entries(value);
    return entries
      .slice(0, 4)
      .map(
        ([key, entryValue]) =>
          `${key}: ${summarizeRenderedParameterValue(entryValue)}`,
      );
  }
  if (value === undefined) {
    return [];
  }
  return [summarizeRenderedParameterValue(value)];
}

function formatOptionalDateTime(
  value: string | null,
  fallback: string,
): string {
  return value ? formatDateTime(value) : fallback;
}

function formatOptionalDateTimeInTimeZone(
  value: string | null,
  timeZone: string,
  fallback: string,
): string {
  return value ? formatDateTimeInTimeZone(value, timeZone) : fallback;
}

function formatDayOfWeek(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function pluralizeUnit(value: number, unit: string): string {
  return value === 1 ? unit.slice(0, -1) : unit;
}

function formatRecurrence(recurrence: ScheduleRecurrence): string {
  if (recurrence.type === "interval") {
    return `Every ${recurrence.every} ${pluralizeUnit(recurrence.every, recurrence.unit)}`;
  }
  if (recurrence.type === "daily") {
    return `Daily at ${recurrence.atLocalTime}`;
  }
  if (recurrence.type === "weekly") {
    return `Weekly ${recurrence.daysOfWeek.map(formatDayOfWeek).join(", ")} at ${recurrence.atLocalTime}`;
  }
  return `Monthly day ${recurrence.daysOfMonth.join(", ")} at ${recurrence.atLocalTime}`;
}

function formatDateTimeLocalInput(value: string | null): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function serializeDateTimeLocalInput(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const date = new Date(trimmed);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function clampPositiveInteger(value: number, fallback: number): number {
  return Number.isFinite(value) && value > 0 ? Math.trunc(value) : fallback;
}

function scheduleDraftFromRead(schedule: ScheduleRead): ScheduleEditorDraft {
  const baseDraft: ScheduleEditorDraft = {
    atLocalTime: "09:00",
    daysOfMonth: [1],
    daysOfWeek: ["mon", "tue", "wed", "thu", "fri"],
    description: schedule.description ?? "",
    endsAt: formatDateTimeLocalInput(schedule.endsAt),
    every: 1,
    intervalUnit: "hours",
    misfireGraceSeconds: schedule.misfireGraceSeconds,
    misfirePolicy: schedule.misfirePolicy,
    name: schedule.name,
    overlapPolicy: schedule.overlapPolicy,
    recurrenceType: schedule.recurrence.type,
    startsAt: formatDateTimeLocalInput(schedule.startsAt),
    status: schedule.status === "enabled" ? "enabled" : "paused",
    timezone: schedule.timezone,
  };

  if (schedule.recurrence.type === "interval") {
    return {
      ...baseDraft,
      every: schedule.recurrence.every,
      intervalUnit: schedule.recurrence.unit,
    };
  }
  if (schedule.recurrence.type === "daily") {
    return { ...baseDraft, atLocalTime: schedule.recurrence.atLocalTime };
  }
  if (schedule.recurrence.type === "weekly") {
    return {
      ...baseDraft,
      atLocalTime: schedule.recurrence.atLocalTime,
      daysOfWeek: schedule.recurrence.daysOfWeek,
    };
  }
  return {
    ...baseDraft,
    atLocalTime: schedule.recurrence.atLocalTime,
    daysOfMonth: schedule.recurrence.daysOfMonth,
  };
}

function recurrenceFromDraft(draft: ScheduleEditorDraft): ScheduleRecurrence {
  if (draft.recurrenceType === "interval") {
    return {
      every: clampPositiveInteger(draft.every, 1),
      type: "interval",
      unit: draft.intervalUnit,
    };
  }
  if (draft.recurrenceType === "daily") {
    return { atLocalTime: draft.atLocalTime, type: "daily" };
  }
  if (draft.recurrenceType === "weekly") {
    return {
      atLocalTime: draft.atLocalTime,
      daysOfWeek: draft.daysOfWeek,
      type: "weekly",
    };
  }
  return {
    atLocalTime: draft.atLocalTime,
    daysOfMonth: draft.daysOfMonth,
    type: "monthly",
  };
}

function scheduleUpdatePayloadFromDraft(
  draft: ScheduleEditorDraft,
): ScheduleUpdateRequest {
  return {
    description: draft.description.trim() || null,
    endsAt: serializeDateTimeLocalInput(draft.endsAt),
    misfireGraceSeconds: clampPositiveInteger(
      draft.misfireGraceSeconds,
      86_400,
    ),
    misfirePolicy: draft.misfirePolicy,
    name: draft.name.trim(),
    overlapPolicy: draft.overlapPolicy,
    recurrence: recurrenceFromDraft(draft),
    startsAt: serializeDateTimeLocalInput(draft.startsAt),
    status: draft.status,
    timezone: draft.timezone.trim(),
  };
}

function toggleDraftValue<T>(
  values: readonly T[],
  value: T,
  enabled: boolean,
): T[] {
  if (enabled) {
    return values.includes(value) ? [...values] : [...values, value];
  }
  return values.filter((item) => item !== value);
}

function formatStatusLabel(value: string): string {
  return value
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function statusBadgeVariant(status: ScheduleStatus) {
  return status === "enabled" ? ("secondary" as const) : ("outline" as const);
}

function latestStatusBadgeVariant(status: ScheduleFireStatus | null) {
  if (status === "failed") {
    return "destructive" as const;
  }
  if (status === "queued") {
    return "secondary" as const;
  }
  return "outline" as const;
}

function fireStatusBadgeVariant(status: ScheduleFireStatus) {
  if (status === "failed") {
    return "destructive" as const;
  }
  if (status === "queued") {
    return "secondary" as const;
  }
  return "outline" as const;
}

function formatFireReason(value: string): string {
  return value === "manual" ? "Manual fire" : "Scheduled run";
}

function fireIssueMessage(fire: ScheduleFireRead): string | null {
  if (fire.skipReason) {
    return `Skipped: ${formatStatusLabel(fire.skipReason)}`;
  }
  if (fire.errorCode || fire.errorMessage) {
    return [
      fire.errorCode ? formatStatusLabel(fire.errorCode) : null,
      fire.errorMessage,
    ]
      .filter(Boolean)
      .join(" — ");
  }
  if (fire.status === "skipped") {
    return "Skipped without a backend-provided reason.";
  }
  if (fire.status === "failed") {
    return "Failed without a backend-provided error message.";
  }
  return null;
}

function fireLocalSummary(fire: ScheduleFireRead): string {
  if (fire.scheduledLocalDateTime) {
    return fire.scheduledLocalDateTime;
  }
  if (fire.scheduledLocalDate || fire.scheduledLocalTime) {
    return [fire.scheduledLocalDate, fire.scheduledLocalTime]
      .filter(Boolean)
      .join(" ");
  }
  return "No local occurrence recorded";
}

function fireHistoryFromRead(
  read: ScheduleFireListRead | undefined,
): FireHistoryState {
  return {
    error: null,
    fires: read?.items ?? [],
    isError: false,
    isPending: false,
    totalCount: read?.totalCount ?? 0,
  };
}

function buildRunNowFeedback(
  schedule: ScheduleRead,
  fire: ScheduleFireRead,
  runId: number,
): RunNowFeedback {
  const issue = fireIssueMessage(fire);
  if (issue) {
    return {
      fireId: fire.id,
      message: `Manual fire #${fire.id} recorded ${issue}. Opening run #${runId} for evidence.`,
      runId,
      severity: fire.status === "failed" ? "error" : "warning",
      title: "Manual fire needs attention",
    };
  }
  if (schedule.overlapPolicy === "queue") {
    return {
      fireId: fire.id,
      message: `Manual fire #${fire.id} queued run #${runId}. Overlap policy is queue, so active schedule runs may overlap instead of being skipped.`,
      runId,
      severity: "warning",
      title: "Manual fire queued with overlap allowed",
    };
  }
  return {
    fireId: fire.id,
    message: `Scheduled task queued as run #${runId}. Opening run detail.`,
    runId,
    severity: "info",
    title: "Manual fire queued",
  };
}

function buildScheduleDiagnostics(
  schedule: ScheduleRead,
): ScheduleDiagnostic[] {
  const diagnostics: ScheduleDiagnostic[] = [];

  if (schedule.status === "enabled" && !schedule.nextFireAt) {
    diagnostics.push({
      message:
        "This task is enabled, but it does not have another upcoming run yet.",
      severity: "error",
      title: "No upcoming run",
    });
  }

  if (schedule.latestStatus === "failed") {
    diagnostics.push({
      message:
        "The latest run did not finish successfully. Review the recent run details before relying on this task.",
      severity: "error",
      title: "Latest fire failed",
    });
  }

  if (schedule.status === "paused") {
    diagnostics.push({
      message:
        "This task is paused. Its settings stay here, but it will not start new scheduled runs.",
      severity: "warning",
      title: "Schedule paused",
    });
  }

  diagnostics.push({
    message:
      "Custom inputs start from the workflow's current input shape and are only saved after you review the preview.",
    severity: "info",
    title: "Inputs use schema draft source",
  });

  return diagnostics;
}

function StatusBadge({ status }: { status: ScheduleStatus }) {
  return (
    <Badge
      className="capitalize"
      data-testid={`scheduled-task-detail-status-${status}`}
      variant={statusBadgeVariant(status)}
    >
      {status}
    </Badge>
  );
}

function LatestStatusBadge({ status }: { status: ScheduleFireStatus | null }) {
  return (
    <Badge variant={latestStatusBadgeVariant(status)}>
      {status ? formatStatusLabel(status) : "No latest status"}
    </Badge>
  );
}

function DetailPageSkeleton() {
  return (
    <WorkspacePageShell
      bodyAriaLabel="Scheduled task detail loading workspace"
      bodyClassName="gap-4"
      contextBar={<Skeleton className="h-24 w-full" />}
      testId="scheduled-task-detail-page"
    >
      <div
        data-testid="scheduled-task-detail-loading"
        className="grid gap-3 xl:grid-cols-3"
      >
        <Skeleton className="h-36 w-full" />
        <Skeleton className="h-36 w-full" />
        <Skeleton className="h-36 w-full" />
      </div>
      <Skeleton className="h-96 w-full" />
    </WorkspacePageShell>
  );
}

function DetailPageMessage({
  description,
  testId,
  title,
}: {
  description: string;
  testId: string;
  title: string;
}) {
  return (
    <WorkspacePageShell
      bodyAriaLabel="Scheduled task detail message workspace"
      bodyClassName="gap-4"
      contextBar={
        <PageContextBar
          description="Open a saved scheduled task to inspect its schedule, inputs, history, and diagnostics."
          title="Scheduled Task Detail"
        />
      }
      testId="scheduled-task-detail-page"
    >
      <Card
        className="min-w-0 border-destructive/30 bg-destructive/5 shadow-ui-xs"
        data-testid={testId}
      >
        <CardHeader>
          <CardTitle className="flex min-w-0 items-center gap-2 text-destructive">
            <AlertCircle />
            {title}
          </CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild size="sm" variant="outline">
            <Link to="/scheduled-tasks">Back to Scheduled Tasks</Link>
          </Button>
        </CardContent>
      </Card>
    </WorkspacePageShell>
  );
}

function ScheduleHeader({
  mutationPending,
  packageDisplayLabel,
  runNowDisabled,
  schedule,
  workflowDisplayLabel,
  onDelete,
  onRunNow,
  onToggleStatus,
}: {
  mutationPending: boolean;
  packageDisplayLabel: string;
  runNowDisabled: boolean;
  schedule: ScheduleRead;
  workflowDisplayLabel: string;
  onDelete: () => void;
  onRunNow: () => void;
  onToggleStatus: () => void;
}) {
  const toggleLabel = schedule.status === "enabled" ? "Disable" : "Enable";
  const actionDisabled = mutationPending;
  const headerMetaItems: ResourceStatusStripItem[] = [
    { label: "Pattern", value: formatRecurrence(schedule.recurrence) },
    { label: "Timezone", value: schedule.timezone },
    { label: "Package", value: packageDisplayLabel },
    { label: "Workflow", value: workflowDisplayLabel },
    { label: "Updated", value: formatDateTime(schedule.updatedAt) },
  ];

  if (schedule.latestRunId !== null) {
    headerMetaItems.push({
      label: "Last run",
      value: <span className="font-mono">#{schedule.latestRunId}</span>,
    });
  }

  if (schedule.nextFireAt) {
    headerMetaItems.push({
      label: "Next run",
      value: formatDateTimeInTimeZone(schedule.nextFireAt, schedule.timezone),
    });
  }

  const status = (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <span className="min-w-0 break-all font-mono text-xs text-muted-foreground">
        schedule:{schedule.id}
      </span>
      <StatusBadge status={schedule.status} />
    </div>
  );

  const actions = (
    <div className="flex min-w-0 flex-wrap items-center gap-2 sm:justify-end">
      <Button
        className="w-full sm:w-auto"
        data-testid="schedule-run-now"
        disabled={actionDisabled || runNowDisabled}
        size="sm"
        type="button"
        onClick={onRunNow}
      >
        <PlayCircle data-icon="inline-start" />
        Run now
      </Button>
      <Button
        className="w-full sm:w-auto"
        disabled={actionDisabled}
        size="sm"
        type="button"
        variant="outline"
        onClick={onToggleStatus}
      >
        {schedule.status === "enabled" ? (
          <PauseCircle data-icon="inline-start" />
        ) : (
          <RotateCcw data-icon="inline-start" />
        )}
        {toggleLabel}
      </Button>
      <ResourceActionsMenu
        ariaLabel="More actions"
        contentClassName="w-48"
        triggerVariant="outline"
      >
          <DropdownMenuGroup>
            <DropdownMenuItem asChild>
              <Link to={`/workflow-packages/${schedule.packageId}`}>
                <ExternalLink data-icon="inline-start" />
                Open package
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link to={`/scheduled-tasks/new?duplicateFrom=${schedule.id}`}>
                <CopyPlus data-icon="inline-start" />
                Duplicate
              </Link>
            </DropdownMenuItem>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            disabled={mutationPending}
            variant="destructive"
            onSelect={onDelete}
          >
            <Trash2 data-icon="inline-start" />
            Delete
          </DropdownMenuItem>
      </ResourceActionsMenu>
    </div>
  );

  return (
    <div className="min-w-0" data-testid="scheduled-task-detail-header">
      <PageContextBar
        actions={actions}
        density="compact"
        description={
          <span data-testid="scheduled-task-detail-header-description">
            {schedule.description ??
              "Manage this saved Workflow Package schedule."}
          </span>
        }
        meta={
          <div
            className="min-w-0"
            data-testid="scheduled-task-detail-header-meta-row"
          >
            <ResourceStatusStrip
              className="border-0 bg-transparent p-0"
              density="toolbar"
              items={headerMetaItems}
            />
          </div>
        }
        status={status}
        title={schedule.name}
      />
    </div>
  );
}

function SummaryCard({
  action,
  children,
  description,
  testId,
  title,
}: {
  action?: ReactNode;
  children: ReactNode;
  description: string;
  testId?: string;
  title: string;
}) {
  return (
    <ConsoleSection
      actions={action}
      className="min-w-0"
      contentClassName="min-w-0 text-sm"
      description={description}
      testId={testId}
      title={title}
    >
      {children}
    </ConsoleSection>
  );
}

function DetailRows({ rows }: { rows: Array<[string, React.ReactNode]> }) {
  return (
    <dl className="grid min-w-0 gap-3 text-xs sm:grid-cols-2">
      {rows.map(([label, value]) => (
        <div className="min-w-0" key={label}>
          <dt className="font-medium text-muted-foreground">{label}</dt>
          <dd className="min-w-0 break-words text-foreground">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function StaleWorkflowAlert({ workflowKey }: { workflowKey: string }) {
  return (
    <Alert
      data-testid="scheduled-task-stale-workflow-warning"
      variant="default"
    >
      <AlertCircle />
      <AlertTitle>Workflow no longer available</AlertTitle>
      <AlertDescription>
        This schedule still references{" "}
        <span className="font-mono">{workflowKey}</span>, but that workflow is
        no longer present in the current package manifest. Preview, run now, and
        runtime inputs are disabled until the schedule target is recreated.
      </AlertDescription>
    </Alert>
  );
}

function actionableDiagnostics(
  diagnostics: readonly ScheduleDiagnostic[],
): ScheduleDiagnostic[] {
  return diagnostics.filter((diagnostic) => diagnostic.severity !== "info");
}

function SummaryPanels({
  diagnostics,
  packageDisplayLabel,
  schedule,
  workflowDisplayLabel,
  workflowIsStale,
}: {
  diagnostics: readonly ScheduleDiagnostic[];
  packageDisplayLabel: string;
  schedule: ScheduleRead;
  workflowDisplayLabel: string;
  workflowIsStale: boolean;
}) {
  const visibleDiagnostics = actionableDiagnostics(diagnostics);

  return (
    <div
      className="grid min-w-0 gap-3 lg:grid-cols-2 2xl:grid-cols-4"
      data-testid="scheduled-task-detail-summary-grid"
    >
      <SummaryCard
        action={<CalendarClock className="text-muted-foreground" />}
        description="The next scheduled occurrence in this task's timezone."
        testId="scheduled-task-detail-next-run-summary"
        title="Next run"
      >
        <div className="flex min-w-0 flex-col gap-3">
          <p className="break-words text-base font-semibold tracking-tight">
            {formatOptionalDateTimeInTimeZone(
              schedule.nextFireAt,
              schedule.timezone,
              "No upcoming run",
            )}
          </p>
          <DetailRows
            rows={[
              ["Pattern", formatStatusLabel(schedule.recurrence.type)],
              ["Timezone", schedule.timezone],
            ]}
          />
        </div>
      </SummaryCard>
      <SummaryCard
        description="The Workflow Package and workflow this task will launch."
        testId="scheduled-task-detail-target-summary"
        title="Target workflow"
      >
        <div className="flex min-w-0 flex-col gap-3">
          <DetailRows
            rows={[
              ["Package", packageDisplayLabel],
              ["Workflow", workflowDisplayLabel],
            ]}
          />
          {workflowIsStale ? (
            <StaleWorkflowAlert workflowKey={schedule.workflowKey} />
          ) : null}
        </div>
      </SummaryCard>
      <SummaryCard
        description="Most recent scheduled or manual run evidence."
        testId="scheduled-task-detail-last-run-summary"
        title="Last run"
      >
        <div className="flex min-w-0 flex-col gap-3">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <LatestStatusBadge status={schedule.latestStatus} />
            {schedule.latestRunId ? (
              <Button asChild size="sm" variant="outline">
                <Link to={`/runs/${schedule.latestRunId}`}>
                  Open run #{schedule.latestRunId}
                </Link>
              </Button>
            ) : null}
          </div>
          <DetailRows
            rows={[
              [
                "Fire",
                schedule.latestFireId ? `#${schedule.latestFireId}` : "None",
              ],
              [
                "Run",
                schedule.latestRunId ? `#${schedule.latestRunId}` : "None",
              ],
            ]}
          />
        </div>
      </SummaryCard>
      <SummaryCard
        description="Only actionable schedule issues appear by default."
        testId="scheduled-task-detail-health-summary"
        title="Health"
      >
        <div className="flex min-w-0 flex-col gap-3">
          {visibleDiagnostics.length === 0 ? (
            <div className="rounded-lg border border-border/70 bg-card/70 px-3 py-2 text-xs text-muted-foreground shadow-ui-xs">
              Ready for scheduled runs
            </div>
          ) : (
            <div className="flex min-w-0 flex-col gap-2">
              {visibleDiagnostics.map((diagnostic) => (
                <Alert
                  className="min-w-0"
                  key={`${diagnostic.severity}-${diagnostic.title}`}
                  variant={
                    diagnostic.severity === "error" ? "destructive" : "default"
                  }
                >
                  <AlertCircle />
                  <AlertTitle>{diagnostic.title}</AlertTitle>
                  <AlertDescription>{diagnostic.message}</AlertDescription>
                </Alert>
              ))}
            </div>
          )}
        </div>
      </SummaryCard>
    </div>
  );
}

function RunNowFeedbackAlert({
  feedback,
}: {
  feedback: RunNowFeedback | null;
}) {
  if (!feedback) {
    return null;
  }

  return (
    <Alert
      data-testid="scheduled-task-run-now-feedback"
      variant={feedback.severity === "error" ? "destructive" : "default"}
    >
      <AlertCircle />
      <AlertTitle>{feedback.title}</AlertTitle>
      <AlertDescription>
        <span>{feedback.message}</span>{" "}
        <Link
          className="font-medium underline underline-offset-4"
          to={`/runs/${feedback.runId}`}
        >
          Open run #{feedback.runId}
        </Link>
      </AlertDescription>
    </Alert>
  );
}

type ScheduleFieldProps = {
  children: ReactNode;
  description?: string;
  htmlFor?: string;
  label: string;
  labelId?: string;
};

function ScheduleField({
  children,
  description,
  htmlFor,
  label,
  labelId,
}: ScheduleFieldProps) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      {htmlFor ? (
        <Label htmlFor={htmlFor} id={labelId}>
          {label}
        </Label>
      ) : labelId ? (
        <div className="text-sm font-medium leading-none" id={labelId}>
          {label}
        </div>
      ) : (
        <div className="text-sm font-medium leading-none">{label}</div>
      )}
      {children}
      {description ? (
        <p className="text-xs leading-5 text-muted-foreground">{description}</p>
      ) : null}
    </div>
  );
}

function ScheduleConfigurationEditor({
  disabled,
  isSaving,
  schedule,
  onSave,
}: {
  disabled: boolean;
  isSaving: boolean;
  schedule: ScheduleRead;
  onSave: (payload: ScheduleUpdateRequest) => Promise<void>;
}) {
  const [draft, setDraft] = useState<ScheduleEditorDraft>(() =>
    scheduleDraftFromRead(schedule),
  );

  const browserTimeZone = useMemo(() => resolveBrowserTimeZone(), []);
  const timeZoneOptions = useMemo(
    () =>
      buildTimeZoneOptions({
        browserTimeZone,
        selectedTimeZone: draft.timezone,
      }),
    [browserTimeZone, draft.timezone],
  );
  const controlDisabled = disabled || isSaving;
  const updateDraft = (updates: Partial<ScheduleEditorDraft>) => {
    setDraft((current) => ({ ...current, ...updates }));
  };
  const saveDraft = async () => {
    await onSave(scheduleUpdatePayloadFromDraft(draft));
  };

  return (
    <div
      className="flex min-w-0 flex-col gap-5"
      data-testid="scheduled-task-recurrence-editor"
    >
      <div className="grid min-w-0 gap-4 lg:grid-cols-2">
        <ScheduleField
          description="This title appears in the scheduled task header and list views."
          htmlFor="schedule-name"
          label="Schedule name"
        >
          <Input
            id="schedule-name"
            value={draft.name}
            disabled={controlDisabled}
            onChange={(event) => updateDraft({ name: event.target.value })}
          />
        </ScheduleField>
        <ScheduleField
          description="Optional operator context. Blank descriptions are cleared when you save."
          htmlFor="schedule-description"
          label="Description"
        >
          <Textarea
            id="schedule-description"
            value={draft.description}
            disabled={controlDisabled}
            onChange={(event) =>
              updateDraft({ description: event.target.value })
            }
          />
        </ScheduleField>
      </div>

      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,16rem)_minmax(0,1fr)]">
        <ScheduleField
          description="Enabled tasks keep creating future runs. Paused tasks keep their setup and history without starting new ones."
          label="Enabled state"
        >
          <div className="flex items-center gap-3 rounded-lg border p-3">
            <Switch
              aria-label="Schedule enabled"
              checked={draft.status === "enabled"}
              disabled={controlDisabled}
              onCheckedChange={(checked) =>
                updateDraft({ status: checked ? "enabled" : "paused" })
              }
            />
            <span className="text-sm font-medium">
              {draft.status === "enabled" ? "Enabled" : "Paused"}
            </span>
          </div>
        </ScheduleField>
        <div
          className="scheduled-task-recurrence-timing-grid grid min-w-0 gap-4 rounded-xl border bg-muted/10 p-4 lg:grid-cols-2 xl:grid-cols-4"
          data-testid="scheduled-task-recurrence-timing-grid"
        >
          <ScheduleField
            description="Choose how often this task should run. Time-based schedules follow the timezone above."
            label="Recurrence"
            labelId="schedule-recurrence-type-label"
          >
            <Select
              value={draft.recurrenceType}
              onValueChange={(value: ScheduleRecurrenceType) =>
                updateDraft({ recurrenceType: value })
              }
              disabled={controlDisabled}
            >
              <SelectTrigger
                id="schedule-recurrence-type"
                aria-labelledby="schedule-recurrence-type-label"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="interval">Interval</SelectItem>
                  <SelectItem value="daily">Daily</SelectItem>
                  <SelectItem value="weekly">Weekly</SelectItem>
                  <SelectItem value="monthly">Monthly</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </ScheduleField>
          <ScheduleField
            description="Use an IANA timezone such as America/New_York. Daily, weekly, and monthly times are interpreted as local wall-clock times in this zone."
            label="Timezone"
            labelId="schedule-timezone-label"
          >
            <Select
              value={draft.timezone}
              onValueChange={(timezone) => updateDraft({ timezone })}
              disabled={controlDisabled}
            >
              <SelectTrigger
                id="schedule-timezone"
                aria-labelledby="schedule-timezone-label"
              >
                <SelectValue placeholder="Select timezone..." />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {timeZoneOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </ScheduleField>
          <div
            className={`scheduled-task-recurrence-interval-row min-w-0 lg:col-span-2 xl:col-span-2 ${draft.recurrenceType === "interval" ? "grid gap-4 sm:grid-cols-2 xl:grid-cols-[minmax(0,9rem)_minmax(0,12rem)]" : "hidden"}`}
            data-testid="scheduled-task-recurrence-interval-row"
          >
            <ScheduleField
              description="The first interval fire is anchor + interval, never immediate."
              htmlFor="schedule-interval-every"
              label="Every"
            >
              <Input
                id="schedule-interval-every"
                min={1}
                type="number"
                value={draft.every}
                disabled={controlDisabled}
                onChange={(event) =>
                  updateDraft({
                    every: Number.parseInt(event.target.value, 10) || 1,
                  })
                }
              />
            </ScheduleField>
            <ScheduleField
              label="Interval unit"
              labelId="schedule-interval-unit-label"
            >
              <Select
                value={draft.intervalUnit}
                onValueChange={(value: ScheduleIntervalUnit) =>
                  updateDraft({ intervalUnit: value })
                }
                disabled={controlDisabled}
              >
                <SelectTrigger
                  id="schedule-interval-unit"
                  aria-labelledby="schedule-interval-unit-label"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="minutes">Minutes</SelectItem>
                    <SelectItem value="hours">Hours</SelectItem>
                    <SelectItem value="days">Days</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </ScheduleField>
          </div>
          {draft.recurrenceType !== "interval" ? (
            <div className="lg:col-span-2 xl:col-span-2">
              <ScheduleField
                description="Local time is resolved in the timezone above, including deterministic DST gap/repeat handling."
                label="At local time"
                labelId="schedule-at-local-time-label"
              >
                <ScheduleTimePicker
                  disabled={controlDisabled}
                  label="At local time"
                  value={draft.atLocalTime}
                  onChange={(atLocalTime) => updateDraft({ atLocalTime })}
                />
              </ScheduleField>
            </div>
          ) : null}
        </div>
      </div>

      {draft.recurrenceType === "weekly" ? (
        <ScheduleField
          description="At least one day stays selected so the backend receives a valid weekly daysOfWeek array."
          label="Days of week"
        >
          <div className="grid min-w-0 gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {DAY_OF_WEEK_OPTIONS.map((option) => {
              const checked = draft.daysOfWeek.includes(option.value);
              const disableLastChecked =
                checked && draft.daysOfWeek.length === 1;
              return (
                <label
                  key={option.value}
                  className="flex min-w-0 items-center gap-2 rounded-md border p-2 text-sm"
                >
                  <Checkbox
                    checked={checked}
                    disabled={controlDisabled || disableLastChecked}
                    onCheckedChange={(nextChecked) =>
                      updateDraft({
                        daysOfWeek: toggleDraftValue(
                          draft.daysOfWeek,
                          option.value,
                          nextChecked === true,
                        ),
                      })
                    }
                  />
                  <span>{option.label}</span>
                </label>
              );
            })}
          </div>
        </ScheduleField>
      ) : null}

      {draft.recurrenceType === "monthly" ? (
        <ScheduleField
          description="Invalid dates for a month are skipped, never clamped to the last day of that month."
          label="Days of month"
        >
          <div className="grid min-w-0 grid-cols-4 gap-2 sm:grid-cols-8 lg:grid-cols-12">
            {MONTH_DAY_OPTIONS.map((day) => {
              const checked = draft.daysOfMonth.includes(day);
              const disableLastChecked =
                checked && draft.daysOfMonth.length === 1;
              return (
                <label
                  key={day}
                  className="flex items-center gap-2 rounded-md border p-2 text-sm"
                >
                  <Checkbox
                    checked={checked}
                    disabled={controlDisabled || disableLastChecked}
                    onCheckedChange={(nextChecked) =>
                      updateDraft({
                        daysOfMonth: toggleDraftValue(
                          draft.daysOfMonth,
                          day,
                          nextChecked === true,
                        ).sort((left, right) => left - right),
                      })
                    }
                  />
                  <span>{day}</span>
                </label>
              );
            })}
          </div>
        </ScheduleField>
      ) : null}

      <div
        className="scheduled-task-recurrence-bounds-grid grid min-w-0 gap-4 rounded-xl border bg-muted/10 p-4 sm:grid-cols-2"
        data-testid="scheduled-task-recurrence-bounds-grid"
      >
        <ScheduleField
          description="Leave blank for no lower bound. Interval schedules anchor to startsAt when supplied."
          label="Starts at"
          labelId="schedule-starts-at-label"
        >
          <ScheduleDateTimePicker
            clearLabel="Clear starts at date and time"
            disabled={controlDisabled}
            label="Starts at"
            labelId="schedule-starts-at-label"
            placeholder="Pick a date and time"
            triggerId="schedule-starts-at"
            triggerTestId="schedule-starts-at-trigger"
            value={draft.startsAt}
            onChange={(startsAt) => updateDraft({ startsAt })}
          />
        </ScheduleField>
        <ScheduleField
          description="Leave blank to keep this task running without an end date."
          label="Ends at"
          labelId="schedule-ends-at-label"
        >
          <ScheduleDateTimePicker
            clearLabel="Clear ends at date and time"
            disabled={controlDisabled}
            label="Ends at"
            labelId="schedule-ends-at-label"
            placeholder="Pick a date and time"
            triggerId="schedule-ends-at"
            triggerTestId="schedule-ends-at-trigger"
            value={draft.endsAt}
            onChange={(endsAt) => updateDraft({ endsAt })}
          />
        </ScheduleField>
      </div>

      <Collapsible className="min-w-0 rounded-xl border bg-card p-3">
        <div className="flex min-w-0 items-center justify-between gap-3">
          <div className="min-w-0">
            <h3 className="text-sm font-semibold">Extra settings</h3>
            <p className="text-xs leading-5 text-muted-foreground">
              Tune overlap and missed-run handling only when this task needs
              custom behavior.
            </p>
          </div>
          <CollapsibleTrigger asChild>
            <Button
              aria-label="Advanced options"
              className="h-7 shrink-0 gap-1 px-2 text-xs"
              size="sm"
              type="button"
              variant="ghost"
            >
              More options
              <ChevronDown className="size-3" />
            </Button>
          </CollapsibleTrigger>
        </div>
        <CollapsibleContent className="pt-4">
          <div className="grid min-w-0 gap-4 border-t pt-4 lg:grid-cols-3">
            <ScheduleField
              description="Skip records the occurrence when an earlier run is still queued or running; queue allows another run."
              label="Overlap policy"
              labelId="schedule-overlap-policy-label"
            >
              <Select
                value={draft.overlapPolicy}
                onValueChange={(value: ScheduleOverlapPolicy) =>
                  updateDraft({ overlapPolicy: value })
                }
                disabled={controlDisabled}
              >
                <SelectTrigger
                  id="schedule-overlap-policy"
                  aria-labelledby="schedule-overlap-policy-label"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="skip">Skip overlapping fire</SelectItem>
                    <SelectItem value="queue">Queue overlapping run</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </ScheduleField>
            <ScheduleField
              description="Choose whether missed occurrences are skipped or the latest eligible occurrence is run."
              label="Misfire policy"
              labelId="schedule-misfire-policy-label"
            >
              <Select
                value={draft.misfirePolicy}
                onValueChange={(value: ScheduleMisfirePolicy) =>
                  updateDraft({ misfirePolicy: value })
                }
                disabled={controlDisabled}
              >
                <SelectTrigger
                  id="schedule-misfire-policy"
                  aria-labelledby="schedule-misfire-policy-label"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="skip">Skip missed occurrence</SelectItem>
                    <SelectItem value="catchUpOne">Catch up one</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </ScheduleField>
            <ScheduleField
              description="Grace is measured in seconds. Older missed occurrences are ignored."
              htmlFor="schedule-misfire-grace"
              label="Misfire grace seconds"
            >
              <Input
                id="schedule-misfire-grace"
                min={1}
                type="number"
                value={draft.misfireGraceSeconds}
                disabled={controlDisabled}
                onChange={(event) =>
                  updateDraft({
                    misfireGraceSeconds:
                      Number.parseInt(event.target.value, 10) || 1,
                  })
                }
              />
            </ScheduleField>
          </div>
        </CollapsibleContent>
      </Collapsible>

      <div className="flex justify-end">
        <Button
          disabled={controlDisabled}
          type="button"
          onClick={() => void saveDraft()}
        >
          {isSaving ? "Saving schedule..." : "Save schedule"}
        </Button>
      </div>
    </div>
  );
}

function ScheduleInputValidationAlert({
  errors,
  testId,
  title,
}: {
  errors: readonly ScheduleValidationError[] | readonly ApiErrorDetail[];
  testId: string;
  title: string;
}) {
  if (errors.length === 0) {
    return null;
  }

  return (
    <Alert data-testid={testId} variant="destructive">
      <AlertCircle />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>
        <ul className="flex list-disc flex-col gap-1 pl-5">
          {errors.map((error) => (
            <li
              className="min-w-0 break-words"
              key={`${error.field}-${error.issue}`}
            >
              <code className="break-all rounded bg-muted/40 px-1 py-0.5 text-xs">
                {error.field}
              </code>
              : {error.issue}
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

function ScheduleTemplateVarsEditor({
  disabled,
  rows,
  onRowsChange,
}: {
  disabled: boolean;
  rows: RuntimeInputRow[];
  onRowsChange: (rows: RuntimeInputRow[]) => void;
}) {
  const updateRow = (rowId: string, field: "key" | "value", value: string) => {
    onRowsChange(
      rows.map((row) => (row.id === rowId ? { ...row, [field]: value } : row)),
    );
  };

  return (
    <div
      className="min-w-0 rounded-xl border bg-card p-3"
      data-testid="scheduled-input-template-vars"
    >
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <div className="min-w-0">
          <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Template variables
          </span>
          <p className="text-xs leading-5 text-muted-foreground">
            Each row becomes a <code>{"vars.<key>"}</code> placeholder you can
            use in custom inputs.
          </p>
        </div>
        <Button
          className="ml-auto h-7 px-2 text-xs"
          disabled={disabled}
          size="sm"
          type="button"
          variant="outline"
          onClick={() =>
            onRowsChange([
              ...rows,
              createRuntimeInputRow("scheduled-template-vars"),
            ])
          }
        >
          Add variable
        </Button>
      </div>
      <div className="mt-2 flex min-w-0 flex-col gap-2">
        {rows.length === 0 ? (
          <p className="rounded-lg border border-border/70 bg-card/70 px-3 py-2 text-xs italic text-muted-foreground shadow-ui-xs">
            No template variables yet.
          </p>
        ) : null}
        {rows.map((row) => (
          <div
            key={row.id}
            className="grid min-w-0 gap-2 sm:grid-cols-[minmax(8rem,14rem)_minmax(0,1fr)_2rem]"
          >
            <Input
              aria-label={`Template variable key ${row.key || row.id}`}
              className="h-8 min-w-0 text-xs"
              disabled={disabled}
              placeholder="analysisTag"
              value={row.key}
              onChange={(event) => updateRow(row.id, "key", event.target.value)}
            />
            <Input
              aria-label={`Template variable value ${row.key || row.id}`}
              className="h-8 min-w-0 text-xs"
              disabled={disabled}
              placeholder="daily_research"
              value={row.value}
              onChange={(event) =>
                updateRow(row.id, "value", event.target.value)
              }
            />
            <Button
              aria-label={`Remove template variable ${row.key || row.id}`}
              className="size-8"
              disabled={disabled}
              size="icon"
              type="button"
              variant="ghost"
              onClick={() =>
                onRowsChange(rows.filter((item) => item.id !== row.id))
              }
            >
              <Trash2 className="size-3" />
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}

function SchedulePlaceholderReference() {
  return (
    <Collapsible
      className="min-w-0 rounded-xl border bg-card p-3"
      data-testid="scheduled-input-placeholder-reference"
      defaultOpen
    >
      <div className="flex min-w-0 items-center justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">
            Allowed scheduled placeholders
          </h3>
          <p className="text-xs leading-5 text-muted-foreground">
            Use only these supported placeholder groups when you build custom
            inputs.
          </p>
        </div>
        <CollapsibleTrigger asChild>
          <Button
            className="h-7 shrink-0 gap-1 px-2 text-xs"
            size="sm"
            type="button"
            variant="ghost"
          >
            Reference
            <ChevronDown className="size-3" />
          </Button>
        </CollapsibleTrigger>
      </div>
      <CollapsibleContent className="pt-3">
        <div className="flex min-w-0 flex-col gap-3 border-t pt-3">
          <div className="grid min-w-0 gap-3 lg:grid-cols-2 2xl:grid-cols-5">
            {SCHEDULE_PLACEHOLDER_GROUPS.map((group) => (
              <div
                className="min-w-0 rounded-lg border border-border/70 bg-card/70 p-3 shadow-ui-xs"
                key={group.title}
              >
                <div className="flex min-w-0 items-center justify-between gap-2">
                  <h4 className="text-xs font-semibold tracking-tight">
                    {group.title}
                  </h4>
                  <Badge variant="secondary">{group.items.length}</Badge>
                </div>
                <div className="mt-2 flex min-w-0 flex-wrap gap-2">
                  {group.items.map((example) => (
                    <Badge
                      className="font-mono"
                      key={example}
                      variant="outline"
                    >
                      {`{{${example}}}`}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <p className="text-xs leading-5 text-muted-foreground">
            Use a full placeholder when you want to keep the original JSON type.
            Mixed text values are always saved as strings.
          </p>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function workflowInputsUnavailableReason(params: {
  manifestError: boolean;
  manifestPending: boolean;
  workflowKey: string;
  workflowState: ScheduleWorkflowState;
}): string | null {
  if (params.manifestPending) {
    return PENDING_WORKFLOW_RUNTIME_INPUTS_UNAVAILABLE_MESSAGE;
  }
  if (params.manifestError) {
    return ERROR_WORKFLOW_RUNTIME_INPUTS_UNAVAILABLE_MESSAGE;
  }
  if (params.workflowState.isStale) {
    return STALE_WORKFLOW_RUNTIME_INPUTS_UNAVAILABLE_MESSAGE;
  }
  if (!params.workflowState.activeWorkflowKey || !params.workflowKey.trim()) {
    return MISSING_WORKFLOW_RUNTIME_INPUTS_UNAVAILABLE_MESSAGE;
  }
  return null;
}

function ScheduleInputPreview({
  preview,
  timeZone,
}: {
  preview: SchedulePreviewRead | null;
  timeZone: string;
}) {
  if (!preview) {
    return (
      <div
        className="rounded-lg border border-border/70 bg-card/70 p-3 text-xs leading-5 text-muted-foreground shadow-ui-xs"
        data-testid="schedule-input-preview-empty"
      >
        Preview the next run to fill in placeholders and check the input shape
        before saving.
      </div>
    );
  }

  return (
    <div
      className="flex min-w-0 flex-col gap-3 rounded-lg border border-border/70 bg-card/70 p-3 shadow-ui-xs"
      data-testid="schedule-input-preview"
    >
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <Badge variant={preview.ready ? "secondary" : "destructive"}>
          {preview.ready ? "Ready" : "Not ready"}
        </Badge>
        <span className="text-xs text-muted-foreground">
          Scheduled for{" "}
          {preview.scheduledFor
            ? formatDateTimeInTimeZone(preview.scheduledFor, timeZone)
            : "not available"}
        </span>
      </div>
      <ScheduleInputValidationAlert
        errors={preview.validationErrors}
        testId="scheduled-input-preview-validation-feedback"
        title="Preview validation failed"
      />
      <div className="grid min-w-0 gap-3 lg:grid-cols-2">
        <div className="min-w-0">
          <p className="mb-1 text-xs font-medium text-muted-foreground">
            Rendered parameters
          </p>
          <pre className="max-h-72 overflow-auto rounded-md bg-muted/40 p-3 text-xs">
            {stringifyJson(preview.renderedParameters)}
          </pre>
        </div>
        <div className="min-w-0">
          <p className="mb-1 text-xs font-medium text-muted-foreground">
            Template context
          </p>
          <pre className="max-h-72 overflow-auto rounded-md bg-muted/40 p-3 text-xs">
            {stringifyJson(preview.templateContext)}
          </pre>
        </div>
      </div>
    </div>
  );
}

function ScheduledInputsEditor({
  activeWorkflowKey,
  disabled,
  inputSchema,
  isSaving,
  schedule,
  workflowInputsUnavailableReason,
  onSave,
}: {
  activeWorkflowKey: string;
  disabled: boolean;
  inputSchema: UnknownRecord | null;
  isSaving: boolean;
  schedule: ScheduleRead;
  workflowInputsUnavailableReason: string | null;
  onSave: (
    payload: ScheduleUpdateRequest,
    successMessage?: string,
  ) => Promise<void>;
}) {
  const previewScheduledInputs = usePreviewUnsavedScheduledTask();
  const [inputTemplateText, setInputTemplateText] = useState(() =>
    stringifyJson({}),
  );
  const [templateVarRows, setTemplateVarRows] = useState<RuntimeInputRow[]>(
    () => createRuntimeInputRows("scheduled-template-vars"),
  );
  const [previewRead, setPreviewRead] = useState<SchedulePreviewRead | null>(
    null,
  );
  const [previewRequestErrors, setPreviewRequestErrors] = useState<
    ScheduleValidationError[]
  >([]);
  const inputTemplateEditedRef = useRef(false);
  const lastTemplateIdentityRef = useRef<string | null>(null);

  const inputSchemaFingerprint = stringifyJson(inputSchema ?? {});
  const inputTemplate = useMemo(
    () => createLaunchParametersTemplate(inputSchema),
    [inputSchema],
  );
  const schemaTemplateText = useMemo(
    () => resetLaunchParametersTemplate(inputTemplate),
    [inputTemplate],
  );
  const templateIdentity = `${schedule.packageId}:${activeWorkflowKey}:${inputSchemaFingerprint}`;
  const draftErrors = useMemo(
    () => scheduleInputDraftErrors(inputTemplateText),
    [inputTemplateText],
  );
  const controlDisabled = disabled || isSaving;
  const canUseNextFire = Boolean(schedule.nextFireAt);

  useEffect(() => {
    if (lastTemplateIdentityRef.current === templateIdentity) {
      return;
    }
    lastTemplateIdentityRef.current = templateIdentity;
    setPreviewRead(null);
    setPreviewRequestErrors([]);
    if (!inputTemplateEditedRef.current) {
      setInputTemplateText(schemaTemplateText);
    }
  }, [schemaTemplateText, templateIdentity]);

  if (workflowInputsUnavailableReason) {
    return (
      <Alert data-testid="scheduled-inputs-unavailable" variant="default">
        <AlertCircle />
        <AlertTitle>Runtime inputs unavailable</AlertTitle>
        <AlertDescription>{workflowInputsUnavailableReason}</AlertDescription>
      </Alert>
    );
  }

  const updateInputTemplateText = (value: string) => {
    inputTemplateEditedRef.current = true;
    let nextValue = value;
    try {
      nextValue = stringifyJson(parseScheduleInputTemplateJson(value));
    } catch {
      nextValue = value;
    }
    setInputTemplateText(nextValue);
    setPreviewRead(null);
    setPreviewRequestErrors([]);
  };

  const resetInputTemplate = () => {
    inputTemplateEditedRef.current = false;
    setInputTemplateText(schemaTemplateText);
    setPreviewRead(null);
    setPreviewRequestErrors([]);
  };

  const buildDraft = (): ScheduleInputDraft | null => {
    if (draftErrors.length > 0) {
      toast.error(
        draftErrors[0]?.issue ?? "Fix scheduled input template errors first.",
      );
      return null;
    }
    return {
      inputTemplate: parseScheduleInputTemplateJson(inputTemplateText),
      templateVars: buildRuntimeInputs(templateVarRows),
    };
  };

  const previewDraft = async (
    draft: ScheduleInputDraft,
  ): Promise<SchedulePreviewRead | null> => {
    if (!schedule.nextFireAt) {
      const errors = [
        {
          field: "scheduledFor",
          issue:
            "Next fire is unavailable, so the scheduled input template cannot be rendered yet.",
        },
      ];
      setPreviewRequestErrors(errors);
      setPreviewRead(null);
      toast.error(errors[0].issue);
      return null;
    }
    try {
      const result = await previewScheduledInputs.mutateAsync({
        packageId: schedule.packageId,
        workflowKey: activeWorkflowKey,
        timezone: schedule.timezone,
        recurrence: schedule.recurrence,
        scheduledFor: schedule.nextFireAt,
        inputTemplate: draft.inputTemplate,
        templateVars: draft.templateVars,
      });
      setPreviewRead(result);
      setPreviewRequestErrors([]);
      if (result.ready) {
        toast.success("Scheduled input preview rendered for the next fire");
      } else {
        toast.warning("Scheduled input preview returned validation errors");
      }
      return result;
    } catch (error) {
      const fallbackIssue = errorMessage(
        error,
        "Scheduled input preview failed.",
      );
      const errors =
        error instanceof ApiRequestError && error.details.length > 0
          ? error.details.map((detail) => ({
              field: detail.field ?? "preview",
              issue: detail.issue ?? fallbackIssue,
            }))
          : [{ field: "preview", issue: fallbackIssue }];
      setPreviewRequestErrors(errors);
      setPreviewRead(null);
      toast.error(errorMessage(error, "Scheduled input preview failed."));
      return null;
    }
  };

  const previewCurrentDraft = async () => {
    const draft = buildDraft();
    if (!draft) {
      return;
    }
    await previewDraft(draft);
  };

  const saveInputTemplate = async () => {
    const draft = buildDraft();
    if (!draft) {
      return;
    }
    const preview = await previewDraft(draft);
    if (!preview?.ready) {
      return;
    }
    await onSave(
      {
        inputTemplate: draft.inputTemplate,
        templateVars: draft.templateVars,
      },
      "Scheduled input template saved",
    );
  };

  return (
    <div
      className="flex min-w-0 flex-col gap-4"
      data-testid="scheduled-inputs-editor"
    >
      {!canUseNextFire ? (
        <Alert variant="destructive">
          <AlertCircle />
          <AlertTitle>Next fire preview unavailable</AlertTitle>
          <AlertDescription>
            Next run preview and save are blocked until a future occurrence
            exists.
          </AlertDescription>
        </Alert>
      ) : null}
      <ScheduleInputValidationAlert
        errors={draftErrors}
        testId="scheduled-input-json-validation-feedback"
        title="Scheduled input template needs attention"
      />
      <ScheduleInputValidationAlert
        errors={previewRequestErrors}
        testId="scheduled-input-preview-request-feedback"
        title="Scheduled input preview failed"
      />
      <div
        className="flex min-w-0 flex-col gap-3"
        data-testid="scheduled-input-json-panel"
      >
        <div
          className="scheduled-inputs-toolbar flex min-w-0 flex-col gap-3 rounded-xl border bg-muted/10 p-3 lg:flex-row lg:items-center lg:justify-between"
          data-testid="scheduled-inputs-toolbar"
        >
          <div className="min-w-0">
            <Label htmlFor="schedule-input-template-json">
              Scheduled input template JSON
            </Label>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Edit the workflow-seeded template, preview the next fire, then
              save the validated payload back to this task.
            </p>
          </div>
          <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:flex-wrap lg:justify-end">
            <Button
              disabled={controlDisabled}
              size="sm"
              type="button"
              variant="outline"
              onClick={resetInputTemplate}
            >
              Reset to schema template
            </Button>
            <Button
              disabled={
                controlDisabled ||
                previewScheduledInputs.isPending ||
                draftErrors.length > 0 ||
                !canUseNextFire
              }
              size="sm"
              type="button"
              variant="outline"
              onClick={() => void previewCurrentDraft()}
            >
              {previewScheduledInputs.isPending ? (
                <Loader2 className="animate-spin" data-icon="inline-start" />
              ) : null}
              Preview next run
            </Button>
            <Button
              disabled={
                controlDisabled ||
                previewScheduledInputs.isPending ||
                draftErrors.length > 0 ||
                !canUseNextFire
              }
              size="sm"
              type="button"
              onClick={() => void saveInputTemplate()}
            >
              {isSaving || previewScheduledInputs.isPending ? (
                <Loader2 className="animate-spin" data-icon="inline-start" />
              ) : null}
              Save inputs
            </Button>
          </div>
        </div>
        <Textarea
          id="schedule-input-template-json"
          aria-label="Scheduled input template JSON"
          className="min-h-[18rem] max-h-[30rem] max-w-full overflow-auto whitespace-pre font-mono text-xs leading-5"
          disabled={controlDisabled}
          rows={16}
          value={inputTemplateText}
          onChange={(event) => updateInputTemplateText(event.target.value)}
        />
        <ScheduleInputPreview
          preview={previewRead}
          timeZone={schedule.timezone}
        />
      </div>
      <div className="flex min-w-0 flex-col gap-3">
        {!inputTemplate.schemaSupported ? (
          <Alert data-testid="scheduled-input-schema-template-warning">
            <AlertCircle />
            <AlertTitle>Schema template started empty</AlertTitle>
            <AlertDescription>
              {inputTemplate.reason ??
                "The workflow input schema could not seed a JSON object template."}
            </AlertDescription>
          </Alert>
        ) : null}
        <SchedulePlaceholderReference />
        <ScheduleTemplateVarsEditor
          disabled={controlDisabled}
          rows={templateVarRows}
          onRowsChange={setTemplateVarRows}
        />
      </div>
    </div>
  );
}

function FireHistoryRow({
  fire,
  timeZone,
}: {
  fire: ScheduleFireRead;
  timeZone: string;
}) {
  const issue = fireIssueMessage(fire);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const parameterSummary = summarizeRenderedParameters(fire.renderedParameters);

  return (
    <div
      className={`flex min-w-0 flex-col gap-3 rounded-lg border border-border/70 bg-card/70 p-3 shadow-ui-xs ${FIRE_HISTORY_ROW_DEFERRED_CLASS_NAME}`}
      data-testid={`scheduled-task-fire-${fire.id}`}
    >
      <div className="flex min-w-0 flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <p className="text-sm font-semibold tracking-tight">
              Fire #{fire.id}
            </p>
            <Badge
              className="capitalize"
              variant={fireStatusBadgeVariant(fire.status)}
            >
              {formatStatusLabel(fire.status)}
            </Badge>
            <Badge variant="outline">{formatFireReason(fire.reason)}</Badge>
          </div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            Occurrence {formatDateTimeInTimeZone(fire.scheduledFor, timeZone)} ·
            Schedule local {fireLocalSummary(fire)}
          </p>
        </div>
        {fire.runId ? (
          <Button
            asChild
            className="w-full lg:w-auto"
            size="sm"
            variant="outline"
          >
            <Link
              aria-label={`Open run #${fire.runId} for fire #${fire.id}`}
              to={`/runs/${fire.runId}`}
            >
              Open run #{fire.runId}
              <ExternalLink data-icon="inline-end" />
            </Link>
          </Button>
        ) : (
          <Button
            className="w-full lg:w-auto"
            disabled
            size="sm"
            type="button"
            variant="outline"
          >
            No linked run
          </Button>
        )}
      </div>
      <DetailRows
        rows={[
          ["Fire key", <span className="font-mono">{fire.fireKey}</span>],
          [
            "Prepared",
            formatOptionalDateTime(fire.materializedAt, "Not prepared"),
          ],
          ["Created", formatDateTime(fire.createdAt)],
          ["Linked run", fire.runId ? `#${fire.runId}` : "None"],
        ]}
      />
      <div className="flex min-w-0 flex-wrap items-center gap-2 rounded-lg border border-border/70 bg-card/70 px-3 py-2 text-xs shadow-ui-xs">
        <span className="font-medium text-muted-foreground">Parameters</span>
        {parameterSummary.length > 0 ? (
          parameterSummary.map((item) => (
            <Badge
              className="max-w-full font-mono"
              key={`${fire.id}-${item}`}
              variant="secondary"
            >
              {item}
            </Badge>
          ))
        ) : (
          <span className="text-muted-foreground">No rendered parameters</span>
        )}
      </div>
      {issue ? (
        <Alert
          data-testid={`scheduled-task-fire-issue-${fire.id}`}
          variant={fire.status === "failed" ? "destructive" : "default"}
        >
          <AlertCircle />
          <AlertTitle>
            {fire.status === "failed" ? "Fire failed" : "Fire skipped"}
          </AlertTitle>
          <AlertDescription>{issue}</AlertDescription>
        </Alert>
      ) : null}
      <Collapsible
        className="min-w-0"
        open={detailsOpen}
        onOpenChange={setDetailsOpen}
      >
        <div className="flex min-w-0 flex-col gap-2 rounded-lg border border-border/70 bg-card/70 px-3 py-2 shadow-ui-xs sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-medium text-foreground">
              Rendered parameters
            </p>
            <p className="text-xs text-muted-foreground">
              Open the full JSON only when you need the expanded payload.
            </p>
          </div>
          <CollapsibleTrigger asChild>
            <Button
              aria-label={`${detailsOpen ? "Hide" : "Show"} details for fire #${fire.id}`}
              className="h-7 shrink-0 gap-1 px-2 text-xs"
              size="sm"
              type="button"
              variant="ghost"
            >
              {detailsOpen ? "Hide details" : "Show details"}
              <ChevronDown
                className={`size-3 ${detailsOpen ? "rotate-180" : ""}`}
              />
            </Button>
          </CollapsibleTrigger>
        </div>
        <CollapsibleContent className="pt-2">
          <div
            className="min-w-0"
            data-testid={`scheduled-task-fire-details-${fire.id}`}
          >
            <pre
              className="max-h-56 overflow-auto rounded-md bg-muted/40 p-3 text-xs"
              data-testid={`scheduled-task-fire-parameters-${fire.id}`}
            >
              {stringifyJson(fire.renderedParameters)}
            </pre>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}

function normalizeFireHistoryState(
  history: FireHistoryState | undefined,
): FireHistoryState {
  return (
    history ?? {
      error: null,
      fires: [],
      isError: false,
      isPending: false,
      totalCount: 0,
    }
  );
}

function FireHistoryPanel({
  history,
  latestRunId,
  onRunNow,
  runNowDisabled,
  timeZone,
}: {
  history: FireHistoryState | undefined;
  latestRunId: number | null;
  onRunNow: () => void;
  runNowDisabled: boolean;
  timeZone: string;
}) {
  const safeHistory = normalizeFireHistoryState(history);

  if (safeHistory.isPending) {
    return <p className="text-xs text-muted-foreground">Loading runs...</p>;
  }
  if (safeHistory.isError) {
    return (
      <Alert
        data-testid="scheduled-task-fire-history-error"
        variant="destructive"
      >
        <AlertCircle />
        <AlertTitle>Runs unavailable</AlertTitle>
        <AlertDescription>
          {safeHistory.error?.message ?? "Failed to load runs for this task."}
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div
      className="flex min-w-0 flex-col gap-3"
      data-testid="scheduled-task-fire-history-panel"
    >
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-2 text-xs">
          <Badge variant="outline">{safeHistory.totalCount} total fires</Badge>
        </div>
        {latestRunId ? (
          <Button
            asChild
            className="w-full sm:w-auto"
            size="sm"
            variant="outline"
          >
            <Link to={`/runs/${latestRunId}`}>
              Open latest run #{latestRunId}
              <ExternalLink data-icon="inline-end" />
            </Link>
          </Button>
        ) : null}
      </div>
      {safeHistory.fires.length === 0 ? (
        <div className="flex min-w-0 flex-col gap-3 rounded-lg border border-border/70 bg-card/70 px-3 py-3 text-xs text-muted-foreground shadow-ui-xs">
          <div>
            <p className="font-medium text-foreground">No runs yet</p>
            <p>Scheduled and manual runs will appear here.</p>
          </div>
          <div>
            <Button
              className="h-8"
              disabled={runNowDisabled}
              size="sm"
              type="button"
              onClick={onRunNow}
            >
              <PlayCircle data-icon="inline-start" />
              Run now
            </Button>
          </div>
        </div>
      ) : null}
      <div className="flex min-w-0 flex-col gap-3">
        {safeHistory.fires.map((fire) => (
          <FireHistoryRow fire={fire} key={fire.id} timeZone={timeZone} />
        ))}
      </div>
    </div>
  );
}

function ScheduleTabs({
  diagnostics,
  fireHistory,
  mutationPending,
  onRunNow,
  onSaveSchedule,
  packageDisplayLabel,
  runNowDisabled,
  schedule,
  workflowDisplayLabel,
  workflowIsStale,
  workflowInputSchema,
  workflowInputsUnavailableReason,
  workflowRegistryKey,
}: {
  diagnostics: readonly ScheduleDiagnostic[];
  fireHistory: FireHistoryState | undefined;
  mutationPending: boolean;
  onRunNow: () => void;
  onSaveSchedule: (
    payload: ScheduleUpdateRequest,
    successMessage?: string,
  ) => Promise<void>;
  packageDisplayLabel: string;
  runNowDisabled: boolean;
  schedule: ScheduleRead;
  workflowDisplayLabel: string;
  workflowIsStale: boolean;
  workflowInputSchema: UnknownRecord | null;
  workflowInputsUnavailableReason: string | null;
  workflowRegistryKey: string;
}) {
  const [activeTab, setActiveTab] = useState<
    "overview" | "schedule" | "inputs" | "runs"
  >("overview");

  return (
    <Tabs
      className="min-h-0 min-w-0 flex-1 gap-3"
      value={activeTab}
      onValueChange={(value) =>
        setActiveTab(value as "overview" | "schedule" | "inputs" | "runs")
      }
    >
      <TabsList
        aria-label="Scheduled task detail sections"
        className="h-8 max-w-full shrink-0 justify-start overflow-x-auto"
      >
        <TabsTrigger value="overview">Overview</TabsTrigger>
        <TabsTrigger value="schedule">Schedule</TabsTrigger>
        <TabsTrigger value="inputs">Inputs</TabsTrigger>
        <TabsTrigger value="runs">Runs</TabsTrigger>
      </TabsList>
      <TabsContent
        className="m-0 min-h-0 min-w-0 overflow-auto data-[state=inactive]:hidden"
        data-testid="scheduled-task-detail-tab-overview"
        value="overview"
      >
        <SummaryPanels
          diagnostics={diagnostics}
          packageDisplayLabel={packageDisplayLabel}
          schedule={schedule}
          workflowDisplayLabel={workflowDisplayLabel}
          workflowIsStale={workflowIsStale}
        />
      </TabsContent>
      <TabsContent
        className="m-0 min-h-0 min-w-0 overflow-auto data-[state=inactive]:hidden"
        data-testid="scheduled-task-detail-tab-schedule"
        forceMount
        value="schedule"
      >
        <SummaryCard
          description="Update timing, timezone, and advanced run rules for this task."
          title="Schedule configuration"
        >
          <ScheduleConfigurationEditor
            key={`${schedule.id}:${schedule.updatedAt}`}
            disabled={false}
            isSaving={mutationPending}
            schedule={schedule}
            onSave={onSaveSchedule}
          />
        </SummaryCard>
      </TabsContent>
      <TabsContent
        className="m-0 min-h-0 min-w-0 overflow-auto data-[state=inactive]:hidden"
        data-testid="scheduled-task-detail-tab-inputs"
        forceMount
        value="inputs"
      >
        <SummaryCard
          description="Review the workflow-seeded input template, placeholders, and future-run values."
          title="Inputs"
        >
          <ScheduledInputsEditor
            activeWorkflowKey={workflowRegistryKey}
            disabled={false}
            inputSchema={workflowInputSchema}
            isSaving={mutationPending}
            schedule={schedule}
            workflowInputsUnavailableReason={workflowInputsUnavailableReason}
            onSave={onSaveSchedule}
          />
        </SummaryCard>
      </TabsContent>
      <TabsContent
        className="m-0 min-h-0 min-w-0 overflow-auto data-[state=inactive]:hidden"
        data-testid="scheduled-task-detail-tab-runs"
        value="runs"
      >
        <div className="flex min-w-0 flex-col gap-3">
          <SummaryCard
            description="Recent scheduled and manual runs for this task."
            title="Runs"
          >
            <FireHistoryPanel
              history={fireHistory}
              latestRunId={schedule.latestRunId}
              onRunNow={onRunNow}
              runNowDisabled={runNowDisabled}
              timeZone={schedule.timezone}
            />
          </SummaryCard>
        </div>
      </TabsContent>
    </Tabs>
  );
}

export function ScheduledTaskDetailPage() {
  const { scheduleId } = useParams<{ scheduleId: string }>();
  const navigate = useNavigate();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [runNowFeedback, setRunNowFeedback] = useState<RunNowFeedback | null>(
    null,
  );
  const scheduleQuery = useScheduledTask(scheduleId);
  const workflowManifestQuery = useWorkflowPackageManifest(
    scheduleQuery.data?.packageId,
  );
  const firesQuery = useScheduledTaskFires(scheduleId, { limit: 20 });
  const updateSchedule = useUpdateScheduledTask();
  const runNow = useRunScheduledTaskNow();
  const deleteSchedule = useDeleteScheduledTask();

  if (!scheduleId) {
    return (
      <DetailPageMessage
        description="The scheduled task route is missing a schedule id."
        testId="scheduled-task-detail-not-found"
        title="Scheduled task not found"
      />
    );
  }

  if (scheduleQuery.isPending) {
    return <DetailPageSkeleton />;
  }

  if (scheduleQuery.isError) {
    return isNotFoundError(scheduleQuery.error) ? (
      <DetailPageMessage
        description="No scheduled task exists for this route. It may be unavailable in this environment."
        testId="scheduled-task-detail-not-found"
        title="Scheduled task not found"
      />
    ) : (
      <DetailPageMessage
        description={errorMessage(
          scheduleQuery.error,
          "Failed to load scheduled task.",
        )}
        testId="scheduled-task-detail-error"
        title="Failed to load scheduled task"
      />
    );
  }

  if (!scheduleQuery.data) {
    return (
      <DetailPageMessage
        description="No scheduled task exists for this route."
        testId="scheduled-task-detail-not-found"
        title="Scheduled task not found"
      />
    );
  }

  const schedule = scheduleQuery.data;
  const workflowState = resolveScheduleWorkflowState(
    schedule,
    workflowManifestQuery.data,
  );
  const workflowScopedActionUnavailableReason = workflowInputsUnavailableReason(
    {
      manifestError: workflowManifestQuery.isError,
      manifestPending: workflowManifestQuery.isPending,
      workflowKey: schedule.workflowKey,
      workflowState,
    },
  );
  const diagnostics = buildScheduleDiagnostics(schedule);
  const fireHistory = {
    ...fireHistoryFromRead(firesQuery?.data),
    error: firesQuery?.error ?? null,
    isError: firesQuery?.isError ?? false,
    isPending: firesQuery?.isPending ?? false,
  };
  const mutationPending =
    updateSchedule.isPending || runNow.isPending || deleteSchedule.isPending;
  const runNowDisabled =
    mutationPending || Boolean(workflowScopedActionUnavailableReason);

  const toggleScheduleStatus = async () => {
    const nextStatus: ScheduleWriteStatus =
      schedule.status === "enabled" ? "paused" : "enabled";
    try {
      await updateSchedule.mutateAsync({
        scheduleId: schedule.id,
        payload: { status: nextStatus },
      });
      toast.success(
        `Scheduled task ${nextStatus === "enabled" ? "resumed" : "paused"}`,
      );
    } catch (error) {
      toast.error(
        errorMessage(error, "Failed to update scheduled task status."),
      );
    }
  };

  const runScheduleNow = async () => {
    if (workflowScopedActionUnavailableReason) {
      return;
    }

    const scheduledFor = new Date().toISOString();
    try {
      const result = await runNow.mutateAsync({
        scheduleId: schedule.id,
        payload: {
          idempotencyKey: `manual-${schedule.id}-${scheduledFor}`,
          scheduledFor,
        },
      });
      const feedback = buildRunNowFeedback(
        schedule,
        result.fire,
        result.run.id,
      );
      setRunNowFeedback(feedback);
      if (feedback.severity === "info") {
        toast.success(feedback.message);
      } else if (feedback.severity === "error") {
        toast.error(feedback.message);
      } else {
        toast.warning(feedback.message);
      }
      navigate(`/runs/${result.run.id}`);
    } catch (error) {
      toast.error(errorMessage(error, "Failed to run scheduled task now."));
    }
  };

  const saveScheduleConfiguration = async (
    payload: ScheduleUpdateRequest,
    successMessage = "Scheduled task configuration saved",
  ) => {
    try {
      await updateSchedule.mutateAsync({
        scheduleId: schedule.id,
        payload,
      });
      toast.success(successMessage);
    } catch (error) {
      toast.error(
        errorMessage(error, "Failed to save scheduled task configuration."),
      );
    }
  };

  const confirmDelete = async () => {
    try {
      await deleteSchedule.mutateAsync({
        latestRunId: schedule.latestRunId,
        scheduleId: schedule.id,
      });
      toast.success("Scheduled task deleted");
      setDeleteDialogOpen(false);
      navigate("/scheduled-tasks");
    } catch (error) {
      toast.error(errorMessage(error, "Failed to delete scheduled task."));
    }
  };

  return (
    <WorkspacePageShell
      bodyAriaLabel="Scheduled task detail workspace"
      bodyClassName="gap-3"
      contextBar={
        <ScheduleHeader
          mutationPending={mutationPending}
          packageDisplayLabel={workflowState.packageDisplayLabel}
          runNowDisabled={runNowDisabled}
          schedule={schedule}
          workflowDisplayLabel={workflowState.workflowDisplayLabel}
          onDelete={() => setDeleteDialogOpen(true)}
          onRunNow={() => void runScheduleNow()}
          onToggleStatus={() => void toggleScheduleStatus()}
        />
      }
      testId="scheduled-task-detail-page"
    >
      <RunNowFeedbackAlert feedback={runNowFeedback} />
      <ScheduleTabs
        diagnostics={diagnostics}
        fireHistory={fireHistory}
        mutationPending={mutationPending}
        onRunNow={() => void runScheduleNow()}
        onSaveSchedule={saveScheduleConfiguration}
        packageDisplayLabel={workflowState.packageDisplayLabel}
        runNowDisabled={runNowDisabled}
        schedule={schedule}
        workflowDisplayLabel={workflowState.workflowDisplayLabel}
        workflowIsStale={workflowState.isStale}
        workflowInputSchema={workflowState.inputSchema}
        workflowInputsUnavailableReason={workflowScopedActionUnavailableReason}
        workflowRegistryKey={workflowState.activeWorkflowKey}
      />
      <ConfirmDeleteDialog
        confirmLabel="Delete scheduled task"
        description={`Delete ${schedule.name}? This removes the schedule and its directly owned run history.`}
        isPending={deleteSchedule.isPending}
        open={deleteDialogOpen}
        title="Delete scheduled task"
        onConfirm={confirmDelete}
        onOpenChange={setDeleteDialogOpen}
      />
    </WorkspacePageShell>
  );
}
