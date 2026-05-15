import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import { ThemeProvider } from "@/components/theme-provider";
import { FINANCE_WORKSPACE_EXTENSION_KEY } from "@/extensions";
import { queryKeys } from "@/lib/query-keys";
import type { ExtensionListRead } from "@/lib/types/extension";

import { Layout } from "./layout";

Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: {
    getItem: () => null,
    removeItem: () => undefined,
    setItem: () => undefined,
  },
});

function extensionList(enabled: boolean): ExtensionListRead {
  return {
    items: [
      {
        contributionCategories: [],
        contributions: [],
        createdAt: "2026-05-15T09:00:00Z",
        defaultEnabled: true,
        dependencies: [],
        disabledAt: enabled ? null : "2026-05-15T11:00:00Z",
        disabledReason: enabled ? null : "Disabled in test",
        enabled,
        enabledAt: enabled ? "2026-05-15T10:00:00Z" : null,
        key: FINANCE_WORKSPACE_EXTENSION_KEY,
        label: "Finance Workspace",
        phase: "phase_1_bundled_first_party",
        stateVersion: enabled ? 1 : 2,
        updatedAt: "2026-05-15T11:00:00Z",
        versioningRule: "follows_backend_application_version",
      },
    ],
  };
}

describe("Layout", () => {
  function renderLayout(initialEntry: string, financeEnabled = true) {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    queryClient.setQueryData(
      queryKeys.platform.extensions.list(),
      extensionList(financeEnabled),
    );

    return render(
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={[initialEntry]}>
            <Routes>
              <Route element={<Layout />}>
                <Route index element={<div>Dashboard content</div>} />
                <Route
                  path="workflow-packages/:packageId"
                  element={<div>Package detail content</div>}
                />
                <Route
                  path="workflow-packages/:packageId/run"
                  element={<div>Package launch content</div>}
                />
              </Route>
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </ThemeProvider>,
    );
  }

  it("shows extension-aware shell navigation when finance is enabled", () => {
    renderLayout("/");

    expect(
      screen.getAllByRole("link").map((link) => link.getAttribute("href")),
    ).toEqual([
      "/",
      "/portfolios",
      "/templates",
      "/reports",
      "/model-connections",
      "/workflow-packages",
      "/runs",
    ]);
    expect(
      screen.getByRole("link", { name: /workflow packages/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /model connections/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /runs/i })).toBeInTheDocument();

    expect(
      screen.queryByRole("link", { name: /agents/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /capabilities/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /mcp servers/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /output schemas/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /^workflows$/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /tryout/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /studio/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /orchestration/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /backtests/i }),
    ).not.toBeInTheDocument();
  });

  it("hides finance navigation while preserving core platform entries when disabled", () => {
    renderLayout("/workflow-packages/88", false);

    expect(screen.queryByTestId("nav-dashboard")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-portfolios")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-templates")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-reports")).not.toBeInTheDocument();
    expect(screen.getByTestId("nav-model-connections")).toHaveAttribute(
      "href",
      "/model-connections",
    );
    expect(screen.getByTestId("nav-workflow-packages")).toHaveAttribute(
      "href",
      "/workflow-packages",
    );
    expect(screen.getByTestId("nav-runs")).toHaveAttribute("href", "/runs");
  });

  it("restores the exact finance navigation set after re-enable", () => {
    const enabledHrefs = [
      "/",
      "/portfolios",
      "/templates",
      "/reports",
      "/model-connections",
      "/workflow-packages",
      "/runs",
    ];
    const enabled = renderLayout("/");
    expect(
      screen.getAllByRole("link").map((link) => link.getAttribute("href")),
    ).toEqual(enabledHrefs);
    enabled.unmount();

    const disabled = renderLayout("/workflow-packages/88", false);
    expect(screen.queryByTestId("nav-dashboard")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-portfolios")).not.toBeInTheDocument();
    disabled.unmount();

    renderLayout("/");
    expect(
      screen.getAllByRole("link").map((link) => link.getAttribute("href")),
    ).toEqual(enabledHrefs);
    expect(screen.getByTestId("nav-reports")).toHaveAttribute(
      "href",
      "/reports",
    );
  });

  it("labels workflow package detail and launch routes", () => {
    renderLayout("/workflow-packages/88");
    expect(
      within(screen.getByRole("banner")).getByText("Workflow Package Detail"),
    ).toBeInTheDocument();

    renderLayout("/workflow-packages/88/run");
    expect(
      within(screen.getAllByRole("banner")[1]).getByText(
        "Launch Workflow Package",
      ),
    ).toBeInTheDocument();
  });
});
