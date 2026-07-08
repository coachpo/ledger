import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, matchRoutes, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { Layout } from "./components/layout";
import { ThemeProvider } from "./components/theme-provider";
import {
  allRouteMetadata,
  assertRouteMetadataCoverage,
  getRouteMetadataByPattern,
  getRouteMetadataForPathname,
  liveRouteMetadata,
  routePatternsFromDefinitions,
  type RouteCoverageDefinition,
} from "./routes.metadata";
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
    expect(getRouteMetadataForPathname("/does-not-exist").pattern).toBe("*");
  });

  it("registers static finance and platform routes without an extensions screen", () => {
    expect(matchRoutes(router.routes, "/templates")).not.toBeNull();
    expect(matchRoutes(router.routes, "/templates/new")).not.toBeNull();
    expect(matchRoutes(router.routes, "/templates/123/edit")).not.toBeNull();
    expect(matchRoutes(router.routes, "/reports")).not.toBeNull();
    expect(matchRoutes(router.routes, "/reports/example-report")).not.toBeNull();
    expect(matchRoutes(router.routes, "/workflow-packages")).not.toBeNull();
    expect(getRouteMetadataByPattern("/extensions")).toBeUndefined();
    expect(getRouteMetadataForPathname("/extensions").pattern).toBe("*");
  });

  it("treats finance workspace pages as static live routes", () => {
    expect(getRouteMetadataByPattern("/templates")).toMatchObject({
      nav: {
        label: "Templates",
        path: "/templates",
        sidebar: true,
        testId: "nav-templates",
      },
      owner: { extensionKey: "signaldeck.finance", kind: "extension" },
      testId: "route-templates-list",
    });
    expect(getRouteMetadataByPattern("/reports")).toMatchObject({
      nav: {
        label: "Reports",
        path: "/reports",
        sidebar: true,
        testId: "nav-reports",
      },
      owner: { extensionKey: "signaldeck.finance", kind: "extension" },
      testId: "route-reports-list",
    });
    expect(
      getRouteMetadataByPattern("/templates")?.stateVariants,
    ).not.toContain("disabledExtension");
    expect(
      getRouteMetadataByPattern("/reports/:slug")?.stateVariants,
    ).not.toContain("disabledExtension");
  });

  it("keeps full-height route metadata for editors and consoles", () => {
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

  it("renders a product-owned catch-all 404 inside the app shell", async () => {
    const testRouter = createMemoryRouter(router.routes, {
      initialEntries: ["/does-not-exist"],
    });

    render(
      <ThemeProvider>
        <QueryClientProvider
          client={new QueryClient({
            defaultOptions: { queries: { retry: false } },
          })}
        >
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
      screen.getByRole("link", { name: "Open workflow packages" }),
    ).toHaveAttribute("href", "/workflow-packages");
    expect(
      screen.queryByText("Unexpected Application Error!"),
    ).not.toBeInTheDocument();
  });

  it("renders the routed error boundary for thrown route errors", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const ThrowingRoute = () => {
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
    consoleError.mockRestore();
  });
});
