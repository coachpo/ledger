import { render, screen } from "@testing-library/react";
import { createMemoryRouter, matchRoutes, RouterProvider } from "react-router";
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
    expect(matchRoutes(router.routes, "/workflow-packages/123/run")).not.toBeNull();

    for (const retiredRoute of retiredAuthoringRoutes) {
      expect(matchRoutes(router.routes, retiredRoute)).toBeNull();
    }
  });

  it("keeps global model connection and run routes", () => {
    expect(matchRoutes(router.routes, "/model-connections")).not.toBeNull();
    expect(matchRoutes(router.routes, "/model-connections/new")).not.toBeNull();
    expect(matchRoutes(router.routes, "/model-connections/123/edit")).not.toBeNull();
    expect(matchRoutes(router.routes, "/runs")).not.toBeNull();
    expect(matchRoutes(router.routes, "/runs/123")).not.toBeNull();
  });

  it("does not render retired page test ids for old authoring URLs", () => {
    for (const retiredRoute of retiredAuthoringRoutes) {
      const testRouter = createMemoryRouter(router.routes, { initialEntries: [retiredRoute] });
      const { unmount } = render(
        <ThemeProvider>
          <RouterProvider router={testRouter} />
        </ThemeProvider>,
      );

      for (const testId of retiredPageTestIds) {
        expect(screen.queryByTestId(testId)).not.toBeInTheDocument();
      }

      unmount();
    }
  });
});
