import { expect, test } from "@playwright/test";

test.describe("Orchestration navigation", () => {
  test("root shell reaches roles and characters by click", async ({ page }) => {
    await page.goto("/");

    const sidebarOrchestrationLink = page.locator('[data-sidebar="menu-button"]').filter({
      hasText: "Orchestration",
    });

    await sidebarOrchestrationLink.click();
    await expect(page).toHaveURL(/\/orchestration$/);
    await expect(page.getByRole("heading", { name: "Orchestration" })).toBeVisible();

    await page.getByRole("link", { name: "Manage Roles" }).click();
    await expect(page).toHaveURL(/\/orchestration\/roles$/);
    await expect(page.getByRole("heading", { name: "Orchestration Roles" })).toBeVisible();

    await sidebarOrchestrationLink.click();
    await expect(page).toHaveURL(/\/orchestration$/);

    await page.getByRole("link", { name: "Manage Characters" }).click();
    await expect(page).toHaveURL(/\/orchestration\/characters$/);
    await expect(page.getByRole("heading", { name: "Orchestration Characters" })).toBeVisible();
  });
});
