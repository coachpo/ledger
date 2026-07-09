import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it } from "vitest";

import { ThemeProvider } from "./components/theme-provider";
import { router } from "./routes";

Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: {
    getItem: () => null,
    removeItem: () => undefined,
    setItem: () => undefined,
  },
});

type RouteWithHandle = {
  handle?: unknown;
  index?: boolean;
  path?: string;
};

type RouteHandle = {
  pattern: string;
  testId: string;
};

function childRoutes(): readonly RouteWithHandle[] {
  const root = router.routes.find((route) => route.path === "/");
  return (root?.children ?? []) as readonly RouteWithHandle[];
}

function routeEntry(pattern: string): string {
  if (pattern === "*") {
    return "/does-not-exist";
  }

  return pattern.replace(/:([A-Za-z0-9_]+)/g, (_match, param: string) => {
    return (
      {
        modelConnectionId: "7",
        packageId: "42",
        runId: "99",
        scheduleId: "5",
        slug: "example-report",
        templateId: "3",
      }[param] ?? "1"
    );
  });
}

function renderRoute(entry: string) {
  const testRouter = createMemoryRouter(router.routes, {
    initialEntries: [entry],
  });

  return render(
    <ThemeProvider>
      <QueryClientProvider
        client={
          new QueryClient({
            defaultOptions: { queries: { retry: false } },
          })
        }
      >
        <RouterProvider router={testRouter} />
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

describe("router", () => {
  it("renders every registered route without crashing", async () => {
    for (const route of childRoutes()) {
      const handle = route.handle as RouteHandle | undefined;

      expect(handle, `Missing handle for ${route.path ?? "index"}`).toBeDefined();
      const view = renderRoute(routeEntry(handle?.pattern ?? "*"));

      expect(await screen.findByTestId(handle?.testId ?? "")).toBeVisible();
      view.unmount();
    }
  });
});
