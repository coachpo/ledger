import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, matchRoutes, RouterProvider } from "react-router";
import { describe, expect, it } from "vitest";

import { ThemeProvider } from "./components/theme-provider";
import {
  FINANCE_WORKSPACE_DEFAULT_ENABLED,
  FINANCE_WORKSPACE_EXTENSION_KEY,
  getBundledFrontendExtension,
  listBundledFrontendExtensions,
} from "./extensions";
import {
  enabledFinanceRoutePaths,
  filterToolsForExtensionState,
} from "./extensions/runtime";
import { queryKeys } from "./lib/query-keys";
import type { ExtensionListRead } from "./lib/types/extension";
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

const retiredPageTestIds = [
  "platform-agents-page",
  "platform-capabilities-page",
  "platform-mcp-servers-page",
  "platform-output-schemas-page",
  "workflows-list-page",
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
        label: "Finance Workspace",
        enabled,
        defaultEnabled: true,
        phase: "phase_1_bundled_first_party",
        versioningRule: "follows_backend_application_version",
        contributionCategories: [],
        dependencies: [],
        contributions: [],
        stateVersion: enabled ? 3 : 4,
        enabledAt: enabled ? "2026-05-15T10:00:00Z" : null,
        disabledAt: enabled ? null : "2026-05-15T11:00:00Z",
        disabledReason: enabled
          ? null
          : "Temporarily disabled for maintenance.",
        createdAt: "2026-05-15T09:00:00Z",
        updatedAt: "2026-05-15T11:00:00Z",
      },
    ],
  };
}

describe("router", () => {
  it("does not register removed legacy route families", () => {
    expect(matchRoutes(router.routes, "/tryout")).toBeNull();
    expect(matchRoutes(router.routes, "/studio")).toBeNull();
    expect(matchRoutes(router.routes, "/studio/agents")).toBeNull();
    expect(matchRoutes(router.routes, "/orchestration")).toBeNull();
    expect(matchRoutes(router.routes, "/orchestration/roles")).toBeNull();
    expect(matchRoutes(router.routes, "/orchestration/characters")).toBeNull();
  });

  it("does not register the removed backtests route family", () => {
    expect(matchRoutes(router.routes, "/backtests")).toBeNull();
    expect(matchRoutes(router.routes, "/backtests/new")).toBeNull();
    expect(matchRoutes(router.routes, "/backtests/123")).toBeNull();
  });

  it("registers workflow package routes and removes old global authoring routes", () => {
    expect(matchRoutes(router.routes, "/workflow-packages")).not.toBeNull();
    expect(matchRoutes(router.routes, "/workflow-packages/new")).not.toBeNull();
    expect(matchRoutes(router.routes, "/workflow-packages/123")).not.toBeNull();
    expect(
      matchRoutes(router.routes, "/workflow-packages/123/run"),
    ).not.toBeNull();

    for (const retiredRoute of retiredAuthoringRoutes) {
      expect(matchRoutes(router.routes, retiredRoute)).toBeNull();
    }
  });

  it("keeps global model connection and run routes", () => {
    expect(matchRoutes(router.routes, "/model-connections")).not.toBeNull();
    expect(matchRoutes(router.routes, "/model-connections/new")).not.toBeNull();
    expect(
      matchRoutes(router.routes, "/model-connections/123/edit"),
    ).not.toBeNull();
    expect(matchRoutes(router.routes, "/runs")).not.toBeNull();
    expect(matchRoutes(router.routes, "/runs/123")).not.toBeNull();
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
    expect(extension.key).toBe("ledger.finance");
    expect(extension.defaultEnabled).toBe(FINANCE_WORKSPACE_DEFAULT_ENABLED);
    expect(extension.availability.stateSource).toMatchObject({
      defaultEnabled: FINANCE_WORKSPACE_DEFAULT_ENABLED,
      endpoint: "/api/extensions",
      extensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
      kind: "backend-extension-state",
    });

    expect(
      extension.routeContributions.map((contribution) => contribution.path),
    ).toEqual([
      "/",
      "/portfolios",
      "/portfolios/:portfolioId",
      "/templates",
      "/templates/new",
      "/templates/:templateId/edit",
      "/reports",
      "/reports/:slug",
    ]);

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
      extension.navContributions.map((contribution) => contribution.testId),
    ).toEqual([
      "nav-dashboard",
      "nav-portfolios",
      "nav-templates",
      "nav-reports",
    ]);
    expect(
      extension.routeContributions.some((contribution) =>
        contribution.path.startsWith("/workflow-packages"),
      ),
    ).toBe(false);
    expect(extension.toolAuthoringDiscovery).toEqual([
      {
        catalogEndpoint: "/api/tools",
        host: "core-workflow-package-authoring",
        id: "finance.workflow-packages.tool-discovery",
        queryKeyNamespace: "platform.tools",
        sourceHook: "@/hooks/use-workflow-packages#useTools",
        toolKeyPrefix: "ledger.",
      },
    ]);
    expect(extension.settingsPages).toEqual([]);
    expect(extension.adminPages).toEqual([]);
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
        key: "ledger.reports.lookup",
        displayName: "Reports",
        description: "Read reports",
        module: "ledger.reports",
      },
      {
        key: "core.echo",
        displayName: "Echo",
        description: "Core smoke tool",
        module: "core",
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
    expect(enabledToolKeys).toEqual(["ledger.reports.lookup", "core.echo"]);
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

    expect(
      await screen.findByTestId("extension-disabled-state"),
    ).toHaveTextContent("Finance Workspace disabled");
    expect(
      screen.getByText("Temporarily disabled for maintenance."),
    ).toBeInTheDocument();
  });

  it("does not render retired page test ids for old authoring URLs", () => {
    for (const retiredRoute of retiredAuthoringRoutes) {
      const testRouter = createMemoryRouter(router.routes, {
        initialEntries: [retiredRoute],
      });
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      queryClient.setQueryData(
        queryKeys.platform.extensions.list(),
        extensionList(true),
      );
      const { unmount } = render(
        <ThemeProvider>
          <QueryClientProvider client={queryClient}>
            <RouterProvider router={testRouter} />
          </QueryClientProvider>
        </ThemeProvider>,
      );

      for (const testId of retiredPageTestIds) {
        expect(screen.queryByTestId(testId)).not.toBeInTheDocument();
      }

      unmount();
    }
  });
});
