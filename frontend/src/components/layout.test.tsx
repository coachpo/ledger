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
  it("shows orchestration in the root shell navigation without a backtests entry", () => {
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

    expect(screen.getByRole("link", { name: /orchestration/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /backtests/i })).not.toBeInTheDocument();
  });
});
