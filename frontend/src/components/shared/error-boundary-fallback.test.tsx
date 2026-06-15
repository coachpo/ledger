import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ErrorBoundaryFallback } from "./error-boundary-fallback";

describe("ErrorBoundaryFallback", () => {
  it("renders app failures through an expanded responsive fallback layout", () => {
    const error = new Error(
      "A very long render failure message should remain readable without squeezing the fallback card into a tiny centered box or forcing one-word-per-line wrapping.",
    );
    const onReset = vi.fn();

    const { container } = render(
      <ErrorBoundaryFallback error={error} onReset={onReset} />,
    );

    const page = container.firstElementChild;
    const content = screen.getByTestId("error-boundary-fallback-content");
    const card = screen
      .getByRole("heading", { level: 1, name: "Something went wrong" })
      .closest("[data-testid='error-boundary-fallback-card']");
    const message = screen.getByTestId("error-boundary-fallback-error");

    expect(page).toHaveClass("min-h-screen", "px-4", "py-8");
    expect(page).not.toHaveClass("items-center", "justify-center", "p-6");
    expect(content).toHaveClass("w-full", "max-w-6xl", "flex-col");
    expect(card).toHaveClass("w-full", "max-w-none");
    expect(message).toHaveClass("w-full", "max-w-4xl", "break-words");
    expect(screen.getByText(error.message)).toBeVisible();
    expect(screen.getByRole("button", { name: "Try again" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Reload app" })).toBeVisible();
  });
});
