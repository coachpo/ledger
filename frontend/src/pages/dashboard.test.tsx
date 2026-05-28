import type { ComponentProps } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Dashboard } from "./dashboard";

const { refetchMock, usePortfoliosMock } = vi.hoisted(() => ({
  refetchMock: vi.fn(),
  usePortfoliosMock: vi.fn(),
}));

vi.mock("react-router", () => ({
  Link: ({ children, to, ...props }: ComponentProps<"a"> & { to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/hooks/use-portfolios", () => ({
  usePortfolios: () => usePortfoliosMock(),
}));

describe("Dashboard", () => {
  beforeEach(() => {
    refetchMock.mockReset();
    usePortfoliosMock.mockReset();
  });

  it("renders the normalized dashboard hero without summary cards", () => {
    usePortfoliosMock.mockReturnValue({
      data: [
        {
          balanceCount: 2,
          baseCurrency: "USD",
          id: 1,
          name: "Growth Fund",
          positionCount: 4,
          updatedAt: "2026-05-20T10:00:00Z",
        },
        {
          balanceCount: 1,
          baseCurrency: "EUR",
          id: 2,
          name: "Income Fund",
          positionCount: 2,
          updatedAt: "2026-05-19T10:00:00Z",
        },
      ],
      error: null,
      isError: false,
      isFetching: false,
      isPending: false,
      refetch: refetchMock,
    });

    render(<Dashboard />);

    expect(screen.getByTestId("dashboard-page")).toBeVisible();
    expect(screen.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
    expect(screen.getByText(/singleton landing context/i)).toBeVisible();
    expect(screen.queryByText("Portfolios")).not.toBeInTheDocument();
    expect(screen.queryByText("Refresh")).not.toBeInTheDocument();
    expect(screen.queryByText("Ready")).not.toBeInTheDocument();
    expect(screen.queryByText("Dashboard context")).not.toBeInTheDocument();
    expect(screen.queryByText("Portfolio summary")).not.toBeInTheDocument();
    expect(screen.queryByText("Operational context")).not.toBeInTheDocument();
    expect(screen.queryByText("Active Portfolios")).not.toBeInTheDocument();
  });

  it("keeps the same dashboard identity while loading", () => {
    usePortfoliosMock.mockReturnValue({
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
    expect(screen.queryByText("Dashboard context")).not.toBeInTheDocument();
    expect(screen.queryByText("Portfolio summary")).not.toBeInTheDocument();
    expect(screen.queryByText("Operational context")).not.toBeInTheDocument();
    expect(screen.queryByText("Loading")).not.toBeInTheDocument();
  });

  it("omits empty portfolio header status without summary cards", () => {
    usePortfoliosMock.mockReturnValue({
      data: [],
      error: null,
      isError: false,
      isFetching: false,
      isPending: false,
      refetch: refetchMock,
    });

    render(<Dashboard />);

    expect(screen.queryByText("Portfolios")).not.toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(screen.queryByText("No portfolio records are available yet.")).not.toBeInTheDocument();
  });

  it("renders stable dashboard retry behavior for API errors", () => {
    usePortfoliosMock.mockReturnValue({
      data: undefined,
      error: new Error("Portfolio API unavailable"),
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
    expect(alert).toHaveTextContent("Portfolio API unavailable");
    expect(screen.queryByText("Unavailable")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetchMock).toHaveBeenCalledTimes(1);
  });
});
