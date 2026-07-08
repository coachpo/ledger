import { test, expect } from "@playwright/test";

test.describe("Smoke tests", () => {
  test("app loads and renders dashboard", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("body")).toBeVisible();
    await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible();
  });

  test("sidebar navigation shows the primary routes", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Workflow Packages", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Scheduled Tasks", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Model Connections", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Runs", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Templates", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Reports", exact: true })).toBeVisible();
  });

  test("navigate to workflow packages page", async ({ page }) => {
    await page.goto("/workflow-packages");
    await expect(page).toHaveURL(/\/workflow-packages/);
  });
});
