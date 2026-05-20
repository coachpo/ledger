import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, matchRoutes, RouterProvider } from "react-router";
import { describe, expect, it } from "vitest";

import { ThemeProvider } from "./components/theme-provider";
import {
  FINANCE_WORKSPACE_EXTENSION_KEY,
  getBundledFrontendExtension,
  listBundledFrontendExtensions,
} from "./extensions";
import {
  enabledFinanceRoutePaths,
  filterToolsForExtensionState,
} from "./extensions/runtime-helpers";
import { queryKeys } from "./lib/query-keys";
import type { ExtensionListRead } from "./lib/types/extension";
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
        label: "Finance Workspace",
        enabled,
      },
    ],
  };
}

type RouteWithComponent = {
  Component?: unknown;
  element?: { type?: unknown } | null;
};

function matchedRouteComponent(path: string) {
  const match = matchRoutes(router.routes, path)?.at(-1)?.route as RouteWithComponent | undefined;
  return match?.Component ?? match?.element?.type;
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
    expect(matchRoutes(router.routes, "/workflow-packages/import")).not.toBeNull();
    expect(matchRoutes(router.routes, "/workflow-packages/new")).not.toBeNull();
    expect(matchedRouteComponent("/workflow-packages/123")).toBe(WorkflowPackageEditorPage);
    expect(matchedRouteComponent("/workflow-packages/123/run")).toBe(WorkflowPackageLaunchPage);
    expect(matchedRouteComponent("/workflow-packages/123/run")).not.toBe(WorkflowPackageEditorPage);
    expect(matchRoutes(router.routes, "/workflow-packages/123/launch")).toBeNull();

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
    expect(Object.keys(extension).sort()).toEqual([
      "key",
      "label",
      "navContributions",
      "routeContributions",
      "toolAuthoringDiscovery",
    ]);
    expect(extension.key).toBe("signaldeck.finance");
    expect(
      extension.routeContributions.map((contribution) => ({
        path: contribution.path,
        requiredExtensionKey: contribution.requiredExtensionKey,
      })),
    ).toEqual([
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
      extension.navContributions.map((contribution) => ({
        requiredExtensionKey: contribution.requiredExtensionKey,
        testId: contribution.testId,
      })),
    ).toEqual([
      {
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
        testId: "nav-dashboard",
      },
      {
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
        testId: "nav-portfolios",
      },
      {
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
        testId: "nav-templates",
      },
      {
        requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
        testId: "nav-reports",
      },
    ]);
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
      "This workspace is unavailable while its bundled extension is disabled.",
    );
    expect(disabledState).not.toHaveTextContent("signaldeck.finance");
    expect(
      screen.getByRole("link", { name: "Open core workflow packages" }),
    ).toHaveAttribute("href", "/workflow-packages");
  });

});
