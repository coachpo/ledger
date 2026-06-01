import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ScheduleRead } from "@/lib/types/schedule";

import { ScheduledTasksListPage } from "./list";

const {
  deleteScheduleMock,
  runNowMock,
  toastErrorMock,
  toastSuccessMock,
  updateScheduleMock,
  useDeleteScheduledTaskMock,
  useRunScheduledTaskNowMock,
  useScheduledTasksMock,
  useUpdateScheduledTaskMock,
} = vi.hoisted(() => ({
  deleteScheduleMock: vi.fn(),
  runNowMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  updateScheduleMock: vi.fn(),
  useDeleteScheduledTaskMock: vi.fn(),
  useRunScheduledTaskNowMock: vi.fn(),
  useScheduledTasksMock: vi.fn(),
  useUpdateScheduledTaskMock: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}));

vi.mock("@/hooks/use-scheduled-tasks", () => ({
  useDeleteScheduledTask: () => useDeleteScheduledTaskMock(),
  useRunScheduledTaskNow: () => useRunScheduledTaskNowMock(),
  useScheduledTasks: (...args: unknown[]) => useScheduledTasksMock(...args),
  useUpdateScheduledTask: () => useUpdateScheduledTaskMock(),
}));

function scheduleFixture(overrides: Partial<ScheduleRead> = {}): ScheduleRead {
  return {
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

function renderPage() {
  return render(
    <MemoryRouter>
      <ScheduledTasksListPage />
    </MemoryRouter>,
  );
}
describe("ScheduledTasksListPage", () => {
  beforeEach(() => {
    deleteScheduleMock.mockReset();
    runNowMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    updateScheduleMock.mockReset();
    useDeleteScheduledTaskMock.mockReset();
    useRunScheduledTaskNowMock.mockReset();
    useScheduledTasksMock.mockReset();
    useUpdateScheduledTaskMock.mockReset();
    deleteScheduleMock.mockResolvedValue(undefined);
    runNowMock.mockResolvedValue({ run: { id: 3001 }, scheduleId: 44 });
    updateScheduleMock.mockResolvedValue(scheduleFixture({ status: "paused" }));
    useDeleteScheduledTaskMock.mockReturnValue({
      isPending: false,
      mutateAsync: deleteScheduleMock,
    });
    useRunScheduledTaskNowMock.mockReturnValue({
      isPending: false,
      mutateAsync: runNowMock,
    });
    useUpdateScheduledTaskMock.mockReturnValue({
      isPending: false,
      mutateAsync: updateScheduleMock,
    });
    useScheduledTasksMock.mockReturnValue({
      data: { items: [], limit: 50, offset: 0, totalCount: 0 },
      error: null,
      isError: false,
      isPending: false,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders loading, error, empty, and filtered-empty states", () => {
    useScheduledTasksMock.mockReturnValue({
      data: undefined,
      error: null,
      isError: false,
      isPending: true,
    });
    const { rerender } = renderPage();

    expect(screen.getByTestId("scheduled-tasks-list-page")).toBeInTheDocument();
    expect(document.querySelectorAll("[data-slot='skeleton']")).toHaveLength(4);

    useScheduledTasksMock.mockReturnValue({
      data: undefined,
      error: new Error("Schedules API unavailable"),
      isError: true,
      isPending: false,
    });
    rerender(
      <MemoryRouter>
        <ScheduledTasksListPage />
      </MemoryRouter>,
    );
    expect(screen.getByText("Failed to load scheduled tasks")).toBeVisible();
    expect(screen.getByText("Schedules API unavailable")).toBeVisible();

    useScheduledTasksMock.mockReturnValue({
      data: { items: [], limit: 50, offset: 0, totalCount: 0 },
      error: null,
      isError: false,
      isPending: false,
    });
    rerender(
      <MemoryRouter>
        <ScheduledTasksListPage />
      </MemoryRouter>,
    );
    expect(screen.getByText("No scheduled tasks yet.")).toBeVisible();

    fireEvent.change(screen.getByLabelText("Search scheduled tasks"), {
      target: { value: "missing" },
    });
    expect(
      screen.getByText("No scheduled tasks match this search or filters."),
    ).toBeVisible();
  });

  it("renders schedule inventory fields and explicit row actions", () => {
    useScheduledTasksMock.mockReturnValue({
      data: {
        items: [
          scheduleFixture(),
          scheduleFixture({
            description: null,
            id: 55,
            latestFireId: null,
            latestRunId: null,
            latestStatus: null,
            name: "Paused allocation check",
            nextFireAt: null,
            packageId: 21,
            packageKey: "allocation_package",
            recurrence: { every: 4, type: "interval", unit: "hours" },
            status: "paused",
            workflowKey: "allocation_check",
          }),
        ],
        limit: 50,
        offset: 0,
        totalCount: 2,
      },
      error: null,
      isError: false,
      isPending: false,
    });

    renderPage();

    expect(
      screen.getByRole("heading", { name: "Scheduled Tasks" }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Create scheduled task" }),
    ).toHaveAttribute("href", "/scheduled-tasks/new");
    expect(screen.getByLabelText("Search scheduled tasks")).toBeVisible();
    expect(screen.getByTestId("scheduled-tasks-filter-enabled")).toBeVisible();
    expect(screen.getByTestId("scheduled-tasks-filter-package")).toBeVisible();
    expect(screen.getByText("2 of 2 scheduled tasks shown")).toBeVisible();

    const table = screen.getByRole("table");
    for (const column of [
      "Schedule",
      "Package / Workflow",
      "Next fire",
      "Latest activity",
      "Actions",
    ]) {
      expect(within(table).getByRole("columnheader", { name: column })).toBeVisible();
    }

    const dailyRow = screen.getByTestId("scheduled-task-row-44");
    expect(dailyRow).toHaveTextContent("Daily market brief");
    expect(dailyRow).toHaveTextContent("enabled");
    expect(within(dailyRow).getByTestId("scheduled-task-status-enabled")).toHaveAttribute(
      "data-tone",
      "success",
    );
    expect(dailyRow).toHaveTextContent("market_research_package");
    expect(dailyRow).toHaveTextContent("daily_research");
    expect(dailyRow).toHaveTextContent("Package id: #12");
    expect(dailyRow).toHaveTextContent("America/New_York");
    expect(dailyRow).toHaveTextContent("Weekly Mon, Tue, Wed, Thu, Fri at 09:00");
    expect(dailyRow).toHaveTextContent("Overlap: Skip");
    expect(dailyRow).toHaveTextContent("Misfire: Catch Up One");
    expect(dailyRow).toHaveTextContent("Latest fire: #801");
    expect(dailyRow).toHaveTextContent("Latest run: #2104");
    expect(dailyRow).toHaveTextContent("Queued");

    expect(
      within(dailyRow).getByRole("link", { name: "Edit schedule Daily market brief" }),
    ).toHaveAttribute("href", "/scheduled-tasks/44");
    expect(
      within(dailyRow).getByRole("link", {
        name: "Duplicate schedule Daily market brief",
      }),
    ).toHaveAttribute("href", "/scheduled-tasks/new?duplicateFrom=44");
    expect(
      within(dailyRow).getByRole("link", {
        name: "Open latest run for Daily market brief",
      }),
    ).toHaveAttribute("href", "/runs/2104");
    expect(
      within(dailyRow).getByRole("button", {
        name: "Run schedule Daily market brief now",
      }),
    ).toBeVisible();
    expect(
      within(dailyRow).getByRole("button", {
        name: "Pause schedule Daily market brief",
      }),
    ).toBeVisible();
    expect(
      within(dailyRow).getByRole("button", {
        name: "Delete schedule Daily market brief",
      }),
    ).toBeVisible();
    expect(
      within(dailyRow).getByTestId("scheduled-task-row-action-delete"),
    ).toBeVisible();

    const pausedRow = screen.getByTestId("scheduled-task-row-55");
    expect(pausedRow).toHaveTextContent("Paused allocation check");
    expect(pausedRow).toHaveTextContent("No upcoming fire");
    expect(pausedRow).toHaveTextContent("Every 4 hours");
    expect(pausedRow).toHaveTextContent("Latest fire: None");
    expect(pausedRow).toHaveTextContent("Latest run: None");
    expect(
      within(pausedRow).getByRole("button", {
        name: "Resume schedule Paused allocation check",
      }),
    ).toBeVisible();
    expect(
      within(pausedRow).queryByTestId("scheduled-task-row-action-open-latest-run"),
    ).not.toBeInTheDocument();
    expect(dailyRow).not.toHaveAttribute("aria-label");
  });

  it("keeps filters routed through schedule hooks while search stays local", () => {
    useScheduledTasksMock.mockReturnValue({
      data: {
        items: [scheduleFixture()],
        limit: 50,
        offset: 0,
        totalCount: 1,
      },
      error: null,
      isError: false,
      isPending: false,
    });

    renderPage();

    expect(useScheduledTasksMock).toHaveBeenLastCalledWith({
      limit: 50,
      packageKey: undefined,
      status: undefined,
      workflowKey: undefined,
    });

    fireEvent.click(screen.getByTestId("scheduled-tasks-filter-enabled"));
    expect(useScheduledTasksMock).toHaveBeenLastCalledWith({
      limit: 50,
      packageKey: undefined,
      status: "enabled",
      workflowKey: undefined,
    });

    fireEvent.change(screen.getByTestId("scheduled-tasks-filter-package"), {
      target: { value: " market_research " },
    });
    expect(useScheduledTasksMock).toHaveBeenLastCalledWith({
      limit: 50,
      packageKey: "market_research",
      status: "enabled",
      workflowKey: undefined,
    });

    fireEvent.change(screen.getByTestId("scheduled-tasks-filter-workflow"), {
      target: { value: " daily " },
    });
    expect(useScheduledTasksMock).toHaveBeenLastCalledWith({
      limit: 50,
      packageKey: "market_research",
      status: "enabled",
      workflowKey: "daily",
    });

    fireEvent.change(screen.getByLabelText("Search scheduled tasks"), {
      target: { value: "no-match" },
    });
    expect(useScheduledTasksMock).toHaveBeenLastCalledWith({
      limit: 50,
      packageKey: "market_research",
      status: "enabled",
      workflowKey: "daily",
    });
    expect(
      screen.getByText("No scheduled tasks match this search or filters."),
    ).toBeVisible();
  });

  it("disables pending row actions while keeping navigation links explicit", () => {
    useRunScheduledTaskNowMock.mockReturnValue({
      isPending: true,
      mutateAsync: runNowMock,
    });
    useScheduledTasksMock.mockReturnValue({
      data: {
        items: [
          scheduleFixture({
            id: 66,
            latestRunId: 2206,
            name: "Market brief pending action",
          }),
        ],
        limit: 50,
        offset: 0,
        totalCount: 1,
      },
      error: null,
      isError: false,
      isPending: false,
    });

    renderPage();

    const pendingRow = screen.getByTestId("scheduled-task-row-66");
    expect(within(pendingRow).getByRole("link", { name: "Edit schedule Market brief pending action" })).toHaveAttribute(
      "href",
      "/scheduled-tasks/66",
    );
    expect(within(pendingRow).getByRole("link", { name: "Open latest run for Market brief pending action" })).toHaveAttribute(
      "href",
      "/runs/2206",
    );
    expect(within(pendingRow).getByRole("button", { name: "Run schedule Market brief pending action now" })).toBeDisabled();
    expect(within(pendingRow).getByRole("button", { name: "Pause schedule Market brief pending action" })).toBeDisabled();
    expect(within(pendingRow).getByRole("button", { name: "Delete schedule Market brief pending action" })).toBeDisabled();
  });

  it("runs mutations from explicit row buttons", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-05-30T12:00:00Z"));
    useScheduledTasksMock.mockReturnValue({
      data: {
        items: [
          scheduleFixture(),
          scheduleFixture({
            id: 55,
            name: "Paused allocation check",
            status: "paused",
            workflowKey: "allocation_check",
          }),
        ],
        limit: 50,
        offset: 0,
        totalCount: 2,
      },
      error: null,
      isError: false,
      isPending: false,
    });

    renderPage();

    const dailyRow = screen.getByTestId("scheduled-task-row-44");
    fireEvent.click(
      within(dailyRow).getByRole("button", {
        name: "Run schedule Daily market brief now",
      }),
    );
    expect(runNowMock).toHaveBeenCalledWith({
      scheduleId: 44,
      payload: {
        idempotencyKey: "manual-44-2026-05-30T12:00:00.000Z",
        scheduledFor: "2026-05-30T12:00:00.000Z",
      },
    });
    await Promise.resolve();
    expect(toastSuccessMock).toHaveBeenCalledWith(
      "Scheduled task queued as run #3001",
    );

    fireEvent.click(
      within(dailyRow).getByRole("button", {
        name: "Pause schedule Daily market brief",
      }),
    );
    expect(updateScheduleMock).toHaveBeenCalledWith({
      scheduleId: 44,
      payload: { status: "paused" },
    });

    const pausedRow = screen.getByTestId("scheduled-task-row-55");
    fireEvent.click(
      within(pausedRow).getByRole("button", {
        name: "Resume schedule Paused allocation check",
      }),
    );
    expect(updateScheduleMock).toHaveBeenCalledWith({
      scheduleId: 55,
      payload: { status: "enabled" },
    });

    fireEvent.click(
      within(dailyRow).getByRole("button", {
        name: "Delete schedule Daily market brief",
      }),
    );
    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      "Delete scheduled task",
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Delete scheduled task" }),
    );
    expect(deleteScheduleMock).toHaveBeenCalledWith({
      latestRunId: 2104,
      scheduleId: 44,
    });
  });

  it("surfaces row mutation failures without changing the visible schedule row", async () => {
    runNowMock.mockRejectedValueOnce(new Error("Manual fire rejected"));
    updateScheduleMock.mockRejectedValueOnce(new Error("Status update rejected"));
    deleteScheduleMock.mockRejectedValueOnce(new Error("Delete rejected"));
    useScheduledTasksMock.mockReturnValue({
      data: {
        items: [scheduleFixture()],
        limit: 50,
        offset: 0,
        totalCount: 1,
      },
      error: null,
      isError: false,
      isPending: false,
    });

    renderPage();

    const dailyRow = screen.getByTestId("scheduled-task-row-44");
    fireEvent.click(within(dailyRow).getByRole("button", { name: "Run schedule Daily market brief now" }));
    await waitFor(() => expect(toastErrorMock).toHaveBeenCalledWith("Manual fire rejected"));
    expect(screen.getByTestId("scheduled-task-row-44")).toHaveTextContent("Daily market brief");

    fireEvent.click(within(dailyRow).getByRole("button", { name: "Pause schedule Daily market brief" }));
    await waitFor(() => expect(toastErrorMock).toHaveBeenCalledWith("Status update rejected"));

    fireEvent.click(within(dailyRow).getByRole("button", { name: "Delete schedule Daily market brief" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete scheduled task" }));
    await waitFor(() => expect(toastErrorMock).toHaveBeenCalledWith("Delete rejected"));
    expect(screen.getByTestId("scheduled-task-row-44")).toHaveTextContent("Daily market brief");
  });
});
