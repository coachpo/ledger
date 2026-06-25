import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SchedulePreviewRead } from "@/lib/types/schedule";
import type {
  WorkflowPackageListRead,
  WorkflowPackageManifestRead,
  WorkflowPackageRead,
} from "@/lib/types/workflow-package";

import { ScheduledTaskEditorPage } from "./editor";

vi.setConfig({ testTimeout: 15_000 });

const {
  createScheduleMock,
  navigateMock,
  previewScheduleMock,
  toastErrorMock,
  toastSuccessMock,
  useCreateScheduledTaskMock,
  usePreviewUnsavedScheduledTaskMock,
  useWorkflowPackageManifestMock,
  useWorkflowPackagesMock,
} = vi.hoisted(() => ({
  createScheduleMock: vi.fn(),
  navigateMock: vi.fn(),
  previewScheduleMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  useCreateScheduledTaskMock: vi.fn(),
  usePreviewUnsavedScheduledTaskMock: vi.fn(),
  useWorkflowPackageManifestMock: vi.fn(),
  useWorkflowPackagesMock: vi.fn(),
}));

vi.mock("react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router")>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}));

vi.mock("@/hooks/use-scheduled-tasks", () => ({
  useCreateScheduledTask: () => useCreateScheduledTaskMock(),
  usePreviewUnsavedScheduledTask: () => usePreviewUnsavedScheduledTaskMock(),
}));

vi.mock("@/hooks/use-workflow-packages", () => ({
  useWorkflowPackageManifest: (...args: unknown[]) => useWorkflowPackageManifestMock(...args),
  useWorkflowPackages: () => useWorkflowPackagesMock(),
}));

const originalResolvedOptions = Intl.DateTimeFormat.prototype.resolvedOptions;
const resolvedOptionsMock = vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions");

function mockBrowserTimeZone(timeZone: string | null) {
  resolvedOptionsMock.mockImplementation(function resolvedOptions(this: Intl.DateTimeFormat) {
    return { ...originalResolvedOptions.call(this), timeZone: timeZone ?? "" };
  });
}

afterEach(() => {
  vi.useRealTimers();
});

function packageRead(overrides: Partial<WorkflowPackageRead>): WorkflowPackageRead {
  return {
    compiledHash: "compiled-hash-123",
    createdAt: "2026-05-01T10:00:00Z",
    description: "Workflow package",
    id: 42,
    key: "market_review_package",
    manifestHash: "manifest-hash-123",
    name: "Market Review Package",
    updatedAt: "2026-05-05T10:00:00Z",
    ...overrides,
  };
}

function manifestRead(
  packageId: number,
  packageKey: string,
  workflows: Array<{ key: string; name?: string; label?: string; description?: string }>,
): WorkflowPackageManifestRead {
  return {
    compiledHash: `compiled-hash-${packageId}`,
    manifestHash: `manifest-hash-${packageId}`,
    manifestSource: "apiVersion: signaldeck.workflowPackage/v1",
    packageDefinition: { spec: { workflows } },
    packageId,
    packageKey,
  };
}

const packagesRead: WorkflowPackageListRead = {
  items: [
    packageRead({ id: 42, key: "market_review_package", name: "Market Review Package" }),
    packageRead({ id: 77, key: "trading_agents", name: "TradingAgents" }),
    packageRead({ id: 88, key: "empty_package", name: "Empty Package" }),
  ],
};

const manifestByPackageId: Record<string, WorkflowPackageManifestRead> = {
  "42": manifestRead(42, "market_review_package", [
    { description: "Run market review", key: "market_review", name: "Market Review" },
  ]),
  "77": manifestRead(77, "trading_agents", [
    { description: "Advisory workflow", key: "advisory_research", label: "Advisory Research" },
    { description: "News workflow", key: "news_research", label: "News Research" },
  ]),
  "88": manifestRead(88, "empty_package", []),
};

function previewResult(overrides: Partial<SchedulePreviewRead> = {}): SchedulePreviewRead {
  return {
    ready: true,
    renderedParameters: { ticker: "AAPL" },
    scheduleId: null,
    scheduledFor: "2026-06-01T13:00:00Z",
    templateContext: { vars: {} },
    validationErrors: [],
    ...overrides,
  };
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

function renderPage() {
  return render(
    <MemoryRouter>
      <ScheduledTaskEditorPage />
    </MemoryRouter>,
  );
}

function packageSelector() {
  return screen.getByRole("combobox", { name: /^Workflow package$/i });
}

function workflowSelector() {
  return screen.getByRole("combobox", { name: /^Workflow$/i });
}

function timeZoneSelector() {
  return screen.getByRole("combobox", { name: /^Timezone$/i });
}

async function choosePackage(optionName: string | RegExp) {
  const selector = packageSelector();
  selector.focus();
  fireEvent.keyDown(selector, { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name: optionName }));
}

async function chooseWorkflow(optionName: string | RegExp) {
  const selector = workflowSelector();
  selector.focus();
  fireEvent.keyDown(selector, { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name: optionName }));
}

async function chooseTimeZone(optionName: string | RegExp) {
  const selector = timeZoneSelector();
  selector.focus();
  fireEvent.keyDown(selector, { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name: optionName }));
}

async function chooseSelectByTestId(testId: string, optionName: string | RegExp) {
  const selector = screen.getByTestId(testId);
  selector.focus();
  fireEvent.keyDown(selector, { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name: optionName }));
}

function currentCalendarDayButton() {
  const currentMonthName = new Intl.DateTimeFormat("en-US", { month: "long" }).format(new Date());
  const currentYear = String(new Date().getFullYear());
  const button = screen
    .getAllByRole("button")
    .find((candidate) => {
      const label = candidate.getAttribute("aria-label") ?? "";
      return label.includes(currentMonthName) && label.includes(currentYear);
    });

  if (!button) {
    throw new Error("Unable to find a day button in the current calendar month.");
  }

  return button;
}

async function choosePreviewScheduledFor(hour: string, minute: string) {
  fireEvent.click(screen.getByTestId("schedule-preview-scheduled-for"));
  fireEvent.click(currentCalendarDayButton());
  await chooseSelectByTestId("schedule-preview-scheduled-for-hour", hour);
  await chooseSelectByTestId("schedule-preview-scheduled-for-minute", minute);
}

describe("ScheduledTaskEditorPage", () => {
  beforeEach(() => {
    mockBrowserTimeZone("UTC");
    createScheduleMock.mockReset();
    navigateMock.mockReset();
    previewScheduleMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    useCreateScheduledTaskMock.mockReset();
    usePreviewUnsavedScheduledTaskMock.mockReset();
    useWorkflowPackageManifestMock.mockReset();
    useWorkflowPackagesMock.mockReset();

    createScheduleMock.mockResolvedValue({ id: 144 });
    previewScheduleMock.mockResolvedValue(previewResult());
    useCreateScheduledTaskMock.mockReturnValue({ isPending: false, mutateAsync: createScheduleMock });
    usePreviewUnsavedScheduledTaskMock.mockReturnValue({ isPending: false, mutateAsync: previewScheduleMock });
    useWorkflowPackagesMock.mockReturnValue({
      data: packagesRead,
      error: null,
      isError: false,
      isPending: false,
    });
    useWorkflowPackageManifestMock.mockImplementation((packageId?: string) => ({
      data: packageId ? manifestByPackageId[packageId] : undefined,
      error: null,
      isError: false,
      isPending: false,
    }));
  });

  it("renders dependent package and workflow selectors", async () => {
    renderPage();

    expect(packageSelector()).toBeVisible();
    expect(workflowSelector()).toBeDisabled();

    await choosePackage(/TradingAgents · trading_agents · #77/i);
    expect(workflowSelector()).not.toBeDisabled();

    packageSelector().focus();
    fireEvent.keyDown(packageSelector(), { key: "ArrowDown" });
    expect(await screen.findByRole("option", { name: /Market Review Package · market_review_package · #42/i })).toBeVisible();
  });

  it("auto-selects a package's only workflow and preserves packageId/workflowKey in preview and save payloads", async () => {
    renderPage();

    await choosePackage(/Market Review Package · market_review_package · #42/i);
    await waitFor(() => expect(workflowSelector()).toHaveTextContent("Market Review"));

    fireEvent.change(screen.getByTestId("schedule-name"), {
      target: { value: "Morning market review" },
    });
    await choosePreviewScheduledFor("09", "00");

    fireEvent.click(screen.getByTestId("schedule-input-preview-trigger"));
    await waitFor(() =>
      expect(previewScheduleMock).toHaveBeenCalledWith(
        expect.objectContaining({ packageId: 42, workflowKey: "market_review" }),
      ),
    );

    fireEvent.click(screen.getByTestId("schedule-save"));
    await waitFor(() =>
      expect(createScheduleMock).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Morning market review",
          packageId: 42,
          workflowKey: "market_review",
        }),
      ),
    );
  });

  it("renders preview scheduledFor in the draft timezone with an explicit zone suffix", async () => {
    renderPage();

    await choosePackage(/Market Review Package · market_review_package · #42/i);
    await waitFor(() => expect(workflowSelector()).toHaveTextContent("Market Review"));

    fireEvent.change(screen.getByTestId("schedule-name"), {
      target: { value: "Morning market review" },
    });
    await chooseTimeZone(/London \(Europe\/London\)/i);
    await choosePreviewScheduledFor("09", "00");

    fireEvent.click(screen.getByTestId("schedule-input-preview-trigger"));

    const preview = await screen.findByTestId("schedule-input-preview");
    const scheduledFor = previewResult().scheduledFor;
    expect(scheduledFor).not.toBeNull();
    expect(previewScheduleMock).toHaveBeenCalledWith(
      expect.objectContaining({ timezone: "Europe/London" }),
    );
    expect(preview).toHaveTextContent(
      expectedDateTimeInTimeZone(scheduledFor ?? "", "Europe/London"),
    );
  });

  it("defaults to the current browser timezone and shows it as the first timezone option", async () => {
    mockBrowserTimeZone("Europe/Helsinki");

    renderPage();

    expect(timeZoneSelector()).toHaveTextContent(
      /^Helsinki \(Europe\/Helsinki\) · Current browser timezone$/i,
    );

    timeZoneSelector().focus();
    fireEvent.keyDown(timeZoneSelector(), { key: "ArrowDown" });

    const options = await screen.findAllByRole("option");
    expect(options[0]).toHaveTextContent(
      /^Helsinki \(Europe\/Helsinki\) · Current browser timezone$/i,
    );
    expect(options[1]).toHaveTextContent(/^UTC$/);
  });

  it("prepends the current browser timezone without duplicating it when it is already in the curated list", async () => {
    renderPage();

    expect(timeZoneSelector()).toHaveTextContent(/^UTC · Current browser timezone$/i);

    timeZoneSelector().focus();
    fireEvent.keyDown(timeZoneSelector(), { key: "ArrowDown" });

    const options = await screen.findAllByRole("option");
    expect(options[0]).toHaveTextContent(/^UTC · Current browser timezone$/i);
    expect(screen.queryByRole("option", { name: /^UTC$/i })).not.toBeInTheDocument();
  });

  it("falls back to UTC only when the browser timezone is unavailable", async () => {
    mockBrowserTimeZone(null);

    renderPage();

    expect(timeZoneSelector()).toHaveTextContent(/^UTC$/i);

    timeZoneSelector().focus();
    fireEvent.keyDown(timeZoneSelector(), { key: "ArrowDown" });

    const options = await screen.findAllByRole("option");
    expect(options[0]).toHaveTextContent(/^UTC$/i);
    expect(screen.queryByRole("option", { name: /Current browser timezone/i })).not.toBeInTheDocument();
  });

  it("clears preview state and blocks preview/save when the selected package has no workflows", async () => {
    renderPage();

    await choosePackage(/TradingAgents · trading_agents · #77/i);
    await chooseWorkflow(/News Research/i);

    fireEvent.change(screen.getByTestId("schedule-name"), {
      target: { value: "Daily trading news" },
    });
    await choosePreviewScheduledFor("09", "00");

    fireEvent.click(screen.getByTestId("schedule-input-preview-trigger"));
    await screen.findByTestId("schedule-input-preview");
    expect(workflowSelector()).toHaveTextContent("News Research");

    await choosePackage(/Empty Package · empty_package · #88/i);

    expect(screen.getByText(/does not define any workflows/i)).toBeVisible();
    expect(screen.getByTestId("schedule-input-preview-empty")).toBeVisible();
    expect(screen.queryByTestId("schedule-input-preview")).not.toBeInTheDocument();
    expect(workflowSelector()).not.toHaveTextContent("News Research");
    expect(screen.getByTestId("schedule-input-preview-trigger")).toBeDisabled();
    expect(screen.getByTestId("schedule-save")).toBeDisabled();
  });
});
