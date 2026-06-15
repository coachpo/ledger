import type { ComponentProps } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NotFoundPage } from "./not-found";

vi.mock("react-router", () => ({
  Link: ({ children, to, ...props }: ComponentProps<"a"> & { to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));

describe("NotFoundPage", () => {
  it("renders the product-owned route fallback through a responsive full-page layout", () => {
    render(<NotFoundPage />);

    const page = screen.getByTestId("not-found-page");
    const content = screen.getByTestId("not-found-content");
    const status = screen.getByTestId("not-found-status");
    const statusStrip = status.querySelector("[role='list']");
    const emptyStateCard = screen
      .getByText("Unknown route")
      .closest("[data-slot='card']");

    expect(page).toBeVisible();
    expect(page).toHaveClass("min-h-[calc(100vh-3rem)]", "px-4", "py-8");
    expect(content).toHaveClass("w-full", "max-w-6xl", "flex-col", "gap-6");
    expect(
      screen.getByRole("heading", { level: 1, name: "Page not found" }),
    ).toBeVisible();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByTestId("not-found-description")).toHaveClass(
      "max-w-4xl",
      "leading-6",
    );
    expect(status).toHaveClass("w-full", "min-w-0");
    expect(
      status.closest("[data-slot='page-context-actions']"),
    ).not.toBeInTheDocument();
    expect(statusStrip).toHaveClass(
      "w-full",
      "max-w-none",
      "justify-start",
      "flex-wrap",
    );
    expect(screen.getByTestId("not-found-meta")).toHaveClass(
      "w-full",
      "flex-wrap",
      "gap-2",
    );
    expect(emptyStateCard).toHaveClass("w-full", "max-w-none");
    expect(screen.getByText("Unknown route")).toBeVisible();
    expect(screen.getByText("Not found")).toBeVisible();
    expect(screen.getByText("Workflow packages")).toBeVisible();
    expect(screen.getByText(/did not match any registered/i)).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Open workflow packages" }),
    ).toHaveAttribute("href", "/workflow-packages");
  });
});
