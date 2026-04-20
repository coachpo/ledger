import { expect, test } from "@playwright/test";

const platformRoutes = [
  { pageTestId: "platform-agents-page", testId: "nav-agents", url: /\/agents$/ },
  { pageTestId: "platform-skills-page", testId: "nav-skills", url: /\/skills$/ },
  {
    pageTestId: "platform-mcp-servers-page",
    testId: "nav-mcp-servers",
    url: /\/mcp-servers$/,
  },
  {
    pageTestId: "platform-output-schemas-page",
    testId: "nav-output-schemas",
    url: /\/output-schemas$/,
  },
  { pageTestId: "workflows-list-page", testId: "nav-workflows", url: /\/workflows$/ },
  { pageTestId: "runs-list-page", testId: "nav-runs", url: /\/runs$/ },
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

    await expect(page.getByTestId("nav-tryout")).toHaveCount(0);
    await expect(page.getByTestId("nav-studio")).toHaveCount(0);
    await expect(page.getByTestId("nav-orchestration")).toHaveCount(0);

    for (const route of platformRoutes) {
      await page.getByTestId(route.testId).click();
      await expect(page).toHaveURL(route.url);
      await expect(page.getByTestId(route.pageTestId)).toBeVisible();
    }
  });
});
