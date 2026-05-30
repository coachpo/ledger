import {
  Archive,
  CalendarClock,
  ClipboardList,
  CopyPlus,
  ExternalLink,
  PauseCircle,
  PlayCircle,
  RotateCcw,
  SquarePen,
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  useArchiveScheduledTask,
  useRunScheduledTaskNow,
  useScheduledTasks,
  useUpdateScheduledTask,
} from "@/hooks/use-scheduled-tasks";
import { formatDateTime } from "@/lib/format";
import type {
  ScheduleFireStatus,
  ScheduleListParams,
  ScheduleRead,
  ScheduleRecurrence,
  ScheduleStatus,
  ScheduleWriteStatus,
} from "@/lib/types/schedule";

const ACTIVE_STATUS_FILTER = "__active__";
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
      <ToggleGroupItem
        className="h-8 px-3 text-xs"
        data-testid="scheduled-tasks-filter-archived"
        value="archived"
      >
        Archived
      </ToggleGroupItem>
    </ToggleGroup>
  );
}

function TextFilter({
  id,
  label,
  testId,
  value,
  onChange,
}: {
  id: string;
  label: string;
  testId: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex min-w-40 flex-col gap-1">
      <Label className="sr-only" htmlFor={id}>
        {label}
      </Label>
      <Input
        aria-label={label}
        className="h-8 text-xs"
        data-testid={testId}
        id={id}
        placeholder={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}
function ScheduleFilters({
  packageKey,
  status,
  workflowKey,
  onPackageKeyChange,
  onStatusChange,
  onWorkflowKeyChange,
}: {
  packageKey: string;
  status: ScheduleStatusFilter;
  workflowKey: string;
  onPackageKeyChange: (value: string) => void;
  onStatusChange: (status: ScheduleStatusFilter) => void;
  onWorkflowKeyChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <ScheduleStatusFilters status={status} onStatusChange={onStatusChange} />
      <TextFilter
        id="scheduled-tasks-package-filter"
        label="Package key"
        testId="scheduled-tasks-filter-package"
        value={packageKey}
        onChange={onPackageKeyChange}
      />
      <TextFilter
        id="scheduled-tasks-workflow-filter"
        label="Workflow key"
        testId="scheduled-tasks-filter-workflow"
        value={workflowKey}
        onChange={onWorkflowKeyChange}
      />
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
      <span>Package id: #{schedule.packageId}</span>
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

type ScheduleActionHandlers = {
  mutationPending: boolean;
  onArchive: (schedule: ScheduleRead) => void;
  onRunNow: (schedule: ScheduleRead) => void;
  onToggleStatus: (schedule: ScheduleRead) => void;
};

function ScheduleRowActions({
  mutationPending,
  schedule,
  onArchive,
  onRunNow,
  onToggleStatus,
}: ScheduleActionHandlers & { schedule: ScheduleRead }) {
  const isArchived = schedule.status === "archived";
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
        disabled={isArchived || mutationPending}
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
        disabled={isArchived || mutationPending}
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
        aria-label={`Archive schedule ${schedule.name}`}
        className="cursor-pointer"
        data-testid="scheduled-task-row-action-archive"
        disabled={isArchived || mutationPending}
        size="sm"
        type="button"
        variant="destructive"
        onClick={() => onArchive(schedule)}
      >
        <Archive data-icon="inline-start" />
        Archive
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
  mutationPending,
  schedules,
  onArchive,
  onRunNow,
  onToggleStatus,
}: ScheduleActionHandlers & { schedules: readonly ScheduleRead[] }) {
  return (
    <div className="min-w-0 overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead>Schedule</TableHead>
            <TableHead>Package / Workflow</TableHead>
            <TableHead>Next fire</TableHead>
            <TableHead>Latest activity</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {schedules.map((schedule) => (
            <TableRow
              data-testid={`scheduled-task-row-${schedule.id}`}
              key={schedule.id}
            >
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
                  onArchive={onArchive}
                  onRunNow={onRunNow}
                  onToggleStatus={onToggleStatus}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
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
  const [archiving, setArchiving] = useState<ScheduleRead | null>(null);
  const updateSchedule = useUpdateScheduledTask();
  const runNow = useRunScheduledTaskNow();
  const archiveSchedule = useArchiveScheduledTask();

  const listParams = useMemo<ScheduleListParams>(
    () => ({
      limit: 50,
      packageKey: normalizeFilter(packageKey),
      status: statusFilterToParams(statusFilter),
      workflowKey: normalizeFilter(workflowKey),
    }),
    [packageKey, statusFilter, workflowKey],
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
  const mutationPending =
    updateSchedule.isPending || runNow.isPending || archiveSchedule.isPending;
  const hasFilters = Boolean(
    search.trim() ||
      packageKey.trim() ||
      workflowKey.trim() ||
      statusFilter !== ACTIVE_STATUS_FILTER,
  );

  const toggleScheduleStatus = async (schedule: ScheduleRead) => {
    if (schedule.status === "archived") {
      return;
    }
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

  const confirmArchive = async () => {
    if (!archiving) {
      return;
    }
    try {
      await archiveSchedule.mutateAsync(archiving.id);
      toast.success("Scheduled task archived");
      setArchiving(null);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Failed to archive scheduled task.",
      );
    }
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
        filters: (
          <ScheduleFilters
            packageKey={packageKey}
            status={statusFilter}
            workflowKey={workflowKey}
            onPackageKeyChange={setPackageKey}
            onStatusChange={setStatusFilter}
            onWorkflowKeyChange={setWorkflowKey}
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
          mutationPending={mutationPending}
          schedules={filteredSchedules}
          onArchive={setArchiving}
          onRunNow={runScheduleNow}
          onToggleStatus={toggleScheduleStatus}
        />
      ) : null}

      <ConfirmDeleteDialog
        confirmLabel="Archive scheduled task"
        description={`Archive ${archiving?.name ?? "this scheduled task"}? Existing fire and run audit history stays available, but the schedule will stop materializing future runs.`}
        isPending={archiveSchedule.isPending}
        open={archiving !== null}
        title="Archive scheduled task"
        onConfirm={confirmArchive}
        onOpenChange={(open) => {
          if (!open) {
            setArchiving(null);
          }
        }}
      />
    </InventoryPageShell>
  );
}
