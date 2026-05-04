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
              <Route path="workflows/:workflowId" element={<div>Workflow detail content</div>} />
              <Route path="workflows/:workflowId/edit" element={<div>Workflow editor content</div>} />
              <Route path="workflows/:workflowId/run" element={<div>Workflow launch content</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </ThemeProvider>,
    );
  }

  it("shows the primary platform shell navigation and hides legacy shell entries", () => {
    renderLayout("/");

    expect(screen.getByRole("link", { name: /agents/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /capabilities/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /mcp servers/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /output schemas/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /workflows/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /runs/i })).toBeInTheDocument();

    expect(screen.queryByRole("link", { name: /tryout/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /studio/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /orchestration/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /backtests/i })).not.toBeInTheDocument();
  });

  it("labels workflow detail, edit, and launch routes", () => {
    renderLayout("/workflows/88");
    expect(within(screen.getByRole("banner")).getByText("Workflow Detail")).toBeInTheDocument();

    renderLayout("/workflows/88/edit#review");
    expect(within(screen.getAllByRole("banner")[1]).getByText("Edit Workflow")).toBeInTheDocument();

    renderLayout("/workflows/88/run");
    expect(within(screen.getAllByRole("banner")[2]).getByText("Run Workflow")).toBeInTheDocument();
  });
});
