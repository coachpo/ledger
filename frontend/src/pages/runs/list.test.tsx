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
    useRunsMock.mockReturnValue({
      data: {
        items: [
          {
            finishedAt: null,
            id: 14,
            queuedAt: "2026-04-20T09:59:00Z",
            startedAt: null,
            status: "queued",
            targetId: 40,
            targetKey: "queued_review",
            targetKind: "workflow",
            targetVersion: 1,
            totalTokens: 0,
            traceId: null,
          },
          {
            finishedAt: null,
            id: 15,
            queuedAt: "2026-04-20T09:59:30Z",
            startedAt: "2026-04-20T10:00:00Z",
            status: "running",
            targetId: 41,
            targetKey: "market_review",
            targetKind: "workflow",
            targetVersion: 2,
            totalTokens: 21,
            traceId: "trace-15",
          },
          {
            finishedAt: "2026-04-20T10:03:00Z",
            id: 16,
            queuedAt: "2026-04-20T10:00:30Z",
            startedAt: "2026-04-20T10:01:00Z",
            status: "succeeded",
            targetId: 12,
            targetKey: "macro_agent",
            targetKind: "agent",
            targetVersion: 9,
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

  it("renders run rows, refreshes, and routes to detail", () => {
    render(<RunsListPage />);

    expect(screen.getByTestId("runs-row-14")).toBeVisible();
    expect(screen.getByTestId("runs-row-15")).toBeVisible();
    expect(screen.getByTestId("runs-row-16")).toBeVisible();
    expect(screen.getAllByText("Workflow")[0]).toBeVisible();
    expect(screen.getAllByText("Agent")[0]).toBeVisible();
    expect(screen.getByText(/queued_review@1/i)).toBeVisible();
    expect(screen.getByText(/market_review@2/i)).toBeVisible();
    expect(screen.getByText(/macro_agent@9/i)).toBeVisible();
    expect(screen.getByRole("link", { name: "Workflow: 40" })).toHaveAttribute(
      "href",
      "/workflows/40",
    );
    expect(screen.getByRole("link", { name: "Workflow: 41" })).toHaveAttribute(
      "href",
      "/workflows/41",
    );
    expect(screen.getByText(/agent id: 12/i)).toBeVisible();
    expect(screen.getByTestId("runs-row-14")).toHaveTextContent(/total tokens: 0/i);
    expect(screen.getByTestId("runs-row-15")).toHaveTextContent(/total tokens: 21/i);
    expect(screen.getByTestId("runs-row-16")).toHaveTextContent(/total tokens: 13/i);
    expect(screen.queryByText(/total cost/i)).not.toBeInTheDocument();

    expect(screen.getByTestId("runs-row-14")).toHaveTextContent(/awaiting execution/i);
    expect(screen.getByTestId("runs-row-14")).toHaveTextContent(/0%/i);
    expect(screen.getByTestId("runs-row-15")).toHaveTextContent(/still running/i);
    expect(screen.getByTestId("runs-row-15")).toHaveTextContent(/50%/i);
    expect(screen.getByTestId("runs-row-16")).toHaveTextContent(/100%/i);

    fireEvent.click(screen.getByRole("button", { name: /refresh/i }));
    expect(refetchMock).toHaveBeenCalled();

    fireEvent.click(within(screen.getByTestId("runs-row-15")).getByRole("button", { name: /open run/i }));
    expect(navigateMock).toHaveBeenCalledWith("/runs/15");
  });
});
