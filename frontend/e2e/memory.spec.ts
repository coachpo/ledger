import { expect, test, type Page } from "@playwright/test";

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

test.describe("canonical memory workspace", () => {
  test("memory route renders private-scope access state", async ({ page }) => {
    await page.goto("/memory");

    await expectSingleRouteMain(page, "route-memory-list", "scroll");
    await expect(page.getByTestId("memory-list-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Canonical Memory" })).toBeVisible();
    await expect(page.getByTestId("memory-contract-notice")).toContainText(
      "concrete private scope",
    );
    await expect(page.getByTestId("memory-contract-notice")).toContainText(
      "browser-authored JSON",
    );
    await expect(page.getByTestId("memory-contract-notice")).toContainText(
      "does not create, edit, delete, or browse report history",
    );
    await expect(page.getByTestId("memory-access-required")).toContainText(
      "Access context required",
    );
    await expect(page.getByTestId("nav-memory")).toBeVisible();
  });
});
