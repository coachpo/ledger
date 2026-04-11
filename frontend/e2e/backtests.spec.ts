import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API_BASE = "http://127.0.0.1:8001/api/v1";

async function setDateValue(page: Page, selector: string, value: string) {
  await page.locator(selector).evaluate((element, nextValue) => {
    const input = element as HTMLInputElement;
    const previousValue = input.value;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(input, nextValue);
    const tracker = (input as HTMLInputElement & { _valueTracker?: { setValue: (value: string) => void } })
      ._valueTracker;
    tracker?.setValue(previousValue);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, value);
}

async function waitForBacktest(
  request: APIRequestContext,
  backtestId: string,
): Promise<{ id: number; name: string; status: string }> {
  const response = await request.get(`${API_BASE}/backtests/${backtestId}`);
  return response.json();
}

async function createPortfolio(
  request: APIRequestContext,
  data: { name: string; slug: string },
): Promise<{ id: number; name: string }> {
  const response = await request.post(`${API_BASE}/portfolios`, {
    data: {
      name: data.name,
      slug: data.slug,
      description: "Playwright backtest coverage portfolio",
      baseCurrency: "USD",
    },
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function createBalance(
  request: APIRequestContext,
  portfolioId: number,
  amount: string,
): Promise<void> {
  const response = await request.post(`${API_BASE}/portfolios/${portfolioId}/balances`, {
    data: {
      label: "Initial Cash",
      amount,
      operationType: "DEPOSIT",
    },
  });
  expect(response.ok()).toBeTruthy();
}

async function createTemplate(
  request: APIRequestContext,
  data: { content: string; name: string },
): Promise<{ id: number; name: string }> {
  const response = await request.post(`${API_BASE}/templates`, { data });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function expectBacktestDeleted(
  page: Page,
  request: APIRequestContext,
  backtestId: string,
  backtestName: string,
) {
  await expect
    .poll(async () => (await request.get(`${API_BASE}/backtests/${backtestId}`)).status())
    .toBe(404);
  await expect(page.getByText(backtestName)).toHaveCount(0);
}

async function configureBacktestForm(
  page: Page,
  backtestName: string,
  portfolioId: number,
  templateId: number,
  portfolioName: string,
  templateName: string,
) {

  await expect(page.locator("#backtest-name")).toBeVisible();
  await page.locator("#backtest-name").fill(backtestName);
  await page.locator("#portfolio-id").evaluate(
    (element, portfolio) => {
      const select = element as HTMLSelectElement;
      const typedPortfolio = portfolio as { id: number; name: string };
      const alreadyPresent = Array.from(select.options).some(
        (option) => option.value === String(typedPortfolio.id),
      );

      if (!alreadyPresent) {
        select.append(new Option(typedPortfolio.name, String(typedPortfolio.id)));
      }
    },
    { id: portfolioId, name: portfolioName },
  );
  await page.locator("#template-id").evaluate(
    (element, template) => {
      const select = element as HTMLSelectElement;
      const typedTemplate = template as { id: number; name: string };
      const alreadyPresent = Array.from(select.options).some(
        (option) => option.value === String(typedTemplate.id),
      );

      if (!alreadyPresent) {
        select.append(new Option(typedTemplate.name, String(typedTemplate.id)));
      }
    },
    { id: templateId, name: templateName },
  );
  await page.locator("#portfolio-id").selectOption(String(portfolioId));
  await page.locator("#template-id").selectOption(String(templateId));
  await page.locator("#frequency").selectOption("MONTHLY");
  await setDateValue(page, "#start-date", "2024-01-02");
  await setDateValue(page, "#end-date", "2024-03-29");
  await page.getByLabel(/s&p 500/i).check();
  await expect(page.getByLabel(/s&p 500/i)).toBeChecked();

  await expect(page.getByText("Choose a complete date range")).toHaveCount(0);
  await expect(page.getByText("Enter a legacy client endpoint URL")).toHaveCount(0);
  await expect(page.getByText("Enter a legacy callback timeout")).toHaveCount(0);
  await expect(page.getByText("Select at least one benchmark")).toHaveCount(0);
}

test.describe("Backtests", () => {
  test("create a backtest, poll until terminal state, and view results", async ({
    page,
    request,
  }) => {
    const backtestName = `E2E Backtest ${Date.now()}`;
    const portfolio = await createPortfolio(request, {
      name: `E2E Portfolio ${Date.now()}`,
      slug: `e2e_portfolio_${Date.now()}`,
    });
    await createBalance(request, portfolio.id, "25000");
    const template = await createTemplate(request, {
      name: `E2E Template ${Date.now()}`,
      content: "# Backtest Template\n\nReview the portfolio.",
    });

    await page.goto("/backtests");
    await page.getByRole("link", { name: /backtests/i }).click();
    await page.getByRole("button", { name: /new backtest/i }).click();
    await page.waitForURL(/\/backtests\/new$/);

    await configureBacktestForm(page, backtestName, portfolio.id, template.id, portfolio.name, template.name);
    await expect(page.locator("#backtest-name")).toHaveValue(backtestName);
    await expect(page.getByRole("button", { name: /launch backtest/i })).toBeEnabled();
    const createResponsePromise = page.waitForResponse(
      (response) =>
        response.url() === `${API_BASE}/backtests` && response.request().method() === "POST",
    );

    await page
      .getByRole("button", { name: /launch backtest/i })
      .evaluate((element) => (element as HTMLButtonElement).click());

    const createResponse = await createResponsePromise;
    expect(createResponse.status()).toBe(201);
    const created = (await createResponse.json()) as { id: number; name: string };
    const backtestId = String(created.id);
    expect(backtestId).toMatch(/^\d+$/);
    await page.goto(`/backtests/${backtestId}`);
    await expect(page.getByText(/current simulation date|total return/i)).toBeVisible();

    const backtest = await waitForBacktest(request, backtestId);
    expect(backtest.name).toBe(created.name);
    await expect
      .poll(async () => (await request.get(`${API_BASE}/backtests/${backtestId}`)).json())
      .toMatchObject({ status: "COMPLETED" });

    await page.reload();
    await expect(page.getByText(/total return/i)).toBeVisible();

    await page.getByRole("button", { name: /^delete$/i }).click();
    await page.getByRole("button", { name: /^delete$/i }).last().click();
    await expectBacktestDeleted(page, request, backtestId, backtestName);
  });
});
