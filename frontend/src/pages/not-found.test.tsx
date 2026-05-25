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
  it("renders the product-owned compact route fallback", () => {
    render(<NotFoundPage />);

    expect(screen.getByTestId("not-found-page")).toBeVisible();
    expect(
      screen.getByRole("heading", { level: 1, name: "Page not found" }),
    ).toBeVisible();
    expect(screen.getByText("Unknown route")).toBeVisible();
    expect(screen.getByText("Not found")).toBeVisible();
    expect(screen.getByText("Workflow packages")).toBeVisible();
    expect(screen.getByText(/did not match any registered/i)).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Open workflow packages" }),
    ).toHaveAttribute("href", "/workflow-packages");
  });
});
