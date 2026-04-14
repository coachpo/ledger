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

async function cleanupResource(
  request: APIRequestContext,
  method: "DELETE" | "POST",
  path: string,
) {
  const response =
    method === "DELETE"
      ? await request.delete(`${API_BASE}${path}`)
      : await request.post(`${API_BASE}${path}`);

  expect([200, 204, 404].includes(response.status())).toBeTruthy();
}

async function waitForBacktestStatus(
  request: APIRequestContext,
  backtestId: string,
  status: "AWAITING_CALLBACK" | "CANCELLED" | "COMPLETED" | "FAILED",
) {
  await expect
    .poll(
      async () => {
        const response = await request.get(`${API_BASE}/backtests/${backtestId}`);
        expect(response.ok()).toBeTruthy();
        return (await response.json()) as { status: string };
      },
      { timeout: 30_000 },
    )
    .toMatchObject({ status });
}

async function cleanupBacktest(request: APIRequestContext, backtestId: string) {
  const detailResponse = await request.get(`${API_BASE}/backtests/${backtestId}`);
  if (detailResponse.status() === 404) {
    return;
  }

  expect(detailResponse.ok()).toBeTruthy();
  const detail = (await detailResponse.json()) as { status: string };

  if (["PENDING", "RUNNING", "AWAITING_CALLBACK", "PROCESSING_CALLBACK"].includes(detail.status)) {
    await cleanupResource(request, "POST", `/backtests/${backtestId}/cancel`);
    await waitForBacktestStatus(request, backtestId, "CANCELLED");
  }

  await cleanupResource(request, "DELETE", `/backtests/${backtestId}`);
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

type ConfigureBacktestFormOptions = {
  backtestName: string;
  launchMode?: "internal" | "legacy_callback";
  orchestrationPatternKey?: string;
  portfolioId: number;
  portfolioName: string;
  templateId: number;
  templateName: string;
  webhookTimeout?: string;
  webhookUrl?: string;
};

async function configureBacktestForm(
  page: Page,
  {
    backtestName,
    launchMode = "internal",
    orchestrationPatternKey,
    portfolioId,
    portfolioName,
    templateId,
    templateName,
    webhookTimeout = "900",
    webhookUrl = "http://127.0.0.1:8765/webhook/legacy",
  }: ConfigureBacktestFormOptions,
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
  if (orchestrationPatternKey) {
    await page.locator("#orchestration-pattern").selectOption(orchestrationPatternKey);
  }
  await page.locator("#frequency").selectOption("MONTHLY");
  await setDateValue(page, "#start-date", "2024-01-02");
  await setDateValue(page, "#end-date", "2024-03-29");
  await page.getByLabel(/s&p 500/i).check();
  await expect(page.getByLabel(/s&p 500/i)).toBeChecked();

  if (launchMode === "legacy_callback") {
    await page.getByLabel(/^legacy callback$/i).check();
    await expect(page.getByLabel(/^legacy callback$/i)).toBeChecked();
    await page.getByLabel(/client endpoint url/i).fill(webhookUrl);
    await page.getByLabel(/client callback timeout/i).fill(webhookTimeout);
  } else {
    await page.getByLabel(/^internal$/i).check();
    await expect(page.getByLabel(/^internal$/i)).toBeChecked();
  }

  await expect(page.getByText("Choose a complete date range")).toHaveCount(0);
  if (launchMode === "legacy_callback") {
    await expect(page.getByText("Enter a legacy client endpoint URL")).toHaveCount(0);
    await expect(page.getByText("Enter a legacy callback timeout")).toHaveCount(0);
  } else {
    await expect(page.getByText("Enter a legacy client endpoint URL")).toHaveCount(0);
    await expect(page.getByText("Enter a legacy callback timeout")).toHaveCount(0);
  }
  await expect(page.getByText("Select at least one benchmark")).toHaveCount(0);
}

async function launchBacktestFromConfig(
  page: Page,
  options: ConfigureBacktestFormOptions,
): Promise<{ id: string; name: string }> {
  await page.goto("/backtests/new");
  await expect(page.locator("#backtest-name")).toBeVisible();

  await configureBacktestForm(page, options);
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
  await page.waitForURL(new RegExp(`/backtests/${backtestId}$`));

  return { id: backtestId, name: created.name };
}

test.describe("Backtests", () => {
  test.describe.configure({ timeout: 90_000 });

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

    await configureBacktestForm(page, {
      backtestName,
      portfolioId: portfolio.id,
      portfolioName: portfolio.name,
      templateId: template.id,
      templateName: template.name,
    });
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

  test("internal and legacy callback modes coexist in one browser session", async ({
    page,
    request,
  }) => {
    const timestamp = Date.now();
    const portfolio = await createPortfolio(request, {
      name: `Mixed Mode Portfolio ${timestamp}`,
      slug: `mixed_mode_portfolio_${timestamp}`,
    });
    await createBalance(request, portfolio.id, "25000");
    const template = await createTemplate(request, {
      name: `Mixed Mode Template ${timestamp}`,
      content: "# Mixed Mode Template\n\nCompare internal and callback paths.",
    });

    const resources = {
      backtests: [] as string[],
    };

    try {
      const internal = await launchBacktestFromConfig(page, {
        backtestName: `Internal Mixed Mode ${timestamp}`,
        orchestrationPatternKey: "analyst_reviewer_tool_enabled_v1",
        portfolioId: portfolio.id,
        portfolioName: portfolio.name,
        templateId: template.id,
        templateName: template.name,
      });
      resources.backtests.push(internal.id);

      await waitForBacktestStatus(request, internal.id, "COMPLETED");
      await page.reload();
      await expect(page.getByText(/langgraph decision summary/i)).toBeVisible();
      await expect(page.getByText(/internal engine/i)).toBeVisible();

      await page.goto("/backtests/new");
      await expect(page.getByLabel(/^internal$/i)).toBeChecked();
      await expect(page.getByLabel(/client endpoint url/i)).toHaveCount(0);

      await configureBacktestForm(page, {
        backtestName: `Legacy Mixed Mode ${timestamp}`,
        launchMode: "legacy_callback",
        orchestrationPatternKey: "seeded_internal_backtest_tool_enabled_v1",
        portfolioId: portfolio.id,
        portfolioName: portfolio.name,
        templateId: template.id,
        templateName: template.name,
      });
      await expect(page.getByLabel(/^legacy callback$/i)).toBeChecked();
      await expect(page.getByLabel(/client endpoint url/i)).toHaveValue(
        "http://127.0.0.1:8765/webhook/legacy",
      );
      await expect(page.getByLabel(/client callback timeout/i)).toHaveValue("900");
      await expect(
        page.getByText(/use the legacy callback mode only when you need the retained compatibility path/i),
      ).toBeVisible();

      const createLegacyResponsePromise = page.waitForResponse(
        (response) =>
          response.url() === `${API_BASE}/backtests` && response.request().method() === "POST",
      );
      await page
        .getByRole("button", { name: /launch backtest/i })
        .evaluate((element) => (element as HTMLButtonElement).click());

      const createLegacyResponse = await createLegacyResponsePromise;
      expect(createLegacyResponse.status()).toBe(201);
      const legacy = (await createLegacyResponse.json()) as { id: number; name: string };
      const legacyBacktestId = String(legacy.id);
      expect(legacyBacktestId).toMatch(/^\d+$/);
      resources.backtests.push(legacyBacktestId);
      await page.waitForURL(new RegExp(`/backtests/${legacyBacktestId}$`));

      await waitForBacktestStatus(request, legacyBacktestId, "COMPLETED");
      const legacyDetailResponse = await request.get(`${API_BASE}/backtests/${legacyBacktestId}`);
      expect(legacyDetailResponse.ok()).toBeTruthy();
      const legacyDetail = (await legacyDetailResponse.json()) as {
        webhookTimeout: number | null;
        webhookUrl: string | null;
      };
      expect(legacyDetail).toMatchObject({
        webhookTimeout: 900,
        webhookUrl: "http://127.0.0.1:8765/webhook/legacy",
      });

      await page.reload();
      await expect(page.getByText(/langgraph decision summary/i)).toBeVisible();

      await page.goto("/backtests");
      await page.waitForLoadState("networkidle");

      const internalCard = page.locator('[data-slot="card"]').filter({ hasText: internal.name }).first();
      const legacyCard = page.locator('[data-slot="card"]').filter({ hasText: legacy.name }).first();

      await expect(internalCard).toBeVisible();
      await expect(internalCard).toContainText(/completed/i);
      await expect(internalCard).toContainText(/total return/i);

      await expect(legacyCard).toBeVisible();
      await expect(legacyCard).toContainText(/completed/i);
      await expect(legacyCard).toContainText(/total return/i);
    } finally {
      for (const backtestId of resources.backtests) {
        await cleanupBacktest(request, backtestId);
      }
    }
  });
});
