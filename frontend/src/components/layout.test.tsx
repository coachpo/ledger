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
        key: FINANCE_WORKSPACE_EXTENSION_KEY,
        label: "Finance Workspace",
        enabled,
      },
    ],
  };
}

const groupedSidebarItems = [
  {
    hrefs: ["/workflow-packages", "/model-connections", "/runs"],
    label: "Agent Platform",
    testIds: ["nav-workflow-packages", "nav-model-connections", "nav-runs"],
  },
  {
    hrefs: ["/", "/portfolios", "/templates", "/reports"],
    label: "Finance Workspace",
    testIds: ["nav-dashboard", "nav-portfolios", "nav-templates", "nav-reports"],
  },
  {
    hrefs: ["/extensions"],
    label: "System",
    testIds: ["nav-extensions"],
  },
] as const;

function groupLabels(container: HTMLElement): (string | null)[] {
  return Array.from(container.querySelectorAll('[data-sidebar="group-label"]')).map(
    (label) => label.textContent,
  );
}

function sidebarGroup(label: string): HTMLElement {
  const labelElement = screen.getByText(label);
  const group = labelElement.closest<HTMLElement>('[data-sidebar="group"]');

  if (!group) {
    throw new Error(`Sidebar group not found for ${label}`);
  }

  return group;
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
                <Route
                  path="runs/:runId"
                  element={<div data-testid="run-detail-content">Run detail workspace</div>}
                />
              </Route>
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </ThemeProvider>,
    );
  }

  it("shows extension-aware grouped shell navigation when finance is enabled", () => {
    const { container } = renderLayout("/");

    expect(groupLabels(container)).toEqual(
      groupedSidebarItems.map((group) => group.label),
    );
    expect(
      screen.getAllByRole("link").map((link) => link.getAttribute("href")),
    ).toEqual(groupedSidebarItems.flatMap((group) => group.hrefs));

    for (const group of groupedSidebarItems) {
      const renderedGroup = sidebarGroup(group.label);
      expect(
        within(renderedGroup)
          .getAllByRole("link")
          .map((link) => link.getAttribute("href")),
      ).toEqual(group.hrefs);

      for (const testId of group.testIds) {
        expect(within(renderedGroup).getByTestId(testId)).toBeInTheDocument();
      }
    }

    expect(
      screen.queryByRole("link", { name: /backtests/i }),
    ).not.toBeInTheDocument();
  });

  it("hides finance navigation while preserving grouped core entries when disabled", () => {
    const { container } = renderLayout("/workflow-packages/88", false);
    const coreGroups = groupedSidebarItems.filter(
      (group) => group.label !== "Finance Workspace",
    );

    expect(groupLabels(container)).toEqual(coreGroups.map((group) => group.label));
    expect(screen.queryByText("Finance Workspace")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-dashboard")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-portfolios")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-templates")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-reports")).not.toBeInTheDocument();

    for (const group of coreGroups) {
      const renderedGroup = sidebarGroup(group.label);
      expect(
        within(renderedGroup)
          .getAllByRole("link")
          .map((link) => link.getAttribute("href")),
      ).toEqual(group.hrefs);
    }
  });

  it("restores the finance group after re-enable", () => {
    const enabled = renderLayout("/");
    expect(sidebarGroup("Finance Workspace")).toBeInTheDocument();
    enabled.unmount();

    const disabled = renderLayout("/workflow-packages/88", false);
    expect(screen.queryByText("Finance Workspace")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-dashboard")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-portfolios")).not.toBeInTheDocument();
    disabled.unmount();

    renderLayout("/");
    expect(sidebarGroup("Finance Workspace")).toBeInTheDocument();
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

  it("gives run detail routes full-height workspace treatment", () => {
    renderLayout("/runs/42");

    const workspace = screen.getByTestId("run-detail-content");
    expect(within(screen.getByRole("banner")).getByText("Run Detail")).toBeInTheDocument();
    expect(workspace.parentElement).toHaveClass("h-full");
  });
});
