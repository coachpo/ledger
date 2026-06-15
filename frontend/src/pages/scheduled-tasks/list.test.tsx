import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

type ScheduleFixtureOverrides = Partial<ScheduleRead>;

function scheduleFixture(overrides: ScheduleFixtureOverrides = {}): ScheduleRead {
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

function shellRegions() {
  return Array.from(
    screen
      .getByTestId("scheduled-tasks-list-page")
      .querySelectorAll("[data-inventory-shell-region]"),
  ).map((element) => element.getAttribute("data-inventory-shell-region"));
}

function expectScheduledListContentAbsent() {
  const page = screen.getByTestId("scheduled-tasks-list-page");

  expect(
    page.querySelector('[data-inventory-shell-region="content"]'),
  ).not.toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(screen.queryByTestId(/scheduled-task-row-/)).not.toBeInTheDocument();
  expect(screen.queryByTestId("scheduled-tasks-loading-state")).not.toBeInTheDocument();
  expect(screen.queryByTestId("scheduled-tasks-error-state")).not.toBeInTheDocument();
  expect(screen.queryByTestId("scheduled-tasks-empty-state")).not.toBeInTheDocument();
  expect(
    screen.queryByTestId("scheduled-tasks-filtered-empty-state"),
  ).not.toBeInTheDocument();
  expect(screen.queryByTestId("scheduled-tasks-bulk-actions")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /run schedule/i }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /pause schedule/i }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /more actions for/i }),
  ).not.toBeInTheDocument();
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

  it("renders context and toolbar while omitting the scheduled-task content region", () => {
    useScheduledTasksMock.mockReturnValue({
      data: { items: [scheduleFixture()], limit: 50, offset: 0, totalCount: 1 },
      error: null,
      isError: false,
      isPending: false,
    });

    renderPage();

    expect(shellRegions()).toEqual(["context", "toolbar"]);
    expect(screen.getByRole("heading", { name: "Scheduled Tasks" })).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Create scheduled task" }),
    ).toHaveAttribute("href", "/scheduled-tasks/new");
    expect(packageSelector()).toHaveTextContent("All packages");
    expect(workflowSelector()).toBeDisabled();
    expect(
      screen.getByText("Choose a package first to filter by workflow."),
    ).toBeVisible();
    expect(screen.getByText("1 of 1 scheduled tasks shown")).toBeVisible();
    expect(screen.queryByLabelText("Search scheduled tasks")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Cards view")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Table view")).not.toBeInTheDocument();
    expectScheduledListContentAbsent();
  });

  it("keeps content state panels absent for loading, error, and empty list states", () => {
    useScheduledTasksMock.mockReturnValue({
      data: undefined,
      error: null,
      isError: false,
      isPending: true,
    });
    const { rerender } = renderPage();

    expect(shellRegions()).toEqual(["context", "toolbar"]);
    expect(screen.getByText("0 of 0 scheduled tasks shown")).toBeVisible();
    expectScheduledListContentAbsent();

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
    expect(screen.queryByText("Failed to load scheduled tasks")).not.toBeInTheDocument();
    expect(screen.queryByText("Schedules API unavailable")).not.toBeInTheDocument();
    expectScheduledListContentAbsent();

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
    expect(screen.queryByText(/No scheduled tasks yet/i)).not.toBeInTheDocument();
    expectScheduledListContentAbsent();
  });

  it("keeps package and workflow hook params scoped to package/workflow filters", async () => {
    useScheduledTasksMock.mockReturnValue({
      data: { items: [scheduleFixture()], limit: 50, offset: 0, totalCount: 1 },
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

    await chooseSelectOption(packageSelector(), "Market Research Package");
    expect(useScheduledTasksMock).toHaveBeenLastCalledWith({
      limit: 50,
      packageKey: "market_research_package",
      workflowKey: undefined,
    });
    expect(workflowSelector()).not.toBeDisabled();
    expect(shellRegions()).toEqual(["context", "toolbar", "filters"]);
    expect(screen.getByTestId("scheduled-tasks-active-filters")).toHaveTextContent(
      "Market Research Package",
    );
    expectScheduledListContentAbsent();

    await chooseSelectOption(workflowSelector(), "Daily Research");
    expect(useScheduledTasksMock).toHaveBeenLastCalledWith({
      limit: 50,
      packageKey: "market_research_package",
      workflowKey: "daily_research",
    });
    expect(screen.getByTestId("scheduled-tasks-active-filters")).toHaveTextContent(
      "Daily Research",
    );
    expectScheduledListContentAbsent();

    fireEvent.click(
      within(screen.getByTestId("scheduled-tasks-active-filters")).getByRole(
        "button",
        { name: "Clear filters" },
      ),
    );

    expect(useScheduledTasksMock).toHaveBeenLastCalledWith({
      limit: 50,
      packageKey: undefined,
      workflowKey: undefined,
    });
    expect(shellRegions()).toEqual(["context", "toolbar"]);
    expect(
      screen.queryByTestId("scheduled-tasks-active-filters"),
    ).not.toBeInTheDocument();
    expectScheduledListContentAbsent();
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
    expect(screen.getByTestId("scheduled-tasks-active-filters")).toHaveTextContent(
      "Unknown workflow: retired_workflow",
    );
    expectScheduledListContentAbsent();
  });
});
