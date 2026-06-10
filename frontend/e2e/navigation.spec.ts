import { expect, test, type Page } from "@playwright/test";

const platformRoutes = [
  {
    pageTestId: "workflow-packages-list-page",
    routeTestId: "route-workflow-packages-list",
    shellMode: "scroll",
    testId: "nav-workflow-packages",
    url: /\/workflow-packages$/,
  },
  {
    pageTestId: "platform-model-connections-page",
    routeTestId: "route-model-connections-list",
    shellMode: "scroll",
    testId: "nav-model-connections",
    url: /\/model-connections$/,
  },
  {
    pageTestId: "scheduled-tasks-list-page",
    routeTestId: "route-scheduled-tasks-list",
    shellMode: "scroll",
    testId: "nav-scheduled-tasks",
    url: /\/scheduled-tasks$/,
  },
  {
    pageTestId: "runs-list-page",
    routeTestId: "route-runs-list",
    shellMode: "scroll",
    testId: "nav-runs",
    url: /\/runs$/,
  },
] as const;

const primaryShellNavTestIds = [
  "nav-dashboard",
  "nav-portfolios",
  "nav-templates",
  "nav-reports",
  "nav-workflow-packages",
  "nav-model-connections",
  "nav-memory",
  "nav-scheduled-tasks",
  "nav-runs",
  "nav-extensions",
] as const;

const retiredNavTestIds = [
  "nav-agents",
  "nav-capabilities",
  "nav-mcp-servers",
  "nav-output-schemas",
  "nav-workflows",
  "nav-skills",
  "nav-tryout",
  "nav-studio",
  "nav-orchestration",
  "nav-runtime-v2",
] as const;

const removedBrowserRoutePaths = [
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
  "/skills",
  "/skills/new",
  "/skills/123/edit",
  "/studio",
  "/studio/agents",
  "/tryout",
  "/orchestration",
  "/orchestration/roles",
  "/orchestration/characters",
  "/runtime-v2",
  "/runtime-v2/agents",
  "/simulations",
  "/simulations/new",
  "/simulations/123",
  "/backtests",
  "/backtests/new",
  "/backtests/123",
  "/digital-oracle",
  "/digital-oracle/prediction-markets",
  "/digital-oracle/sec-filings",
  "/digital-oracle/market-sentiment",
  "/prediction-markets",
  "/sec-filings",
  "/market-sentiment",
] as const;

async function expectSingleRouteMain(
  page: Page,
  testId: string,
  shellMode: string,
) {
  const main = page.getByRole("main");
  await expect(main).toHaveCount(1);
  await expect(main).toHaveAttribute("data-testid", testId);
  await expect(main).toHaveAttribute("data-route-shell-mode", shellMode);
}

async function expectNoDocumentOverflow(page: Page) {
  const metrics = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));

  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth + 1);
}

test.describe("Primary workspace navigation", () => {
  test("shows the new platform shell and hides legacy shell entries", async ({
    page,
  }) => {
    await page.goto("/");

    for (const testId of primaryShellNavTestIds) {
      await expect(page.getByTestId(testId)).toBeVisible();
    }
    await expect(page.getByRole("banner")).toHaveClass(/h-12/);
    await expect(page.getByTestId("nav-dashboard")).toHaveAttribute(
      "data-active",
      "true",
    );
    await expectSingleRouteMain(page, "route-dashboard", "scroll");
    const dashboardPage = page.getByTestId("dashboard-page");
    await expect(dashboardPage.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expect(dashboardPage.getByText("Portfolio overview.")).toBeVisible();
    await expect(dashboardPage.getByRole("button")).toHaveCount(0);
    await expect(dashboardPage.getByRole("link")).toHaveCount(0);

    for (const route of platformRoutes) {
      await expect(page.getByTestId(route.testId)).toBeVisible();
    }

    for (const testId of retiredNavTestIds) {
      await expect(page.getByTestId(testId)).toHaveCount(0);
    }

    for (const route of platformRoutes) {
      await page.getByTestId(route.testId).click();
      await expect(page).toHaveURL(route.url);
      await expect(page.getByTestId(route.pageTestId)).toBeVisible();
      await expect(page.getByTestId(route.testId)).toHaveAttribute(
        "data-active",
        "true",
      );
      await expectSingleRouteMain(page, route.routeTestId, route.shellMode);
    }
  });

  test("template seed removal routes to the product-owned 404", async ({
    page,
  }) => {
    await page.goto("/templates");

    await expect(
      page.getByRole("button", { name: "Reset Workspace" }),
    ).toHaveCount(0);

    await page.goto("/templates/seed");

    await expect(page.getByTestId("template-seed-page")).toHaveCount(0);
    await expect(page.getByTestId("not-found-page")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Page not found" }),
    ).toBeVisible();
    await expectSingleRouteMain(page, "route-unknown", "scroll");
    await expect(page.locator("body")).not.toContainText(
      "Run the existing starter workspace reset-and-seed flow from the Web UI.",
    );
  });

  test("removed browser route families route to the product-owned 404", async ({
    page,
  }) => {
    for (const path of removedBrowserRoutePaths) {
      await page.goto(path);

      await expect(page.getByTestId("not-found-page")).toBeVisible();
      await expect(
        page.getByRole("heading", { name: "Page not found" }),
      ).toBeVisible();
      await expectSingleRouteMain(page, "route-unknown", "scroll");
      await expect(page.locator("body")).not.toContainText(
        "Unexpected Application Error!",
      );
    }
  });

  test("renders a product-owned unknown-route shell", async ({ page }) => {
    await page.goto("/does-not-exist");

    await expect(page.getByTestId("not-found-page")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Page not found" }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Open workflow packages" }),
    ).toHaveAttribute("href", "/workflow-packages");
    await expectSingleRouteMain(page, "route-unknown", "scroll");
    await expect(page.locator("body")).not.toContainText(
      "Unexpected Application Error!",
    );
  });

  test("keeps navigation semantics, dark chrome, and mobile overflow stable", async ({
    page,
  }) => {
    await page.goto("/workflow-packages");

    await expect(
      page.getByRole("link", { name: "Import workflow package manifest" }),
    ).toHaveAttribute("href", "/workflow-packages/import");
    await expect(
      page.getByRole("link", { name: "Create new workflow package" }),
    ).toHaveAttribute("href", "/workflow-packages/new");
    await expect(page.getByRole("radio", { name: "Cards view" })).toHaveCount(0);
    await expect(page.getByRole("radio", { name: "Table view" })).toHaveCount(0);

    await page.getByRole("button", { name: "Toggle theme" }).click();
    await page.getByRole("menuitem", { name: "Dark" }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
    await expect(page.getByRole("banner")).toBeVisible();
    await expectSingleRouteMain(page, "route-workflow-packages-list", "scroll");

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByTestId("workflow-packages-list-page")).toBeVisible();
    await page.getByRole("button", { name: "Open sidebar" }).click();

    const mobileSidebar = page.getByRole("dialog", { name: "Sidebar" });
    await expect(mobileSidebar).toBeVisible();
    for (const testId of primaryShellNavTestIds) {
      await expect(mobileSidebar.getByTestId(testId)).toBeVisible();
    }
    for (const testId of retiredNavTestIds) {
      await expect(mobileSidebar.getByTestId(testId)).toHaveCount(0);
    }
    await expect(
      mobileSidebar.getByTestId("nav-workflow-packages"),
    ).toHaveAttribute("data-active", "true");

    await mobileSidebar.getByTestId("nav-dashboard").click();
    await expect(page).toHaveURL(/\/$/);
    await expect(mobileSidebar).toHaveCount(0);
    await expectSingleRouteMain(page, "route-dashboard", "scroll");
    await expectNoDocumentOverflow(page);
  });
});
