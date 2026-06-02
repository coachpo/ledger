import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ScheduleRead } from "@/lib/types/schedule";
import type {
  WorkflowPackageManifestRead,
  WorkflowPackageRead,
} from "@/lib/types/workflow-package";

import { ScheduledTasksListPage } from "./list";

const {
  deleteScheduleMock,
  deleteSchedulesMock,
  runNowMock,
  toastErrorMock,
  toastSuccessMock,
  updateScheduleMock,
  useDeleteScheduledTaskMock,
  useDeleteScheduledTasksMock,
  useRunScheduledTaskNowMock,
  useScheduledTasksMock,
  useUpdateScheduledTaskMock,
  useWorkflowPackageManifestMock,
  useWorkflowPackagesMock,
} = vi.hoisted(() => ({
  deleteScheduleMock: vi.fn(),
  deleteSchedulesMock: vi.fn(),
  runNowMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  updateScheduleMock: vi.fn(),
  useDeleteScheduledTaskMock: vi.fn(),
  useDeleteScheduledTasksMock: vi.fn(),
  useRunScheduledTaskNowMock: vi.fn(),
  useScheduledTasksMock: vi.fn(),
  useUpdateScheduledTaskMock: vi.fn(),
  useWorkflowPackageManifestMock: vi.fn(),
  useWorkflowPackagesMock: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}));

vi.mock("@/hooks/use-scheduled-tasks", () => ({
  useDeleteScheduledTask: () => useDeleteScheduledTaskMock(),
  useDeleteScheduledTasks: () => useDeleteScheduledTasksMock(),
  useRunScheduledTaskNow: () => useRunScheduledTaskNowMock(),
  useScheduledTasks: (...args: unknown[]) => useScheduledTasksMock(...args),
  useUpdateScheduledTask: () => useUpdateScheduledTaskMock(),
}));

vi.mock("@/hooks/use-workflow-packages", () => ({
  useWorkflowPackageManifest: (...args: unknown[]) =>
    useWorkflowPackageManifestMock(...args),
  useWorkflowPackages: () => useWorkflowPackagesMock(),
}));

type ScheduleFixtureOverrides = Omit<Partial<ScheduleRead>, "latestStatus"> & {
  latestStatus?: string | null;
};

function scheduleFixture(overrides: ScheduleFixtureOverrides = {}) {
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

function workflowPackageFixture(
  overrides: Partial<WorkflowPackageRead> = {},
): WorkflowPackageRead {
  return {
    compiledHash: "compiled-hash-1",
    createdAt: "2026-05-01T10:00:00Z",
    description: "Workflow package",
    id: 12,
    key: "market_research_package",
    manifestHash: "manifest-hash-1",
    name: "Market Research Package",
    updatedAt: "2026-05-30T10:00:00Z",
    ...overrides,
  };
}

function workflowManifestFixture({
  packageId = 12,
  packageKey = "market_research_package",
  workflows = [
    {
      description: "Daily research flow",
      key: "daily_research",
      label: "Daily Research",
    },
    {
      description: "News research flow",
      key: "news_research",
      label: "News Research",
    },
  ],
}: {
  packageId?: number;
  packageKey?: string;
  workflows?: Array<{ description: string; key: string; label: string }>;
} = {}): WorkflowPackageManifestRead {
  return {
    compiledHash: `compiled-${packageKey}`,
    manifestHash: `manifest-${packageKey}`,
    manifestSource: "apiVersion: signaldeck.workflowPackage/v1",
    packageDefinition: {
      spec: {
        workflows,
      },
    },
    packageId,
    packageKey,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ScheduledTasksListPage />
    </MemoryRouter>,
  );
}

function setViewportWidth(width: number) {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: width,
    writable: true,
  });
  window.dispatchEvent(new Event("resize"));
}

function packageSelector() {
  return screen.getByRole("combobox", { name: /package/i });
}

function workflowSelector() {
  return screen.getByRole("combobox", { name: /workflow/i });
}

async function chooseSelectOption(
  selector: HTMLElement,
  optionName: string | RegExp,
) {
  selector.focus();
  fireEvent.keyDown(selector, { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name: optionName }));
}

function openActionMenu(container: HTMLElement) {
  const trigger = within(container).getByRole("button", {
    name: /open actions for/i,
  });
  trigger.focus();
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
}

function expectRowBefore(first: HTMLElement, second: HTMLElement) {
  expect(
    first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
}

describe("ScheduledTasksListPage", () => {
  beforeEach(() => {
    setViewportWidth(1280);
    deleteScheduleMock.mockReset();
    deleteSchedulesMock.mockReset();
    runNowMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    updateScheduleMock.mockReset();
    useDeleteScheduledTaskMock.mockReset();
    useDeleteScheduledTasksMock.mockReset();
    useRunScheduledTaskNowMock.mockReset();
    useScheduledTasksMock.mockReset();
    useUpdateScheduledTaskMock.mockReset();
    useWorkflowPackageManifestMock.mockReset();
    useWorkflowPackagesMock.mockReset();
    deleteScheduleMock.mockResolvedValue(undefined);
    deleteSchedulesMock.mockImplementation(
      (_variables: unknown, options?: { onSuccess?: () => void }) =>
        options?.onSuccess?.(),
    );
    runNowMock.mockResolvedValue({ run: { id: 3001 }, scheduleId: 44 });
    updateScheduleMock.mockResolvedValue(scheduleFixture({ status: "paused" }));
    useDeleteScheduledTaskMock.mockReturnValue({
      isPending: false,
      mutateAsync: deleteScheduleMock,
    });
    useDeleteScheduledTasksMock.mockReturnValue({
      isPending: false,
      mutate: deleteSchedulesMock,
    });
    useRunScheduledTaskNowMock.mockReturnValue({
      isPending: false,
      mutateAsync: runNowMock,
    });
    useUpdateScheduledTaskMock.mockReturnValue({
      isPending: false,
      mutateAsync: updateScheduleMock,
    });
    useWorkflowPackagesMock.mockReturnValue({
      data: {
        items: [
          workflowPackageFixture(),
          workflowPackageFixture({
            id: 21,
            key: "allocation_package",
            name: "Allocation Package",
          }),
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });
    useWorkflowPackageManifestMock.mockImplementation((packageId?: string | number) => {
      const normalizedPackageId = Number(packageId);
      const data =
        normalizedPackageId === 12
          ? workflowManifestFixture()
          : normalizedPackageId === 21
            ? workflowManifestFixture({
                packageId: 21,
                packageKey: "allocation_package",
                workflows: [
                  {
                    description: "Allocation check flow",
                    key: "allocation_check",
                    label: "Allocation Check",
                  },
                ],
              })
            : undefined;

      return {
        data,
        error: null,
        isError: false,
        isPending: false,
      };
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
    rerender(
      <MemoryRouter>
        <ScheduledTasksListPage />
      </MemoryRouter>,
    );
    expect(screen.getByText("Daily market brief")).toBeVisible();

    fireEvent.click(screen.getByTestId("scheduled-tasks-filter-succeeded"));
    expect(
      screen.getByText("No scheduled tasks match this search or filters."),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("radio", { name: "All" }));

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
    expect(screen.getByText(/No scheduled tasks yet/i)).toBeVisible();
  });

  it("renders redesigned schedule rows with sortable headers, expansion, and menu actions", async () => {
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

    expect(screen.getByRole("heading", { name: "Scheduled Tasks" })).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Create scheduled task" }),
    ).toHaveAttribute("href", "/scheduled-tasks/new");
    expect(screen.getByLabelText("Search scheduled tasks")).toBeVisible();
    for (const filter of ["All", "Running", "Failed", "Succeeded", "Paused"]) {
      expect(screen.getByRole("radio", { name: filter })).toBeVisible();
    }
    expect(packageSelector()).toHaveTextContent("All packages");
    expect(workflowSelector()).toBeDisabled();
    expect(
      screen.getByText("Choose a package first to filter by workflow."),
    ).toBeVisible();
    expect(screen.getByText("2 of 2 scheduled tasks shown")).toBeVisible();

    const table = screen.getByRole("table");
    expect(
      within(table).getByRole("columnheader", { name: /workflow/i }),
    ).not.toHaveAttribute("aria-sort");
    expect(within(table).getByRole("columnheader", { name: /next run/i })).toHaveAttribute(
      "aria-sort",
      "ascending",
    );
    for (const column of [
      /^Workflow$/i,
      /^Schedule$/i,
      /^Next run$/i,
      /^Latest activity$/i,
      /^Actions$/i,
    ]) {
      expect(within(table).getByRole("columnheader", { name: column })).toBeVisible();
    }
    expect(
      screen.getByRole("button", { name: "Sort scheduled tasks by Workflow" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Sort scheduled tasks by Next run (ascending)" }),
    ).toBeVisible();

    const dailyRow = screen.getByTestId("scheduled-task-row-44");
    expect(dailyRow).toHaveTextContent("Daily market brief");
    expect(dailyRow).toHaveTextContent("Enabled");
    expect(within(dailyRow).getByTestId("scheduled-task-status-enabled")).toHaveAttribute(
      "data-tone",
      "success",
    );
    expect(dailyRow).toHaveTextContent("America/New_York");
    expect(dailyRow).toHaveTextContent("Weekly Mon, Tue, Wed, Thu, Fri at 09:00");
    expect(dailyRow).toHaveTextContent("Overlap: Skip");
    expect(dailyRow).toHaveTextContent("Misfire: Catch Up One");
    expect(dailyRow).toHaveTextContent("Fire #801 · Run #2104");
    expect(
      within(dailyRow).getByRole("button", { name: "Run schedule Daily market brief now" }),
    ).toBeVisible();
    expect(
      within(dailyRow).queryByRole("button", {
        name: "Resume schedule Daily market brief",
      }),
    ).not.toBeInTheDocument();

    fireEvent.click(
      within(dailyRow).getByRole("button", {
        name: "Show details for Daily market brief",
      }),
    );
    const details = screen.getByTestId("scheduled-task-row-details-44");
    expect(details).toHaveTextContent("Package ID");
    expect(details).toHaveTextContent("market_research_package");
    expect(details).toHaveTextContent("daily_research");
    expect(details).toHaveTextContent("Misfire grace");
    expect(details).toHaveTextContent("86400 seconds");

    openActionMenu(dailyRow);
    expect(screen.getByText("Edit").closest("a")).toHaveAttribute(
      "href",
      "/scheduled-tasks/44",
    );
    expect(screen.getByText("Pause")).toBeVisible();
    expect(screen.getByText("Duplicate").closest("a")).toHaveAttribute(
      "href",
      "/scheduled-tasks/new?duplicateFrom=44",
    );
    expect(
      screen.getByRole("menuitem", {
        name: "Open latest run for Daily market brief",
      }),
    ).toHaveAttribute("href", "/runs/2104");
    expect(screen.getByText("Delete")).toBeVisible();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });

    const pausedRow = screen.getByTestId("scheduled-task-row-55");
    expect(pausedRow).toHaveTextContent("Paused allocation check");
    expect(within(pausedRow).getByTestId("scheduled-task-status-paused")).toHaveAttribute(
      "data-tone",
      "muted",
    );
    expect(pausedRow).toHaveTextContent("No upcoming run");
    expect(pausedRow).toHaveTextContent("Every 4 hours");
    expect(pausedRow).toHaveTextContent("No latest status");
    expect(
      within(pausedRow).getByRole("button", {
        name: "Resume schedule Paused allocation check",
      }),
    ).toBeVisible();

    openActionMenu(pausedRow);
    const latestRunItem = screen.getByRole("menuitem", { name: "Latest run" });
    expect(latestRunItem.closest("[data-disabled]")).not.toBeNull();
    expect(screen.queryByRole("menuitem", { name: "Pause" })).not.toBeInTheDocument();
  });

  it("keeps package and workflow hook params stable while status filters and search stay local", async () => {
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
      workflowKey: undefined,
    });
    expect(workflowSelector()).toBeDisabled();

    fireEvent.click(screen.getByTestId("scheduled-tasks-filter-failed"));
    expect(useScheduledTasksMock).toHaveBeenLastCalledWith({
      limit: 50,
      packageKey: undefined,
      workflowKey: undefined,
    });

    await chooseSelectOption(packageSelector(), "Market Research Package");
    expect(useScheduledTasksMock).toHaveBeenLastCalledWith({
      limit: 50,
      packageKey: "market_research_package",
      workflowKey: undefined,
    });
    expect(workflowSelector()).not.toBeDisabled();

    await chooseSelectOption(workflowSelector(), "Daily Research");
    expect(useScheduledTasksMock).toHaveBeenLastCalledWith({
      limit: 50,
      packageKey: "market_research_package",
      workflowKey: "daily_research",
    });

    fireEvent.change(screen.getByLabelText("Search scheduled tasks"), {
      target: { value: "no-match" },
    });
    expect(useScheduledTasksMock).toHaveBeenLastCalledWith({
      limit: 50,
      packageKey: "market_research_package",
      workflowKey: "daily_research",
    });
    expect(
      screen.getByText("No scheduled tasks match this search or filters."),
    ).toBeVisible();
  });

  it("shows manifest-order workflow options and keeps stale workflow keys selectable", async () => {
    useScheduledTasksMock.mockReturnValue({
      data: {
        items: [
          scheduleFixture(),
          scheduleFixture({
            id: 45,
            latestFireId: null,
            latestRunId: null,
            latestStatus: null,
            name: "Stale workflow schedule",
            workflowKey: "retired_workflow",
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

    await chooseSelectOption(packageSelector(), "Market Research Package");

    const selector = workflowSelector();
    selector.focus();
    fireEvent.keyDown(selector, { key: "ArrowDown" });

    const options = await screen.findAllByRole("option");
    expect(options.map((option) => option.textContent?.trim())).toEqual([
      "All workflows",
      "Daily Research",
      "News Research",
      "Unknown workflow: retired_workflow",
    ]);

    fireEvent.click(
      await screen.findByRole("option", {
        name: "Unknown workflow: retired_workflow",
      }),
    );

    expect(useScheduledTasksMock).toHaveBeenLastCalledWith({
      limit: 50,
      packageKey: "market_research_package",
      workflowKey: "retired_workflow",
    });
  });

  it("sorts rows locally and filters real runtime succeeded status", () => {
    useScheduledTasksMock.mockReturnValue({
      data: {
        items: [
          scheduleFixture({
            id: 70,
            name: "Zulu schedule",
            nextFireAt: "2026-06-01T11:00:00Z",
            updatedAt: "2026-05-29T10:00:00Z",
          }),
          scheduleFixture({
            id: 71,
            latestStatus: "failed",
            name: "Alpha schedule",
            nextFireAt: "2026-06-01T12:00:00Z",
            updatedAt: "2026-05-31T10:00:00Z",
          }),
          scheduleFixture({
            id: 72,
            latestFireId: null,
            latestRunId: null,
            latestStatus: null,
            name: "Beta schedule",
            nextFireAt: null,
            updatedAt: "2026-05-28T10:00:00Z",
          }),
          scheduleFixture({
            id: 73,
            latestStatus: "succeeded",
            name: "Gamma schedule",
            nextFireAt: "2026-06-01T14:00:00Z",
            updatedAt: "2026-06-01T08:00:00Z",
          }),
        ],
        limit: 50,
        offset: 0,
        totalCount: 4,
      },
      error: null,
      isError: false,
      isPending: false,
    });

    renderPage();

    const zuluRow = screen.getByTestId("scheduled-task-row-70");
    const alphaRow = screen.getByTestId("scheduled-task-row-71");
    const betaRow = screen.getByTestId("scheduled-task-row-72");
    const gammaRow = screen.getByTestId("scheduled-task-row-73");

    expectRowBefore(zuluRow, alphaRow);
    expectRowBefore(alphaRow, gammaRow);
    expectRowBefore(gammaRow, betaRow);

    fireEvent.click(screen.getByRole("button", { name: "Sort scheduled tasks by Workflow" }));
    expect(screen.getByRole("columnheader", { name: /workflow/i })).toHaveAttribute(
      "aria-sort",
      "ascending",
    );
    expectRowBefore(alphaRow, betaRow);
    expectRowBefore(betaRow, gammaRow);
    expectRowBefore(gammaRow, zuluRow);

    fireEvent.click(screen.getByRole("button", { name: /Sort scheduled tasks by Latest activity/ }));
    expect(
      screen.getByRole("columnheader", { name: /latest activity/i }),
    ).toHaveAttribute("aria-sort", "descending");
    expectRowBefore(gammaRow, alphaRow);
    expectRowBefore(alphaRow, zuluRow);
    expectRowBefore(zuluRow, betaRow);

    expect(gammaRow).toHaveTextContent("Succeeded");
    fireEvent.click(screen.getByTestId("scheduled-tasks-filter-succeeded"));
    expect(screen.getByTestId("scheduled-task-row-73")).toHaveTextContent(
      "Gamma schedule",
    );
    expect(screen.queryByTestId("scheduled-task-row-70")).not.toBeInTheDocument();
    expect(screen.queryByTestId("scheduled-task-row-71")).not.toBeInTheDocument();
    expect(screen.queryByTestId("scheduled-task-row-72")).not.toBeInTheDocument();
    expect(useScheduledTasksMock).toHaveBeenLastCalledWith({
      limit: 50,
      packageKey: undefined,
      workflowKey: undefined,
    });
  });

  it("selects visible schedules and bulk deletes the filtered selection", async () => {
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

    const dailyRow = screen.getByTestId("scheduled-task-row-44");
    fireEvent.click(
      within(dailyRow).getByRole("checkbox", {
        name: "Select scheduled task Daily market brief",
      }),
    );

    expect(dailyRow).toHaveAttribute("data-state", "selected");
    expect(screen.getByText("1 of 2 scheduled tasks selected")).toBeVisible();

    fireEvent.change(screen.getByLabelText("Search scheduled tasks"), {
      target: { value: "allocation" },
    });
    expect(screen.queryByTestId("scheduled-task-row-44")).not.toBeInTheDocument();
    expect(screen.queryByTestId("scheduled-tasks-bulk-actions")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search scheduled tasks"), {
      target: { value: "" },
    });
    expect(screen.getByText("1 of 2 scheduled tasks selected")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.queryByText("1 of 2 scheduled tasks selected")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: "Select all shown scheduled tasks" }));
    expect(screen.getByText("2 of 2 scheduled tasks selected")).toBeVisible();

    fireEvent.change(screen.getByLabelText("Search scheduled tasks"), {
      target: { value: "allocation" },
    });
    expect(screen.getByText("1 of 1 scheduled tasks selected")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Delete selected" }));
    expect(deleteSchedulesMock).not.toHaveBeenCalled();

    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent("Delete selected scheduled tasks");
    expect(dialog).toHaveTextContent("Delete 1 selected scheduled task?");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete selected" }));

    await waitFor(() =>
      expect(deleteSchedulesMock).toHaveBeenCalledWith(
        [{ latestRunId: null, scheduleId: 55 }],
        expect.objectContaining({
          onError: expect.any(Function),
          onSuccess: expect.any(Function),
        }),
      ),
    );
    expect(toastSuccessMock).toHaveBeenCalledWith("1 scheduled task deleted");
  });

  it("runs, pauses, resumes, and deletes schedules from explicit controls", async () => {
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

    openActionMenu(dailyRow);
    fireEvent.click(screen.getByText("Pause"));
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

    openActionMenu(dailyRow);
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Delete scheduled task");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Delete scheduled task" }));
      await Promise.resolve();
    });
    expect(deleteScheduleMock).toHaveBeenCalledWith({
      latestRunId: 2104,
      scheduleId: 44,
    });
  });

  it("keeps navigation explicit while pending mutation actions stay disabled", async () => {
    useDeleteScheduledTasksMock.mockReturnValue({
      isPending: true,
      mutate: deleteSchedulesMock,
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

    const row = screen.getByTestId("scheduled-task-row-66");
    expect(
      within(row).getByRole("button", { name: "Run schedule Market brief pending action now" }),
    ).toBeDisabled();

    openActionMenu(row);
    expect(screen.getByText("Edit").closest("a")).toHaveAttribute(
      "href",
      "/scheduled-tasks/66",
    );
    expect(screen.getByText("Latest run").closest("a")).toHaveAttribute(
      "href",
      "/runs/2206",
    );
    expect(screen.getByText("Pause").closest("[data-disabled]")).not.toBeNull();
    expect(screen.getByText("Delete").closest("[data-disabled]")).not.toBeNull();
  });

  it("retains visible selection when bulk delete fails and surfaces row mutation failures", async () => {
    deleteSchedulesMock.mockImplementation(
      (_variables: unknown, options?: { onError?: (error: Error) => void }) =>
        options?.onError?.(new Error("Bulk delete rejected")),
    );
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

    const row = screen.getByTestId("scheduled-task-row-44");
    fireEvent.click(
      within(row).getByRole("checkbox", {
        name: "Select scheduled task Daily market brief",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete selected" }));
    fireEvent.click(
      within(screen.getByRole("alertdialog")).getByRole("button", {
        name: "Delete selected",
      }),
    );

    await waitFor(() =>
      expect(toastErrorMock).toHaveBeenCalledWith("Bulk delete rejected"),
    );
    expect(screen.getByText("1 of 1 scheduled tasks selected")).toBeVisible();

    fireEvent.click(
      within(row).getByRole("button", { name: "Run schedule Daily market brief now" }),
    );
    await waitFor(() =>
      expect(toastErrorMock).toHaveBeenCalledWith("Manual fire rejected"),
    );

    openActionMenu(row);
    fireEvent.click(screen.getByText("Pause"));
    await waitFor(() =>
      expect(toastErrorMock).toHaveBeenCalledWith("Status update rejected"),
    );

    openActionMenu(row);
    fireEvent.click(screen.getByText("Delete"));
    fireEvent.click(screen.getByRole("button", { name: "Delete scheduled task" }));
    await waitFor(() =>
      expect(toastErrorMock).toHaveBeenCalledWith("Delete rejected"),
    );
    expect(screen.getByTestId("scheduled-task-row-44")).toHaveTextContent(
      "Daily market brief",
    );
  });

  it("renders the mobile card layout with explicit actions and expansion", () => {
    setViewportWidth(480);
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

    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    const card = screen.getByTestId("scheduled-task-card-44");
    expect(card).toHaveTextContent("Daily market brief");
    expect(card).toHaveTextContent("Schedule");
    expect(card).toHaveTextContent("Next run");
    expect(card).toHaveTextContent("Latest activity");
    expect(
      within(card).getByRole("button", { name: "Run schedule Daily market brief now" }),
    ).toBeVisible();

    fireEvent.click(
      within(card).getByRole("button", {
        name: "Show details for Daily market brief",
      }),
    );
    expect(card).toHaveTextContent("Package ID");
  });
});
