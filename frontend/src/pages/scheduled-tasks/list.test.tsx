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

function openMoreActions(container: HTMLElement, scheduleName: string) {
  const trigger = within(container).getByRole("button", {
    name: `More actions for ${scheduleName}`,
  });
  trigger.focus();
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
}

function closeOpenMenu() {
  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
}

function getActionsCell(row: HTMLElement) {
  const cells = within(row).getAllByRole("cell");
  expect(cells).toHaveLength(6);
  return cells[cells.length - 1]!;
}

function expectRowBefore(first: HTMLElement, second: HTMLElement) {
  expect(
    first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
}

function expectedViewerLocalDateTime(isoString: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(new Date(isoString));
}

function expectedDateTimeInTimeZone(isoString: string, timeZone: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone,
    timeZoneName: "short",
  }).format(new Date(isoString));
}

function expectedDateTimeWithExplicitTimeZone(
  isoString: string,
  timeZone: string,
): string {
  return `${new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone,
  }).format(new Date(isoString))} ${timeZone}`;
}

describe("ScheduledTasksListPage", () => {
  beforeEach(() => {
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
    expect(
      document.querySelector("[data-slot='skeleton']")?.closest("[data-slot='card']"),
    ).not.toBeInTheDocument();

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
    expect(screen.getByTestId("scheduled-tasks-error-state")).toHaveTextContent(
      "Schedules API unavailable",
    );

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
    expect(screen.getByTestId("scheduled-tasks-filtered-empty-state")).toHaveTextContent(
      "No scheduled tasks match this search or filters.",
    );
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
    expect(screen.getByTestId("scheduled-tasks-empty-state")).toHaveTextContent(
      "No scheduled tasks yet.",
    );
  });

  it("renders redesigned schedule rows with sortable headers, grouped expansion, and inline actions", async () => {
    useScheduledTasksMock.mockReturnValue({
      data: {
        items: [
          scheduleFixture({
            endsAt: "2026-06-30T20:00:00Z",
            startsAt: "2026-06-01T12:00:00Z",
          }),
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

    const expectedNextRun = expectedDateTimeInTimeZone(
      "2026-06-01T13:00:00Z",
      "America/New_York",
    );
    const expectedStartsAt = expectedDateTimeInTimeZone(
      "2026-06-01T12:00:00Z",
      "America/New_York",
    );
    const expectedEndsAt = expectedDateTimeInTimeZone(
      "2026-06-30T20:00:00Z",
      "America/New_York",
    );
    const expectedUpdatedAt = expectedViewerLocalDateTime("2026-05-30T10:00:00Z");
    const expectedCreatedAt = expectedViewerLocalDateTime("2026-05-01T10:00:00Z");

    expect(screen.getByRole("heading", { name: "Scheduled Tasks" })).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Create scheduled task" }),
    ).toHaveAttribute("href", "/scheduled-tasks/new");
    expect(screen.getByLabelText("Search scheduled tasks")).toBeVisible();
    expect(screen.queryByLabelText("Cards view")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Table view")).not.toBeInTheDocument();
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
    const actionsHeader = within(table).getByRole("columnheader", {
      name: /^Actions$/i,
    });
    expect(actionsHeader).not.toHaveClass("sticky");
    expect(actionsHeader).not.toHaveClass("right-0");
    expect(
      screen.getByRole("button", { name: "Sort scheduled tasks by Workflow" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Sort scheduled tasks by Next run (ascending)" }),
    ).toBeVisible();

    const dailyRow = screen.getByTestId("scheduled-task-row-44");
    expect(dailyRow).toHaveTextContent("Daily market brief");
    expect(within(dailyRow).getByTestId("scheduled-task-row-next-run-44")).toHaveTextContent(
      expectedNextRun,
    );
    expect(dailyRow).toHaveTextContent("Enabled");
    expect(within(dailyRow).getByTestId("scheduled-task-status-enabled")).toHaveAttribute(
      "data-tone",
      "success",
    );
    expect(dailyRow).toHaveTextContent("Weekly Mon, Tue, Wed, Thu, Fri at 09:00");
    expect(within(dailyRow).queryByText("Overlap: Skip")).not.toBeInTheDocument();
    expect(
      within(dailyRow).queryByText("Misfire: Catch Up One"),
    ).not.toBeInTheDocument();
    expect(dailyRow).toHaveTextContent("Fire #801 · Run #2104");
    const dailyActionsCell = getActionsCell(dailyRow);
    expect(dailyActionsCell).not.toHaveClass("sticky");
    expect(dailyActionsCell).not.toHaveClass("right-0");
    expect(
      within(dailyActionsCell).getByRole("button", { name: "Show details" }),
    ).toBeVisible();
    expect(
      within(dailyActionsCell).getByRole("button", {
        name: "Run schedule Daily market brief now",
      }),
    ).toBeVisible();
    expect(
      within(dailyActionsCell).getByRole("button", {
        name: "Pause schedule Daily market brief",
      }),
    ).toBeVisible();
    expect(
      within(dailyActionsCell).getByRole("button", {
        name: "More actions for Daily market brief",
      }),
    ).toBeVisible();
    expect(
      within(dailyActionsCell).queryByRole("button", {
        name: "Resume schedule Daily market brief",
      }),
    ).not.toBeInTheDocument();
    expect(
      within(dailyRow).queryByRole("link", { name: "Edit schedule Daily market brief" }),
    ).not.toBeInTheDocument();
    expect(
      within(dailyRow).queryByRole("link", {
        name: "Duplicate schedule Daily market brief",
      }),
    ).not.toBeInTheDocument();
    expect(
      within(dailyRow).queryByRole("link", {
        name: "Open latest run for Daily market brief",
      }),
    ).not.toBeInTheDocument();
    expect(
      within(dailyRow).queryByRole("button", { name: "Delete schedule Daily market brief" }),
    ).not.toBeInTheDocument();

    openMoreActions(dailyRow, "Daily market brief");
    expect(screen.getByText("Edit").closest("a")).toHaveAttribute(
      "href",
      "/scheduled-tasks/44",
    );
    expect(screen.getByText("Duplicate").closest("a")).toHaveAttribute(
      "href",
      "/scheduled-tasks/new?duplicateFrom=44",
    );
    expect(screen.getByText("Latest run").closest("a")).toHaveAttribute(
      "href",
      "/runs/2104",
    );
    expect(screen.getByRole("menuitem", { name: "Delete" })).toHaveAttribute(
      "data-variant",
      "destructive",
    );
    closeOpenMenu();

    const detailsToggle = within(dailyRow).getByRole("button", {
      name: "Show details",
    });
    expect(detailsToggle).toHaveAttribute("aria-controls", "scheduled-task-row-details-44");
    expect(detailsToggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(detailsToggle);
    expect(detailsToggle).toHaveAttribute("aria-expanded", "true");
    expect(
      within(dailyRow).getByRole("button", { name: "Hide details" }),
    ).toBeVisible();
    const details = screen.getByTestId("scheduled-task-row-details-44");
    expect(details).toHaveTextContent("Workflow package");
    expect(details).toHaveTextContent("Recurrence and policies");
    expect(details).toHaveTextContent("Overlap policy");
    expect(details).toHaveTextContent("Skip");
    expect(details).toHaveTextContent("Misfire policy");
    expect(details).toHaveTextContent("Catch Up One");
    expect(details).toHaveTextContent("America/New_York");
    expect(details).toHaveTextContent("market_research_package");
    expect(details).toHaveTextContent("daily_research");
    expect(details).toHaveTextContent(expectedStartsAt);
    expect(details).toHaveTextContent(expectedEndsAt);
    expect(details).toHaveTextContent(expectedNextRun);
    expect(details).toHaveTextContent(expectedUpdatedAt);
    expect(details).toHaveTextContent(expectedCreatedAt);
    expect(details).toHaveTextContent("Misfire grace");
    expect(details).toHaveTextContent("86400 seconds");

    const pausedRow = screen.getByTestId("scheduled-task-row-55");
    expect(pausedRow).toHaveTextContent("Paused allocation check");
    expect(within(pausedRow).getByTestId("scheduled-task-status-paused")).toHaveAttribute(
      "data-tone",
      "muted",
    );
    expect(pausedRow).toHaveTextContent("No upcoming run");
    expect(pausedRow).toHaveTextContent("Every 4 hours");
    expect(pausedRow).toHaveTextContent("No latest status");
    const pausedActionsCell = getActionsCell(pausedRow);
    expect(
      within(pausedActionsCell).getByRole("button", {
        name: "Resume schedule Paused allocation check",
      }),
    ).toBeVisible();
    expect(
      within(pausedActionsCell).getByRole("button", {
        name: "More actions for Paused allocation check",
      }),
    ).toBeVisible();
    expect(
      within(pausedActionsCell).queryByRole("button", {
        name: "Pause schedule Paused allocation check",
      }),
    ).not.toBeInTheDocument();

    openMoreActions(pausedRow, "Paused allocation check");
    expect(screen.getByRole("menuitem", { name: "Latest run" })).toHaveAttribute(
      "data-disabled",
    );
    closeOpenMenu();
  });

  it("toggles absolute scheduled-task times between schedule and browser timezones across list and detail views", () => {
    const browserTimeZone = "Europe/Helsinki";
    const resolvedOptions = new Intl.DateTimeFormat("en-US").resolvedOptions();
    const resolvedOptionsSpy = vi
      .spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions")
      .mockReturnValue({ ...resolvedOptions, timeZone: browserTimeZone });

    try {
      useScheduledTasksMock.mockReturnValue({
        data: {
          items: [
            scheduleFixture({
              endsAt: "2026-06-30T20:00:00Z",
              startsAt: "2026-06-01T12:00:00Z",
            }),
            scheduleFixture({
              id: 45,
              latestFireId: 802,
              latestRunId: 2105,
              name: "Midday rebalance check",
              nextFireAt: "2026-06-01T18:00:00Z",
              workflowKey: "news_research",
            }),
            scheduleFixture({
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
          totalCount: 3,
        },
        error: null,
        isError: false,
        isPending: false,
      });

      renderPage();

      const scheduleNextRunLabel = expectedDateTimeInTimeZone(
        "2026-06-01T13:00:00Z",
        "America/New_York",
      );
      const browserNextRunLabel = expectedDateTimeWithExplicitTimeZone(
        "2026-06-01T13:00:00Z",
        browserTimeZone,
      );
      const scheduleStartsAtLabel = expectedDateTimeInTimeZone(
        "2026-06-01T12:00:00Z",
        "America/New_York",
      );
      const browserStartsAtLabel = expectedDateTimeWithExplicitTimeZone(
        "2026-06-01T12:00:00Z",
        browserTimeZone,
      );
      const scheduleEndsAtLabel = expectedDateTimeInTimeZone(
        "2026-06-30T20:00:00Z",
        "America/New_York",
      );
      const browserEndsAtLabel = expectedDateTimeWithExplicitTimeZone(
        "2026-06-30T20:00:00Z",
        browserTimeZone,
      );
      const secondScheduleTimeZoneLabel = expectedDateTimeInTimeZone(
        "2026-06-01T18:00:00Z",
        "America/New_York",
      );

      const firstRow = screen.getByTestId("scheduled-task-row-44");
      const pausedRow = screen.getByTestId("scheduled-task-row-55");
      const firstRowNextRun = within(firstRow).getByTestId(
        "scheduled-task-row-next-run-44",
      );
      const secondRowNextRun = within(
        screen.getByTestId("scheduled-task-row-45"),
      ).getByTestId("scheduled-task-row-next-run-45");
      const noUpcomingRowNextRun = within(pausedRow).getByTestId(
        "scheduled-task-row-next-run-55",
      );

      fireEvent.click(
        within(firstRowNextRun).getByRole("button", {
          name: scheduleNextRunLabel,
        }),
      );
      const firstRowBrowserNextRunButton = within(firstRowNextRun).getByRole("button", {
        name: browserNextRunLabel,
      });
      expect(firstRowBrowserNextRunButton).toBeVisible();
      expect(firstRowBrowserNextRunButton).toHaveClass("max-w-full");
      expect(firstRowBrowserNextRunButton).toHaveClass("break-words");
      expect(firstRowBrowserNextRunButton.className).toContain("[font-size:inherit]");
      fireEvent.click(firstRowBrowserNextRunButton);
      expect(
        within(firstRowNextRun).getByRole("button", {
          name: scheduleNextRunLabel,
        }),
      ).toBeVisible();

      expect(
        within(secondRowNextRun).getByRole("button", {
          name: secondScheduleTimeZoneLabel,
        }),
      ).toBeVisible();
      expect(noUpcomingRowNextRun).toHaveTextContent("No upcoming run");
      expect(within(noUpcomingRowNextRun).queryByRole("button")).not.toBeInTheDocument();

      const rowDetailsToggle = within(firstRow).getByRole("button", {
        name: "Show details",
      });
      fireEvent.click(rowDetailsToggle);
      const rowDetails = screen.getByTestId("scheduled-task-row-details-44");
      expect(rowDetails).toHaveTextContent("America/New_York");

      fireEvent.click(
        within(rowDetails).getByRole("button", {
          name: scheduleStartsAtLabel,
        }),
      );
      expect(
        within(rowDetails).getByRole("button", {
          name: browserStartsAtLabel,
        }),
      ).toBeVisible();
      fireEvent.click(
        within(rowDetails).getByRole("button", {
          name: browserStartsAtLabel,
        }),
      );
      expect(
        within(rowDetails).getByRole("button", {
          name: scheduleStartsAtLabel,
        }),
      ).toBeVisible();

      fireEvent.click(
        within(rowDetails).getByRole("button", {
          name: scheduleEndsAtLabel,
        }),
      );
      expect(
        within(rowDetails).getByRole("button", {
          name: browserEndsAtLabel,
        }),
      ).toBeVisible();
      fireEvent.click(
        within(rowDetails).getByRole("button", {
          name: browserEndsAtLabel,
        }),
      );
      expect(
        within(rowDetails).getByRole("button", {
          name: scheduleEndsAtLabel,
        }),
      ).toBeVisible();

      fireEvent.click(
        within(rowDetails).getByRole("button", {
          name: scheduleNextRunLabel,
        }),
      );
      expect(
        within(rowDetails).getByRole("button", {
          name: browserNextRunLabel,
        }),
      ).toBeVisible();
      fireEvent.click(
        within(rowDetails).getByRole("button", {
          name: browserNextRunLabel,
        }),
      );
      expect(
        within(rowDetails).getByRole("button", {
          name: scheduleNextRunLabel,
        }),
      ).toBeVisible();

      fireEvent.click(
        within(pausedRow).getByRole("button", {
          name: "Show details",
        }),
      );
      const pausedRowDetails = screen.getByTestId("scheduled-task-row-details-55");
      expect(pausedRowDetails).toHaveTextContent("Not set");
      expect(pausedRowDetails).toHaveTextContent("No upcoming run");
      expect(within(pausedRowDetails).queryByRole("button", { name: "Not set" })).not.toBeInTheDocument();
      expect(
        within(pausedRowDetails).queryByRole("button", {
          name: "No upcoming run",
        }),
      ).not.toBeInTheDocument();

      expect(screen.queryByLabelText("Cards view")).not.toBeInTheDocument();
      expect(screen.queryByLabelText("Table view")).not.toBeInTheDocument();
    } finally {
      resolvedOptionsSpy.mockRestore();
    }
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

  it("keeps scheduled-task selection clearable in table-only view", () => {
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

    fireEvent.click(
      within(screen.getByTestId("scheduled-task-row-44")).getByRole("checkbox", {
        name: "Select scheduled task Daily market brief",
      }),
    );
    expect(screen.getByText("1 of 2 scheduled tasks selected")).toBeVisible();
    expect(screen.getByTestId("scheduled-tasks-bulk-actions")).toBeVisible();

    expect(screen.queryByLabelText("Cards view")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Table view")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(
      within(screen.getByTestId("scheduled-task-row-44")).getByRole("checkbox", {
        name: "Select scheduled task Daily market brief",
      }),
    ).toHaveAttribute("aria-checked", "false");
    expect(
      screen.queryByRole("button", { name: "Delete selected" }),
    ).not.toBeInTheDocument();
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

    openMoreActions(dailyRow, "Daily market brief");
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

    expect(
      within(row).getByRole("button", {
        name: "Pause schedule Market brief pending action",
      }),
    ).toBeDisabled();
    expect(
      within(row).getByRole("button", {
        name: "More actions for Market brief pending action",
      }),
    ).toBeVisible();

    openMoreActions(row, "Market brief pending action");
    expect(screen.getByText("Edit").closest("a")).toHaveAttribute(
      "href",
      "/scheduled-tasks/66",
    );
    expect(screen.getByText("Latest run").closest("a")).toHaveAttribute(
      "href",
      "/runs/2206",
    );
    expect(screen.getByRole("menuitem", { name: "Delete" })).toHaveAttribute(
      "data-disabled",
    );
    closeOpenMenu();
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

    fireEvent.click(
      within(row).getByRole("button", {
        name: "Pause schedule Daily market brief",
      }),
    );
    await waitFor(() =>
      expect(toastErrorMock).toHaveBeenCalledWith("Status update rejected"),
    );

    openMoreActions(row, "Daily market brief");
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete scheduled task" }));
    await waitFor(() =>
      expect(toastErrorMock).toHaveBeenCalledWith("Delete rejected"),
    );
    expect(screen.getByTestId("scheduled-task-row-44")).toHaveTextContent(
      "Daily market brief",
    );
  });

  it("keeps scheduled tasks in the table-only inventory", () => {
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

    expect(screen.queryByLabelText("Cards view")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Table view")).not.toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(table).toBeInTheDocument();
    const row = screen.getByTestId("scheduled-task-row-44");
    expect(row).toHaveTextContent("Daily market brief");
    expect(
      within(row).getByRole("checkbox", {
        name: "Select scheduled task Daily market brief",
      }),
    ).toBeVisible();
    expect(
      within(row).getByRole("button", { name: "Run schedule Daily market brief now" }),
    ).toBeVisible();

    fireEvent.click(
      within(row).getByRole("button", {
        name: "Show details",
      }),
    );
    expect(screen.getByTestId("scheduled-task-row-details-44")).toHaveTextContent(
      "Package ID",
    );
  });
});
