import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import { ThemeProvider } from "@/components/theme-provider";

import { Layout } from "./layout";

Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: {
    getItem: () => null,
    setItem: () => undefined,
    removeItem: () => undefined,
  },
});

describe("Layout", () => {
  it("shows the primary platform shell navigation and hides legacy shell entries", () => {
    render(
      <ThemeProvider>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<div>Dashboard content</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </ThemeProvider>,
    );

    expect(screen.getByRole("link", { name: /agents/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /skills/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /mcp servers/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /output schemas/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /workflows/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /runs/i })).toBeInTheDocument();

    expect(screen.queryByRole("link", { name: /tryout/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /studio/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /orchestration/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /backtests/i })).not.toBeInTheDocument();
  });
});
