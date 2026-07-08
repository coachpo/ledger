import type { ComponentType } from "react";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, matchRoutes, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { Layout } from "./components/layout";
import { ThemeProvider } from "./components/theme-provider";
import {
  DIGITAL_ORACLE_EXTENSION_KEY,
  DIGITAL_ORACLE_LABEL,
  FINANCE_WORKSPACE_EXTENSION_KEY,
  getBundledFrontendExtension,
  listBundledFrontendExtensions,
} from "./extensions";
import {
  assembleNavGroups,
  enabledFinanceRoutePaths,
  filterToolsForExtensionState,
} from "./extensions/runtime-helpers";
import {
  allRouteMetadata,
  assertRouteMetadataCoverage,
  FINANCE_WORKSPACE_NAV_GROUP,
  getRouteMetadataByPattern,
  getRouteMetadataForPathname,
  getSidebarRouteMetadataGroups,
  liveRouteMetadata,
  routePatternsFromDefinitions,
  unknownRouteMetadata,
  type RouteCoverageDefinition,
  type RouteMetadata,
  type RoutePattern,
} from "./routes.metadata";
import { queryKeys } from "./lib/query-keys";
import type { ExtensionListRead } from "./lib/types/extension";
import { NotFoundPage } from "./pages/not-found";
import { RouteErrorPage } from "./pages/route-error";
import { router } from "./routes";

Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: {
    getItem: () => null,
    removeItem: () => undefined,
    setItem: () => undefined,
  },
});

const LIVE_BROWSER_ROUTE_PREFIXES = [
  "/workflow-packages",
  "/scheduled-tasks",
  "/model-connections",
  "/runs",
  "/extensions",
];
const LIVE_PLATFORM_NAV_ENTRIES = [
  {
    label: "Workflow Packages",
    testId: "nav-workflow-packages",
    to: "/workflow-packages",
  },
  {
    label: "Scheduled Tasks",
    testId: "nav-scheduled-tasks",
    to: "/scheduled-tasks",
  },
  {
    label: "Model Connections",
    testId: "nav-model-connections",
    to: "/model-connections",
  },
  { label: "Extensions", testId: "nav-extensions", to: "/extensions" },
  { label: "Runs", testId: "nav-runs", to: "/runs" },
] as const;

function sampleExtensionRoutePath(path: string) {
  return path
    .replace(":templateId", "456")
    .replace(":slug", "sample-report");
}

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

function expectCanonicalGateLayout(testId: string) {
  const gate = screen.getByTestId(testId);
  const content = screen.getByTestId("extension-gate-content");
  const status = screen.getByTestId("extension-gate-status");
  const statusStrip = status.querySelector("[role='list']");
  const meta = screen.getByTestId("extension-gate-meta");
  const panel = screen.getByTestId("extension-gate-panel");

  expect(gate).toHaveClass(
    "min-h-full",
    "px-4",
    "py-8",
    "sm:px-6",
    "sm:py-10",
    "lg:px-8",
  );
  expect(content).toHaveClass("w-full", "max-w-6xl", "flex-col", "gap-6");
  expect(status).toHaveClass("w-full", "min-w-0");
  expect(statusStrip).toHaveClass(
    "w-full",
    "max-w-none",
    "justify-start",
    "flex-wrap",
  );
  expect(meta).toHaveClass("w-full", "min-w-0", "flex-wrap", "gap-2");
  expect(panel).toHaveClass("w-full", "max-w-none");
}

function isMetadataVisibleForExtensions(
  metadata: RouteMetadata,
  extensions: ExtensionListRead | undefined,
): boolean {
  if (metadata.owner.kind !== "extension") {
    return true;
  }

  const { extensionKey } = metadata.owner;

  return (
    extensions?.items.find((extension) => extension.key === extensionKey)
      ?.enabled === true
  );
}

function navItemSummaryFromMetadata(metadata: RouteMetadata) {
  if (!metadata.nav.path) {
    throw new Error(
      `Sidebar metadata is missing a nav path for ${metadata.pattern}`,
    );
  }

  return {
    label: metadata.nav.label,
    testId: metadata.nav.testId,
    to: metadata.nav.path,
  };
}

function navGroupSummaryFromMetadata(
  extensions: ExtensionListRead | undefined,
) {
  return getSidebarRouteMetadataGroups()
    .map((group) => ({
      items: group.items
        .filter((metadata) =>
          isMetadataVisibleForExtensions(metadata, extensions),
        )
        .map(navItemSummaryFromMetadata),
      label: group.label,
    }))
    .filter((group) => group.items.length > 0);
}

function routePatternStartsWithPrefix(pattern: string, prefix: string) {
  return pattern === prefix || pattern.startsWith(`${prefix}/`);
}

function navItemsFromGroups(groups: ReturnType<typeof assembleNavGroups>) {
  return groups.flatMap((group) => group.items);
}

type RootRouteWithChildren = {
  children?: readonly RouteCoverageDefinition[];
  path?: string;
};

function registeredChildRoutes(): readonly RouteCoverageDefinition[] {
  const rootRoute = router.routes.find((route) => route.path === "/") as
    | RootRouteWithChildren
    | undefined;

  if (!rootRoute?.children) {
    throw new Error("Root layout route children were not registered.");
  }

  return rootRoute.children;
}

describe("router", () => {
  it("keeps route metadata coverage aligned with registered live routes", () => {
    const registeredPatterns = routePatternsFromDefinitions(
      registeredChildRoutes(),
    );

    expect(registeredPatterns).toEqual(
      allRouteMetadata.map((metadata) => metadata.pattern),
    );
    expect(() =>
      assertRouteMetadataCoverage(registeredChildRoutes()),
    ).not.toThrow();
    expect(liveRouteMetadata.map((metadata) => metadata.pattern)).not.toContain(
      "*",
    );
    expect(allRouteMetadata.map((metadata) => metadata.pattern)).toContain("*");
    expect(getRouteMetadataForPathname("/does-not-exist")).toBe(
      unknownRouteMetadata,
    );
  });

  it("registers live platform route prefixes in route registration and metadata", () => {
    const registeredPatterns = routePatternsFromDefinitions(
      registeredChildRoutes(),
    );
    const livePatterns = liveRouteMetadata.map((metadata) => metadata.pattern);
    const sidebarPaths = liveRouteMetadata.flatMap((metadata) =>
      metadata.nav.path ? [metadata.nav.path] : [],
    );

    for (const prefix of LIVE_BROWSER_ROUTE_PREFIXES) {
      expect(
        registeredPatterns.some((pattern) =>
          routePatternStartsWithPrefix(pattern, prefix),
        ),
      ).toBe(true);
      expect(
        livePatterns.some((pattern) =>
          routePatternStartsWithPrefix(pattern, prefix),
        ),
      ).toBe(true);
      expect(
        sidebarPaths.some((path) => routePatternStartsWithPrefix(path, prefix)),
      ).toBe(true);
    }
  });

  it("classifies dashboard, platform inventories, runs monitor, and system state routes", () => {
    expect(getRouteMetadataByPattern("/")).toMatchObject({
      archetype: "dashboard",
      owner: { kind: "platform" },
      widthMode: "wide",
      stateVariants: ["loading", "ready", "error"],
      testId: "route-dashboard",
    });
    expect(getRouteMetadataByPattern("/workflow-packages")).toMatchObject({
      archetype: "inventory",
      owner: { kind: "platform" },
      widthMode: "wide",
      stateVariants: ["loading", "ready", "error", "empty", "filteredEmpty"],
      testId: "route-workflow-packages-list",
    });
    expect(getRouteMetadataByPattern("/model-connections")).toMatchObject({
      archetype: "inventory",
      owner: { kind: "platform" },
      widthMode: "wide",
      stateVariants: ["loading", "ready", "error", "empty", "filteredEmpty"],
      testId: "route-model-connections-list",
    });
    expect(getRouteMetadataByPattern("/scheduled-tasks")).toMatchObject({
      archetype: "inventory",
      breadcrumb: { title: "Scheduled Tasks" },
      nav: {
        group: "Agent Platform",
        label: "Scheduled Tasks",
        path: "/scheduled-tasks",
        sidebar: true,
        testId: "nav-scheduled-tasks",
      },
      owner: { kind: "platform" },
      shellMode: "scroll",
      widthMode: "wide",
      stateVariants: ["loading", "ready", "error", "empty", "filteredEmpty"],
      testId: "route-scheduled-tasks-list",
    });
    expect(getRouteMetadataByPattern("/runs")).toMatchObject({
      archetype: "inventory",
      owner: { kind: "platform" },
      widthMode: "wide",
      stateVariants: [
        "loading",
        "ready",
        "error",
        "empty",
        "filteredEmpty",
        "polling",
      ],
      testId: "route-runs-list",
    });
    expect(getRouteMetadataByPattern("/extensions")).toMatchObject({
      archetype: "systemState",
      owner: { kind: "system" },
      widthMode: "wide",
      stateVariants: ["loading", "ready", "error", "empty"],
      testId: "route-extensions",
    });
  });

  it("requires every metadata entry to declare the route ownership contract", () => {
    const patterns = new Set(
      allRouteMetadata.map((metadata) => metadata.pattern),
    );
    const testIds = new Set(
      allRouteMetadata.map((metadata) => metadata.testId),
    );

    expect(patterns.size).toBe(allRouteMetadata.length);
    expect(testIds.size).toBe(allRouteMetadata.length);

    for (const metadata of allRouteMetadata) {
      expect(metadata.archetype).toBeTruthy();
      expect(metadata.breadcrumb.title).toBeTruthy();
      expect(metadata.nav.group).toBeTruthy();
      expect(metadata.nav.label).toBeTruthy();
      expect(metadata.nav.testId).toBeTruthy();
      expect(["scroll", "fullHeight"]).toContain(metadata.shellMode);
      expect(["wide", "full", "compact", "readable"]).toContain(
        metadata.widthMode,
      );
      expect(metadata.stateVariants.length).toBeGreaterThan(0);
      expect(metadata.testId).toMatch(/^route-/);

      if (metadata.nav.sidebar) {
        expect(metadata.nav.path).toBe(metadata.pattern);
        expect(metadata.nav.testId).toMatch(/^nav-/);
      }
    }
  });

  it("keeps global guardrail coverage aligned to live route archetypes", () => {
    expect(
      new Set(allRouteMetadata.map((metadata) => metadata.archetype)),
    ).toEqual(
      new Set([
        "dashboard",
        "inventory",
        "detail",
        "editor",
        "console",
        "systemState",
        "unknown",
      ]),
    );

    expect(getRouteMetadataByPattern("/reports")?.stateVariants).toEqual(
      expect.arrayContaining([
        "loading",
        "ready",
        "error",
        "empty",
        "filteredEmpty",
        "disabledExtension",
      ]),
    );
    expect(
      getRouteMetadataByPattern("/workflow-packages/:packageId/run"),
    ).toMatchObject({
      archetype: "console",
      shellMode: "fullHeight",
      widthMode: "full",
      stateVariants: expect.arrayContaining([
        "loading",
        "ready",
        "error",
        "launching",
        "notFound",
      ]),
    });
    expect(getRouteMetadataByPattern("/runs/:runId")).toMatchObject({
      archetype: "console",
      shellMode: "fullHeight",
      widthMode: "full",
      stateVariants: expect.arrayContaining([
        "loading",
        "ready",
        "error",
        "notFound",
        "polling",
      ]),
    });
    expect(getRouteMetadataByPattern("/reports/:slug")).toMatchObject({
      archetype: "detail",
      shellMode: "scroll",
      widthMode: "wide",
    });
    expect(getRouteMetadataByPattern("/scheduled-tasks/new")).toMatchObject({
      archetype: "editor",
      breadcrumb: {
        parent: { href: "/scheduled-tasks", title: "Scheduled Tasks" },
        title: "New Scheduled Task",
      },
      shellMode: "fullHeight",
      widthMode: "full",
      stateVariants: expect.arrayContaining([
        "creating",
        "saving",
        "validating",
        "error",
      ]),
      testId: "route-scheduled-task-new",
    });
    expect(
      getRouteMetadataByPattern("/scheduled-tasks/:scheduleId"),
    ).toMatchObject({
      archetype: "console",
      breadcrumb: {
        parent: { href: "/scheduled-tasks", title: "Scheduled Tasks" },
        title: "Scheduled Task Detail",
      },
      shellMode: "fullHeight",
      widthMode: "full",
      stateVariants: expect.arrayContaining([
        "loading",
        "ready",
        "editing",
        "saving",
        "validating",
        "error",
        "notFound",
        "polling",
      ]),
      testId: "route-scheduled-task-detail",
    });
    expect(getRouteMetadataByPattern("/templates/new")).toMatchObject({
      archetype: "editor",
      shellMode: "fullHeight",
      widthMode: "full",
    });
    expect(
      getRouteMetadataByPattern("/templates/:templateId/edit"),
    ).toMatchObject({
      archetype: "editor",
      shellMode: "fullHeight",
      widthMode: "full",
    });
    expect(unknownRouteMetadata).toMatchObject({
      archetype: "unknown",
      shellMode: "scroll",
      widthMode: "wide",
      stateVariants: ["notFound"],
      testId: "route-unknown",
    });
  });

  it("assembles sidebar labels and test ids from route metadata", () => {
    const enabledExtensions = extensionList(true);
    const disabledExtensions = extensionList(false);

    expect(
      assembleNavGroups(enabledExtensions).map((group) => ({
        items: group.items.map((item) => ({
          label: item.label,
          testId: item.testId,
          to: item.to,
        })),
        label: group.label,
      })),
    ).toEqual(navGroupSummaryFromMetadata(enabledExtensions));
    expect(
      assembleNavGroups(disabledExtensions).map((group) => ({
        items: group.items.map((item) => ({
          label: item.label,
          testId: item.testId,
          to: item.to,
        })),
        label: group.label,
      })),
    ).toEqual(navGroupSummaryFromMetadata(disabledExtensions));
  });

  it("keeps live platform controls under mocked extension state", () => {
    const extensionStates = [
      extensionList(true, true),
      extensionList(false, true),
    ];

    for (const extensions of extensionStates) {
      const navItems = navItemsFromGroups(assembleNavGroups(extensions));

      for (const liveEntry of LIVE_PLATFORM_NAV_ENTRIES) {
        expect(navItems).toEqual(
          expect.arrayContaining([expect.objectContaining(liveEntry)]),
        );
      }
    }
  });

  it("captures full-height shell ownership in route metadata", () => {
    expect(
      liveRouteMetadata
        .filter((metadata) => metadata.shellMode === "fullHeight")
        .map((metadata) => metadata.pattern),
    ).toEqual([
      "/templates/new",
      "/templates/:templateId/edit",
      "/workflow-packages/import",
      "/workflow-packages/new",
      "/workflow-packages/:packageId",
      "/workflow-packages/:packageId/run",
      "/model-connections/new",
      "/model-connections/:modelConnectionId/edit",
      "/scheduled-tasks/new",
      "/scheduled-tasks/:scheduleId",
      "/runs/:runId",
    ]);
  });

  it("registers workflow package routes", () => {
    const registeredPatterns = routePatternsFromDefinitions(
      registeredChildRoutes(),
    );

    expect(matchRoutes(router.routes, "/workflow-packages")).not.toBeNull();
    expect(
      matchRoutes(router.routes, "/workflow-packages/import"),
    ).not.toBeNull();
    expect(matchRoutes(router.routes, "/workflow-packages/new")).not.toBeNull();
    expect(matchRoutes(router.routes, "/workflow-packages/123")).not.toBeNull();
    expect(
      matchRoutes(router.routes, "/workflow-packages/123/run"),
    ).not.toBeNull();

    for (const prefix of LIVE_BROWSER_ROUTE_PREFIXES) {
      expect(
        registeredPatterns.some((pattern) =>
          routePatternStartsWithPrefix(pattern, prefix),
        ),
      ).toBe(true);
    }
  });

  it("keeps global model connection, scheduled tasks, and run routes", () => {
    expect(matchRoutes(router.routes, "/model-connections")).not.toBeNull();
    expect(matchRoutes(router.routes, "/model-connections/new")).not.toBeNull();
    expect(
      matchRoutes(router.routes, "/model-connections/123/edit"),
    ).not.toBeNull();
    expect(matchRoutes(router.routes, "/scheduled-tasks")).not.toBeNull();
    expect(matchRoutes(router.routes, "/scheduled-tasks/new")).not.toBeNull();
    expect(matchRoutes(router.routes, "/scheduled-tasks/123")).not.toBeNull();
    expect(getRouteMetadataForPathname("/scheduled-tasks")?.testId).toBe(
      "route-scheduled-tasks-list",
    );
    expect(getRouteMetadataForPathname("/scheduled-tasks/123")?.testId).toBe(
      "route-scheduled-task-detail",
    );
    expect(matchRoutes(router.routes, "/runs")).not.toBeNull();
    expect(matchRoutes(router.routes, "/runs/123")).not.toBeNull();
  });

  it("renders a product-owned catch-all 404 inside the app shell", async () => {
    const testRouter = createMemoryRouter(router.routes, {
      initialEntries: ["/does-not-exist"],
    });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    queryClient.setQueryData(
      queryKeys.platform.extensions.list(),
      extensionList(true),
    );

    render(
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={testRouter} />
        </QueryClientProvider>
      </ThemeProvider>,
    );

    expect(await screen.findByTestId("route-unknown")).toHaveAttribute(
      "data-route-shell-mode",
      "scroll",
    );
    expect(screen.getByTestId("route-unknown")).toHaveAttribute(
      "data-route-width-mode",
      "wide",
    );
    expect(screen.getByTestId("not-found-page")).toBeVisible();
    expect(
      screen.getByRole("heading", { level: 1, name: "Page not found" }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Open workflow packages" }),
    ).toHaveAttribute("href", "/workflow-packages");
    expect(
      screen.queryByText("Unexpected Application Error!"),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("route-error-page")).not.toBeInTheDocument();
  });

  it("renders the routed error boundary for thrown route errors", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const ThrowingRoute: ComponentType = () => {
      throw new Error("Route harness failure");
    };
    const testRouter = createMemoryRouter([
      {
        path: "/",
        Component: Layout,
        ErrorBoundary: RouteErrorPage,
        children: [
          { index: true, Component: ThrowingRoute },
          { path: "*", Component: NotFoundPage },
        ],
      },
    ]);

    render(
      <ThemeProvider>
        <QueryClientProvider client={new QueryClient()}>
          <RouterProvider router={testRouter} />
        </QueryClientProvider>
      </ThemeProvider>,
    );

    expect(await screen.findByTestId("route-error-page")).toBeVisible();
    expect(
      screen.getByRole("heading", { level: 1, name: "Route failed to render" }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Open workflow packages" }),
    ).toHaveAttribute("href", "/workflow-packages");
    expect(
      screen.queryByText("Unexpected Application Error!"),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("not-found-page")).not.toBeInTheDocument();
    expect(screen.queryByText("Route harness failure")).not.toBeInTheDocument();
    consoleError.mockRestore();
  });

  it("assembles bundled extension contributions by owning scaffold", () => {
    const financeExtension = getBundledFrontendExtension(
      FINANCE_WORKSPACE_EXTENSION_KEY,
    );
    const digitalOracleExtension = getBundledFrontendExtension(
      DIGITAL_ORACLE_EXTENSION_KEY,
    );
    if (!financeExtension || !digitalOracleExtension) {
      throw new Error("Bundled frontend extensions were not registered.");
    }

    expect(listBundledFrontendExtensions()).toEqual([
      financeExtension,
      digitalOracleExtension,
    ]);
    for (const extension of [financeExtension, digitalOracleExtension]) {
      expect(Object.keys(extension).sort()).toEqual([
        "key",
        "label",
        "navContributions",
        "routeContributions",
        "toolAuthoringDiscovery",
      ]);
    }
    expect(financeExtension.key).toBe("signaldeck.finance");
    expect(digitalOracleExtension.key).toBe("signaldeck.digital_oracle");
    expect(digitalOracleExtension.label).toBe(DIGITAL_ORACLE_LABEL);
    expect(digitalOracleExtension.routeContributions).toEqual([]);
    expect(digitalOracleExtension.navContributions).toEqual([]);

    const financeRouteContracts = financeExtension.routeContributions.map(
      (contribution) => ({
        path: contribution.path,
        requiredExtensionKey: contribution.requiredExtensionKey,
        routeMetadata: contribution.routeMetadata,
      }),
    );

    expect(
      financeExtension.routeContributions.map((contribution) =>
        Object.keys(contribution).sort(),
      ),
    ).toEqual(
      financeExtension.routeContributions.map(() => [
        "lazy",
        "path",
        "requiredExtensionKey",
        "routeMetadata",
      ]),
    );
    expect(financeRouteContracts).toEqual(
      liveRouteMetadata
        .filter((metadata) => metadata.owner.kind === "extension")
        .map((metadata) => {
          if (metadata.owner.kind !== "extension") {
            throw new Error("Expected extension-owned route metadata.");
          }

          const { owner, pattern, ...routeMetadata } = metadata;

          return {
            path: pattern,
            requiredExtensionKey: owner.extensionKey,
            routeMetadata,
          };
        }),
    );
    expect(financeExtension.navContributions).toEqual(
      financeExtension.routeContributions
        .filter((contribution) => contribution.routeMetadata.nav.sidebar)
        .map((contribution) => {
          const { nav } = contribution.routeMetadata;

          if (!nav.path) {
            throw new Error(
              "Expected sidebar finance route to own a nav path.",
            );
          }

          return {
            iconName: nav.iconName,
            label: nav.label,
            requiredExtensionKey: contribution.requiredExtensionKey,
            testId: nav.testId,
            to: nav.path,
          };
        }),
    );

    for (const contribution of financeExtension.navContributions) {
      const metadata = getRouteMetadataByPattern(
        contribution.to as RoutePattern,
      );

      expect(contribution.requiredExtensionKey).toBe(
        FINANCE_WORKSPACE_EXTENSION_KEY,
      );
      expect(metadata?.nav).toMatchObject({
        group: FINANCE_WORKSPACE_NAV_GROUP,
        label: contribution.label,
        path: contribution.to,
        sidebar: true,
        testId: contribution.testId,
      });
    }

    expect(enabledFinanceRoutePaths(extensionList(true))).toEqual(
      financeExtension.routeContributions.map(
        (contribution) => contribution.path,
      ),
    );
    expect(enabledFinanceRoutePaths(extensionList(false))).toEqual([]);

    for (const contribution of financeExtension.routeContributions) {
      expect(
        matchRoutes(router.routes, sampleExtensionRoutePath(contribution.path)),
      ).not.toBeNull();
    }

    expect(
      financeExtension.routeContributions.some((contribution) =>
        contribution.path.startsWith("/workflow-packages"),
      ),
    ).toBe(false);
    expect(financeExtension.toolAuthoringDiscovery).toEqual([
      {
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
        toolKeyPrefix: "signaldeck.finance.market_data.",
      },
      {
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
        toolKeyPrefix: "signaldeck.finance.indicators.",
      },
      {
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
        toolKeyPrefix: "signaldeck.finance.fundamentals.",
      },
      {
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
        toolKeyPrefix: "signaldeck.finance.news.",
      },
      {
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
        toolKeyPrefix: "signaldeck.finance.social_sentiment.",
      },
      {
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
        toolKeyPrefix: "signaldeck.finance.insider_data.",
      },
      {
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
        toolKeyPrefix: "signaldeck.finance.reports.",
      },
    ]);
    expect(digitalOracleExtension.toolAuthoringDiscovery).toEqual([
      {
        requiredExtensionKey: DIGITAL_ORACLE_EXTENSION_KEY,
        toolKeyPrefix: "signaldeck.digital_oracle.prediction_markets.",
      },
      {
        requiredExtensionKey: DIGITAL_ORACLE_EXTENSION_KEY,
        toolKeyPrefix: "signaldeck.digital_oracle.sec_filings.",
      },
      {
        requiredExtensionKey: DIGITAL_ORACLE_EXTENSION_KEY,
        toolKeyPrefix: "signaldeck.digital_oracle.market_sentiment.",
      },
      {
        requiredExtensionKey: DIGITAL_ORACLE_EXTENSION_KEY,
        toolKeyPrefix: "signaldeck.digital_oracle.macro_rates.",
      },
      {
        requiredExtensionKey: DIGITAL_ORACLE_EXTENSION_KEY,
        toolKeyPrefix: "signaldeck.digital_oracle.crypto_derivatives.",
      },
      {
        requiredExtensionKey: DIGITAL_ORACLE_EXTENSION_KEY,
        toolKeyPrefix: "signaldeck.digital_oracle.cftc_positioning.",
      },
      {
        requiredExtensionKey: DIGITAL_ORACLE_EXTENSION_KEY,
        toolKeyPrefix: "signaldeck.digital_oracle.options.",
      },
    ]);
  });

  it("filters bundled extension tool discovery while preserving finance route gates", () => {
    const extension = getBundledFrontendExtension(
      FINANCE_WORKSPACE_EXTENSION_KEY,
    );
    if (!extension) {
      throw new Error(
        "Finance workspace frontend extension was not registered.",
      );
    }
    const tools = [
      {
        key: "signaldeck.finance.reports.lookup",
        displayName: "Reports",
        description: "Read reports",
      },
      {
        key: "signaldeck.digital_oracle.prediction_markets.lookup",
        displayName: "Prediction Markets",
        description: "Find prediction-market signals.",
      },
      {
        key: "signaldeck.digital_oracle.sec_filings.lookup",
        displayName: "SEC Filings",
        description: "Find SEC filing summaries.",
      },
      {
        key: "signaldeck.digital_oracle.market_sentiment.lookup",
        displayName: "Market Sentiment",
        description: "Read market sentiment snapshots.",
      },
      {
        key: "signaldeck.digital_oracle.macro_rates.lookup",
        displayName: "Macro Rates",
        description: "Read macro rates snapshots.",
      },
      {
        key: "signaldeck.digital_oracle.crypto_derivatives.lookup",
        displayName: "Crypto Derivatives",
        description: "Read crypto derivatives signals.",
      },
      {
        key: "signaldeck.digital_oracle.cftc_positioning.lookup",
        displayName: "CFTC Positioning",
        description: "Read CFTC positioning signals.",
      },
      {
        key: "signaldeck.digital_oracle.options.lookup",
        displayName: "Options",
        description: "Read options market signals.",
      },
      {
        key: "core.echo",
        displayName: "Echo",
        description: "Core smoke tool",
      },
    ];
    const financeRoutePaths = extension.routeContributions.map(
      (contribution) => contribution.path,
    );
    const toolKeysForState = (
      financeEnabled: boolean,
      digitalOracleEnabled = true,
    ) =>
      filterToolsForExtensionState(
        tools,
        extensionList(financeEnabled, digitalOracleEnabled),
      ).map((tool) => tool.key);

    expect(enabledFinanceRoutePaths(extensionList(true, true))).toEqual(
      financeRoutePaths,
    );
    expect(toolKeysForState(true, true)).toEqual([
      "signaldeck.finance.reports.lookup",
      "signaldeck.digital_oracle.prediction_markets.lookup",
      "signaldeck.digital_oracle.sec_filings.lookup",
      "signaldeck.digital_oracle.market_sentiment.lookup",
      "signaldeck.digital_oracle.macro_rates.lookup",
      "signaldeck.digital_oracle.crypto_derivatives.lookup",
      "signaldeck.digital_oracle.cftc_positioning.lookup",
      "signaldeck.digital_oracle.options.lookup",
      "core.echo",
    ]);
    expect(enabledFinanceRoutePaths(extensionList(true, false))).toEqual(
      financeRoutePaths,
    );
    expect(toolKeysForState(true, false)).toEqual([
      "signaldeck.finance.reports.lookup",
      "core.echo",
    ]);
    expect(enabledFinanceRoutePaths(extensionList(false, true))).toEqual([]);
    expect(toolKeysForState(false, true)).toEqual([
      "signaldeck.digital_oracle.prediction_markets.lookup",
      "signaldeck.digital_oracle.sec_filings.lookup",
      "signaldeck.digital_oracle.market_sentiment.lookup",
      "signaldeck.digital_oracle.macro_rates.lookup",
      "signaldeck.digital_oracle.crypto_derivatives.lookup",
      "signaldeck.digital_oracle.cftc_positioning.lookup",
      "signaldeck.digital_oracle.options.lookup",
      "core.echo",
    ]);
    expect(enabledFinanceRoutePaths(extensionList(false, false))).toEqual([]);
    expect(toolKeysForState(false, false)).toEqual(["core.echo"]);
  });

  it("renders the finance gate unavailable state through the wide responsive error layout", async () => {
    const originalFetch = globalThis.fetch;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: "extension_state_unavailable",
            details: [],
            message: "Extension state unavailable",
          }),
          {
            headers: { "Content-Type": "application/json" },
            status: 503,
          },
        ),
      ),
    );
    const testRouter = createMemoryRouter(router.routes, {
      initialEntries: ["/templates"],
    });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    try {
      render(
        <ThemeProvider>
          <QueryClientProvider client={queryClient}>
            <RouterProvider router={testRouter} />
          </QueryClientProvider>
        </ThemeProvider>,
      );

      const unavailableState = await screen.findByTestId(
        "extension-state-unavailable",
      );
      expect(unavailableState).toHaveTextContent("Extension state unavailable");
      expect(unavailableState).toHaveTextContent(
        "SignalDeck could not load backend extension state, so extension-owned routes are paused until the state read succeeds.",
      );
      expect(
        screen.getByRole("button", { name: "Retry extension state" }),
      ).toBeVisible();
      expectCanonicalGateLayout("extension-state-unavailable");
    } finally {
      vi.stubGlobal("fetch", originalFetch);
    }
  });

  it("renders a deterministic disabled state for direct finance route links", async () => {
    const testRouter = createMemoryRouter(router.routes, {
      initialEntries: ["/reports"],
    });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    queryClient.setQueryData(
      queryKeys.platform.extensions.list(),
      extensionList(false),
    );

    render(
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={testRouter} />
        </QueryClientProvider>
      </ThemeProvider>,
    );

    const disabledState = await screen.findByTestId("extension-disabled-state");
    expect(disabledState).toHaveTextContent("Finance Workspace disabled");
    expect(disabledState).toHaveTextContent(
      "Finance-owned routes, navigation, and tools are paused while this bundled extension is disabled.",
    );
    expect(disabledState).toHaveTextContent("Blast radius");
    expectCanonicalGateLayout("extension-disabled-state");
    expect(
      screen.getByRole("link", { name: "Open core workflow packages" }),
    ).toHaveAttribute("href", "/workflow-packages");
  });
});
