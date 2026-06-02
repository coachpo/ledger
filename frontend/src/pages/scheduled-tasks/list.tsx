import {
  AlertTriangle,
  CalendarClock,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  CopyPlus,
  ExternalLink,
  MoreHorizontal,
  PauseCircle,
  PlayCircle,
  RotateCcw,
  SquarePen,
  Trash2,
} from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";

import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";
import { EmptyStatePanel } from "@/components/shared/empty-state-panel";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { ResourceFilterBar } from "@/components/shared/resource-filter-bar";
import {
  ResourceStatusBadge,
  type ResourceStatusTone,
} from "@/components/shared/resource-status-strip";
import { ResourceTableFrame } from "@/components/shared/resource-table-frame";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/components/ui/utils";
import {
  useDeleteScheduledTask,
  useDeleteScheduledTasks,
  useRunScheduledTaskNow,
  useScheduledTasks,
  useUpdateScheduledTask,
} from "@/hooks/use-scheduled-tasks";
import {
  useWorkflowPackageManifest,
  useWorkflowPackages,
} from "@/hooks/use-workflow-packages";
import { formatDateTime } from "@/lib/format";
import type {
  ScheduleListParams,
  ScheduleRead,
  ScheduleRecurrence,
  ScheduleStatus,
  ScheduleWriteStatus,
} from "@/lib/types/schedule";
import type { WorkflowPackageRead } from "@/lib/types/workflow-package";
import {
  getWorkflowOptions,
  type WorkflowOption,
} from "@/lib/workflow-options";

const ALL_PACKAGES_FILTER = "__all_packages__";
const ALL_STATUS_FILTER = "__all_status__";
const ALL_WORKFLOWS_FILTER = "__all_workflows__";
const MOBILE_BREAKPOINT = 768;

const STATUS_FILTER_OPTIONS = [
  { label: "All", value: ALL_STATUS_FILTER },
  { label: "Running", value: "running" },
  { label: "Failed", value: "failed" },
  { label: "Succeeded", value: "succeeded" },
  { label: "Paused", value: "paused" },
] as const;

type LocalStatusFilter = (typeof STATUS_FILTER_OPTIONS)[number]["value"];
type StatusTone = ResourceStatusTone;
type ScheduleSortField = "workflow" | "nextRun" | "latestActivity";
type ScheduleSortDirection = "asc" | "desc";
type ScheduleSortState = {
  direction: ScheduleSortDirection;
  field: ScheduleSortField;
};

type ScheduleSelectionHandlers = {
  onSelect: (schedulesToUpdate: readonly ScheduleRead[], selected: boolean) => void;
};

type ScheduleActionHandlers = {
  mutationPending: boolean;
  onDelete: (schedule: ScheduleRead) => void;
  onRunNow: (schedule: ScheduleRead) => void;
  onToggleStatus: (schedule: ScheduleRead) => void;
};

function normalizeFilter(value: string): string | undefined {
  const normalized = value.trim();
  return normalized ? normalized : undefined;
}

function formatOptionalDateTime(value: string | null, fallback: string): string {
  return value ? formatDateTime(value) : fallback;
}

function formatStatusLabel(value: string): string {
  return value
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function scheduleStatusTone(status: ScheduleStatus): StatusTone {
  return status === "enabled" ? "success" : "muted";
}

function getLatestStatus(
  schedule: Pick<ScheduleRead, "latestStatus">,
): string | null {
  return schedule.latestStatus ?? null;
}

function latestStatusTone(status: string | null): StatusTone {
  if (status === "succeeded") {
    return "success";
  }
  if (status === "queued" || status === "pending" || status === "running") {
    return "warning";
  }
  if (status === "failed") {
    return "danger";
  }
  if (status === "skipped") {
    return "muted";
  }
  return "neutral";
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

function formatDurationFromMs(milliseconds: number): string {
  const absolute = Math.abs(milliseconds);
  const units = [
    { label: "month", milliseconds: 1000 * 60 * 60 * 24 * 30 },
    { label: "week", milliseconds: 1000 * 60 * 60 * 24 * 7 },
    { label: "day", milliseconds: 1000 * 60 * 60 * 24 },
    { label: "hour", milliseconds: 1000 * 60 * 60 },
    { label: "minute", milliseconds: 1000 * 60 },
  ];

  if (absolute < 1000 * 60) {
    return "under a minute";
  }

  for (const unit of units) {
    if (absolute >= unit.milliseconds) {
      const value = Math.round(absolute / unit.milliseconds);
      return `${value} ${value === 1 ? unit.label : `${unit.label}s`}`;
    }
  }

  return "under a minute";
}

function formatRelativeNextRun(value: string | null): string {
  if (!value) {
    return "No upcoming run";
  }

  const difference = new Date(value).getTime() - Date.now();
  const duration = formatDurationFromMs(difference);
  return difference >= 0 ? `in ${duration}` : `overdue by ${duration}`;
}

function formatRelativeUpdatedAt(value: string): string {
  const difference = new Date(value).getTime() - Date.now();
  const duration = formatDurationFromMs(difference);
  return difference >= 0 ? `updated in ${duration}` : `updated ${duration} ago`;
}

function matchesStatusFilter(
  schedule: ScheduleRead,
  statusFilter: LocalStatusFilter,
): boolean {
  const latestStatus = getLatestStatus(schedule);

  if (statusFilter === ALL_STATUS_FILTER) {
    return true;
  }
  if (statusFilter === "paused") {
    return schedule.status === "paused";
  }
  if (statusFilter === "running") {
    return (
      latestStatus === "pending" ||
      latestStatus === "queued" ||
      latestStatus === "running"
    );
  }
  if (statusFilter === "failed") {
    return latestStatus === "failed";
  }
  if (statusFilter === "succeeded") {
    return latestStatus === "succeeded";
  }
  return false;
}

function filterSchedules(
  schedules: readonly ScheduleRead[],
  search: string,
  statusFilter: LocalStatusFilter,
): ScheduleRead[] {
  const query = search.trim().toLowerCase();

  return schedules.filter((schedule) => {
    if (!matchesStatusFilter(schedule, statusFilter)) {
      return false;
    }

    if (!query) {
      return true;
    }

    return [
      schedule.name,
      schedule.description ?? "",
      schedule.packageKey,
      schedule.workflowKey,
      schedule.status,
      schedule.latestStatus ?? "",
      formatRecurrence(schedule.recurrence),
      schedule.timezone,
      schedule.latestFireId ? `fire ${schedule.latestFireId}` : "",
      schedule.latestRunId ? `run ${schedule.latestRunId}` : "",
    ]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });
}

function defaultSortDirectionForField(
  field: ScheduleSortField,
): ScheduleSortDirection {
  if (field === "latestActivity") {
    return "desc";
  }
  return "asc";
}

function compareNullableDate(
  left: string | null,
  right: string | null,
  direction: ScheduleSortDirection,
): number {
  if (left && right) {
    return direction === "asc"
      ? left.localeCompare(right)
      : right.localeCompare(left);
  }
  if (left) {
    return direction === "asc" ? -1 : 1;
  }
  if (right) {
    return direction === "asc" ? 1 : -1;
  }
  return 0;
}

function sortSchedules(
  items: readonly ScheduleRead[],
  sortState: ScheduleSortState,
): ScheduleRead[] {
  return [...items].sort((left, right) => {
    let result = 0;

    if (sortState.field === "workflow") {
      result = left.name.localeCompare(right.name);
      if (result === 0) {
        result = left.packageKey.localeCompare(right.packageKey);
      }
      if (result === 0) {
        result = left.workflowKey.localeCompare(right.workflowKey);
      }
      if (sortState.direction === "desc") {
        result *= -1;
      }
    }

    if (sortState.field === "nextRun") {
      result = compareNullableDate(
        left.nextFireAt,
        right.nextFireAt,
        sortState.direction,
      );
    }

    if (sortState.field === "latestActivity") {
      result = compareNullableDate(
        left.updatedAt,
        right.updatedAt,
        sortState.direction,
      );
      if (result === 0) {
        result = compareNullableDate(
          left.nextFireAt,
          right.nextFireAt,
          sortState.direction,
        );
      }
    }

    return result !== 0 ? result : left.id - right.id;
  });
}

function getNextRunTone(schedule: ScheduleRead): StatusTone {
  const latestStatus = getLatestStatus(schedule);

  if (latestStatus === "failed") {
    return "danger";
  }
  if (!schedule.nextFireAt) {
    return schedule.status === "paused" ? "muted" : "warning";
  }
  return new Date(schedule.nextFireAt).getTime() < Date.now() ? "warning" : "neutral";
}

function createUnknownWorkflowOption(workflowKey: string): WorkflowOption {
  return {
    description: "Missing manifest workflow",
    inputSchema: {},
    key: workflowKey,
    label: `Unknown workflow: ${workflowKey}`,
  };
}

function buildWorkflowFilterOptions({
  manifestOptions,
  schedules,
  selectedPackageKey,
}: {
  manifestOptions: readonly WorkflowOption[];
  schedules: readonly ScheduleRead[];
  selectedPackageKey: string;
}): WorkflowOption[] {
  const seenKeys = new Set(manifestOptions.map((option) => option.key));
  const staleOptions: WorkflowOption[] = [];

  for (const schedule of schedules) {
    const workflowKey = schedule.workflowKey.trim();
    if (
      schedule.packageKey !== selectedPackageKey ||
      !workflowKey ||
      seenKeys.has(workflowKey)
    ) {
      continue;
    }

    seenKeys.add(workflowKey);
    staleOptions.push(createUnknownWorkflowOption(workflowKey));
  }

  return [...manifestOptions, ...staleOptions];
}

function useIsMobileLayout() {
  const [isMobileLayout, setIsMobileLayout] = useState(
    typeof window !== "undefined" ? window.innerWidth < MOBILE_BREAKPOINT : false,
  );

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    const updateLayout = () => {
      setIsMobileLayout(window.innerWidth < MOBILE_BREAKPOINT);
    };

    updateLayout();
    window.addEventListener("resize", updateLayout);
    return () => window.removeEventListener("resize", updateLayout);
  }, []);

  return isMobileLayout;
}

function LoadingState() {
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 p-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton className="h-14 w-full" key={index} />
        ))}
      </CardContent>
    </Card>
  );
}

function ScheduleStatusFilters({
  status,
  onStatusChange,
}: {
  status: LocalStatusFilter;
  onStatusChange: (status: LocalStatusFilter) => void;
}) {
  return (
    <ToggleGroup
      aria-label="Scheduled task status filter"
      type="single"
      value={status}
      onValueChange={(value) => {
        if (value) {
          onStatusChange(value as LocalStatusFilter);
        }
      }}
    >
      {STATUS_FILTER_OPTIONS.map((option) => (
        <ToggleGroupItem
          className="h-8 px-3 text-xs"
          data-testid={`scheduled-tasks-filter-${option.label.toLowerCase()}`}
          key={option.value}
          value={option.value}
        >
          {option.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

function SelectFilter({
  disabled = false,
  id,
  items,
  label,
  testId,
  value,
  onValueChange,
}: {
  disabled?: boolean;
  id: string;
  items: ReadonlyArray<{ label: string; value: string }>;
  label: string;
  testId: string;
  value: string;
  onValueChange: (value: string) => void;
}) {
  return (
    <div className="flex min-w-40 flex-col gap-1">
      <Label className="sr-only" htmlFor={id}>
        {label}
      </Label>
      <Select disabled={disabled} value={value} onValueChange={onValueChange}>
        <SelectTrigger
          aria-label={label}
          className="min-w-40 text-xs"
          data-testid={testId}
          id={id}
          size="sm"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            {items.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
    </div>
  );
}

function ScheduleFilters({
  packageItems,
  packageKey,
  status,
  workflowDisabled,
  workflowItems,
  workflowKey,
  onPackageKeyChange,
  onStatusChange,
  onWorkflowKeyChange,
}: {
  packageItems: ReadonlyArray<{ label: string; value: string }>;
  packageKey: string;
  status: LocalStatusFilter;
  workflowDisabled: boolean;
  workflowItems: ReadonlyArray<{ label: string; value: string }>;
  workflowKey: string;
  onPackageKeyChange: (value: string) => void;
  onStatusChange: (status: LocalStatusFilter) => void;
  onWorkflowKeyChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-start gap-2">
      <ScheduleStatusFilters status={status} onStatusChange={onStatusChange} />
      <SelectFilter
        id="scheduled-tasks-package-filter"
        items={packageItems}
        label="Package"
        testId="scheduled-tasks-filter-package"
        value={packageKey || ALL_PACKAGES_FILTER}
        onValueChange={onPackageKeyChange}
      />
      <div className="flex min-w-40 flex-col gap-1">
        <SelectFilter
          disabled={workflowDisabled}
          id="scheduled-tasks-workflow-filter"
          items={workflowItems}
          label="Workflow"
          testId="scheduled-tasks-filter-workflow"
          value={workflowKey || ALL_WORKFLOWS_FILTER}
          onValueChange={onWorkflowKeyChange}
        />
        {workflowDisabled ? (
          <p className="text-xs text-muted-foreground">
            Choose a package first to filter by workflow.
          </p>
        ) : null}
      </div>
    </div>
  );
}

function ScheduledTasksPageActions() {
  return (
    <Button asChild size="sm">
      <Link
        aria-label="Create scheduled task"
        data-testid="scheduled-tasks-new"
        to="/scheduled-tasks/new"
      >
        <CalendarClock data-icon="inline-start" />
        New Scheduled Task
      </Link>
    </Button>
  );
}

function renderSortButton({
  field,
  label,
  sortState,
  onSort,
}: {
  field: ScheduleSortField;
  label: string;
  sortState: ScheduleSortState;
  onSort: (field: ScheduleSortField) => void;
}) {
  const isActive = sortState.field === field;
  const directionLabel = sortState.direction === "asc" ? "ascending" : "descending";

  return (
    <Button
      aria-label={
        isActive
          ? `Sort scheduled tasks by ${label} (${directionLabel})`
          : `Sort scheduled tasks by ${label}`
      }
      className="-ml-2 h-8 px-2 text-xs font-medium"
      size="sm"
      title={isActive ? `${label}: ${directionLabel}` : `Sort by ${label}`}
      type="button"
      variant="ghost"
      onClick={() => onSort(field)}
    >
      <span>{label}</span>
      {isActive ? (
        <span aria-hidden="true" className="ml-1">
          {sortState.direction === "asc" ? "↑" : "↓"}
        </span>
      ) : null}
    </Button>
  );
}

function getAriaSort(
  field: ScheduleSortField,
  sortState: ScheduleSortState,
): "ascending" | "descending" | undefined {
  if (sortState.field !== field) {
    return undefined;
  }
  return sortState.direction === "asc" ? "ascending" : "descending";
}

function WorkflowCell({ schedule }: { schedule: ScheduleRead }) {
  return (
    <div className="flex min-w-0 flex-col gap-2 whitespace-normal">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="truncate font-semibold text-foreground">{schedule.name}</span>
        <ResourceStatusBadge
          className="capitalize"
          label={formatStatusLabel(schedule.status)}
          testId={`scheduled-task-status-${schedule.status}`}
          tone={scheduleStatusTone(schedule.status)}
        />
      </div>
      {schedule.description ? (
        <p className="truncate text-xs text-muted-foreground">{schedule.description}</p>
      ) : null}
    </div>
  );
}

function ScheduleDetailsToggleButton({
  className,
  detailsId,
  expanded,
  onToggle,
}: {
  className?: string;
  detailsId: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <Button
      aria-controls={detailsId}
      aria-expanded={expanded}
      className={cn("h-8 px-2", className)}
      size="sm"
      type="button"
      variant="ghost"
      onClick={onToggle}
    >
      {expanded ? (
        <ChevronDown data-icon="inline-start" />
      ) : (
        <ChevronRight data-icon="inline-start" />
      )}
      {expanded ? "Hide details" : "Show details"}
    </Button>
  );
}

function ScheduleCell({ schedule }: { schedule: ScheduleRead }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 whitespace-normal">
      <span className="font-medium text-foreground">{formatRecurrence(schedule.recurrence)}</span>
    </div>
  );
}

function NextRunCell({ schedule }: { schedule: ScheduleRead }) {
  const tone = getNextRunTone(schedule);
  const nextRunLabel = formatOptionalDateTime(schedule.nextFireAt, "No upcoming run");
  const relativeLabel = formatRelativeNextRun(schedule.nextFireAt);
  const showWarning = tone === "warning" || tone === "danger";

  return (
    <div
      className="flex min-w-0 flex-col gap-1 whitespace-normal"
      data-testid={`scheduled-task-row-next-run-${schedule.id}`}
    >
      <div className="flex min-w-0 items-start gap-1.5">
        {showWarning ? <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-500" /> : null}
        <span
          className={cn(
            "font-medium",
            tone === "danger" && "text-destructive",
            tone === "warning" && "text-amber-600",
            tone === "muted" && "text-muted-foreground",
            tone === "neutral" && "text-foreground",
          )}
        >
          {nextRunLabel}
        </span>
      </div>
      <span className="text-xs text-muted-foreground">{relativeLabel}</span>
    </div>
  );
}

function LatestActivityCell({ schedule }: { schedule: ScheduleRead }) {
  const latestStatus = getLatestStatus(schedule);

  return (
    <div
      className="flex min-w-0 flex-col gap-1 whitespace-normal"
      data-testid={`scheduled-task-row-latest-${schedule.id}`}
    >
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <ResourceStatusBadge
          className="capitalize"
          label={latestStatus ? formatStatusLabel(latestStatus) : "No latest status"}
          tone={latestStatusTone(latestStatus)}
        />
      </div>
      <span className="text-xs text-foreground">
        Fire {schedule.latestFireId ? `#${schedule.latestFireId}` : "—"} · Run {schedule.latestRunId ? `#${schedule.latestRunId}` : "—"}
      </span>
      <span className="text-xs text-muted-foreground">{formatRelativeUpdatedAt(schedule.updatedAt)}</span>
    </div>
  );
}

function ScheduleDetailField({
  children,
  label,
  mono = false,
}: {
  children: ReactNode;
  label: string;
  mono?: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 sm:flex-row sm:items-start sm:gap-2">
      <dt className="shrink-0 text-xs font-medium uppercase tracking-wide text-muted-foreground sm:w-28">
        {label}
      </dt>
      <dd
        className={cn(
          "min-w-0 break-words text-xs leading-5 text-foreground",
          mono ? "break-all font-mono" : null,
        )}
      >
        {children}
      </dd>
    </div>
  );
}

function ScheduleDetailGroup({
  children,
  title,
}: {
  children: ReactNode;
  title: string;
}) {
  return (
    <section className="min-w-0">
      <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-foreground">
        {title}
      </h4>
      <dl className="flex min-w-0 flex-col gap-1.5">{children}</dl>
    </section>
  );
}

function ScheduleDetailSections({
  ariaLabel,
  className,
  role,
  schedule,
}: {
  ariaLabel?: string;
  className?: string;
  role?: "group";
  schedule: ScheduleRead;
}) {
  return (
    <div
      aria-label={ariaLabel}
      className={cn("grid min-w-0 gap-x-6 gap-y-2 md:grid-cols-2 xl:grid-cols-4", className)}
      role={role}
    >
      <ScheduleDetailGroup title="Workflow package">
        <ScheduleDetailField label="Package ID">{schedule.packageId}</ScheduleDetailField>
        <ScheduleDetailField label="Package key" mono>
          {schedule.packageKey}
        </ScheduleDetailField>
        <ScheduleDetailField label="Workflow key" mono>
          {schedule.workflowKey}
        </ScheduleDetailField>
      </ScheduleDetailGroup>
      <ScheduleDetailGroup title="Recurrence and policies">
        <ScheduleDetailField label="Recurrence">
          {formatRecurrence(schedule.recurrence)}
        </ScheduleDetailField>
        <ScheduleDetailField label="Overlap policy">
          {formatStatusLabel(schedule.overlapPolicy)}
        </ScheduleDetailField>
        <ScheduleDetailField label="Misfire policy">
          {formatStatusLabel(schedule.misfirePolicy)}
        </ScheduleDetailField>
        <ScheduleDetailField label="Misfire grace">
          {schedule.misfireGraceSeconds} seconds
        </ScheduleDetailField>
      </ScheduleDetailGroup>
      <ScheduleDetailGroup title="Timing">
        <ScheduleDetailField label="Timezone">{schedule.timezone}</ScheduleDetailField>
        <ScheduleDetailField label="Starts">
          {formatOptionalDateTime(schedule.startsAt, "Not set")}
        </ScheduleDetailField>
        <ScheduleDetailField label="Ends">
          {formatOptionalDateTime(schedule.endsAt, "Not set")}
        </ScheduleDetailField>
        <ScheduleDetailField label="Next run">
          {formatOptionalDateTime(schedule.nextFireAt, "No upcoming run")}
        </ScheduleDetailField>
      </ScheduleDetailGroup>
      <ScheduleDetailGroup title="Recent activity">
        <ScheduleDetailField label="Latest fire">
          {schedule.latestFireId ? `#${schedule.latestFireId}` : "None"}
        </ScheduleDetailField>
        <ScheduleDetailField label="Latest run">
          {schedule.latestRunId ? `#${schedule.latestRunId}` : "None"}
        </ScheduleDetailField>
        <ScheduleDetailField label="Updated">
          {formatDateTime(schedule.updatedAt)}
        </ScheduleDetailField>
        <ScheduleDetailField label="Created">
          {formatDateTime(schedule.createdAt)}
        </ScheduleDetailField>
      </ScheduleDetailGroup>
    </div>
  );
}

function ExpandedScheduleDetails({
  className,
  schedule,
}: {
  className?: string;
  schedule: ScheduleRead;
}) {
  return (
    <ScheduleDetailSections
      ariaLabel={`Expanded details for ${schedule.name}`}
      className={cn("rounded-md bg-muted/30 px-3 py-2 text-xs text-muted-foreground", className)}
      role="group"
      schedule={schedule}
    />
  );
}

function MobileActionMenu({
  mutationPending,
  schedule,
  onDelete,
  onToggleStatus,
}: ScheduleActionHandlers & { schedule: ScheduleRead }) {
  const duplicatePath = `/scheduled-tasks/new?duplicateFrom=${schedule.id}`;
  const showPauseAction = schedule.status === "enabled";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          aria-label={`Open actions for ${schedule.name}`}
          size="icon"
          type="button"
          variant="ghost"
        >
          <MoreHorizontal className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuGroup>
          <DropdownMenuItem asChild>
            <Link aria-label={`Edit schedule ${schedule.name}`} to={`/scheduled-tasks/${schedule.id}`}>
              <SquarePen className="size-3.5" />
              Edit
            </Link>
          </DropdownMenuItem>
          {showPauseAction ? (
            <DropdownMenuItem
              disabled={mutationPending}
              onSelect={() => onToggleStatus(schedule)}
            >
              <PauseCircle className="size-3.5" />
              Pause
            </DropdownMenuItem>
          ) : null}
          <DropdownMenuItem asChild>
            <Link aria-label={`Duplicate schedule ${schedule.name}`} to={duplicatePath}>
              <CopyPlus className="size-3.5" />
              Duplicate
            </Link>
          </DropdownMenuItem>
          {schedule.latestRunId ? (
            <DropdownMenuItem asChild>
              <Link
                aria-label={`Open latest run for ${schedule.name}`}
                to={`/runs/${schedule.latestRunId}`}
              >
                <ExternalLink className="size-3.5" />
                Latest run
              </Link>
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem disabled>
              <ExternalLink className="size-3.5" />
              Latest run
            </DropdownMenuItem>
          )}
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          disabled={mutationPending}
          variant="destructive"
          onSelect={() => onDelete(schedule)}
        >
          <Trash2 className="size-3.5" />
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ScheduleTableActions({
  detailsId,
  expanded,
  mutationPending,
  schedule,
  onDelete,
  onRunNow,
  onToggleDetails,
  onToggleStatus,
}: {
  detailsId: string;
  expanded: boolean;
  schedule: ScheduleRead;
  onToggleDetails: () => void;
} & ScheduleActionHandlers) {
  const duplicatePath = `/scheduled-tasks/new?duplicateFrom=${schedule.id}`;
  const isPaused = schedule.status === "paused";

  return (
    <div className="flex flex-wrap justify-end gap-1.5">
      <ScheduleDetailsToggleButton
        detailsId={detailsId}
        expanded={expanded}
        onToggle={onToggleDetails}
      />
      <Button
        aria-label={`Run schedule ${schedule.name} now`}
        className="h-8 px-2"
        disabled={mutationPending}
        size="sm"
        type="button"
        onClick={() => onRunNow(schedule)}
      >
        <PlayCircle data-icon="inline-start" />
        Run now
      </Button>
      <Button
        aria-label={`${isPaused ? "Resume" : "Pause"} schedule ${schedule.name}`}
        className="h-8 px-2"
        disabled={mutationPending}
        size="sm"
        type="button"
        variant="outline"
        onClick={() => onToggleStatus(schedule)}
      >
        {isPaused ? (
          <RotateCcw data-icon="inline-start" />
        ) : (
          <PauseCircle data-icon="inline-start" />
        )}
        {isPaused ? "Resume" : "Pause"}
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            aria-label={`More actions for ${schedule.name}`}
            className="h-8 w-8"
            size="icon"
            type="button"
            variant="outline"
          >
            <MoreHorizontal aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          <DropdownMenuGroup>
            <DropdownMenuItem asChild>
              <Link aria-label={`Edit schedule ${schedule.name}`} to={`/scheduled-tasks/${schedule.id}`}>
                <SquarePen data-icon="inline-start" />
                Edit
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link aria-label={`Duplicate schedule ${schedule.name}`} to={duplicatePath}>
                <CopyPlus data-icon="inline-start" />
                Duplicate
              </Link>
            </DropdownMenuItem>
            {schedule.latestRunId ? (
              <DropdownMenuItem asChild>
                <Link
                  aria-label={`Open latest run for ${schedule.name}`}
                  to={`/runs/${schedule.latestRunId}`}
                >
                  <ExternalLink data-icon="inline-start" />
                  Latest run
                </Link>
              </DropdownMenuItem>
            ) : (
              <DropdownMenuItem disabled>
                <ExternalLink data-icon="inline-start" />
                Latest run
              </DropdownMenuItem>
            )}
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            disabled={mutationPending}
            variant="destructive"
            onSelect={() => onDelete(schedule)}
          >
            <Trash2 data-icon="inline-start" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

function ScheduleRow({
  expanded,
  isSelected,
  mutationPending,
  schedule,
  onDelete,
  onRunNow,
  onSelect,
  onToggleExpand,
  onToggleStatus,
}: {
  expanded: boolean;
  isSelected: boolean;
  schedule: ScheduleRead;
  onToggleExpand: (scheduleId: number) => void;
} & ScheduleActionHandlers &
  ScheduleSelectionHandlers) {
  const detailsId = `scheduled-task-row-details-${schedule.id}`;

  return (
    <>
      <TableRow
        data-state={isSelected ? "selected" : undefined}
        data-testid={`scheduled-task-row-${schedule.id}`}
      >
        <TableCell className="align-top px-2 py-1.5">
          <Checkbox
            aria-label={`Select scheduled task ${schedule.name}`}
            checked={isSelected}
            onCheckedChange={(checked) => onSelect([schedule], checked === true)}
          />
        </TableCell>
        <TableCell className="min-w-[20rem] align-top px-2 py-1.5 whitespace-normal">
          <WorkflowCell schedule={schedule} />
        </TableCell>
        <TableCell className="min-w-[15rem] align-top px-2 py-1.5 whitespace-normal">
          <ScheduleCell schedule={schedule} />
        </TableCell>
        <TableCell className="min-w-[14rem] align-top px-2 py-1.5 whitespace-normal">
          <NextRunCell schedule={schedule} />
        </TableCell>
        <TableCell className="min-w-[14rem] align-top px-2 py-1.5 whitespace-normal">
          <LatestActivityCell schedule={schedule} />
        </TableCell>
        <TableCell className="min-w-[22rem] align-top px-2 py-1.5 text-right">
          <ScheduleTableActions
            detailsId={detailsId}
            expanded={expanded}
            mutationPending={mutationPending}
            schedule={schedule}
            onDelete={onDelete}
            onRunNow={onRunNow}
            onToggleDetails={() => onToggleExpand(schedule.id)}
            onToggleStatus={onToggleStatus}
          />
        </TableCell>
      </TableRow>
      {expanded ? (
        <TableRow
          className="bg-muted/20 hover:bg-muted/20"
          data-testid={detailsId}
          id={detailsId}
        >
          <TableCell className="whitespace-normal px-3 py-2" colSpan={6}>
            <ExpandedScheduleDetails schedule={schedule} />
          </TableCell>
        </TableRow>
      ) : null}
    </>
  );
}

function ScheduleTable({
  allFilteredSelected,
  expandedScheduleIds,
  mutationPending,
  schedules,
  selectedScheduleIds,
  someFilteredSelected,
  sortState,
  onDelete,
  onRunNow,
  onSelect,
  onSort,
  onToggleExpand,
  onToggleStatus,
}: {
  allFilteredSelected: boolean;
  expandedScheduleIds: ReadonlySet<ScheduleRead["id"]>;
  schedules: readonly ScheduleRead[];
  selectedScheduleIds: ReadonlySet<ScheduleRead["id"]>;
  someFilteredSelected: boolean;
  sortState: ScheduleSortState;
  onSort: (field: ScheduleSortField) => void;
  onToggleExpand: (scheduleId: number) => void;
} & ScheduleActionHandlers &
  ScheduleSelectionHandlers) {
  return (
    <ResourceTableFrame>
      <Table className="table-fixed text-xs">
        <TableHeader>
          <TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead className="sticky top-0 z-20 w-9 bg-background px-2 py-1.5">
              <Checkbox
                aria-label="Select all shown scheduled tasks"
                checked={
                  allFilteredSelected
                    ? true
                    : someFilteredSelected
                      ? "indeterminate"
                      : false
                }
                onCheckedChange={(checked) => onSelect(schedules, checked === true)}
              />
            </TableHead>
            <TableHead
              aria-sort={getAriaSort("workflow", sortState)}
              className="sticky top-0 z-10 w-[24%] bg-background px-2 py-1.5"
            >
              {renderSortButton({ field: "workflow", label: "Workflow", sortState, onSort })}
            </TableHead>
            <TableHead className="sticky top-0 z-10 w-[18%] bg-background px-2 py-1.5">
              Schedule
            </TableHead>
            <TableHead
              aria-sort={getAriaSort("nextRun", sortState)}
              className="sticky top-0 z-10 w-[16%] bg-background px-2 py-1.5"
            >
              {renderSortButton({ field: "nextRun", label: "Next run", sortState, onSort })}
            </TableHead>
            <TableHead
              aria-sort={getAriaSort("latestActivity", sortState)}
              className="sticky top-0 z-10 w-[16%] bg-background px-2 py-1.5"
            >
              {renderSortButton({ field: "latestActivity", label: "Latest activity", sortState, onSort })}
            </TableHead>
            <TableHead className="w-[22rem] bg-background px-2 py-1.5 text-right">
              Actions
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {schedules.map((schedule) => (
            <ScheduleRow
              expanded={expandedScheduleIds.has(schedule.id)}
              isSelected={selectedScheduleIds.has(schedule.id)}
              key={schedule.id}
              mutationPending={mutationPending}
              schedule={schedule}
              onDelete={onDelete}
              onRunNow={onRunNow}
              onSelect={onSelect}
              onToggleExpand={onToggleExpand}
              onToggleStatus={onToggleStatus}
            />
          ))}
        </TableBody>
      </Table>
    </ResourceTableFrame>
  );
}

function ScheduleCards({
  allFilteredSelected,
  expandedScheduleIds,
  mutationPending,
  schedules,
  selectedScheduleIds,
  someFilteredSelected,
  onDelete,
  onRunNow,
  onSelect,
  onToggleExpand,
  onToggleStatus,
}: {
  allFilteredSelected: boolean;
  expandedScheduleIds: ReadonlySet<ScheduleRead["id"]>;
  schedules: readonly ScheduleRead[];
  selectedScheduleIds: ReadonlySet<ScheduleRead["id"]>;
  someFilteredSelected: boolean;
  onToggleExpand: (scheduleId: number) => void;
} & ScheduleActionHandlers &
  ScheduleSelectionHandlers) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 rounded-md border bg-muted/30 px-3 py-2">
        <Checkbox
          aria-label="Select all shown scheduled tasks"
          checked={
            allFilteredSelected
              ? true
              : someFilteredSelected
                ? "indeterminate"
                : false
          }
          onCheckedChange={(checked) => onSelect(schedules, checked === true)}
        />
        <span className="text-xs text-muted-foreground">Select all shown scheduled tasks</span>
      </div>
      {schedules.map((schedule) => {
        const expanded = expandedScheduleIds.has(schedule.id);
        const isSelected = selectedScheduleIds.has(schedule.id);
        const detailsId = `scheduled-task-card-details-${schedule.id}`;

        return (
          <Card data-testid={`scheduled-task-card-${schedule.id}`} key={schedule.id}>
            <CardContent className="space-y-4 p-4">
              <div className="flex items-start gap-3">
                <Checkbox
                  aria-label={`Select scheduled task ${schedule.name}`}
                  checked={isSelected}
                  onCheckedChange={(checked) => onSelect([schedule], checked === true)}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex min-w-0 flex-wrap items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <WorkflowCell schedule={schedule} />
                    </div>
                    <ScheduleDetailsToggleButton
                      className="h-7 px-2 text-xs"
                      detailsId={detailsId}
                      expanded={expanded}
                      onToggle={() => onToggleExpand(schedule.id)}
                    />
                  </div>
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Schedule
                  </p>
                  <ScheduleCell schedule={schedule} />
                </div>
                <div className="space-y-1">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Next run
                  </p>
                  <NextRunCell schedule={schedule} />
                </div>
                <div className="space-y-1 sm:col-span-2">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Latest activity
                  </p>
                  <LatestActivityCell schedule={schedule} />
                </div>
              </div>
              {expanded ? (
                <div id={detailsId}>
                  <ExpandedScheduleDetails schedule={schedule} />
                </div>
              ) : null}
              <div className="flex flex-wrap justify-end gap-2">
                <Button
                  aria-label={`Run schedule ${schedule.name} now`}
                  disabled={mutationPending}
                  size="sm"
                  type="button"
                  onClick={() => onRunNow(schedule)}
                >
                  <PlayCircle data-icon="inline-start" />
                  Run now
                </Button>
                {schedule.status === "paused" ? (
                  <Button
                    aria-label={`Resume schedule ${schedule.name}`}
                    disabled={mutationPending}
                    size="sm"
                    type="button"
                    variant="outline"
                    onClick={() => onToggleStatus(schedule)}
                  >
                    <RotateCcw data-icon="inline-start" />
                    Resume
                  </Button>
                ) : null}
                <MobileActionMenu
                  mutationPending={mutationPending}
                  schedule={schedule}
                  onDelete={onDelete}
                  onRunNow={onRunNow}
                  onToggleStatus={onToggleStatus}
                />
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function ScheduledTasksBulkActions({
  filteredCount,
  isPending,
  selectedCount,
  onClear,
  onDeleteSelected,
}: {
  filteredCount: number;
  isPending: boolean;
  selectedCount: number;
  onClear: () => void;
  onDeleteSelected: () => void;
}) {
  if (selectedCount === 0) {
    return null;
  }

  return (
    <ResourceFilterBar
      actions={
        <>
          <Button
            disabled={isPending}
            size="sm"
            variant="destructive"
            onClick={onDeleteSelected}
          >
            <Trash2 className="size-3.5" /> Delete selected
          </Button>
          <Button size="sm" variant="ghost" onClick={onClear}>
            Clear
          </Button>
        </>
      }
      summary={`${selectedCount} of ${filteredCount} scheduled tasks selected`}
      testId="scheduled-tasks-bulk-actions"
    />
  );
}

function ScheduledTasksEmptyState({ hasFilters }: { hasFilters: boolean }) {
  return (
    <EmptyStatePanel
      description={
        hasFilters
          ? "Refine the search, status, package, or workflow filters to widen the schedule inventory."
          : "Create a scheduled task to materialize Workflow Package runs on a durable recurrence."
      }
      icon={<ClipboardList />}
      title={
        hasFilters
          ? "No scheduled tasks match this search or filters."
          : "No scheduled tasks yet."
      }
    />
  );
}

export function ScheduledTasksListPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<LocalStatusFilter>(ALL_STATUS_FILTER);
  const [packageKey, setPackageKey] = useState("");
  const [workflowKey, setWorkflowKey] = useState("");
  const [deleting, setDeleting] = useState<ScheduleRead | null>(null);
  const [expandedScheduleIds, setExpandedScheduleIds] = useState<Set<ScheduleRead["id"]>>(
    new Set(),
  );
  const [isBulkDeleting, setIsBulkDeleting] = useState(false);
  const [selectedScheduleIds, setSelectedScheduleIds] = useState<Set<ScheduleRead["id"]>>(
    new Set(),
  );
  const [sortState, setSortState] = useState<ScheduleSortState>({
    direction: "asc",
    field: "nextRun",
  });

  const isMobileLayout = useIsMobileLayout();
  const updateSchedule = useUpdateScheduledTask();
  const runNow = useRunScheduledTaskNow();
  const deleteSchedule = useDeleteScheduledTask();
  const deleteSchedules = useDeleteScheduledTasks();
  const workflowPackagesQuery = useWorkflowPackages();
  const resolvedPackageKey = normalizeFilter(packageKey) ?? "";
  const resolvedWorkflowKey = normalizeFilter(workflowKey) ?? "";
  const selectedPackage = useMemo<WorkflowPackageRead | null>(
    () =>
      workflowPackagesQuery.data?.items.find(
        (workflowPackage) => workflowPackage.key === resolvedPackageKey,
      ) ?? null,
    [resolvedPackageKey, workflowPackagesQuery.data?.items],
  );
  const manifestQuery = useWorkflowPackageManifest(selectedPackage?.id);
  const manifestWorkflowOptions = useMemo(
    () =>
      manifestQuery.data
        ? getWorkflowOptions(manifestQuery.data, resolvedWorkflowKey || null)
        : resolvedWorkflowKey
          ? [createUnknownWorkflowOption(resolvedWorkflowKey)]
          : [],
    [manifestQuery.data, resolvedWorkflowKey],
  );

  const listParams = useMemo<ScheduleListParams>(
    () => ({
      limit: 50,
      packageKey: resolvedPackageKey || undefined,
      workflowKey:
        resolvedPackageKey && resolvedWorkflowKey ? resolvedWorkflowKey : undefined,
    }),
    [resolvedPackageKey, resolvedWorkflowKey],
  );

  const schedulesQuery = useScheduledTasks(listParams);
  const schedules = useMemo(
    () => schedulesQuery.data?.items ?? [],
    [schedulesQuery.data?.items],
  );
  const filteredSchedules = useMemo(
    () => filterSchedules(schedules, search, statusFilter),
    [schedules, search, statusFilter],
  );
  const visibleSchedules = useMemo(
    () => sortSchedules(filteredSchedules, sortState),
    [filteredSchedules, sortState],
  );
  const workflowOptions = useMemo(
    () =>
      resolvedPackageKey
        ? buildWorkflowFilterOptions({
            manifestOptions: manifestWorkflowOptions,
            schedules,
            selectedPackageKey: resolvedPackageKey,
          })
        : [],
    [manifestWorkflowOptions, resolvedPackageKey, schedules],
  );
  const packageItems = useMemo(
    () => [
      { label: "All packages", value: ALL_PACKAGES_FILTER },
      ...(workflowPackagesQuery.data?.items ?? []).map((workflowPackage) => ({
        label: workflowPackage.name || workflowPackage.key,
        value: workflowPackage.key,
      })),
    ],
    [workflowPackagesQuery.data?.items],
  );
  const workflowItems = useMemo(
    () => [
      { label: "All workflows", value: ALL_WORKFLOWS_FILTER },
      ...workflowOptions.map((option) => ({
        label: option.label,
        value: option.key,
      })),
    ],
    [workflowOptions],
  );
  const workflowFilterDisabled = !resolvedPackageKey;
  const selectedSchedules = useMemo(
    () =>
      filteredSchedules.filter((schedule) => selectedScheduleIds.has(schedule.id)),
    [filteredSchedules, selectedScheduleIds],
  );
  const selectedCount = selectedSchedules.length;
  const allFilteredSelected =
    filteredSchedules.length > 0 &&
    filteredSchedules.every((schedule) => selectedScheduleIds.has(schedule.id));
  const someFilteredSelected = filteredSchedules.some((schedule) =>
    selectedScheduleIds.has(schedule.id),
  );
  const mutationPending =
    updateSchedule.isPending ||
    runNow.isPending ||
    deleteSchedule.isPending ||
    deleteSchedules.isPending;
  const hasFilters = Boolean(
    search.trim() ||
      packageKey.trim() ||
      workflowKey.trim() ||
      statusFilter !== ALL_STATUS_FILTER,
  );

  const updatePackageFilter = (nextValue: string) => {
    const nextPackageKey =
      nextValue === ALL_PACKAGES_FILTER ? "" : normalizeFilter(nextValue) ?? "";

    if (nextPackageKey === resolvedPackageKey) {
      return;
    }

    setPackageKey(nextPackageKey);
    setWorkflowKey("");
  };

  const updateWorkflowFilter = (nextValue: string) => {
    setWorkflowKey(
      nextValue === ALL_WORKFLOWS_FILTER ? "" : normalizeFilter(nextValue) ?? "",
    );
  };

  const setSchedulesSelected = (
    schedulesToUpdate: readonly ScheduleRead[],
    selected: boolean,
  ) => {
    setSelectedScheduleIds((previous) => {
      const next = new Set(previous);
      schedulesToUpdate.forEach((schedule) => {
        if (selected) {
          next.add(schedule.id);
        } else {
          next.delete(schedule.id);
        }
      });
      return next;
    });
  };

  const toggleScheduleExpanded = (scheduleId: number) => {
    setExpandedScheduleIds((previous) => {
      const next = new Set(previous);
      if (next.has(scheduleId)) {
        next.delete(scheduleId);
      } else {
        next.add(scheduleId);
      }
      return next;
    });
  };

  const handleSort = (field: ScheduleSortField) => {
    setSortState((previous) => {
      if (previous.field === field) {
        return {
          direction: previous.direction === "asc" ? "desc" : "asc",
          field,
        };
      }
      return { direction: defaultSortDirectionForField(field), field };
    });
  };

  const toggleScheduleStatus = async (schedule: ScheduleRead) => {
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
        error instanceof Error
          ? error.message
          : "Failed to update scheduled task status.",
      );
    }
  };

  const runScheduleNow = async (schedule: ScheduleRead) => {
    const scheduledFor = new Date().toISOString();
    try {
      const result = await runNow.mutateAsync({
        scheduleId: schedule.id,
        payload: {
          idempotencyKey: `manual-${schedule.id}-${scheduledFor}`,
          scheduledFor,
        },
      });
      toast.success(`Scheduled task queued as run #${result.run.id}`);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Failed to run scheduled task now.",
      );
    }
  };

  const confirmDelete = async () => {
    if (!deleting) {
      return;
    }
    try {
      await deleteSchedule.mutateAsync({
        latestRunId: deleting.latestRunId,
        scheduleId: deleting.id,
      });
      toast.success("Scheduled task deleted");
      setSelectedScheduleIds((previous) => {
        const next = new Set(previous);
        next.delete(deleting.id);
        return next;
      });
      setDeleting(null);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Failed to delete scheduled task.",
      );
    }
  };

  const confirmBulkDelete = () => {
    if (selectedSchedules.length === 0) {
      return;
    }

    const count = selectedSchedules.length;
    deleteSchedules.mutate(
      selectedSchedules.map((schedule) => ({
        latestRunId: schedule.latestRunId,
        scheduleId: schedule.id,
      })),
      {
        onError: (error) =>
          toast.error(
            error instanceof Error
              ? error.message
              : "Failed to delete scheduled tasks.",
          ),
        onSuccess: () => {
          toast.success(
            `${count} ${count === 1 ? "scheduled task" : "scheduled tasks"} deleted`,
          );
          setSelectedScheduleIds(new Set());
          setIsBulkDeleting(false);
        },
      },
    );
  };

  return (
    <InventoryPageShell
      pageContext={{
        actions: <ScheduledTasksPageActions />,
        description: "Manage durable Workflow Package schedules.",
        title: "Scheduled Tasks",
      }}
      testId="scheduled-tasks-list-page"
      toolbar={{
        className: "[&>div:first-child]:items-start",
        filters: (
          <ScheduleFilters
            packageItems={packageItems}
            packageKey={resolvedPackageKey}
            status={statusFilter}
            workflowDisabled={workflowFilterDisabled}
            workflowItems={workflowItems}
            workflowKey={resolvedWorkflowKey}
            onPackageKeyChange={updatePackageFilter}
            onStatusChange={setStatusFilter}
            onWorkflowKeyChange={updateWorkflowFilter}
          />
        ),
        resultSummary: `${visibleSchedules.length} of ${
          schedulesQuery.data?.totalCount ?? schedules.length
        } scheduled tasks shown`,
        search: {
          id: "scheduled-tasks-search",
          label: "Search scheduled tasks",
          name: "scheduledTasksSearch",
          placeholder: "Search schedules by name, package, workflow, status, or run...",
          testId: "scheduled-tasks-search",
          value: search,
          onChange: setSearch,
        },
      }}
    >
      {schedulesQuery.isPending ? <LoadingState /> : null}

      {schedulesQuery.isError ? (
        <EmptyStatePanel
          description={
            schedulesQuery.error instanceof Error
              ? schedulesQuery.error.message
              : "Failed to load scheduled tasks."
          }
          title="Failed to load scheduled tasks"
          tone="danger"
        />
      ) : null}

      {!schedulesQuery.isPending &&
      !schedulesQuery.isError &&
      visibleSchedules.length === 0 ? (
        <ScheduledTasksEmptyState hasFilters={hasFilters} />
      ) : null}

      {!schedulesQuery.isPending &&
      !schedulesQuery.isError &&
      visibleSchedules.length > 0 ? (
        isMobileLayout ? (
          <ScheduleCards
            allFilteredSelected={allFilteredSelected}
            expandedScheduleIds={expandedScheduleIds}
            mutationPending={mutationPending}
            schedules={visibleSchedules}
            selectedScheduleIds={selectedScheduleIds}
            someFilteredSelected={someFilteredSelected}
            onDelete={setDeleting}
            onRunNow={runScheduleNow}
            onSelect={setSchedulesSelected}
            onToggleExpand={toggleScheduleExpanded}
            onToggleStatus={toggleScheduleStatus}
          />
        ) : (
          <ScheduleTable
            allFilteredSelected={allFilteredSelected}
            expandedScheduleIds={expandedScheduleIds}
            mutationPending={mutationPending}
            schedules={visibleSchedules}
            selectedScheduleIds={selectedScheduleIds}
            someFilteredSelected={someFilteredSelected}
            sortState={sortState}
            onDelete={setDeleting}
            onRunNow={runScheduleNow}
            onSelect={setSchedulesSelected}
            onSort={handleSort}
            onToggleExpand={toggleScheduleExpanded}
            onToggleStatus={toggleScheduleStatus}
          />
        )
      ) : null}

      <ScheduledTasksBulkActions
        filteredCount={visibleSchedules.length}
        isPending={deleteSchedules.isPending}
        selectedCount={selectedCount}
        onClear={() => setSelectedScheduleIds(new Set())}
        onDeleteSelected={() => setIsBulkDeleting(true)}
      />

      <ConfirmDeleteDialog
        confirmLabel="Delete selected"
        description={`Delete ${selectedCount} selected ${selectedCount === 1 ? "scheduled task" : "scheduled tasks"}? This removes ${selectedCount === 1 ? "the schedule" : "the selected schedules"} and ${selectedCount === 1 ? "its" : "their"} directly owned run history.`}
        isPending={deleteSchedules.isPending}
        open={isBulkDeleting}
        title="Delete selected scheduled tasks"
        onConfirm={confirmBulkDelete}
        onOpenChange={setIsBulkDeleting}
      />

      <ConfirmDeleteDialog
        confirmLabel="Delete scheduled task"
        description={`Delete ${deleting?.name ?? "this scheduled task"}? This removes the schedule and its directly owned run history.`}
        isPending={deleteSchedule.isPending}
        open={deleting !== null}
        title="Delete scheduled task"
        onConfirm={confirmDelete}
        onOpenChange={(open) => {
          if (!open) {
            setDeleting(null);
          }
        }}
      />
    </InventoryPageShell>
  );
}
