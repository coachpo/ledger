import { expect, test, type Page } from "@playwright/test";

const sidebarRoutes = [
  {
    navTestId: "nav-dashboard",
    pageTestId: "dashboard-page",
    routeTestId: "route-dashboard",
    shellMode: "scroll",
    url: "/",
  },
  {
    navTestId: "nav-workflow-packages",
    pageTestId: "workflow-packages-list-page",
    routeTestId: "route-workflow-packages-list",
    shellMode: "scroll",
    url: "/workflow-packages",
  },
  {
    navTestId: "nav-model-connections",
    pageTestId: "platform-model-connections-page",
    routeTestId: "route-model-connections-list",
    shellMode: "scroll",
    url: "/model-connections",
  },
  {
    navTestId: "nav-scheduled-tasks",
    pageTestId: "scheduled-tasks-list-page",
    routeTestId: "route-scheduled-tasks-list",
    shellMode: "scroll",
    url: "/scheduled-tasks",
  },
  {
    navTestId: "nav-runs",
    pageTestId: "runs-list-page",
    routeTestId: "route-runs-list",
    shellMode: "scroll",
    url: "/runs",
  },
  {
    navTestId: "nav-templates",
    pageTestId: "templates-list-page",
    routeTestId: "route-templates-list",
    shellMode: "scroll",
    url: "/templates",
  },
  {
    navTestId: "nav-reports",
    pageTestId: "reports-list-page",
    routeTestId: "route-reports-list",
    shellMode: "scroll",
    url: "/reports",
  },
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
  await expect
    .poll(async () =>
      page.evaluate(
        () =>
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
      ),
    )
    .toBeLessThanOrEqual(1);
}

test.describe("Shell", () => {
  test("sidebar contains all main routes and can navigate", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("banner")).toBeVisible();
    await expectSingleRouteMain(page, "route-dashboard", "scroll");
    await expect(page.getByTestId("dashboard-page")).toBeVisible();

    for (const route of sidebarRoutes) {
      await expect(page.getByTestId(route.navTestId)).toBeVisible();
    }

    for (const route of sidebarRoutes) {
      await page.getByTestId(route.navTestId).click();
      await expect(page).toHaveURL(route.url);
      await expect(page.getByTestId(route.navTestId)).toHaveAttribute(
        "data-active",
        "true",
      );
      await expect(page.getByTestId(route.pageTestId)).toBeVisible();
      await expectSingleRouteMain(page, route.routeTestId, route.shellMode);
    }
  });

  test("unknown route renders product-owned shell", async ({ page }) => {
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

  test("mobile overflow and width mode stay stable", async ({ page }) => {
    await page.goto("/workflow-packages/import");
    await expectSingleRouteMain(page, "route-workflow-package-import", "fullHeight");
    await expect(page.getByTestId("workflow-package-import-page")).toBeVisible();
    await expect(page.getByRole("main")).toHaveAttribute(
      "data-route-width-mode",
      "full",
    );

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByTestId("workflow-package-import-page")).toBeVisible();
    await expectSingleRouteMain(page, "route-workflow-package-import", "fullHeight");
    await expect(page.getByRole("main")).toHaveAttribute(
      "data-route-width-mode",
      "full",
    );
    await expectNoDocumentOverflow(page);
    await page.getByRole("button", { name: "Open sidebar" }).click();

    const mobileSidebar = page.getByRole("dialog", { name: "Sidebar" });
    await expect(mobileSidebar).toBeVisible();
    await expect(mobileSidebar.getByTestId("nav-workflow-packages")).toHaveAttribute(
      "data-active",
      "true",
    );

    await mobileSidebar.getByTestId("nav-dashboard").click();
    await expect(page).toHaveURL("/");
    await expect(mobileSidebar).toHaveCount(0);
    await expectSingleRouteMain(page, "route-dashboard", "scroll");
    await expectNoDocumentOverflow(page);
  });
});
