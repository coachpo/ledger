import { render, screen, within } from "@testing-library/react";
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
  function renderLayout(initialEntry: string) {
    return render(
      <ThemeProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<div>Dashboard content</div>} />
              <Route path="workflow-packages/:packageId" element={<div>Package detail content</div>} />
              <Route path="workflow-packages/:packageId/run" element={<div>Package launch content</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </ThemeProvider>,
    );
  }

  it("shows the exact shell navigation and hides old authoring entries", () => {
    renderLayout("/");

    expect(screen.getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual([
      "/",
      "/portfolios",
      "/templates",
      "/reports",
      "/model-connections",
      "/workflow-packages",
      "/runs",
    ]);
    expect(screen.getByRole("link", { name: /workflow packages/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /model connections/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /runs/i })).toBeInTheDocument();

    expect(screen.queryByRole("link", { name: /agents/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /capabilities/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /mcp servers/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /output schemas/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^workflows$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /tryout/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /studio/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /orchestration/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /backtests/i })).not.toBeInTheDocument();
  });

  it("labels workflow package detail and launch routes", () => {
    renderLayout("/workflow-packages/88");
    expect(within(screen.getByRole("banner")).getByText("Workflow Package Detail")).toBeInTheDocument();

    renderLayout("/workflow-packages/88/run");
    expect(within(screen.getAllByRole("banner")[1]).getByText("Launch Workflow Package")).toBeInTheDocument();
  });
});
