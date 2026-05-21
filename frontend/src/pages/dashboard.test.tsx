import type { ComponentProps } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
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

  it("renders the singleton landing summary with explicit KPI hierarchy", () => {
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
    expect(
      screen.getByText(/singleton landing summary for portfolio inventory/i),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { level: 2, name: "Portfolio summary" }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { level: 2, name: "Operational context" }),
    ).toBeVisible();

    const summarySection = screen.getByRole("heading", {
      level: 2,
      name: "Portfolio summary",
    }).closest("section");
    expect(summarySection).not.toBeNull();
    expect(within(summarySection as HTMLElement).getByText("Active Portfolios")).toBeVisible();
    expect(within(summarySection as HTMLElement).getByText("2")).toBeVisible();
    expect(within(summarySection as HTMLElement).getByText("Total Positions")).toBeVisible();
    expect(within(summarySection as HTMLElement).getByText("6")).toBeVisible();
    expect(
      within(summarySection as HTMLElement).getByRole("link", {
        name: /active portfolios/i,
      }),
    ).toHaveAttribute("href", "/portfolios");
  });

  it("keeps the same singleton summary identity while loading", () => {
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
    expect(
      screen.getByRole("heading", { level: 2, name: "Portfolio summary" }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { level: 2, name: "Operational context" }),
    ).toBeVisible();
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

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetchMock).toHaveBeenCalledTimes(1);
  });
});
