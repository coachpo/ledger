import type { ComponentProps } from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RouteErrorPage } from "./route-error";

const { isRouteErrorResponseMock, routeErrorMock } = vi.hoisted(() => ({
  isRouteErrorResponseMock: vi.fn(),
  routeErrorMock: vi.fn(),
}));

vi.mock("react-router", () => ({
  Link: ({ children, to, ...props }: ComponentProps<"a"> & { to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
  isRouteErrorResponse: (error: unknown) => isRouteErrorResponseMock(error),
  useRouteError: () => routeErrorMock(),
}));

describe("RouteErrorPage", () => {
  beforeEach(() => {
    isRouteErrorResponseMock.mockReset();
    routeErrorMock.mockReset();
    isRouteErrorResponseMock.mockReturnValue(false);
  });

  it("renders unexpected render failures through the compact error grammar", () => {
    routeErrorMock.mockReturnValue(new Error("Route harness failure"));

    render(<RouteErrorPage />);

    const page = screen.getByTestId("route-error-page");
    const content = screen.getByTestId("route-error-content");
    const status = screen.getByTestId("route-error-status");
    const statusStrip = status.querySelector("[role='list']");

    expect(page).toBeVisible();
    expect(page).toHaveClass("min-h-screen", "px-4", "py-10");
    expect(content).toHaveClass("max-w-5xl", "flex-col", "gap-4");
    expect(
      screen.getByRole("heading", { level: 1, name: "Route failed to render" }),
    ).toBeVisible();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByTestId("route-error-description")).toHaveClass(
      "max-w-2xl",
      "leading-6",
    );
    expect(status).toHaveClass("min-w-0");
    expect(
      status.closest("[data-slot='page-context-actions']"),
    ).not.toBeInTheDocument();
    expect(statusStrip).toHaveClass("w-fit", "max-w-full", "flex-wrap");
    expect(screen.getByTestId("route-error-meta")).toHaveClass(
      "flex-wrap",
      "gap-2",
    );
    expect(screen.getByText("Route error boundary")).toBeVisible();
    expect(screen.getByText("Render failure")).toBeVisible();
    expect(screen.queryByText("Route harness failure")).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open workflow packages" }),
    ).toHaveAttribute("href", "/workflow-packages");
  });

  it("renders route response failures without the default router error UI", () => {
    const routeResponse = { status: 404, statusText: "Not Found" };
    routeErrorMock.mockReturnValue(routeResponse);
    isRouteErrorResponseMock.mockImplementation((error) => error === routeResponse);

    render(<RouteErrorPage />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Route resource not found" }),
    ).toBeVisible();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByText("404")).toBeVisible();
    expect(
      screen.queryByText("Unexpected Application Error!"),
    ).not.toBeInTheDocument();
  });
});
