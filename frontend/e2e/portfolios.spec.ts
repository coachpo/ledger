import { test, expect, type Page } from "@playwright/test";

const API_BASE = "http://127.0.0.1:8001/api/v1";

async function expectNoDocumentOverflow(page: Page) {
  const metrics = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));

  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth + 1);
}

async function expectSharedDialogShell(page: Page) {
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.locator('[data-slot="entity-dialog-constraint-strip"]'),
  ).toBeVisible();
  await expect(
    dialog.locator('[data-slot="entity-dialog-body"]'),
  ).toBeVisible();
  await expect(dialog.locator('[data-slot="dialog-footer"]')).toBeVisible();
  await expect(
    dialog
      .locator('[data-slot="dialog-footer"]')
      .getByRole("button", { name: "Cancel" }),
  ).toBeVisible();
}

test.describe("Portfolio details", () => {
  test("opens the portfolio create dialog with the shared shell", async ({
    page,
  }) => {
    await page.goto("/portfolios");
    await page
      .getByRole("button", { name: /new portfolio/i })
      .first()
      .click();

    const dialog = page.getByRole("dialog", { name: "Create Portfolio" });
    await expect(dialog).toBeVisible();
    await expectSharedDialogShell(page);
    await expect(dialog).toContainText("Finance Workspace portfolio");
    await expect(dialog).toContainText("Slug");
    await expect(dialog).toContainText("3-letter code");
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toBeHidden();
  });

  test("renders explicit identity, actions, and tabbed finance sections", async ({
    page,
    request,
  }) => {
    let portfolioId: number | undefined;

    try {
      const timestamp = Date.now();
      const portfolioResponse = await request.post(`${API_BASE}/portfolios`, {
        data: {
          baseCurrency: "USD",
          description: "Detail surface browser fixture",
          name: `Detail Portfolio ${timestamp}`,
          slug: `detail_portfolio_${timestamp}`,
        },
      });
      expect(portfolioResponse.ok()).toBeTruthy();
      const portfolio = await portfolioResponse.json();
      portfolioId = portfolio.id;

      await page.goto(`/portfolios/${portfolio.id}`);
      await expect(
        page.getByRole("heading", { name: portfolio.name }),
      ).toBeVisible();

      const header = page.getByTestId("portfolio-detail-header");
      await expect(header.getByText("Portfolio workspace")).toBeVisible();
      await expect(header.getByText("Finance Workspace")).toBeVisible();
      await expect(header.getByText("Quotes")).toBeVisible();
      const actions = page.getByTestId("portfolio-detail-actions");
      await expect(
        actions.getByRole("button", { name: /edit/i }),
      ).toBeVisible();
      await expect(
        actions.getByRole("button", { name: /delete/i }),
      ).toBeVisible();

      await expect(
        page.getByRole("heading", { name: "Portfolio sections" }),
      ).toBeVisible();
      const tabs = page.getByTestId("portfolio-detail-tabs");
      await expect(tabs.getByRole("tab", { name: "Positions" })).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Add Position" }),
      ).toBeVisible();

      await tabs.getByRole("tab", { name: "Balances" }).click();
      await expect(
        page.getByRole("button", { name: "Add Balance" }),
      ).toBeVisible();

      await tabs.getByRole("tab", { name: "Trades" }).click();
      await expect(
        page.getByRole("button", { name: "Add Operation" }),
      ).toBeVisible();
      await expectNoDocumentOverflow(page);
    } finally {
      if (portfolioId) {
        await request.delete(`${API_BASE}/portfolios/${portfolioId}`);
      }
    }
  });
});
