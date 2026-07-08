import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { ThemeProvider } from "@/components/theme-provider";
import {
  FINANCE_WORKSPACE_NAV_GROUP,
  getRouteMetadataForPathname,
  getSidebarRouteMetadataGroups,
} from "@/routes.metadata";

import { Layout } from "./layout";

const localStorageState = new Map<string, string>();

Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: {
    getItem: (key: string) => localStorageState.get(key) ?? null,
    removeItem: (key: string) => localStorageState.delete(key),
    setItem: (key: string, value: string) => localStorageState.set(key, value),
  },
});

beforeEach(() => {
  localStorageState.clear();
  document.documentElement.classList.remove("dark");
});

const groupedSidebarItems = getSidebarRouteMetadataGroups().map((group) => ({
  items: group.items.map((metadata) => {
    if (!metadata.nav.path) {
      throw new Error(
        `Sidebar metadata is missing a nav path for ${metadata.pattern}`,
      );
    }

    return {
      href: metadata.nav.path,
      label: metadata.nav.label,
      testId: metadata.nav.testId,
    };
  }),
  label: group.label,
}));

function renderLayout(initialEntry: string) {
  return render(
    <ThemeProvider>
      <QueryClientProvider
        client={new QueryClient({
          defaultOptions: { queries: { retry: false } },
        })}
      >
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<div>Dashboard content</div>} />
              <Route path="templates" element={<div>Templates content</div>} />
              <Route
                path="templates/new"
                element={<div data-testid="template-new-content">Template new</div>}
              />
              <Route
                path="reports/:slug"
                element={<div>Report detail content</div>}
              />
              <Route
                path="workflow-packages"
                element={<div>Workflow packages</div>}
              />
              <Route
                path="workflow-packages/import"
                element={<div>Import workspace</div>}
              />
              <Route
                path="workflow-packages/:packageId/run"
                element={
                  <div data-testid="workflow-package-launch-page">
                    Package launch content
                  </div>
                }
              />
              <Route
                path="scheduled-tasks"
                element={<div>Scheduled tasks</div>}
              />
              <Route
                path="runs/:runId"
                element={<div>Run detail content</div>}
              />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
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
  it("renders the static sidebar groups without extension state", () => {
    const { container } = renderLayout("/");

    expect(
      Array.from(container.querySelectorAll('[data-sidebar="group-label"]')).map(
        (label) => label.textContent,
      ),
    ).toEqual(groupedSidebarItems.map((group) => group.label));
    expect(screen.getByTestId("nav-dashboard")).toBeVisible();
    expect(screen.getByTestId("nav-templates")).toBeVisible();
    expect(screen.getByTestId("nav-reports")).toBeVisible();
    expect(screen.queryByTestId("nav-extensions")).not.toBeInTheDocument();
  });

  it("keeps finance sidebar items visible as static navigation", () => {
    renderLayout("/");

    const financeGroup = sidebarGroup(FINANCE_WORKSPACE_NAV_GROUP);
    expect(
      within(financeGroup)
        .getAllByRole("link")
        .map((link) => link.getAttribute("href")),
    ).toEqual(["/templates", "/reports"]);
  });

  it("maps width modes onto scroll routes", () => {
    renderLayout("/reports/example-report");

    const metadata = getRouteMetadataForPathname("/reports/example-report");
    const routedMain = screen.getByTestId(metadata.testId);
    const wrapper = Array.from(routedMain.querySelectorAll<HTMLElement>("div")).find(
      (element) =>
        element.className.includes("min-h-full") &&
        element.className.includes("max-w-full"),
    );

    expect(wrapper).toHaveClass(
      "min-h-full",
      "min-w-0",
      "max-w-full",
      "[&>*]:min-w-0",
      "[&>*]:w-full",
    );
    expect(wrapper?.parentElement).toHaveAttribute(
      "data-slot",
      "layout-scroll-viewport",
    );
  });

  it("marks full-height routed mains", () => {
    renderLayout("/workflow-packages/88/run");

    const routedMain = screen
      .getByTestId("workflow-package-launch-page")
      .closest("main");

    expect(routedMain).toHaveAttribute("data-route-shell-mode", "fullHeight");
    expect(routedMain).toHaveAttribute("data-route-width-mode", "full");
  });

  it("keeps metadata-owned shell chrome visible in dark mode", () => {
    localStorageState.set("signaldeck-theme", "dark");
    renderLayout("/workflow-packages");

    const metadata = getRouteMetadataForPathname("/workflow-packages");
    expect(document.documentElement).toHaveClass("dark");
    expect(screen.getByRole("banner")).toBeVisible();
    expect(screen.getByTestId(metadata.testId)).toHaveAttribute(
      "data-route-shell-mode",
      metadata.shellMode,
    );
  });
});
