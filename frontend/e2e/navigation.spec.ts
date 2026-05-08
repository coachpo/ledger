import { expect, test } from "@playwright/test";

const platformRoutes = [
  {
    pageTestId: "workflow-packages-list-page",
    testId: "nav-workflow-packages",
    url: /\/workflow-packages$/,
  },
  {
    pageTestId: "platform-model-connections-page",
    testId: "nav-model-connections",
    url: /\/model-connections$/,
  },
  { pageTestId: "runs-list-page", testId: "nav-runs", url: /\/runs$/ },
] as const;

const retiredNavTestIds = [
  "nav-agents",
  "nav-capabilities",
  "nav-mcp-servers",
  "nav-output-schemas",
  "nav-workflows",
  "nav-tryout",
  "nav-studio",
  "nav-orchestration",
] as const;

test.describe("Primary workspace navigation", () => {
  test("shows the new platform shell and hides legacy shell entries", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByTestId("nav-dashboard")).toBeVisible();
    await expect(page.getByTestId("nav-portfolios")).toBeVisible();
    await expect(page.getByTestId("nav-templates")).toBeVisible();
    await expect(page.getByTestId("nav-reports")).toBeVisible();

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
    }
  });

  test("template seed removal hides the Reset Workspace entry point and retires /templates/seed", async ({ page }) => {
    await page.goto("/templates");

    await expect(page.getByRole("button", { name: "Reset Workspace" })).toHaveCount(0);

    await page.goto("/templates/seed");

    await expect(page.getByTestId("template-seed-page")).toHaveCount(0);
    await expect(page.locator("body")).not.toContainText(
      "Run the existing starter workspace reset-and-seed flow from the Web UI.",
    );
  });
});
