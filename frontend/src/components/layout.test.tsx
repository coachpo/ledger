import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { ThemeProvider } from "@/components/theme-provider";
import {
  DIGITAL_ORACLE_EXTENSION_KEY,
  DIGITAL_ORACLE_LABEL,
  FINANCE_WORKSPACE_EXTENSION_KEY,
} from "@/extensions";
import { queryKeys } from "@/lib/query-keys";
import type { ExtensionListRead } from "@/lib/types/extension";
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

function extensionList(
  financeEnabled: boolean,
  digitalOracleEnabled = true,
): ExtensionListRead {
  return {
    items: [
      {
        key: FINANCE_WORKSPACE_EXTENSION_KEY,
        label: FINANCE_WORKSPACE_NAV_GROUP,
        enabled: financeEnabled,
      },
      {
        key: DIGITAL_ORACLE_EXTENSION_KEY,
        label: DIGITAL_ORACLE_LABEL,
        enabled: digitalOracleEnabled,
      },
    ],
  };
}

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

const financeSidebarGroup = groupedSidebarItems.find(
  (group) => group.label === FINANCE_WORKSPACE_NAV_GROUP,
);

if (!financeSidebarGroup) {
  throw new Error("Finance sidebar metadata group was not registered.");
}

function groupLabels(container: HTMLElement): (string | null)[] {
  return Array.from(
    container.querySelectorAll('[data-sidebar="group-label"]'),
  ).map((label) => label.textContent);
}

function sidebarGroup(label: string): HTMLElement {
  const labelElement = screen.getByText(label);
  const group = labelElement.closest<HTMLElement>('[data-sidebar="group"]');

  if (!group) {
    throw new Error(`Sidebar group not found for ${label}`);
  }

  return group;
}

const representativeShellRoutes = [
  { label: "dashboard", pathname: "/" },
  { label: "inventory", pathname: "/workflow-packages" },
  { label: "editor", pathname: "/workflow-packages/import" },
  { label: "workflow launch console", pathname: "/workflow-packages/88/run" },
  { label: "scheduled tasks inventory", pathname: "/scheduled-tasks" },
  { label: "scheduled task detail", pathname: "/scheduled-tasks/42" },
  { label: "run detail console", pathname: "/runs/42" },
  { label: "system state", pathname: "/extensions" },
] as const;

function expectSinglePageMain(container: HTMLElement, pathname: string) {
  const metadata = getRouteMetadataForPathname(pathname);
  const pageMains = screen.getAllByRole("main");
  const sidebarInset = container.querySelector<HTMLElement>(
    '[data-slot="sidebar-inset"]',
  );

  expect(pageMains).toHaveLength(1);
  expect(pageMains[0]).toBe(screen.getByTestId(metadata.testId));
  expect(pageMains[0]).toHaveAttribute(
    "data-route-shell-mode",
    metadata.shellMode,
  );
  expect(pageMains[0].querySelector("main")).toBeNull();
  expect(sidebarInset).not.toBeNull();
  expect(sidebarInset?.tagName).toBe("DIV");
  expect(sidebarInset).toContainElement(pageMains[0]);
  expect(
    within(screen.getByRole("banner")).getByText(metadata.breadcrumb.title),
  ).toBeInTheDocument();
}

function getLayoutContentWrapper(pathname: string) {
  const metadata = getRouteMetadataForPathname(pathname);
  const routedMain = screen.getByTestId(metadata.testId);
  const firstChild = routedMain.firstElementChild as HTMLElement | null;

  if (metadata.shellMode === "fullHeight") {
    return firstChild;
  }

  return (
    Array.from(routedMain.querySelectorAll<HTMLElement>("div")).find(
      (element) =>
        element.className.includes("min-h-full") &&
        element.className.includes("max-w-full"),
    ) ?? null
  );
}

describe("Layout", () => {
  function renderLayout(
    initialEntry: string,
    financeEnabled = true,
    digitalOracleEnabled = true,
  ) {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    queryClient.setQueryData(
      queryKeys.platform.extensions.list(),
      extensionList(financeEnabled, digitalOracleEnabled),
    );

    return render(
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={[initialEntry]}>
            <Routes>
              <Route element={<Layout />}>
                <Route index element={<div>Dashboard content</div>} />
                <Route
                  path="extensions"
                  element={
                    <div data-testid="extensions-content">
                      Extensions system state
                    </div>
                  }
                />
                <Route
                  path="workflow-packages"
                  element={
                    <div data-testid="workflow-packages-list-content">
                      Package inventory content
                    </div>
                  }
                />
                <Route
                  path="model-connections"
                  element={
                    <div data-testid="model-connections-list-content">
                      Model connections inventory content
                    </div>
                  }
                />
                <Route
                  path="memory"
                  element={
                    <div data-testid="memory-workspace-content">
                      Memory inspection workspace
                    </div>
                  }
                />
                <Route
                  path="scheduled-tasks"
                  element={
                    <div data-testid="scheduled-tasks-list-content">
                      Scheduled tasks inventory content
                    </div>
                  }
                />
                <Route
                  path="scheduled-tasks/new"
                  element={
                    <div data-testid="scheduled-task-new-content">
                      Scheduled task creation workspace
                    </div>
                  }
                />
                <Route
                  path="scheduled-tasks/:scheduleId"
                  element={
                    <div data-testid="scheduled-task-detail-content">
                      Scheduled task detail workspace
                    </div>
                  }
                />
                <Route
                  path="workflow-packages/import"
                  element={
                    <div data-testid="workflow-package-import-content">
                      Import workspace
                    </div>
                  }
                />
                <Route
                  path="workflow-packages/:packageId"
                  element={<div>Package detail content</div>}
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
                  path="reports/:slug"
                  element={
                    <div data-testid="report-detail-content">
                      Report detail content
                    </div>
                  }
                />
                <Route
                  path="runs/:runId"
                  element={
                    <div data-testid="run-detail-content">
                      Run detail workspace
                    </div>
                  }
                />
              </Route>
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </ThemeProvider>,
    );
  }

  it.each(representativeShellRoutes)(
    "exposes one page main landmark for the $label route",
    ({ pathname }) => {
      const { container } = renderLayout(pathname);

      expectSinglePageMain(container, pathname);
    },
  );

  it("renders compact shell chrome and emphasizes the active route", () => {
    const { container } = renderLayout("/workflow-packages");
    const metadata = getRouteMetadataForPathname("/workflow-packages");
    const banner = screen.getByRole("banner");
    const sidebarHeader = container.querySelector<HTMLElement>(
      '[data-sidebar="header"]',
    );
    const sidebarInset = container.querySelector<HTMLElement>(
      '[data-slot="sidebar-inset"]',
    );
    const activeItem = screen.getByTestId(metadata.nav.testId);

    expect(banner).toHaveClass(
      "h-[var(--ui-layout-header-height)]",
      "gap-2",
      "px-3",
      "bg-ui-surface-chrome",
    );
    expect(sidebarHeader).toHaveClass(
      "h-[var(--ui-layout-header-height)]",
      "px-3",
    );
    expect(sidebarInset).toHaveClass(
      "md:peer-data-[variant=inset]:my-2",
      "md:peer-data-[variant=inset]:mr-2",
      "md:peer-data-[variant=inset]:rounded-r-xl",
      "md:peer-data-[variant=inset]:shadow-ui-sm",
    );
    expect(activeItem).toHaveAttribute("data-active", "true");
    expect(activeItem).toHaveClass(
      "data-[active=true]:bg-sidebar-primary/12",
      "data-[active=true]:font-semibold",
      "data-[active=true]:text-sidebar-primary",
    );
    expect(screen.getByTestId("nav-dashboard")).toHaveAttribute(
      "data-active",
      "false",
    );
  });

  it("maps width modes onto the scroll shell wrappers", () => {
    const routeCases = [
      {
        pathname: "/workflow-packages",
        wrapperClassNames: [
          "min-h-full",
          "min-w-0",
          "max-w-full",
          "[&>*]:min-w-0",
          "[&>*]:w-full",
        ],
      },
      {
        pathname: "/extensions",
        wrapperClassNames: [
          "min-h-full",
          "min-w-0",
          "max-w-full",
          "[&>*]:min-w-0",
          "[&>*]:w-full",
        ],
      },
      {
        pathname: "/reports/example-report",
        wrapperClassNames: [
          "min-h-full",
          "min-w-0",
          "max-w-full",
          "[&>*]:min-w-0",
          "[&>*]:w-full",
        ],
      },
    ] as const;

    for (const { pathname, wrapperClassNames } of routeCases) {
      const { unmount } = renderLayout(pathname);

      const wrapper = getLayoutContentWrapper(pathname);

      expect(wrapper).toHaveClass(...wrapperClassNames);
      unmount();
    }
  });

  it("marks full-height routed mains and preserves the outlet path", () => {
    const { container } = renderLayout("/workflow-packages/88/run");
    const routedMain = screen
      .getByTestId("workflow-package-launch-page")
      .closest("main");
    const fullHeightWrapper = screen.getByTestId(
      "workflow-package-launch-page",
    ).parentElement;

    expect(routedMain).toHaveAttribute("data-route-shell-mode", "fullHeight");
    expect(routedMain).toHaveAttribute("data-route-width-mode", "full");
    expect(fullHeightWrapper).toHaveClass(
      "h-full",
      "[&>*]:h-full",
      "[&>*]:w-full",
    );
    expect(container.querySelector('[data-slot="scroll-area"]')).toBeNull();
  });

  it("shows extension-aware grouped shell navigation when finance is enabled", () => {
    const { container } = renderLayout("/");

    expect(groupLabels(container)).toEqual(
      groupedSidebarItems.map((group) => group.label),
    );
    expect(
      screen
        .getAllByRole("link")
        .filter((link) => link.getAttribute("href") !== "#app-main")
        .map((link) => link.getAttribute("href")),
    ).toEqual(
      groupedSidebarItems.flatMap((group) =>
        group.items.map((item) => item.href),
      ),
    );

    for (const group of groupedSidebarItems) {
      const renderedGroup = sidebarGroup(group.label);
      expect(
        within(renderedGroup)
          .getAllByRole("link")
          .map((link) => link.getAttribute("href")),
      ).toEqual(group.items.map((item) => item.href));

      for (const item of group.items) {
        expect(
          within(renderedGroup).getByTestId(item.testId),
        ).toHaveTextContent(item.label);
      }
    }

    expect(
      screen.queryByRole("link", { name: /backtests/i }),
    ).not.toBeInTheDocument();
  });

  it("keeps finance navigation when only Digital Oracle is disabled", () => {
    const { container } = renderLayout("/", true, false);

    expect(groupLabels(container)).toEqual(
      groupedSidebarItems.map((group) => group.label),
    );
    expect(sidebarGroup(FINANCE_WORKSPACE_NAV_GROUP)).toBeInTheDocument();
    expect(screen.getByTestId("nav-dashboard")).toBeVisible();
    expect(screen.getByTestId("nav-reports")).toBeVisible();
    expect(screen.queryByText(DIGITAL_ORACLE_LABEL)).not.toBeInTheDocument();
  });

  it("hides finance navigation while preserving grouped core entries when disabled", () => {
    const { container } = renderLayout("/workflow-packages/88", false, true);
    const coreGroups = groupedSidebarItems.filter(
      (group) => group.label !== FINANCE_WORKSPACE_NAV_GROUP,
    );

    expect(groupLabels(container)).toEqual(
      coreGroups.map((group) => group.label),
    );
    expect(
      screen.queryByText(FINANCE_WORKSPACE_NAV_GROUP),
    ).not.toBeInTheDocument();

    for (const item of financeSidebarGroup.items) {
      expect(screen.queryByTestId(item.testId)).not.toBeInTheDocument();
    }

    for (const group of coreGroups) {
      const renderedGroup = sidebarGroup(group.label);
      expect(
        within(renderedGroup)
          .getAllByRole("link")
          .map((link) => link.getAttribute("href")),
      ).toEqual(group.items.map((item) => item.href));
    }
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
    expect(screen.getByTestId("nav-workflow-packages")).toHaveTextContent(
      metadata.nav.label,
    );
  });

  it("restores the finance group after re-enable", () => {
    const enabled = renderLayout("/");
    expect(sidebarGroup(FINANCE_WORKSPACE_NAV_GROUP)).toBeInTheDocument();
    enabled.unmount();

    const disabled = renderLayout("/workflow-packages/88", false);
    expect(
      screen.queryByText(FINANCE_WORKSPACE_NAV_GROUP),
    ).not.toBeInTheDocument();
    for (const item of financeSidebarGroup.items) {
      expect(screen.queryByTestId(item.testId)).not.toBeInTheDocument();
    }
    disabled.unmount();

    renderLayout("/");
    expect(sidebarGroup(FINANCE_WORKSPACE_NAV_GROUP)).toBeInTheDocument();
    const reportsItem = financeSidebarGroup.items.find(
      (item) => item.href === getRouteMetadataForPathname("/reports").nav.path,
    );

    if (!reportsItem) {
      throw new Error("Reports sidebar metadata was not registered.");
    }

    expect(screen.getByTestId(reportsItem.testId)).toHaveAttribute(
      "href",
      reportsItem.href,
    );
  });

  it("labels workflow package import, detail, and launch routes", () => {
    const importMetadata = getRouteMetadataForPathname(
      "/workflow-packages/import",
    );
    renderLayout("/workflow-packages/import");
    expect(
      within(screen.getByRole("banner")).getByText(
        importMetadata.breadcrumb.title,
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId(importMetadata.testId)).toHaveAttribute(
      "data-route-shell-mode",
      importMetadata.shellMode,
    );
    expect(
      screen.getByTestId("workflow-package-import-content").parentElement,
    ).toHaveClass("h-full");

    const detailMetadata = getRouteMetadataForPathname("/workflow-packages/88");
    renderLayout("/workflow-packages/88");
    expect(
      within(screen.getAllByRole("banner")[1]).getByText(
        detailMetadata.breadcrumb.title,
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId(detailMetadata.testId)).toHaveAttribute(
      "data-route-shell-mode",
      detailMetadata.shellMode,
    );

    const launchMetadata = getRouteMetadataForPathname(
      "/workflow-packages/88/run",
    );
    renderLayout("/workflow-packages/88/run");
    expect(
      within(screen.getAllByRole("banner")[2]).getByText(
        launchMetadata.breadcrumb.title,
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId(launchMetadata.testId)).toHaveAttribute(
      "data-route-shell-mode",
      launchMetadata.shellMode,
    );
    expect(
      screen.getByTestId("workflow-package-launch-page").parentElement,
    ).toHaveClass("h-full");
  });

  it("labels scheduled tasks routes with metadata-owned breadcrumbs and shell modes", () => {
    const listMetadata = getRouteMetadataForPathname("/scheduled-tasks");
    renderLayout("/scheduled-tasks");
    expect(screen.getByTestId("nav-scheduled-tasks")).toHaveTextContent(
      listMetadata.nav.label,
    );
    expect(screen.getByTestId(listMetadata.testId)).toHaveAttribute(
      "data-route-shell-mode",
      "scroll",
    );
    expect(
      within(screen.getByRole("banner")).getByText(
        listMetadata.breadcrumb.title,
      ),
    ).toBeInTheDocument();

    const newMetadata = getRouteMetadataForPathname("/scheduled-tasks/new");
    renderLayout("/scheduled-tasks/new");
    expect(
      within(screen.getAllByRole("banner")[1]).getByText(
        newMetadata.breadcrumb.parent?.title ?? "",
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getAllByRole("banner")[1]).getByText(
        newMetadata.breadcrumb.title,
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId(newMetadata.testId)).toHaveAttribute(
      "data-route-shell-mode",
      "fullHeight",
    );
    expect(
      screen.getByTestId("scheduled-task-new-content").parentElement,
    ).toHaveClass("h-full");

    const detailMetadata = getRouteMetadataForPathname("/scheduled-tasks/42");
    renderLayout("/scheduled-tasks/42");
    expect(
      within(screen.getAllByRole("banner")[2]).getByText(
        detailMetadata.breadcrumb.title,
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId(detailMetadata.testId)).toHaveAttribute(
      "data-route-shell-mode",
      "fullHeight",
    );
    expect(
      screen.getByTestId("scheduled-task-detail-content").parentElement,
    ).toHaveClass("h-full");
  });

  it("gives run detail routes full-height workspace treatment", () => {
    const runMetadata = getRouteMetadataForPathname("/runs/42");
    renderLayout("/runs/42");

    const workspace = screen.getByTestId("run-detail-content");
    expect(
      within(screen.getByRole("banner")).getByText(
        runMetadata.breadcrumb.title,
      ),
    ).toBeInTheDocument();
    expect(runMetadata.shellMode).toBe("fullHeight");
    expect(screen.getByTestId(runMetadata.testId)).toHaveAttribute(
      "data-route-shell-mode",
      runMetadata.shellMode,
    );
    expect(workspace.parentElement).toHaveClass("h-full");
  });
});
