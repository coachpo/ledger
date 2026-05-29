import type { ComponentProps } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RunsListPage } from "./list";

const navigateMock = vi.fn();
const refetchMock = vi.fn();
const useRunsMock = vi.fn();

vi.mock("react-router", () => ({
  Link: ({ children, to, ...props }: ComponentProps<"a"> & { to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
  useNavigate: () => navigateMock,
}));

vi.mock("@/hooks/use-runs", () => ({
  useRuns: (...args: unknown[]) => useRunsMock(...args),
}));

describe("RunsListPage", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    refetchMock.mockReset();
    useRunsMock.mockReset();
    useRunsMock.mockReturnValue({
      data: {
        items: [
          {
            finishedAt: null,
            id: 14,
            queuedAt: "2026-04-20T09:59:00Z",
            startedAt: null,
            status: "queued",
            progress: {
              unit: "invocation",
              terminalCount: 1,
              totalCount: 8,
              percent: 12,
            },
            queue: {
              blockingRunId: null,
              message: "Backend queue read model: waiting on worker capacity.",
              reason: "awaiting-worker-capacity",
              state: "waiting",
            },
            targetId: 40,
            targetKey: "queued_review",
            targetKind: "workflow",
            totalTokens: 0,
            traceId: null,
          },
          {
            finishedAt: null,
            id: 17,
            queuedAt: "2026-04-20T09:59:15Z",
            startedAt: null,
            status: "queued",
            progress: {
              unit: "invocation",
              terminalCount: 0,
              totalCount: 3,
              percent: 0,
            },
            queue: {
              blockingRunId: 14,
              message:
                "Backend queue read model: run #14 is holding package serial lane.",
              reason: "blocked-by-package-serial-policy",
              state: "blocked",
            },
            targetId: 42,
            targetKey: "queued_review",
            targetKind: "workflowPackage",
            totalTokens: 0,
            traceId: null,
          },
          {
            finishedAt: null,
            id: 15,
            queuedAt: "2026-04-20T09:59:30Z",
            startedAt: "2026-04-20T10:00:00Z",
            status: "running",
            progress: {
              unit: "invocation",
              terminalCount: 2,
              totalCount: 5,
              percent: 37,
            },
            queue: null,
            targetId: 41,
            targetKey: "market_review_package",
            targetKind: "workflowPackage",
            totalTokens: 21,
            traceId: "trace-15",
          },
          {
            finishedAt: "2026-04-20T10:03:00Z",
            id: 16,
            queuedAt: "2026-04-20T10:00:30Z",
            startedAt: "2026-04-20T10:01:00Z",
            status: "succeeded",
            progress: {
              unit: "invocation",
              terminalCount: 3,
              totalCount: 3,
              percent: 100,
            },
            queue: null,
            targetId: 12,
            targetKey: "macro_agent",
            targetKind: "agent",
            totalTokens: 13,
            traceId: "trace-16",
          },
        ],
      },
      error: null,
      isError: false,
      isPending: false,
      refetch: refetchMock,
    });
  });

  it("keeps monitor-specific empty and error states", () => {
    useRunsMock.mockReturnValue({
      data: { items: [] },
      error: null,
      isError: false,
      isPending: false,
      refetch: refetchMock,
    });
    const { rerender } = render(<RunsListPage />);

    expect(screen.getByTestId("runs-monitor-filter-card")).toHaveTextContent(
      "Polling every 2 seconds while queued or running rows are present.",
    );
    expect(
      screen.getByText("No runs match the current monitor filters"),
    ).toBeVisible();
    expect(screen.getByText(/widen the polling window/i)).toBeVisible();

    useRunsMock.mockReturnValue({
      data: undefined,
      error: new Error("Runs API unavailable"),
      isError: true,
      isPending: false,
      refetch: refetchMock,
    });
    rerender(<RunsListPage />);

    expect(screen.getByRole("alert")).toHaveTextContent("Runs API unavailable");
  });

  it("renders dense run monitor rows, refreshes, and routes to detail", () => {
    render(<RunsListPage />);

    const page = screen.getByTestId("runs-list-page");
    expect(
      within(page).getByText(
        /monitor recent workflow package runs/i,
      ),
    ).toBeVisible();
    const contextRegion = page.querySelector(
      '[data-inventory-shell-region="context"]',
    );
    expect(contextRegion).toBeInTheDocument();
    const header = within(contextRegion as HTMLElement)
      .getByRole("heading", { level: 1, name: "Runs" })
      .closest("[data-slot='page-context-bar']");
    expect(header).toHaveClass("sm:flex-row", "sm:items-start");
    expect(header?.closest("[data-slot='card']")).not.toBeInTheDocument();
    expect(
      within(contextRegion as HTMLElement).getByText(
        /monitor recent workflow package runs/i,
      ),
    ).toHaveClass("max-w-3xl", "truncate", "text-sm");
    expect(
      within(contextRegion as HTMLElement).queryByRole("list"),
    ).not.toBeInTheDocument();
    expect(
      page.querySelector('[data-inventory-shell-region="toolbar"]'),
    ).toBeInTheDocument();
    expect(
      page.querySelector('[data-inventory-shell-region="filters"]'),
    ).toBeInTheDocument();
    expect(within(contextRegion as HTMLElement).queryByText("Returned")).not.toBeInTheDocument();
    expect(within(contextRegion as HTMLElement).queryByText("Active")).not.toBeInTheDocument();
    expect(within(contextRegion as HTMLElement).queryByText("Queued")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Target key")).toBeVisible();
    expect(screen.getByLabelText("Target kind")).toBeVisible();
    expect(screen.getByLabelText("Run status")).toBeVisible();
    expect(screen.getByTestId("runs-monitor-filter-card")).toHaveTextContent(
      "Target kind",
    );
    expect(screen.getByTestId("runs-monitor-filter-card")).toHaveTextContent(
      "All statuses",
    );

    const table = screen.getByRole("table");
    for (const column of [
      "Run",
      "Target",
      "Status",
      "Progress",
      "Queue",
      "Tokens",
      "Timestamps",
      "Open",
    ]) {
      expect(
        within(table).getByRole("columnheader", { name: column }),
      ).toBeVisible();
    }

    expect(screen.getByTestId("runs-row-14")).toBeVisible();
    expect(screen.getByTestId("runs-row-17")).toBeVisible();
    expect(screen.getByTestId("runs-row-15")).toBeVisible();
    expect(screen.getByTestId("runs-row-16")).toBeVisible();
    expect(screen.getAllByText("Workflow")[0]).toBeVisible();
    expect(screen.getAllByText("Agent")[0]).toBeVisible();
    expect(screen.getAllByText(/^queued_review$/i)[0]).toBeVisible();
    expect(screen.getAllByText(/^market_review_package$/i)[0]).toBeVisible();
    expect(screen.getAllByText(/^macro_agent$/i)[0]).toBeVisible();
    expect(screen.getByText(/workflow id: 40/i)).toBeVisible();
    expect(
      screen.getByText(/captured snapshot: market_review_package/i),
    ).toBeVisible();
    expect(screen.getByText(/package id at launch: #41/i)).toBeVisible();
    expect(screen.getByText(/agent id: 12/i)).toBeVisible();
    expect(screen.getByText(/trace-15/i)).toBeVisible();
    expect(
      screen.queryByRole("link", { name: /package:/i }),
    ).not.toBeInTheDocument();

    const queuedRow = screen.getByTestId("runs-row-14");
    expect(queuedRow).toHaveTextContent(/run #14/i);
    expect(queuedRow).toHaveTextContent(/queued/i);
    expect(queuedRow).toHaveTextContent(/1\/8 invocations · 12%/i);
    expect(queuedRow).toHaveTextContent(/0/i);
    expect(queuedRow).toHaveTextContent(/queued:/i);
    expect(queuedRow).toHaveTextContent(/started:/i);
    expect(queuedRow).toHaveTextContent(/not started/i);
    expect(queuedRow).toHaveTextContent(/finished:/i);
    expect(queuedRow).toHaveTextContent(/not finished/i);
    expect(queuedRow).toHaveTextContent(/awaiting worker capacity/i);
    expect(queuedRow).toHaveTextContent(
      /backend queue read model: waiting on worker capacity/i,
    );
    expect(screen.getByTestId("runs-row-progress-14")).toHaveTextContent(
      /12%/i,
    );

    const blockedRow = screen.getByTestId("runs-row-17");
    expect(blockedRow).toHaveTextContent(/blocked by package serial policy/i);
    expect(blockedRow).toHaveTextContent(
      /backend queue read model: run #14 is holding package serial lane/i,
    );
    expect(blockedRow).toHaveTextContent(/blocking run: #14/i);
    expect(blockedRow).toHaveTextContent(/0\/3 invocations · 0%/i);
    expect(screen.queryByText(/awaiting execution/i)).not.toBeInTheDocument();

    expect(screen.getByTestId("runs-row-15")).toHaveTextContent(
      /2\/5 invocations · 37%/i,
    );
    expect(screen.getByTestId("runs-row-15")).toHaveTextContent(/21/i);
    expect(screen.getByTestId("runs-row-16")).toHaveTextContent(
      /3\/3 invocations · 100%/i,
    );
    expect(screen.queryByText(/total cost/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /refresh/i }));
    expect(refetchMock).toHaveBeenCalled();

    const runsRow = screen.getByTestId("runs-row-15");
    const openAction = within(runsRow).getByTestId("runs-row-action-15");

    expect(openAction).toHaveAccessibleName("Open run #15");
    expect(openAction).toHaveAttribute("href", "/runs/15");
    expect(
      within(runsRow).queryByRole("button", { name: /open run #15/i }),
    ).not.toBeInTheDocument();
  });

  it("keeps target filters route-owned while polling through the runs hook", () => {
    render(<RunsListPage />);

    expect(useRunsMock).toHaveBeenLastCalledWith(
      {
        limit: 50,
        status: undefined,
        targetKey: undefined,
        targetKind: undefined,
      },
      { refetchInterval: 2000 },
    );

    fireEvent.change(screen.getByLabelText("Target key"), {
      target: { value: " market_review_package " },
    });

    expect(useRunsMock).toHaveBeenLastCalledWith(
      {
        limit: 50,
        status: undefined,
        targetKey: undefined,
        targetKind: undefined,
      },
      { refetchInterval: 2000 },
    );
    expect(screen.getByTestId("runs-monitor-filter-card")).toHaveTextContent(
      "market_review_package · select target kind to apply",
    );

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    expect(useRunsMock).toHaveBeenLastCalledWith(
      {
        limit: 50,
        status: undefined,
        targetKey: undefined,
        targetKind: undefined,
      },
      { refetchInterval: 2000 },
    );
  });
});
