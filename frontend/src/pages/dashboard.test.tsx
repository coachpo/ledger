import type { ComponentProps } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Dashboard } from "./dashboard";
import type { RunListItemRead } from "@/lib/types/run";

const { refetchMock, useRunsMock } = vi.hoisted(() => ({
  refetchMock: vi.fn(),
  useRunsMock: vi.fn(),
}));

vi.mock("react-router", () => ({
  Link: ({ children, to, ...props }: ComponentProps<"a"> & { to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/hooks/use-runs", () => ({
  useRuns: () => useRunsMock(),
}));

function buildRun(overrides: Partial<RunListItemRead> = {}): RunListItemRead {
  return {
    id: 1,
    status: "succeeded",
    targetId: 12,
    targetKey: "daily_research",
    targetKind: "workflowPackage",
    totalTokens: 1200,
    progress: {
      percent: 100,
      terminalCount: 1,
      totalCount: 1,
      unit: "invocation",
    },
    queue: null,
    scheduleId: null,
    scheduleFireId: null,
    scheduledFor: null,
    scheduleReason: null,
    scheduleProvenance: null,
    traceId: "trace-1",
    workflowKey: "daily",
    queuedAt: "2026-05-20T10:00:00Z",
    startedAt: "2026-05-20T10:00:01Z",
    finishedAt: "2026-05-20T10:00:02Z",
    ...overrides,
  };
}

describe("Dashboard", () => {
  beforeEach(() => {
    refetchMock.mockReset();
    useRunsMock.mockReset();
  });

  it("renders recent workflow runs", () => {
    useRunsMock.mockReturnValue({
      data: { items: [buildRun(), buildRun({ id: 2, status: "queued" })] },
      error: null,
      isError: false,
      isFetching: false,
      isPending: false,
      refetch: refetchMock,
    });

    render(<Dashboard />);

    expect(screen.getByTestId("dashboard-page")).toBeVisible();
    expect(screen.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
    expect(screen.getByText("Recent workflow runs.")).toBeVisible();
    expect(screen.getByTestId("runs-row-1")).toBeVisible();
    expect(screen.getByTestId("runs-row-2")).toBeVisible();
  });

  it("keeps the same dashboard identity while loading", () => {
    useRunsMock.mockReturnValue({
      data: undefined,
      error: null,
      isError: false,
      isFetching: true,
      isPending: true,
      refetch: refetchMock,
    });

    render(<Dashboard />);

    expect(screen.getByTestId("dashboard-page")).toBeVisible();
    expect(screen.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
  });

  it("renders stable dashboard retry behavior for API errors", () => {
    useRunsMock.mockReturnValue({
      data: undefined,
      error: new Error("Runs API unavailable"),
      isError: true,
      isFetching: false,
      isPending: false,
      refetch: refetchMock,
    });

    render(<Dashboard />);

    expect(screen.getByTestId("dashboard-page")).toBeVisible();
    expect(screen.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Unable to load the dashboard summary.");
    expect(alert).toHaveTextContent("Runs API unavailable");

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetchMock).toHaveBeenCalledTimes(1);
  });
});
