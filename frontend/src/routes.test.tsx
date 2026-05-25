import type { ComponentType } from "react";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, matchRoutes, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { Layout } from "./components/layout";
import { ThemeProvider } from "./components/theme-provider";
import {
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
import { MemoryListPage } from "./pages/memory/list";
import { WorkflowPackageEditorPage } from "./pages/workflow-packages/editor";
import { WorkflowPackageLaunchPage } from "./pages/workflow-packages/launch";
import { router } from "./routes";

Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: {
    getItem: () => null,
    removeItem: () => undefined,
    setItem: () => undefined,
  },
});

const retiredAuthoringRoutes = [
  "/agents",
  "/agents/new",
  "/agents/123/edit",
  "/capabilities",
  "/capabilities/new",
  "/capabilities/123/edit",
  "/mcp-servers",
  "/mcp-servers/new",
  "/mcp-servers/123/edit",
  "/output-schemas",
  "/output-schemas/new",
  "/output-schemas/123/edit",
  "/workflows",
  "/workflows/new",
  "/workflows/123/edit",
  "/workflows/123/run",
];

function sampleExtensionRoutePath(path: string) {
  return path
    .replace(":portfolioId", "123")
    .replace(":templateId", "456")
    .replace(":slug", "sample-report");
}

function extensionList(enabled: boolean): ExtensionListRead {
  return {
    items: [
      {
        key: FINANCE_WORKSPACE_EXTENSION_KEY,
        label: FINANCE_WORKSPACE_NAV_GROUP,
        enabled,
      },
    ],
  };
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

type RouteWithComponent = {
  Component?: unknown;
  element?: { type?: unknown } | null;
};

function matchedRouteComponent(path: string) {
  const match = matchRoutes(router.routes, path)?.at(-1)?.route as
    | RouteWithComponent
    | undefined;
  return match?.Component ?? match?.element?.type;
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

  it("classifies dashboard, platform inventories, runs monitor, and system state routes", () => {
    expect(getRouteMetadataByPattern("/")).toMatchObject({
      archetype: "dashboard",
      owner: { kind: "extension" },
      stateVariants: ["loading", "ready", "error", "disabledExtension"],
      testId: "route-dashboard",
    });
    expect(getRouteMetadataByPattern("/workflow-packages")).toMatchObject({
      archetype: "inventory",
      owner: { kind: "platform" },
      stateVariants: ["loading", "ready", "error", "empty", "filteredEmpty"],
      testId: "route-workflow-packages-list",
    });
    expect(getRouteMetadataByPattern("/model-connections")).toMatchObject({
      archetype: "inventory",
      owner: { kind: "platform" },
      stateVariants: ["loading", "ready", "error", "empty", "filteredEmpty"],
      testId: "route-model-connections-list",
    });
    expect(getRouteMetadataByPattern("/memory")).toMatchObject({
      archetype: "inventory",
      owner: { kind: "platform" },
      stateVariants: ["loading", "ready", "error", "empty", "unauthorized"],
      testId: "route-memory-list",
    });
    expect(getRouteMetadataByPattern("/runs")).toMatchObject({
      archetype: "inventory",
      owner: { kind: "platform" },
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
      stateVariants: expect.arrayContaining([
        "loading",
        "ready",
        "error",
        "notFound",
        "polling",
      ]),
    });
    expect(unknownRouteMetadata).toMatchObject({
      archetype: "unknown",
      shellMode: "scroll",
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
      "/runs/:runId",
    ]);
  });

  it("routes removed legacy families to the product-owned 404", () => {
    expect(matchedRouteComponent("/tryout")).toBe(NotFoundPage);
    expect(matchedRouteComponent("/studio")).toBe(NotFoundPage);
    expect(matchedRouteComponent("/studio/agents")).toBe(NotFoundPage);
    expect(matchedRouteComponent("/orchestration")).toBe(NotFoundPage);
    expect(matchedRouteComponent("/orchestration/roles")).toBe(NotFoundPage);
    expect(matchedRouteComponent("/orchestration/characters")).toBe(
      NotFoundPage,
    );
  });

  it("routes the removed backtests family to the product-owned 404", () => {
    expect(matchedRouteComponent("/backtests")).toBe(NotFoundPage);
    expect(matchedRouteComponent("/backtests/new")).toBe(NotFoundPage);
    expect(matchedRouteComponent("/backtests/123")).toBe(NotFoundPage);
  });

  it("registers workflow package routes and removes old global authoring routes", () => {
    expect(matchRoutes(router.routes, "/workflow-packages")).not.toBeNull();
    expect(
      matchRoutes(router.routes, "/workflow-packages/import"),
    ).not.toBeNull();
    expect(matchRoutes(router.routes, "/workflow-packages/new")).not.toBeNull();
    expect(matchedRouteComponent("/workflow-packages/123")).toBe(
      WorkflowPackageEditorPage,
    );
    expect(matchedRouteComponent("/workflow-packages/123/run")).toBe(
      WorkflowPackageLaunchPage,
    );
    expect(matchedRouteComponent("/workflow-packages/123/run")).not.toBe(
      WorkflowPackageEditorPage,
    );
    expect(matchedRouteComponent("/workflow-packages/123/launch")).toBe(
      NotFoundPage,
    );

    for (const retiredRoute of retiredAuthoringRoutes) {
      expect(matchedRouteComponent(retiredRoute)).toBe(NotFoundPage);
    }
  });

  it("keeps global model connection, canonical memory, and run routes", () => {
    expect(matchRoutes(router.routes, "/model-connections")).not.toBeNull();
    expect(matchRoutes(router.routes, "/model-connections/new")).not.toBeNull();
    expect(
      matchRoutes(router.routes, "/model-connections/123/edit"),
    ).not.toBeNull();
    expect(matchedRouteComponent("/memory")).toBe(MemoryListPage);
    expect(getRouteMetadataForPathname("/memory")?.testId).toBe(
      "route-memory-list",
    );
    expect(matchedRouteComponent("/api/memory")).toBe(NotFoundPage);
    expect(getRouteMetadataForPathname("/api/memory")).toBe(unknownRouteMetadata);
    expect(matchRoutes(router.routes, "/runs")).not.toBeNull();
    expect(matchRoutes(router.routes, "/runs/123")).not.toBeNull();
  });

  it("renders deterministic private-scope access state for /memory", async () => {
    const testRouter = createMemoryRouter(router.routes, {
      initialEntries: ["/memory"],
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

    expect(await screen.findByTestId("route-memory-list")).toHaveAttribute(
      "data-route-shell-mode",
      "scroll",
    );
    expect(screen.getByTestId("memory-list-page")).toBeVisible();
    expect(screen.getByTestId("memory-access-required")).toHaveTextContent(
      "Access context required",
    );
    expect(screen.getByText(/explicit private scopes only/i)).toBeVisible();
    expect(screen.queryByLabelText("Namespace declarations")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Namespace grants")).not.toBeInTheDocument();
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

  it("assembles bundled finance routes from extension contributions", () => {
    const extension = getBundledFrontendExtension(
      FINANCE_WORKSPACE_EXTENSION_KEY,
    );
    if (!extension) {
      throw new Error(
        "Finance workspace frontend extension was not registered.",
      );
    }

    expect(listBundledFrontendExtensions()).toEqual([extension]);
    expect(Object.keys(extension).sort()).toEqual([
      "key",
      "label",
      "navContributions",
      "routeContributions",
      "toolAuthoringDiscovery",
    ]);
    expect(extension.key).toBe("signaldeck.finance");
    const expectedFinanceRoutes = [
      { path: "/", requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY },
      {
        path: "/portfolios",
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
      },
      {
        path: "/portfolios/:portfolioId",
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
      },
      {
        path: "/templates",
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
      },
      {
        path: "/templates/new",
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
      },
      {
        path: "/templates/:templateId/edit",
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
      },
      {
        path: "/reports",
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
      },
      {
        path: "/reports/:slug",
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
      },
    ];

    expect(
      extension.routeContributions.map((contribution) => ({
        path: contribution.path,
        requiredExtensionKey: contribution.requiredExtensionKey,
      })),
    ).toEqual(expectedFinanceRoutes);

    expect(
      liveRouteMetadata
        .filter((metadata) => metadata.owner.kind === "extension")
        .map((metadata) => {
          if (metadata.owner.kind !== "extension") {
            throw new Error("Expected extension-owned route metadata.");
          }

          return {
            path: metadata.pattern,
            requiredExtensionKey: metadata.owner.extensionKey,
          };
        }),
    ).toEqual(expectedFinanceRoutes);

    for (const contribution of extension.navContributions) {
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
      extension.routeContributions.map((contribution) => contribution.path),
    );
    expect(enabledFinanceRoutePaths(extensionList(false))).toEqual([]);

    for (const contribution of extension.routeContributions) {
      expect(
        matchRoutes(router.routes, sampleExtensionRoutePath(contribution.path)),
      ).not.toBeNull();
    }

    expect(
      extension.routeContributions.some((contribution) =>
        contribution.path.startsWith("/workflow-packages"),
      ),
    ).toBe(false);
    expect(extension.toolAuthoringDiscovery).toEqual([
      {
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
        toolKeyPrefix: "signaldeck.",
      },
    ]);
  });

  it("restores finance route and tool discovery contributions after re-enable", () => {
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
        key: "signaldeck.reports.lookup",
        displayName: "Reports",
        description: "Read reports",
      },
      {
        key: "core.echo",
        displayName: "Echo",
        description: "Core smoke tool",
      },
    ];
    const enabledPaths = enabledFinanceRoutePaths(extensionList(true));
    const enabledToolKeys = filterToolsForExtensionState(
      tools,
      extensionList(true),
    ).map((tool) => tool.key);

    expect(enabledPaths).toEqual(
      extension.routeContributions.map((contribution) => contribution.path),
    );
    expect(enabledToolKeys).toEqual(["signaldeck.reports.lookup", "core.echo"]);
    expect(enabledFinanceRoutePaths(extensionList(false))).toEqual([]);
    expect(
      filterToolsForExtensionState(tools, extensionList(false)).map(
        (tool) => tool.key,
      ),
    ).toEqual(["core.echo"]);
    expect(enabledFinanceRoutePaths(extensionList(true))).toEqual(enabledPaths);
    expect(
      filterToolsForExtensionState(tools, extensionList(true)).map(
        (tool) => tool.key,
      ),
    ).toEqual(enabledToolKeys);
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
    expect(disabledState).not.toHaveTextContent("signaldeck.finance");
    expect(
      screen.getByRole("link", { name: "Open core workflow packages" }),
    ).toHaveAttribute("href", "/workflow-packages");
  });
});
