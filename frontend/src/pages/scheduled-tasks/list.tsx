import {
  CalendarClock,
  ClipboardList,
  CopyPlus,
  ExternalLink,
  PauseCircle,
  PlayCircle,
  RotateCcw,
  SquarePen,
  Trash2,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";

import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";
import { EmptyStatePanel } from "@/components/shared/empty-state-panel";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
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
  ScheduleFireStatus,
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

const ACTIVE_STATUS_FILTER = "__active__";
const ALL_PACKAGES_FILTER = "__all_packages__";
const ALL_WORKFLOWS_FILTER = "__all_workflows__";

type ScheduleStatusFilter = ScheduleStatus | typeof ACTIVE_STATUS_FILTER;

function statusFilterToParams(
  status: ScheduleStatusFilter,
): ScheduleListParams["status"] {
  return status === ACTIVE_STATUS_FILTER ? undefined : status;
}

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

function scheduleStatusTone(
  status: ScheduleStatus,
): "success" | "warning" | "muted" {
  if (status === "enabled") {
    return "success";
  }
  return status === "paused" ? "warning" : "muted";
}

function fireStatusTone(
  status: ScheduleFireStatus | null,
): "neutral" | "success" | "warning" | "danger" | "muted" {
  if (status === "queued") {
    return "success";
  }
  if (status === "pending") {
    return "warning";
  }
  if (status === "failed") {
    return "danger";
  }
  return status === "skipped" ? "muted" : "neutral";
}

function badgeVariantForTone(
  tone: "neutral" | "success" | "warning" | "danger" | "muted",
): "secondary" | "outline" | "destructive" {
  if (tone === "danger") {
    return "destructive";
  }
  return tone === "success" || tone === "muted" ? "secondary" : "outline";
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
function filterSchedules(
  schedules: readonly ScheduleRead[],
  search: string,
): ScheduleRead[] {
  const query = search.trim().toLowerCase();
  if (!query) {
    return [...schedules];
  }

  return schedules.filter((schedule) =>
    [
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
      .includes(query),
  );
}
function sortSchedules(items: readonly ScheduleRead[]): ScheduleRead[] {
  return [...items].sort((left, right) => {
    if (left.nextFireAt && right.nextFireAt) {
      const byNextFire = left.nextFireAt.localeCompare(right.nextFireAt);
      return byNextFire !== 0 ? byNextFire : left.id - right.id;
    }
    if (left.nextFireAt) {
      return -1;
    }
    if (right.nextFireAt) {
      return 1;
    }
    return left.id - right.id;
  });
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

function StatusBadge({ status }: { status: ScheduleStatus }) {
  const tone = scheduleStatusTone(status);
  return (
    <Badge
      className="capitalize"
      data-testid={`scheduled-task-status-${status}`}
      data-tone={tone}
      variant={badgeVariantForTone(tone)}
    >
      {status}
    </Badge>
  );
}

function LatestStatusBadge({ status }: { status: ScheduleFireStatus | null }) {
  const tone = fireStatusTone(status);
  return (
    <Badge data-tone={tone} variant={badgeVariantForTone(tone)}>
      {status ? formatStatusLabel(status) : "No latest status"}
    </Badge>
  );
}
function ScheduleStatusFilters({
  status,
  onStatusChange,
}: {
  status: ScheduleStatusFilter;
  onStatusChange: (status: ScheduleStatusFilter) => void;
}) {
  return (
    <ToggleGroup
      aria-label="Scheduled task status"
      type="single"
      value={status}
      onValueChange={(value) => {
        if (value) {
          onStatusChange(value as ScheduleStatusFilter);
        }
      }}
    >
      <ToggleGroupItem className="h-8 px-3 text-xs" value={ACTIVE_STATUS_FILTER}>
        Active
      </ToggleGroupItem>
      <ToggleGroupItem
        className="h-8 px-3 text-xs"
        data-testid="scheduled-tasks-filter-enabled"
        value="enabled"
      >
        Enabled
      </ToggleGroupItem>
      <ToggleGroupItem
        className="h-8 px-3 text-xs"
        data-testid="scheduled-tasks-filter-paused"
        value="paused"
      >
        Paused
      </ToggleGroupItem>
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
  status: ScheduleStatusFilter;
  workflowDisabled: boolean;
  workflowItems: ReadonlyArray<{ label: string; value: string }>;
  workflowKey: string;
  onPackageKeyChange: (value: string) => void;
  onStatusChange: (status: ScheduleStatusFilter) => void;
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

function ScheduleIdentityCell({ schedule }: { schedule: ScheduleRead }) {
  return (
    <div className="flex min-w-64 flex-col gap-1 whitespace-normal">
      <div className="flex min-w-0 flex-wrap items-center gap-1.5">
        <span className="font-medium text-foreground">{schedule.name}</span>
        <StatusBadge status={schedule.status} />
      </div>
      {schedule.description ? (
        <span className="break-words text-xs text-muted-foreground">
          {schedule.description}
        </span>
      ) : null}
      <span className="text-xs text-muted-foreground">
        Timezone: {schedule.timezone}
      </span>
    </div>
  );
}

function PackageWorkflowCell({ schedule }: { schedule: ScheduleRead }) {
  return (
    <div
      className="flex min-w-60 flex-col gap-1 whitespace-normal text-xs text-muted-foreground"
      data-testid={`scheduled-task-row-identity-${schedule.id}`}
    >
      <span>
        <span className="font-medium text-foreground">Package:</span>{" "}
        <span className="break-all font-mono">{schedule.packageKey}</span>
      </span>
      <span>
        <span className="font-medium text-foreground">Workflow:</span>{" "}
        <span className="break-all font-mono">{schedule.workflowKey}</span>
      </span>
    </div>
  );
}

function NextFireCell({ schedule }: { schedule: ScheduleRead }) {
  return (
    <div
      className="flex min-w-52 flex-col gap-1 whitespace-normal text-xs text-muted-foreground"
      data-testid={`scheduled-task-row-next-fire-${schedule.id}`}
    >
      <span className="font-medium text-foreground">
        {formatOptionalDateTime(schedule.nextFireAt, "No upcoming fire")}
      </span>
      <span>{formatRecurrence(schedule.recurrence)}</span>
      <span>Overlap: {formatStatusLabel(schedule.overlapPolicy)}</span>
      <span>Misfire: {formatStatusLabel(schedule.misfirePolicy)}</span>
    </div>
  );
}

function LatestActivityCell({ schedule }: { schedule: ScheduleRead }) {
  return (
    <div
      className="flex min-w-52 flex-col gap-1 whitespace-normal text-xs text-muted-foreground"
      data-testid={`scheduled-task-row-latest-${schedule.id}`}
    >
      <div className="flex min-w-0 flex-wrap items-center gap-1.5">
        <LatestStatusBadge status={schedule.latestStatus} />
      </div>
      <span>
        Latest fire: {schedule.latestFireId ? `#${schedule.latestFireId}` : "None"}
      </span>
      <span>
        Latest run: {schedule.latestRunId ? `#${schedule.latestRunId}` : "None"}
      </span>
      <span>Updated: {formatDateTime(schedule.updatedAt)}</span>
    </div>
  );
}

type ScheduleSelectionHandlers = {
  onDelete: (schedule: ScheduleRead) => void;
  onSelect: (schedulesToUpdate: readonly ScheduleRead[], selected: boolean) => void;
};

type ScheduleActionHandlers = {
  mutationPending: boolean;
  onDelete: (schedule: ScheduleRead) => void;
  onRunNow: (schedule: ScheduleRead) => void;
  onToggleStatus: (schedule: ScheduleRead) => void;
};

function ScheduleRowActions({
  mutationPending,
  schedule,
  onDelete,
  onRunNow,
  onToggleStatus,
}: ScheduleActionHandlers & { schedule: ScheduleRead }) {
  const toggleLabel = schedule.status === "enabled" ? "Pause" : "Resume";
  const duplicatePath = `/scheduled-tasks/new?duplicateFrom=${schedule.id}`;

  return (
    <div className="flex min-w-72 flex-wrap justify-end gap-2">
      <Button asChild size="sm" variant="outline">
        <Link
          aria-label={`Edit schedule ${schedule.name}`}
          data-testid="scheduled-task-row-action-edit"
          to={`/scheduled-tasks/${schedule.id}`}
        >
          <SquarePen data-icon="inline-start" />
          Edit
        </Link>
      </Button>
      <Button
        aria-label={`Run schedule ${schedule.name} now`}
        className="cursor-pointer"
        data-testid="scheduled-task-row-action-run-now"
        disabled={mutationPending}
        size="sm"
        type="button"
        onClick={() => onRunNow(schedule)}
      >
        <PlayCircle data-icon="inline-start" />
        Run now
      </Button>
      <Button
        aria-label={`${toggleLabel} schedule ${schedule.name}`}
        className="cursor-pointer"
        data-testid="scheduled-task-row-action-pause-resume"
        disabled={mutationPending}
        size="sm"
        type="button"
        variant="outline"
        onClick={() => onToggleStatus(schedule)}
      >
        {schedule.status === "enabled" ? (
          <PauseCircle data-icon="inline-start" />
        ) : (
          <RotateCcw data-icon="inline-start" />
        )}
        {toggleLabel}
      </Button>
      <Button asChild size="sm" variant="outline">
        <Link
          aria-label={`Duplicate schedule ${schedule.name}`}
          data-testid="scheduled-task-row-action-duplicate"
          to={duplicatePath}
        >
          <CopyPlus data-icon="inline-start" />
          Duplicate
        </Link>
      </Button>
      <Button
        aria-label={`Delete schedule ${schedule.name}`}
        className="cursor-pointer"
        data-testid="scheduled-task-row-action-delete"
        disabled={mutationPending}
        size="sm"
        type="button"
        variant="destructive"
        onClick={() => onDelete(schedule)}
      >
        <Trash2 data-icon="inline-start" />
        Delete
      </Button>
      {schedule.latestRunId ? (
        <Button asChild size="sm" variant="outline">
          <Link
            aria-label={`Open latest run for ${schedule.name}`}
            data-testid="scheduled-task-row-action-open-latest-run"
            to={`/runs/${schedule.latestRunId}`}
          >
            <ExternalLink data-icon="inline-start" />
            Latest run
          </Link>
        </Button>
      ) : (
        <Button disabled size="sm" type="button" variant="outline">
          Latest run
        </Button>
      )}
    </div>
  );
}

function ScheduledTasksTable({
  allFilteredSelected,
  mutationPending,
  schedules,
  selectedScheduleIds,
  someFilteredSelected,
  onDelete,
  onRunNow,
  onSelect,
  onToggleStatus,
}: {
  allFilteredSelected: boolean;
  mutationPending: boolean;
  schedules: readonly ScheduleRead[];
  selectedScheduleIds: ReadonlySet<ScheduleRead["id"]>;
  someFilteredSelected: boolean;
} & ScheduleActionHandlers & ScheduleSelectionHandlers) {
  return (
    <div className="min-w-0 overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead className="w-9">
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
            <TableHead>Schedule</TableHead>
            <TableHead>Package / Workflow</TableHead>
            <TableHead>Next fire</TableHead>
            <TableHead>Latest activity</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {schedules.map((schedule) => {
            const isSelected = selectedScheduleIds.has(schedule.id);

            return (
              <TableRow
                data-state={isSelected ? "selected" : undefined}
                data-testid={`scheduled-task-row-${schedule.id}`}
                key={schedule.id}
              >
                <TableCell>
                  <Checkbox
                    aria-label={`Select scheduled task ${schedule.name}`}
                    checked={isSelected}
                    onCheckedChange={(checked) =>
                      onSelect([schedule], checked === true)
                    }
                  />
                </TableCell>
                <TableCell className="whitespace-normal">
                  <ScheduleIdentityCell schedule={schedule} />
                </TableCell>
                <TableCell className="whitespace-normal">
                  <PackageWorkflowCell schedule={schedule} />
                </TableCell>
                <TableCell className="whitespace-normal">
                  <NextFireCell schedule={schedule} />
                </TableCell>
                <TableCell className="whitespace-normal">
                  <LatestActivityCell schedule={schedule} />
                </TableCell>
                <TableCell>
                  <ScheduleRowActions
                    mutationPending={mutationPending}
                    schedule={schedule}
                    onDelete={onDelete}
                    onRunNow={onRunNow}
                    onToggleStatus={onToggleStatus}
                  />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
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
    <div
      className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-muted/30 px-3 py-2"
      data-testid="scheduled-tasks-bulk-actions"
    >
      <span className="text-xs text-muted-foreground">
        {selectedCount} of {filteredCount} scheduled tasks selected
      </span>
      <div className="flex flex-wrap items-center gap-2">
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
      </div>
    </div>
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
  const [statusFilter, setStatusFilter] = useState<ScheduleStatusFilter>(
    ACTIVE_STATUS_FILTER,
  );
  const [packageKey, setPackageKey] = useState("");
  const [workflowKey, setWorkflowKey] = useState("");
  const [deleting, setDeleting] = useState<ScheduleRead | null>(null);
  const [isBulkDeleting, setIsBulkDeleting] = useState(false);
  const [selectedScheduleIds, setSelectedScheduleIds] = useState<
    Set<ScheduleRead["id"]>
  >(new Set());
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
      status: statusFilterToParams(statusFilter),
      workflowKey:
        resolvedPackageKey && resolvedWorkflowKey
          ? resolvedWorkflowKey
          : undefined,
    }),
    [resolvedPackageKey, resolvedWorkflowKey, statusFilter],
  );
  const schedulesQuery = useScheduledTasks(listParams);
  const schedules = useMemo(
    () => sortSchedules(schedulesQuery.data?.items ?? []),
    [schedulesQuery.data?.items],
  );
  const filteredSchedules = useMemo(
    () => filterSchedules(schedules, search),
    [schedules, search],
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
      statusFilter !== ACTIVE_STATUS_FILTER,
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
        resultSummary: `${filteredSchedules.length} of ${
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
      filteredSchedules.length === 0 ? (
        <ScheduledTasksEmptyState hasFilters={hasFilters} />
      ) : null}

      {!schedulesQuery.isPending &&
      !schedulesQuery.isError &&
      filteredSchedules.length > 0 ? (
        <ScheduledTasksTable
          allFilteredSelected={allFilteredSelected}
          mutationPending={mutationPending}
          schedules={filteredSchedules}
          selectedScheduleIds={selectedScheduleIds}
          someFilteredSelected={someFilteredSelected}
          onDelete={setDeleting}
          onRunNow={runScheduleNow}
          onSelect={setSchedulesSelected}
          onToggleStatus={toggleScheduleStatus}
        />
      ) : null}

      <ScheduledTasksBulkActions
        filteredCount={filteredSchedules.length}
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
