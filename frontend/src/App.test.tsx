import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-router", () => ({
  RouterProvider: () => <div data-testid="router-provider" />,
}));

vi.mock("sonner", () => ({
  Toaster: ({
    position,
    richColors,
  }: {
    position?: string;
    richColors?: boolean;
  }) => (
    <div
      data-testid="sonner-toaster"
      data-position={position}
      data-rich-colors={String(richColors)}
    />
  ),
}));

vi.mock("./components/theme-provider", () => ({
  ThemeProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("./routes", () => ({
  router: {},
}));

import App from "./App";

describe("App", () => {
  it("mounts the sonner toaster in the top-right with rich colors", () => {
    render(<App />);
    expect(screen.getByTestId("router-provider")).toBeVisible();
    expect(screen.getByTestId("sonner-toaster")).toHaveAttribute("data-position", "top-right");
    expect(screen.getByTestId("sonner-toaster")).toHaveAttribute("data-rich-colors", "true");
  });
});
