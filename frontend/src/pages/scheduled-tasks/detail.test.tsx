import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ComponentProps, PropsWithChildren } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkflowPackageManifestRead } from "@/lib/types/workflow-package";
import type {
  ScheduleFireListRead,
  SchedulePreviewRead,
  ScheduleRead,
} from "@/lib/types/schedule";

import { ScheduledTaskDetailPage } from "./detail";

const {
  deleteScheduleMock,
  navigateMock,
  previewScheduledInputsMock,
  runNowMock,
  updateScheduleMock,
  useDeleteScheduledTaskMock,
  usePreviewUnsavedScheduledTaskMock,
  useRunScheduledTaskNowMock,
  useScheduledTaskFiresMock,
  useScheduledTaskMock,
  useUpdateScheduledTaskMock,
  useWorkflowPackageManifestMock,
} = vi.hoisted(() => ({
  deleteScheduleMock: vi.fn(),
  navigateMock: vi.fn(),
  previewScheduledInputsMock: vi.fn(),
  runNowMock: vi.fn(),
  updateScheduleMock: vi.fn(),
  useDeleteScheduledTaskMock: vi.fn(),
  usePreviewUnsavedScheduledTaskMock: vi.fn(),
  useRunScheduledTaskNowMock: vi.fn(),
  useScheduledTaskFiresMock: vi.fn(),
  useScheduledTaskMock: vi.fn(),
  useUpdateScheduledTaskMock: vi.fn(),
  useWorkflowPackageManifestMock: vi.fn(),
}));

vi.mock("react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router")>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("@/hooks/use-scheduled-tasks", () => ({
  useDeleteScheduledTask: () => useDeleteScheduledTaskMock(),
  usePreviewUnsavedScheduledTask: () => usePreviewUnsavedScheduledTaskMock(),
  useRunScheduledTaskNow: () => useRunScheduledTaskNowMock(),
  useScheduledTask: (...args: unknown[]) => useScheduledTaskMock(...args),
  useScheduledTaskFires: (...args: unknown[]) => useScheduledTaskFiresMock(...args),
  useUpdateScheduledTask: () => useUpdateScheduledTaskMock(),
}));

vi.mock("@/hooks/use-workflow-packages", () => ({
  useWorkflowPackageManifest: (...args: unknown[]) => useWorkflowPackageManifestMock(...args),
}));

vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: PropsWithChildren) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: PropsWithChildren) => <div>{children}</div>,
  DropdownMenuGroup: ({ children }: PropsWithChildren) => <div>{children}</div>,
  DropdownMenuItem: ({
    children,
    onSelect,
    ...props
  }: PropsWithChildren<{ onSelect?: () => void } & Omit<ComponentProps<"button">, "onSelect">>) => (
    <button {...props} type="button" onClick={() => onSelect?.()}>
      {children}
    </button>
  ),
  DropdownMenuSeparator: () => <div />,
  DropdownMenuTrigger: ({ children }: PropsWithChildren) => <div>{children}</div>,
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
    timezone: "UTC",
    updatedAt: "2026-05-30T10:00:00Z",
    workflowKey: "daily_research",
    ...overrides,
  };
}

function manifestFixture(workflows: Array<{ key: string; name: string }>): WorkflowPackageManifestRead {
  return {
    compiledHash: "compiled-hash-123",
    manifestHash: "manifest-hash-123",
    manifestSource: "apiVersion: signaldeck.workflowPackage/v1",
    packageDefinition: {
      metadata: {
        key: "market_research_package",
        name: "Market Research Package",
      },
      spec: {
        workflows: workflows.map(({ key, name }) => ({
          description: `${name} description`,
          inputSchema: {
            properties: {
              asOfDate: { title: "As of date", type: "string" },
              analysisTag: { title: "Analysis tag", type: "string" },
            },
            required: ["asOfDate", "analysisTag"],
            type: "object",
          },
          key,
          label: name,
          name,
        })),
      },
    },
    packageId: 12,
    packageKey: "market_research_package",
  };
}

function previewRead(): SchedulePreviewRead {
  return {
    ready: true,
    renderedParameters: { asOfDate: "", analysisTag: "" },
    scheduleId: null,
    scheduledFor: "2026-06-01T13:00:00Z",
    templateContext: {},
    validationErrors: [],
  };
}

function firesFixture(): ScheduleFireListRead {
  return { items: [], limit: 20, offset: 0, totalCount: 0 };
}

function renderDetailPage(initialEntry = "/scheduled-tasks/44") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/scheduled-tasks/:scheduleId" element={<ScheduledTaskDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ScheduledTaskDetailPage", () => {
  beforeEach(() => {
    deleteScheduleMock.mockReset();
    navigateMock.mockReset();
    previewScheduledInputsMock.mockReset();
    runNowMock.mockReset();
    updateScheduleMock.mockReset();
    useScheduledTaskMock.mockReset();
    useScheduledTaskFiresMock.mockReset();
    useWorkflowPackageManifestMock.mockReset();

    previewScheduledInputsMock.mockResolvedValue(previewRead());
    useDeleteScheduledTaskMock.mockReturnValue({ isPending: false, mutateAsync: deleteScheduleMock });
    usePreviewUnsavedScheduledTaskMock.mockReturnValue({ isPending: false, mutateAsync: previewScheduledInputsMock });
    useRunScheduledTaskNowMock.mockReturnValue({ isPending: false, mutateAsync: runNowMock });
    useUpdateScheduledTaskMock.mockReturnValue({ isPending: false, mutateAsync: updateScheduleMock });
    useScheduledTaskMock.mockReturnValue({
      data: scheduleFixture(),
      error: null,
      isError: false,
      isPending: false,
    });
    useScheduledTaskFiresMock.mockReturnValue({
      data: firesFixture(),
      error: null,
      isError: false,
      isPending: false,
    });
    useWorkflowPackageManifestMock.mockReturnValue({
      data: manifestFixture([{ key: "daily_research", name: "Daily research" }]),
      error: null,
      isError: false,
      isPending: false,
    });
  });

  it("seeds scheduled inputs from the manifest workflow schema without the removed saved inputs helper", async () => {
    renderDetailPage();

    fireEvent.click(screen.getByRole("tab", { name: "Inputs" }));
    const textarea = await screen.findByLabelText("Scheduled input template JSON");
    expect(textarea).toHaveValue(
      JSON.stringify({ analysisTag: "", asOfDate: "" }, null, 2),
    );
    expect(screen.queryByTestId("runtime-input-saved-inputs-helper")).not.toBeInTheDocument();
    expect(screen.queryByText(/saved runtime input preset/i)).not.toBeInTheDocument();
  });

  it("uses the manifest-derived workflow key and template when previewing inputs", async () => {
    renderDetailPage();

    fireEvent.click(screen.getByRole("tab", { name: "Inputs" }));
    fireEvent.click(await screen.findByRole("button", { name: "Preview next run" }));

    await waitFor(() =>
      expect(previewScheduledInputsMock).toHaveBeenCalledWith({
        inputTemplate: { asOfDate: "", analysisTag: "" },
        packageId: 12,
        recurrence: scheduleFixture().recurrence,
        scheduledFor: "2026-06-01T13:00:00Z",
        templateVars: {},
        timezone: "UTC",
        workflowKey: "daily_research",
      }),
    );
  });

  it("blocks invalid scheduled input JSON and unsupported placeholders before preview or save", async () => {
    renderDetailPage();

    fireEvent.click(screen.getByRole("tab", { name: "Inputs" }));
    const textarea = await screen.findByLabelText("Scheduled input template JSON");
    fireEvent.change(textarea, { target: { value: "[]" } });

    expect(screen.getByTestId("scheduled-input-json-validation-feedback")).toHaveTextContent(
      "Scheduled input template JSON must be a valid object.",
    );
    expect(screen.getByRole("button", { name: "Preview next run" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save inputs" })).toBeDisabled();
    expect(previewScheduledInputsMock).not.toHaveBeenCalled();

    fireEvent.change(textarea, { target: { value: '{"ticker":"{{inputs.ticker}}"}' } });

    expect(screen.getByTestId("scheduled-input-json-validation-feedback")).toHaveTextContent(
      "Unsupported placeholder",
    );
    expect(screen.getByTestId("scheduled-input-json-validation-feedback")).toHaveTextContent(
      "inputs.ticker",
    );
    expect(screen.getByRole("button", { name: "Preview next run" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save inputs" })).toBeDisabled();
    expect(updateScheduleMock).not.toHaveBeenCalled();
  });

  it("saves scheduled inputs only after a ready preview accepts the draft", async () => {
    renderDetailPage();

    fireEvent.click(screen.getByRole("tab", { name: "Inputs" }));
    fireEvent.change(await screen.findByLabelText("Scheduled input template JSON"), {
      target: { value: '{"asOfDate":"{{fire.scheduledLocalDate}}"}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save inputs" }));

    await waitFor(() =>
      expect(previewScheduledInputsMock).toHaveBeenCalledWith({
        inputTemplate: { asOfDate: "{{fire.scheduledLocalDate}}" },
        packageId: 12,
        recurrence: scheduleFixture().recurrence,
        scheduledFor: "2026-06-01T13:00:00Z",
        templateVars: {},
        timezone: "UTC",
        workflowKey: "daily_research",
      }),
    );
    await waitFor(() =>
      expect(updateScheduleMock).toHaveBeenCalledWith({
        payload: {
          inputTemplate: { asOfDate: "{{fire.scheduledLocalDate}}" },
          templateVars: {},
        },
        scheduleId: 44,
      }),
    );
  });

  it("does not save scheduled inputs when preview validation rejects the draft", async () => {
    previewScheduledInputsMock.mockResolvedValueOnce({
      ...previewRead(),
      ready: false,
      validationErrors: [{ field: "parameters.extra", issue: "Unknown field" }],
    });
    renderDetailPage();

    fireEvent.click(screen.getByRole("tab", { name: "Inputs" }));
    fireEvent.change(await screen.findByLabelText("Scheduled input template JSON"), {
      target: { value: '{"extra":"{{fire.scheduledLocalDate}}"}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save inputs" }));

    const feedback = await screen.findByTestId("scheduled-input-preview-validation-feedback");
    expect(feedback).toHaveTextContent("parameters.extra");
    expect(feedback).toHaveTextContent("Unknown field");
    expect(updateScheduleMock).not.toHaveBeenCalled();
  });

  it("surfaces runtime inputs as unavailable when the schedule workflow is missing from the manifest", async () => {
    useWorkflowPackageManifestMock.mockReturnValue({
      data: manifestFixture([{ key: "other_workflow", name: "Other workflow" }]),
      error: null,
      isError: false,
      isPending: false,
    });

    renderDetailPage();
    fireEvent.click(screen.getByRole("tab", { name: "Inputs" }));

    expect(await screen.findByTestId("scheduled-inputs-unavailable")).toHaveTextContent(
      "Runtime inputs are unavailable because this schedule references a workflow that is no longer in the package manifest.",
    );
  });
});
