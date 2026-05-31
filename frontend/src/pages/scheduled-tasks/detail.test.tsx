import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ComponentProps, PropsWithChildren } from "react";
import { MemoryRouter, Route, Routes, useParams } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError } from "@/lib/api-client";
import type {
  ScheduleFireListRead,
  ScheduleFireRead,
  SchedulePreviewRead,
  ScheduleRead,
  ScheduleRunNowRead,
} from "@/lib/types/schedule";
import type {
  WorkflowPackageRuntimeInputEntryRead,
  WorkflowPackageRuntimeInputRegistryRead,
} from "@/lib/types/workflow-package";

import { ScheduledTaskDetailPage } from "./detail";

const {
  archiveScheduleMock,
  createRuntimeInputPersonalEntryMock,
  deleteRuntimeInputPersonalEntryMock,
  previewScheduledInputsMock,
  runNowMock,
  toastErrorMock,
  toastSuccessMock,
  toastWarningMock,
  updateRuntimeInputPersonalEntryMock,
  updateScheduleMock,
  useArchiveScheduledTaskMock,
  useCreateRuntimeInputPersonalEntryMock,
  useDeleteRuntimeInputPersonalEntryMock,
  usePreviewUnsavedScheduledTaskMock,
  useRunScheduledTaskNowMock,
  useScheduledTaskFiresMock,
  useScheduledTaskMock,
  useUpdateRuntimeInputPersonalEntryMock,
  useUpdateScheduledTaskMock,
  useWorkflowPackageRuntimeInputRegistryMock,
} = vi.hoisted(() => ({
  archiveScheduleMock: vi.fn(),
  createRuntimeInputPersonalEntryMock: vi.fn(),
  deleteRuntimeInputPersonalEntryMock: vi.fn(),
  previewScheduledInputsMock: vi.fn(),
  runNowMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  toastWarningMock: vi.fn(),
  updateRuntimeInputPersonalEntryMock: vi.fn(),
  updateScheduleMock: vi.fn(),
  useArchiveScheduledTaskMock: vi.fn(),
  useCreateRuntimeInputPersonalEntryMock: vi.fn(),
  useDeleteRuntimeInputPersonalEntryMock: vi.fn(),
  usePreviewUnsavedScheduledTaskMock: vi.fn(),
  useRunScheduledTaskNowMock: vi.fn(),
  useScheduledTaskFiresMock: vi.fn(),
  useScheduledTaskMock: vi.fn(),
  useUpdateRuntimeInputPersonalEntryMock: vi.fn(),
  useUpdateScheduledTaskMock: vi.fn(),
  useWorkflowPackageRuntimeInputRegistryMock: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
    warning: toastWarningMock,
  },
}));

vi.mock("@/hooks/use-scheduled-tasks", () => ({
  useArchiveScheduledTask: () => useArchiveScheduledTaskMock(),
  usePreviewUnsavedScheduledTask: () => usePreviewUnsavedScheduledTaskMock(),
  useRunScheduledTaskNow: () => useRunScheduledTaskNowMock(),
  useScheduledTask: (...args: unknown[]) => useScheduledTaskMock(...args),
  useScheduledTaskFires: (...args: unknown[]) => useScheduledTaskFiresMock(...args),
  useUpdateScheduledTask: () => useUpdateScheduledTaskMock(),
}));

vi.mock("@/hooks/use-workflow-packages", () => ({
  useCreateWorkflowPackageRuntimeInputPersonalEntry: () => useCreateRuntimeInputPersonalEntryMock(),
  useDeleteWorkflowPackageRuntimeInputPersonalEntry: () => useDeleteRuntimeInputPersonalEntryMock(),
  useUpdateWorkflowPackageRuntimeInputPersonalEntry: () => useUpdateRuntimeInputPersonalEntryMock(),
  useWorkflowPackageRuntimeInputRegistry: (...args: unknown[]) => useWorkflowPackageRuntimeInputRegistryMock(...args),
}));

vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: PropsWithChildren) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: PropsWithChildren) => <div>{children}</div>,
  DropdownMenuGroup: ({ children }: PropsWithChildren) => <div>{children}</div>,
  DropdownMenuSeparator: () => <div />,
  DropdownMenuItem: ({ children, onSelect, ...props }: PropsWithChildren<{ onSelect?: () => void; variant?: string } & Omit<ComponentProps<"button">, "onSelect">>) => (
    <button {...props} type="button" onClick={() => onSelect?.()}>
      {children}
    </button>
  ),
  DropdownMenuTrigger: ({ children }: PropsWithChildren) => <div>{children}</div>,
}));

function scheduleFixture(overrides: Partial<ScheduleRead> = {}): ScheduleRead {
  return {
    archivedAt: null,
    createdAt: "2026-05-01T10:00:00Z",
    description: "Runs before the opening bell",
    endsAt: null,
    id: 44,
    latestFireId: 801,
    latestRunId: 2104,
    latestStatus: "queued",
    misfireGraceSeconds: 86400,
    misfirePolicy: "catchUpOne",
    name: "Daily market brief",
    nextFireAt: "2026-06-01T13:00:00Z",
    overlapPolicy: "skip",
    packageId: 12,
    packageKey: "market_research_package",
    recurrence: {
      atLocalTime: "09:00",
      daysOfWeek: ["mon", "tue", "wed", "thu", "fri"],
      type: "weekly",
    },
    startsAt: null,
    status: "enabled",
    timezone: "America/New_York",
    updatedAt: "2026-05-30T10:00:00Z",
    workflowKey: "daily_research",
    ...overrides,
  };
}

function runNowResult(): ScheduleRunNowRead {
  return {
    fire: {
      createdAt: "2026-05-30T12:00:00Z",
      errorCode: null,
      errorMessage: null,
      fireKey: "manual-44-2026-05-30T12:00:00Z",
      id: 900,
      materializedAt: "2026-05-30T12:00:00Z",
      reason: "manual",
      renderedParameters: {},
      runId: 3001,
      scheduleId: 44,
      scheduledFor: "2026-05-30T12:00:00Z",
      scheduledLocalDate: "2026-05-30",
      scheduledLocalDateTime: "2026-05-30T08:00:00-04:00",
      scheduledLocalTime: "08:00:00",
      skipReason: null,
      status: "queued",
    },
    run: {
      createdAt: "2026-05-30T12:00:00Z",
      id: 3001,
      status: "queued",
      workflowKey: "daily_research",
      workflowPackageId: 12,
      workflowPackageKey: "market_research_package",
    },
    scheduleId: 44,
  };
}

function scheduleFireFixture(overrides: Partial<ScheduleFireRead> = {}): ScheduleFireRead {
  return {
    createdAt: "2026-05-30T11:59:55Z",
    errorCode: null,
    errorMessage: null,
    fireKey: "44:scheduled:2026-05-30T12:00:00Z",
    id: 801,
    materializedAt: "2026-05-30T12:00:00Z",
    reason: "scheduled",
    renderedParameters: { asOfDate: "2026-05-30", portfolioSlug: "core_portfolio" },
    runId: 2104,
    scheduleId: 44,
    scheduledFor: "2026-05-30T12:00:00Z",
    scheduledLocalDate: "2026-05-30",
    scheduledLocalDateTime: "2026-05-30T08:00:00-04:00",
    scheduledLocalTime: "08:00:00",
    skipReason: null,
    status: "queued",
    ...overrides,
  };
}

function scheduleFireList(items: ScheduleFireRead[]): ScheduleFireListRead {
  return {
    items,
    limit: 20,
    offset: 0,
    totalCount: items.length,
  };
}

function schedulePreviewResult(overrides: Partial<SchedulePreviewRead> = {}): SchedulePreviewRead {
  return {
    ready: true,
    renderedParameters: {
      asOfDate: "2026-06-01",
      portfolioSlug: "core_portfolio",
    },
    scheduleId: null,
    scheduledFor: "2026-06-01T13:00:00Z",
    templateContext: {
      fire: { scheduledLocalDate: "2026-06-01" },
      vars: { portfolioSlug: "core_portfolio" },
    },
    validationErrors: [],
    ...overrides,
  };
}

function runtimeInputEntry(
  overrides: Partial<WorkflowPackageRuntimeInputEntryRead> & Pick<WorkflowPackageRuntimeInputEntryRead, "id" | "slot">,
): WorkflowPackageRuntimeInputEntryRead {
  const entry: WorkflowPackageRuntimeInputEntryRead = {
    compiledHash: "compiled-hash-123",
    createdAt: "2026-05-08T10:00:00Z",
    id: overrides.id,
    inputSchemaSnapshot: null,
    manifestHash: "manifest-hash-123",
    name: null,
    packageId: 12,
    payload: { asOfDate: "{{fire.scheduledLocalDate}}" },
    schemaFingerprint: "schema-fingerprint-123",
    slot: overrides.slot,
    sourceKind: overrides.slot,
    sourceRunId: null,
    stale: { reasons: [], stale: false },
    updatedAt: "2026-05-08T10:00:00Z",
    workflowKey: "daily_research",
  };
  return { ...entry, ...overrides };
}

function runtimeInputRegistry(
  overrides: Partial<WorkflowPackageRuntimeInputRegistryRead> & {
    isError?: boolean;
    isFetching?: boolean;
    isPending?: boolean;
  } = {},
) {
  return {
    data: {
      currentMetadata: {
        compiledHash: "compiled-hash-123",
        inputSchema: {
          properties: {
            asOfDate: { title: "As of date", type: "string" },
            portfolioSlug: { title: "Portfolio slug", type: "string" },
          },
          required: ["asOfDate", "portfolioSlug"],
          type: "object",
        },
        manifestHash: "manifest-hash-123",
        schemaFingerprint: "schema-fingerprint-123",
        workflowKey: "daily_research",
      },
      history: [],
      packageId: 12,
      packageKey: "market_research_package",
      personal: [],
      workflowKey: "daily_research",
      ...overrides,
    },
    error: overrides.isError ? new Error("Saved inputs failed") : null,
    isError: overrides.isError ?? false,
    isFetching: overrides.isFetching ?? false,
    isPending: overrides.isPending ?? false,
  };
}

function RunDetailRouteProbe() {
  const { runId } = useParams<{ runId: string }>();
  return <div data-testid="run-detail-route">Run detail {runId}</div>;
}

function renderDetailPage(initialEntry = "/scheduled-tasks/44") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/scheduled-tasks/:scheduleId" element={<ScheduledTaskDetailPage />} />
        <Route path="/runs/:runId" element={<RunDetailRouteProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function chooseSelectOption(label: string, optionName: RegExp | string) {
  const select = screen.getByLabelText(label);
  select.focus();
  fireEvent.keyDown(select, { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name: optionName }));
}

describe("ScheduledTaskDetailPage", () => {
  beforeEach(() => {
    archiveScheduleMock.mockReset();
    createRuntimeInputPersonalEntryMock.mockReset();
    deleteRuntimeInputPersonalEntryMock.mockReset();
    previewScheduledInputsMock.mockReset();
    runNowMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    toastWarningMock.mockReset();
    updateRuntimeInputPersonalEntryMock.mockReset();
    updateScheduleMock.mockReset();
    useArchiveScheduledTaskMock.mockReset();
    useCreateRuntimeInputPersonalEntryMock.mockReset();
    useDeleteRuntimeInputPersonalEntryMock.mockReset();
    usePreviewUnsavedScheduledTaskMock.mockReset();
    useRunScheduledTaskNowMock.mockReset();
    useScheduledTaskFiresMock.mockReset();
    useScheduledTaskMock.mockReset();
    useUpdateRuntimeInputPersonalEntryMock.mockReset();
    useUpdateScheduledTaskMock.mockReset();
    useWorkflowPackageRuntimeInputRegistryMock.mockReset();

    archiveScheduleMock.mockResolvedValue(scheduleFixture({ status: "archived" }));
    createRuntimeInputPersonalEntryMock.mockResolvedValue(runtimeInputEntry({ id: 30, name: "Saved preset", slot: "personal" }));
    deleteRuntimeInputPersonalEntryMock.mockResolvedValue(undefined);
    previewScheduledInputsMock.mockResolvedValue(schedulePreviewResult());
    runNowMock.mockResolvedValue(runNowResult());
    updateRuntimeInputPersonalEntryMock.mockResolvedValue(runtimeInputEntry({ id: 7, name: "Updated preset", slot: "personal" }));
    updateScheduleMock.mockResolvedValue(scheduleFixture({ status: "paused" }));
    useArchiveScheduledTaskMock.mockReturnValue({
      isPending: false,
      mutateAsync: archiveScheduleMock,
    });
    useRunScheduledTaskNowMock.mockReturnValue({
      isPending: false,
      mutateAsync: runNowMock,
    });
    usePreviewUnsavedScheduledTaskMock.mockReturnValue({
      isPending: false,
      mutateAsync: previewScheduledInputsMock,
    });
    useUpdateScheduledTaskMock.mockReturnValue({
      isPending: false,
      mutateAsync: updateScheduleMock,
    });
    useCreateRuntimeInputPersonalEntryMock.mockReturnValue({
      isPending: false,
      mutateAsync: createRuntimeInputPersonalEntryMock,
    });
    useUpdateRuntimeInputPersonalEntryMock.mockReturnValue({
      isPending: false,
      mutateAsync: updateRuntimeInputPersonalEntryMock,
    });
    useDeleteRuntimeInputPersonalEntryMock.mockReturnValue({
      isPending: false,
      mutateAsync: deleteRuntimeInputPersonalEntryMock,
    });
    useWorkflowPackageRuntimeInputRegistryMock.mockReturnValue(runtimeInputRegistry());
    useScheduledTaskFiresMock.mockReturnValue({
      data: scheduleFireList([scheduleFireFixture()]),
      error: null,
      isError: false,
      isPending: false,
    });
    useScheduledTaskMock.mockReturnValue({
      data: scheduleFixture(),
      error: null,
      isError: false,
      isPending: false,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders a deterministic loading shell", () => {
    useScheduledTaskMock.mockReturnValue({
      data: undefined,
      error: null,
      isError: false,
      isPending: true,
    });

    renderDetailPage();

    expect(screen.getByTestId("scheduled-task-detail-page")).toBeVisible();
    expect(screen.getByTestId("scheduled-task-detail-loading")).toBeVisible();
    expect(screen.getByTestId("workspace-page-shell-context")).toHaveClass("sticky", "top-0");
    expect(useScheduledTaskMock).toHaveBeenCalledWith("44");
  });

  it("renders a deterministic generic error state", () => {
    useScheduledTaskMock.mockReturnValue({
      data: undefined,
      error: new Error("Schedules API unavailable"),
      isError: true,
      isPending: false,
    });

    renderDetailPage();

    expect(screen.getByTestId("scheduled-task-detail-error")).toBeVisible();
    expect(screen.getByText("Failed to load scheduled task")).toBeVisible();
    expect(screen.getByText("Schedules API unavailable")).toBeVisible();
    expect(screen.getByRole("link", { name: "Back to Scheduled Tasks" })).toHaveAttribute(
      "href",
      "/scheduled-tasks",
    );
  });

  it("renders a deterministic not-found state for 404 responses", () => {
    useScheduledTaskMock.mockReturnValue({
      data: undefined,
      error: new ApiRequestError({
        code: "schedule_not_found",
        message: "No schedule",
        status: 404,
      }),
      isError: true,
      isPending: false,
    });

    renderDetailPage();

    expect(screen.getByTestId("scheduled-task-detail-not-found")).toBeVisible();
    expect(screen.getByText("Scheduled task not found")).toBeVisible();
    expect(screen.getByText(/No scheduled task exists for this route/i)).toBeVisible();
  });

  it("renders not-found when the detail hook completes without data", () => {
    useScheduledTaskMock.mockReturnValue({
      data: undefined,
      error: null,
      isError: false,
      isPending: false,
    });

    renderDetailPage();

    expect(screen.getByTestId("scheduled-task-detail-not-found")).toBeVisible();
    expect(screen.getByText("No scheduled task exists for this route.")).toBeVisible();
  });

  it("renders a cleaner management header, compact summaries, and isolated top-level tabs", async () => {
    renderDetailPage();

    const shell = screen.getByTestId("scheduled-task-detail-page");
    expect(shell).toHaveClass("h-full", "min-h-0", "min-w-0", "overflow-hidden");
    expect(screen.queryByRole("main")).not.toBeInTheDocument();
    const header = screen.getByTestId("scheduled-task-detail-header");
    expect(header).toBeVisible();
    expect(screen.getByRole("heading", { name: "Daily market brief" })).toBeVisible();
    expect(within(header).getByTestId("scheduled-task-detail-status-enabled")).toHaveTextContent("enabled");
    expect(screen.getByRole("link", { name: "Scheduled Tasks" })).toHaveAttribute("href", "/scheduled-tasks");
    expect(within(header).getByTestId("schedule-run-now")).toBeVisible();

    fireEvent.click(within(header).getByRole("button", { name: "Disable" }));
    expect(updateScheduleMock).toHaveBeenCalledWith({
      payload: { status: "paused" },
      scheduleId: 44,
    });

    const summaryGrid = screen.getByTestId("scheduled-task-detail-summary-grid");
    expect(summaryGrid).toHaveClass("grid", "min-w-0");
    expect(screen.getByTestId("scheduled-task-detail-next-run-summary")).toHaveTextContent("Next run");
    expect(screen.getByTestId("scheduled-task-detail-target-summary")).toHaveTextContent("Target workflow");
    expect(screen.getByTestId("scheduled-task-detail-target-summary")).toHaveTextContent("market_research_package");
    expect(screen.getByTestId("scheduled-task-detail-target-summary")).toHaveTextContent("daily_research");
    expect(screen.getByTestId("scheduled-task-detail-target-summary")).not.toHaveTextContent("Package id");
    expect(screen.getByTestId("scheduled-task-detail-target-summary")).not.toHaveTextContent("Schedule id");
    expect(screen.getByTestId("scheduled-task-detail-last-run-summary")).toHaveTextContent("Last run");
    expect(screen.getByTestId("scheduled-task-detail-health-summary")).toHaveTextContent("Health");
    expect(screen.queryByTestId("scheduled-task-detail-diagnostics-strip")).not.toBeInTheDocument();
    expect(screen.queryByText("Inputs use schema draft source")).not.toBeInTheDocument();

    expect(screen.getByRole("tab", { name: "Overview" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "Schedule" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "Inputs" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "Runs" })).toBeVisible();
    expect(screen.queryByRole("tab", { name: "Diagnostics" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "History" })).not.toBeInTheDocument();

    const overviewPanel = screen.getByTestId("scheduled-task-detail-tab-overview");
    const schedulePanel = screen.getByTestId("scheduled-task-detail-tab-schedule");
    expect(overviewPanel).toHaveAttribute("data-state", "active");
    expect(schedulePanel).toHaveAttribute("data-state", "inactive");
    expect(schedulePanel).toHaveClass("data-[state=inactive]:hidden");
    expect(overviewPanel).toHaveTextContent("Ready for scheduled runs");

    fireEvent.pointerDown(within(header).getByRole("button", { name: "More actions" }));
    expect((await screen.findByText("Open package")).closest("a")).toHaveAttribute(
      "href",
      "/workflow-packages/12",
    );
    expect((await screen.findByText(/duplicate/i)).closest("a")).toHaveAttribute(
      "href",
      "/scheduled-tasks/new?duplicateFrom=44",
    );
    fireEvent.click(await screen.findByText("Archive"));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Archive scheduled task");
  });

  it("keeps unsaved schedule edits when switching top-level tabs", async () => {
    renderDetailPage();

    fireEvent.click(screen.getByRole("tab", { name: "Schedule" }));
    expect(screen.getByTestId("scheduled-task-detail-tab-schedule")).toHaveTextContent("Schedule configuration");
    expect(screen.queryByText("Weekly Mon, Tue, Wed, Thu, Fri at 09:00")).not.toBeInTheDocument();
    expect(screen.queryByText("Advanced options")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Timezone"), { target: { value: "UTC" } });
    fireEvent.click(screen.getByRole("button", { name: "Advanced options" }));
    fireEvent.change(screen.getByLabelText("Misfire grace seconds"), { target: { value: "42" } });
    fireEvent.click(screen.getByRole("tab", { name: "Overview" }));
    fireEvent.click(screen.getByRole("tab", { name: "Schedule" }));

    expect(screen.getByLabelText("Timezone")).toHaveValue("UTC");
    expect(screen.getByLabelText("Misfire grace seconds")).toHaveValue(42);
    expect(screen.getByRole("button", { name: "Advanced options" })).toBeVisible();
    expect(screen.getByLabelText("Timezone")).not.toHaveValue(scheduleFixture().timezone);
  });

  it("shows actionable health once and keeps info diagnostics in developer details", () => {
    useScheduledTaskMock.mockReturnValue({
      data: scheduleFixture({ latestStatus: "failed", status: "paused" }),
      error: null,
      isError: false,
      isPending: false,
    });

    renderDetailPage();

    const health = screen.getByTestId("scheduled-task-detail-health-summary");
    expect(health).toHaveTextContent("Latest fire failed");
    expect(health).toHaveTextContent("Schedule paused");
    expect(screen.getAllByText("Latest fire failed")).toHaveLength(1);
    expect(screen.queryByText("Inputs use schema draft source")).not.toBeInTheDocument();

    fireEvent.click(within(health).getByRole("button", { name: "Developer details" }));
    expect(screen.getByText("Inputs use schema draft source")).toBeVisible();
  });

  it("renders archived schedules as read-only while preserving duplicate and runs affordances", async () => {
    useScheduledTaskMock.mockReturnValue({
      data: scheduleFixture({
        archivedAt: "2026-05-29T10:00:00Z",
        status: "archived",
      }),
      error: null,
      isError: false,
      isPending: false,
    });

    renderDetailPage();

    const header = screen.getByTestId("scheduled-task-detail-header");
    expect(within(header).getByTestId("schedule-run-now")).toBeDisabled();
    expect(within(header).getByRole("button", { name: "Enable" })).toBeDisabled();
    expect(screen.getByTestId("scheduled-task-detail-health-summary")).toHaveTextContent("Schedule archived");

    fireEvent.pointerDown(within(header).getByRole("button", { name: "More actions" }));
    expect((await screen.findByText(/duplicate/i)).closest("a")).toHaveAttribute(
      "href",
      "/scheduled-tasks/new?duplicateFrom=44",
    );
    expect(await screen.findByText("Archive")).toBeDisabled();

    fireEvent.click(screen.getByRole("tab", { name: "Schedule" }));
    expect(screen.getByLabelText("Schedule enabled")).toBeDisabled();

    fireEvent.click(screen.getByRole("tab", { name: "Inputs" }));
    expect(screen.getByText("Start a custom draft from the workflow defaults.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Customize inputs" })).toBeDisabled();

    fireEvent.click(screen.getByRole("tab", { name: "Runs" }));
    expect(screen.getAllByRole("link", { name: "Open run #2104" })[0]).toHaveAttribute("href", "/runs/2104");
  });

  it("keeps run-now disabled for archived schedules even when runs are empty", () => {
    useScheduledTaskMock.mockReturnValue({
      data: scheduleFixture({
        archivedAt: "2026-05-29T10:00:00Z",
        latestFireId: null,
        latestRunId: null,
        status: "archived",
      }),
      error: null,
      isError: false,
      isPending: false,
    });
    useScheduledTaskFiresMock.mockReturnValue(undefined);

    renderDetailPage();

    fireEvent.click(screen.getByRole("tab", { name: "Runs" }));
    expect(within(screen.getByTestId("scheduled-task-detail-tab-runs")).getByRole("button", { name: "Run now" })).toBeDisabled();
  });

  it("renders fire history panels safely when the fire-history hook state is missing", () => {
    useScheduledTaskFiresMock.mockReturnValue(undefined);

    renderDetailPage();

    fireEvent.click(screen.getByRole("tab", { name: "Runs" }));
    const history = screen.getByTestId("scheduled-task-detail-tab-runs");
    expect(history).toHaveTextContent("No runs yet");
    expect(history).toHaveTextContent("Scheduled and manual runs will appear here.");
    expect(within(history).getByRole("button", { name: "Run now" })).toBeVisible();
    expect(screen.queryByRole("tab", { name: "Diagnostics" })).not.toBeInTheDocument();
  });

  it("renders runs loading and error states without a default diagnostics tab", () => {
    useScheduledTaskFiresMock.mockReturnValue({
      data: undefined,
      error: null,
      isError: false,
      isPending: true,
    });
    const loadingView = renderDetailPage();
    fireEvent.click(screen.getByRole("tab", { name: "Runs" }));
    expect(screen.getByText("Loading runs...")).toBeVisible();
    expect(screen.queryByRole("tab", { name: "Diagnostics" })).not.toBeInTheDocument();
    loadingView.unmount();

    useScheduledTaskFiresMock.mockReturnValue({
      data: undefined,
      error: new Error("Fire history API unavailable"),
      isError: true,
      isPending: false,
    });
    renderDetailPage();
    fireEvent.click(screen.getByRole("tab", { name: "Runs" }));
    expect(screen.getByTestId("scheduled-task-fire-history-error")).toHaveTextContent(
      "Fire history API unavailable",
    );
    expect(screen.queryByText("Recent fire diagnostics unavailable")).not.toBeInTheDocument();
  });

  it("renders fire history with reasons, rendered parameters, linked runs, and run-now history navigation", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-05-30T12:00:00Z"));
    const queued = scheduleFireFixture({
      id: 801,
      reason: "manual",
      renderedParameters: { asOfDate: "2026-05-30", portfolioSlug: "core_portfolio" },
      runId: 2104,
      status: "queued",
    });
    const skipped = scheduleFireFixture({
      fireKey: "44:scheduled:2026-05-29T12:00:00Z",
      id: 800,
      materializedAt: "2026-05-29T12:00:00Z",
      renderedParameters: { asOfDate: "2026-05-29" },
      runId: null,
      scheduledFor: "2026-05-29T12:00:00Z",
      skipReason: "schedule_overlap_active",
      status: "skipped",
    });
    const failed = scheduleFireFixture({
      errorCode: "schedule_template_missing_value",
      errorMessage: "Missing vars.portfolioSlug",
      fireKey: "44:scheduled:2026-05-28T12:00:00Z",
      id: 799,
      renderedParameters: { asOfDate: "2026-05-28" },
      runId: null,
      scheduledFor: "2026-05-28T12:00:00Z",
      status: "failed",
    });
    useScheduledTaskFiresMock.mockReturnValue({
      data: scheduleFireList([queued, skipped, failed]),
      error: null,
      isError: false,
      isPending: false,
    });

    renderDetailPage();

    expect(useScheduledTaskFiresMock).toHaveBeenCalledWith("44", { limit: 20 });
    fireEvent.click(screen.getByRole("tab", { name: "Runs" }));
    const history = screen.getByTestId("scheduled-task-detail-tab-runs");
    expect(history).toHaveTextContent("3 total fires");
    expect(history).toHaveTextContent("Fire #801");
    expect(history).toHaveTextContent("Queued");
    expect(history).toHaveTextContent("Manual fire");
    expect(history).toHaveTextContent("core_portfolio");
    expect(history).toHaveTextContent("Fire #800");
    expect(history).toHaveTextContent("Skipped: Schedule Overlap Active");
    expect(history).toHaveTextContent("No linked run");
    expect(history).toHaveTextContent("Fire #799");
    expect(history).toHaveTextContent("Schedule Template Missing Value");
    expect(history).toHaveTextContent("Missing vars.portfolioSlug");
    expect(screen.getByRole("link", { name: "Open run #2104 for fire #801" })).toHaveAttribute(
      "href",
      "/runs/2104",
    );
    expect(screen.getByRole("link", { name: /Open latest run #2104/i })).toHaveAttribute(
      "href",
      "/runs/2104",
    );

    fireEvent.click(within(history).getByRole("button", { name: "Developer details" }));
    const fireDiagnostics = screen.getByTestId("scheduled-task-fire-diagnostics-panel");
    expect(fireDiagnostics).toHaveTextContent("1 failed");
    expect(fireDiagnostics).toHaveTextContent("1 skipped");
    expect(fireDiagnostics).toHaveTextContent("1 queued");
    expect(screen.getByTestId("scheduled-task-fire-diagnostic-799")).toHaveTextContent(
      "Missing vars.portfolioSlug",
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId("schedule-run-now"));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(runNowMock).toHaveBeenCalledWith({
      payload: {
        idempotencyKey: "manual-44-2026-05-30T12:00:00.000Z",
        scheduledFor: "2026-05-30T12:00:00.000Z",
      },
      scheduleId: 44,
    });
    expect(toastSuccessMock).toHaveBeenCalledWith("Scheduled task queued as run #3001. Opening run detail.");
    expect(screen.getByTestId("run-detail-route")).toHaveTextContent("Run detail 3001");
  });

  it("surfaces history-visible overlap warning when run-now queues overlapping runs", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-05-30T12:00:00Z"));
    useScheduledTaskMock.mockReturnValue({
      data: scheduleFixture({ overlapPolicy: "queue" }),
      error: null,
      isError: false,
      isPending: false,
    });

    renderDetailPage();

    await act(async () => {
      fireEvent.click(screen.getByTestId("schedule-run-now"));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(runNowMock).toHaveBeenCalledTimes(1);
    expect(toastWarningMock).toHaveBeenCalledWith(
      "Manual fire #900 queued run #3001. Overlap policy is queue, so active schedule runs may overlap instead of being skipped.",
    );
    expect(screen.getByTestId("run-detail-route")).toHaveTextContent("Run detail 3001");
  });

  it("keeps run-now failures visible on the schedule detail route", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-05-30T12:00:00Z"));
    runNowMock.mockRejectedValueOnce(new Error("Manual fire rejected"));

    renderDetailPage();

    await act(async () => {
      fireEvent.click(screen.getByTestId("schedule-run-now"));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(runNowMock).toHaveBeenCalledWith({
      payload: {
        idempotencyKey: "manual-44-2026-05-30T12:00:00.000Z",
        scheduledFor: "2026-05-30T12:00:00.000Z",
      },
      scheduleId: 44,
    });
    expect(toastErrorMock).toHaveBeenCalledWith("Manual fire rejected");
    expect(screen.queryByTestId("run-detail-route")).not.toBeInTheDocument();
    expect(screen.getByTestId("scheduled-task-detail-page")).toHaveTextContent("Daily market brief");
    expect(screen.queryByTestId("scheduled-task-run-now-feedback")).not.toBeInTheDocument();
  });

  it("keeps basic schedule controls visible and advanced scheduler options collapsed by default", () => {
    renderDetailPage();

    fireEvent.click(screen.getByRole("tab", { name: "Schedule" }));
    const scheduleTab = screen.getByTestId("scheduled-task-detail-tab-schedule");
    expect(scheduleTab).toHaveTextContent("Schedule configuration");
    expect(screen.getByLabelText("Schedule enabled")).toBeChecked();
    expect(screen.getByLabelText("Timezone")).toHaveValue("America/New_York");
    expect(screen.getByLabelText("At local time")).toHaveValue("09:00");
    expect(screen.queryByLabelText("Overlap policy")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Misfire policy")).not.toBeInTheDocument();
    expect(screen.queryByText(/PATCH endpoint/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Advanced options" }));
    expect(screen.getByLabelText("Overlap policy")).toBeVisible();
    expect(screen.getByLabelText("Misfire policy")).toBeVisible();
    expect(screen.getByLabelText("Misfire grace seconds")).toBeVisible();
  });

  it("serializes recurrence and policy edits to the canonical backend update payload", async () => {
    updateScheduleMock.mockResolvedValue(
      scheduleFixture({
        misfireGraceSeconds: 7200,
        misfirePolicy: "skip",
        overlapPolicy: "queue",
        recurrence: { every: 2, type: "interval", unit: "hours" },
        status: "paused",
        timezone: "Europe/London",
      }),
    );

    renderDetailPage();

    fireEvent.click(screen.getByRole("tab", { name: "Schedule" }));
    fireEvent.click(screen.getByRole("button", { name: "Advanced options" }));
    fireEvent.click(screen.getByLabelText("Schedule enabled"));
    fireEvent.change(screen.getByLabelText("Timezone"), { target: { value: "Europe/London" } });
    await chooseSelectOption("Recurrence type", "Interval");
    fireEvent.change(screen.getByLabelText("Every"), { target: { value: "2" } });
    await chooseSelectOption("Interval unit", "Hours");
    fireEvent.change(screen.getByLabelText("Starts at"), { target: { value: "2026-06-02T09:30" } });
    fireEvent.change(screen.getByLabelText("Ends at"), { target: { value: "" } });
    await chooseSelectOption("Overlap policy", /queue overlapping run/i);
    await chooseSelectOption("Misfire policy", /skip missed occurrence/i);
    fireEvent.change(screen.getByLabelText("Misfire grace seconds"), { target: { value: "7200" } });

    fireEvent.click(screen.getByRole("button", { name: "Save schedule" }));

    await waitFor(() => expect(updateScheduleMock).toHaveBeenCalledTimes(1));
    expect(updateScheduleMock).toHaveBeenCalledWith({
      payload: {
        endsAt: null,
        misfireGraceSeconds: 7200,
        misfirePolicy: "skip",
        overlapPolicy: "queue",
        recurrence: {
          every: 2,
          type: "interval",
          unit: "hours",
        },
        startsAt: new Date("2026-06-02T09:30").toISOString(),
        status: "paused",
        timezone: "Europe/London",
      },
      scheduleId: 44,
    });
    expect(toastSuccessMock).toHaveBeenCalledWith("Scheduled task configuration saved");
  });

  it("serializes weekly and monthly recurrence arrays without raw JSON editing", async () => {
    renderDetailPage();

    fireEvent.click(screen.getByRole("tab", { name: "Schedule" }));
    expect(screen.queryByText(/raw json/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Sunday"));
    fireEvent.click(screen.getByLabelText("Wednesday"));
    fireEvent.click(screen.getByRole("button", { name: "Save schedule" }));

    await waitFor(() => expect(updateScheduleMock).toHaveBeenCalledTimes(1));
    expect(updateScheduleMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        payload: expect.objectContaining({
          recurrence: {
            atLocalTime: "09:00",
            daysOfWeek: ["mon", "tue", "thu", "fri", "sun"],
            type: "weekly",
          },
        }),
      }),
    );

    updateScheduleMock.mockClear();
    await chooseSelectOption("Recurrence type", "Monthly");
    fireEvent.click(screen.getByLabelText("15"));
    fireEvent.click(screen.getByRole("button", { name: "Save schedule" }));

    await waitFor(() => expect(updateScheduleMock).toHaveBeenCalledTimes(1));
    expect(updateScheduleMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        payload: expect.objectContaining({
          recurrence: {
            atLocalTime: "09:00",
            daysOfMonth: [1, 15],
            type: "monthly",
          },
        }),
      }),
    );
  });

  it("scheduled inputs start with workflow defaults and keep placeholders/presets collapsed until customization", async () => {
    renderDetailPage();

    fireEvent.click(screen.getByRole("tab", { name: "Inputs" }));
    const editor = screen.getByTestId("scheduled-inputs-editor");
    expect(editor).toHaveTextContent("Start a custom draft from the workflow defaults.");
    expect(screen.queryByLabelText("Scheduled input template JSON")).not.toBeInTheDocument();
    expect(screen.queryByTestId("scheduled-input-placeholder-reference")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Customize inputs" }));
    const inputJson = screen.getByLabelText("Scheduled input template JSON") as HTMLTextAreaElement;
    expect(screen.queryByTestId("scheduled-input-placeholder-reference")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Placeholders and presets" }));
    expect(screen.getByTestId("scheduled-input-placeholder-reference")).toHaveTextContent("Allowed scheduled placeholders");
    fireEvent.click(within(screen.getByTestId("scheduled-input-placeholder-reference")).getByRole("button", { name: "Reference" }));
    expect(screen.getByTestId("scheduled-input-placeholder-reference")).toHaveTextContent("{{fire.scheduledLocalDate}}");
    expect(screen.getByTestId("scheduled-input-placeholder-reference")).toHaveTextContent("{{vars.<key>}}");
    expect(inputJson.value).toBe(JSON.stringify({ asOfDate: "", portfolioSlug: "" }, null, 2));
    fireEvent.change(inputJson, {
      target: {
        value: JSON.stringify({ asOfDate: "{{fire.scheduledLocalDate}}", portfolioSlug: "{{vars.portfolioSlug}}" }),
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add variable" }));
    fireEvent.change(screen.getByLabelText(/Template variable key/i), { target: { value: "portfolioSlug" } });
    fireEvent.change(screen.getByLabelText(/Template variable value/i), { target: { value: "core_portfolio" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview next run" }));

    await waitFor(() => expect(previewScheduledInputsMock).toHaveBeenCalledWith({
      inputTemplate: { asOfDate: "{{fire.scheduledLocalDate}}", portfolioSlug: "{{vars.portfolioSlug}}" },
      packageId: 12,
      recurrence: scheduleFixture().recurrence,
      scheduledFor: "2026-06-01T13:00:00Z",
      templateVars: { portfolioSlug: "core_portfolio" },
      timezone: "America/New_York",
      workflowKey: "daily_research",
    }));
    expect(screen.getByTestId("schedule-input-preview")).toHaveTextContent("Ready");
    expect(screen.getByTestId("schedule-input-preview")).toHaveTextContent("2026-06-01");

    fireEvent.change(inputJson, { target: { value: '{"asOfDate":"changed"}' } });
    fireEvent.click(screen.getByRole("button", { name: "Reset to schema template" }));
    expect(inputJson.value).toBe(JSON.stringify({ asOfDate: "", portfolioSlug: "" }, null, 2));
  });

  it("keeps custom inputs and edited template vars when switching top-level tabs", async () => {
    renderDetailPage();

    fireEvent.click(screen.getByRole("tab", { name: "Inputs" }));
    fireEvent.click(screen.getByRole("button", { name: "Customize inputs" }));
    fireEvent.click(screen.getByRole("button", { name: "Placeholders and presets" }));

    const inputJson = screen.getByLabelText("Scheduled input template JSON") as HTMLTextAreaElement;
    fireEvent.change(inputJson, {
      target: {
        value: JSON.stringify({ asOfDate: "{{fire.scheduledLocalDate}}", portfolioSlug: "{{vars.portfolioSlug}}" }),
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add variable" }));
    fireEvent.change(screen.getByPlaceholderText("portfolioSlug"), { target: { value: "portfolioSlug" } });
    fireEvent.change(screen.getByPlaceholderText("core_portfolio"), { target: { value: "core_portfolio" } });

    fireEvent.click(screen.getByRole("tab", { name: "Overview" }));
    fireEvent.click(screen.getByRole("tab", { name: "Inputs" }));

    expect(screen.getByRole("radio", { name: "Customize inputs" })).toBeChecked();
    expect(screen.getByLabelText("Scheduled input template JSON")).toHaveValue(
      JSON.stringify({ asOfDate: "{{fire.scheduledLocalDate}}", portfolioSlug: "{{vars.portfolioSlug}}" }, null, 2),
    );
    expect(screen.getByLabelText("Template variable key portfolioSlug")).toHaveValue("portfolioSlug");
    expect(screen.getByLabelText("Template variable value portfolioSlug")).toHaveValue("core_portfolio");
    expect(screen.getByTestId("scheduled-input-placeholder-reference")).toHaveTextContent("Allowed scheduled placeholders");
  });

  it("scheduled inputs save only after a ready preview returns canonical template payloads", async () => {
    renderDetailPage();

    fireEvent.click(screen.getByRole("tab", { name: "Inputs" }));
    fireEvent.click(screen.getByRole("button", { name: "Customize inputs" }));
    fireEvent.click(screen.getByRole("button", { name: "Placeholders and presets" }));
    fireEvent.change(screen.getByLabelText("Scheduled input template JSON"), {
      target: {
        value: JSON.stringify({ asOfDate: "{{fire.scheduledLocalDate}}", portfolioSlug: "{{vars.portfolioSlug}}" }),
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add variable" }));
    fireEvent.change(screen.getByLabelText(/Template variable key/i), { target: { value: "portfolioSlug" } });
    fireEvent.change(screen.getByLabelText(/Template variable value/i), { target: { value: "core_portfolio" } });
    fireEvent.click(screen.getByRole("button", { name: "Save inputs" }));

    await waitFor(() => expect(previewScheduledInputsMock).toHaveBeenCalledWith({
      inputTemplate: { asOfDate: "{{fire.scheduledLocalDate}}", portfolioSlug: "{{vars.portfolioSlug}}" },
      packageId: 12,
      recurrence: scheduleFixture().recurrence,
      scheduledFor: "2026-06-01T13:00:00Z",
      templateVars: { portfolioSlug: "core_portfolio" },
      timezone: "America/New_York",
      workflowKey: "daily_research",
    }));
    expect(updateScheduleMock).toHaveBeenCalledWith({
      payload: {
        inputTemplate: { asOfDate: "{{fire.scheduledLocalDate}}", portfolioSlug: "{{vars.portfolioSlug}}" },
        templateVars: { portfolioSlug: "core_portfolio" },
      },
      scheduleId: 44,
    });
    expect(toastSuccessMock).toHaveBeenCalledWith("Scheduled input template saved");
  });

  it("scheduled inputs block preview and save when nextFireAt is unavailable", async () => {
    useScheduledTaskMock.mockReturnValue({
      data: scheduleFixture({ nextFireAt: null }),
      error: null,
      isError: false,
      isPending: false,
    });

    renderDetailPage();

    fireEvent.click(screen.getByRole("tab", { name: "Inputs" }));
    fireEvent.click(screen.getByRole("button", { name: "Customize inputs" }));
    const inputsTab = screen.getByTestId("scheduled-task-detail-tab-inputs");
    expect(inputsTab).toHaveTextContent("Next fire preview unavailable");
    expect(inputsTab).toHaveTextContent("preview and save are blocked");
    expect(screen.getByRole("button", { name: "Preview next run" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save inputs" })).toBeDisabled();
    expect(previewScheduledInputsMock).not.toHaveBeenCalled();
    expect(updateScheduleMock).not.toHaveBeenCalled();
  });

  it("scheduled inputs block invalid JSON and unsupported placeholders before preview or save", async () => {
    renderDetailPage();

    fireEvent.click(screen.getByRole("tab", { name: "Inputs" }));
    fireEvent.click(screen.getByRole("button", { name: "Customize inputs" }));
    const inputJson = screen.getByLabelText("Scheduled input template JSON");
    fireEvent.change(inputJson, { target: { value: "[]" } });
    expect(screen.getByTestId("scheduled-input-json-validation-feedback")).toHaveTextContent("must be a valid object");
    expect(screen.getByRole("button", { name: "Preview next run" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save inputs" })).toBeDisabled();
    expect(previewScheduledInputsMock).not.toHaveBeenCalled();

    fireEvent.change(inputJson, { target: { value: '{"ticker":"{{inputs.ticker}}"}' } });
    expect(screen.getByTestId("scheduled-input-json-validation-feedback")).toHaveTextContent("Unsupported placeholder");
    expect(screen.getByTestId("scheduled-input-json-validation-feedback")).toHaveTextContent("inputs.ticker");
    expect(screen.getByRole("button", { name: "Preview next run" })).toBeDisabled();
  });

  it("scheduled inputs show preview validation failures and avoid saving rejected drafts", async () => {
    previewScheduledInputsMock.mockResolvedValueOnce(schedulePreviewResult({
      ready: false,
      renderedParameters: { asOfDate: "2026-06-01", extra: true },
      validationErrors: [{ field: "parameters.extra", issue: "Unknown field" }],
    }));
    renderDetailPage();

    fireEvent.click(screen.getByRole("tab", { name: "Inputs" }));
    fireEvent.click(screen.getByRole("button", { name: "Customize inputs" }));
    fireEvent.click(screen.getByRole("button", { name: "Placeholders and presets" }));
    fireEvent.change(screen.getByLabelText("Scheduled input template JSON"), {
      target: { value: JSON.stringify({ asOfDate: "{{fire.scheduledLocalDate}}", extra: true }) },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save inputs" }));

    const feedback = await screen.findByTestId("scheduled-input-preview-validation-feedback");
    expect(feedback).toHaveTextContent("parameters.extra");
    expect(feedback).toHaveTextContent("Unknown field");
    expect(updateScheduleMock).not.toHaveBeenCalled();
    expect(toastWarningMock).toHaveBeenCalledWith("Scheduled input preview returned validation errors");
  });

  it("scheduled inputs reuse workflow runtime-input presets and history with schedule-specific copy", async () => {
    const personal = runtimeInputEntry({ id: 7, name: "Morning schedule", payload: { asOfDate: "{{fire.scheduledLocalDate}}" }, slot: "personal" });
    const olderHistory = runtimeInputEntry({ createdAt: "2026-05-08T08:00:00Z", id: 10, payload: { asOfDate: "2026-05-08" }, slot: "history", sourceRunId: 88 });
    const newerHistory = runtimeInputEntry({ createdAt: "2026-05-08T11:00:00Z", id: 11, payload: { asOfDate: "2026-05-09" }, slot: "history", sourceRunId: 99 });
    useWorkflowPackageRuntimeInputRegistryMock.mockReturnValue(runtimeInputRegistry({ history: [olderHistory, newerHistory], personal: [personal] }));
    renderDetailPage();

    fireEvent.click(screen.getByRole("tab", { name: "Inputs" }));
    fireEvent.click(screen.getByRole("button", { name: "Customize inputs" }));
    fireEvent.click(screen.getByRole("button", { name: "Placeholders and presets" }));
    const helper = await screen.findByTestId("scheduled-input-saved-inputs-helper");
    expect(helper).toHaveTextContent("Schedule input presets");
    expect(helper).toHaveTextContent("1/20");
    expect(helper).toHaveTextContent("2/20");
    const inputJson = screen.getByLabelText("Scheduled input template JSON") as HTMLTextAreaElement;
    fireEvent.change(inputJson, { target: { value: '{"asOfDate":"{{fire.scheduledLocalDate}}"}' } });
    fireEvent.change(screen.getByLabelText("Scheduled input preset name"), { target: { value: "Reusable schedule" } });
    fireEvent.click(screen.getByRole("button", { name: "Save current template" }));

    await waitFor(() => expect(createRuntimeInputPersonalEntryMock).toHaveBeenCalledWith({
      packageId: 12,
      payload: { name: "Reusable schedule", payload: { asOfDate: "{{fire.scheduledLocalDate}}" } },
      workflowKey: "daily_research",
    }));
    fireEvent.click(screen.getByRole("button", { name: "Load personal scheduled input Morning schedule" }));
    expect(inputJson.value).toBe(JSON.stringify({ asOfDate: "{{fire.scheduledLocalDate}}" }, null, 2));

    fireEvent.change(inputJson, { target: { value: '{"asOfDate":"{{window.endDate}}"}' } });
    fireEvent.click(screen.getByRole("button", { name: "Overwrite personal scheduled input Morning schedule" }));
    await waitFor(() => expect(updateRuntimeInputPersonalEntryMock).toHaveBeenCalledWith({
      entryId: 7,
      packageId: 12,
      payload: { name: "Morning schedule", payload: { asOfDate: "{{window.endDate}}" } },
      workflowKey: "daily_research",
    }));
    fireEvent.click(screen.getByRole("button", { name: "Delete personal scheduled input Morning schedule" }));
    await waitFor(() => expect(deleteRuntimeInputPersonalEntryMock).toHaveBeenCalledWith({ entryId: 7, packageId: 12, workflowKey: "daily_research" }));

    fireEvent.mouseDown(within(helper).getByRole("tab", { name: /history/i }), { button: 0 });
    expect(screen.getByTestId("scheduled-input-history-11").compareDocumentPosition(screen.getByTestId("scheduled-input-history-10")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Load history scheduled input Run #99" }));
    expect(inputJson.value).toBe(JSON.stringify({ asOfDate: "2026-05-09" }, null, 2));
  });
});
