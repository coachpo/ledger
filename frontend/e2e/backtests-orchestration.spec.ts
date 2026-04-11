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

type LaunchBacktestOptions = {
  backtestName: string;
  orchestrationPatternKey: "seeded_internal_backtest_v1" | "analyst_reviewer_v1";
  portfolioId: number;
  portfolioName: string;
  templateId: number;
  templateName: string;
};

type CreatedTemplate = { id: number; name: string };
type CreatedRole = { id: number };
type CreatedCharacter = { id: number };
type CreatedPortfolio = { id: number; name: string };

async function createTemplate(
  request: APIRequestContext,
  data: { content: string; name: string },
): Promise<CreatedTemplate> {
  const response = await request.post(`${API_BASE}/templates`, { data });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function createRole(
  request: APIRequestContext,
  data: { description: string; key: string; name: string; systemPrompt: string },
): Promise<CreatedRole> {
  const response = await request.post(`${API_BASE}/orchestration/roles`, { data });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function createCharacter(
  request: APIRequestContext,
  data: {
    description: string;
    displayName: string;
    enabled: boolean;
    handle: string;
    promptAppend?: string | null;
    roleId: number;
  },
): Promise<CreatedCharacter> {
  const response = await request.post(`${API_BASE}/orchestration/characters`, { data });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function createPortfolio(
  request: APIRequestContext,
  data: { name: string; slug: string },
): Promise<CreatedPortfolio> {
  const response = await request.post(`${API_BASE}/portfolios`, {
    data: {
      name: data.name,
      slug: data.slug,
      description: "Playwright orchestration coverage portfolio",
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

async function configureBacktestForm(
  page: Page,
  {
    backtestName,
    orchestrationPatternKey,
    portfolioId,
    portfolioName,
    templateId,
    templateName,
  }: LaunchBacktestOptions,
) {
  await expect(page.locator("#backtest-name")).toBeVisible();
  await page.locator("#backtest-name").fill(backtestName);
  await page.locator("#orchestration-pattern").selectOption(orchestrationPatternKey);
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
}

async function launchBacktestFromConfig(
  page: Page,
  options: LaunchBacktestOptions,
): Promise<string> {
  await page.goto("/backtests/new");
  await page.waitForLoadState("networkidle");

    await configureBacktestForm(page, options);
    const launchButton = page.getByRole("button", { name: /launch backtest/i });
    await expect(launchButton).toBeEnabled();

    const createResponsePromise = page.waitForResponse(
      (response) =>
        response.url() === `${API_BASE}/backtests` && response.request().method() === "POST",
    );

    await launchButton.evaluate((element) => (element as HTMLButtonElement).click());

    const createResponse = await createResponsePromise;
    expect(createResponse.status()).toBe(201);
    const created = (await createResponse.json()) as { id: number };
    const backtestId = String(created.id);
    expect(backtestId).toMatch(/^\d+$/);
    await page.goto(`/backtests/${backtestId}`);
    return backtestId;
}

async function waitForBacktestStatus(
  request: APIRequestContext,
  backtestId: string,
  status: "COMPLETED" | "FAILED",
) {
  await expect
    .poll(
      async () => {
        const response = await request.get(`${API_BASE}/backtests/${backtestId}`);
        expect(response.ok()).toBeTruthy();
        return (await response.json()) as { errorMessage: string | null; status: string };
      },
      { timeout: 30_000 },
    )
    .toMatchObject({ status });
}

async function cleanupResource(
  request: APIRequestContext,
  method: "DELETE" | "PATCH",
  path: string,
  data?: Record<string, unknown>,
) {
  const response =
    method === "DELETE"
      ? await request.delete(`${API_BASE}${path}`)
      : await request.patch(`${API_BASE}${path}`, { data });

  expect([200, 204, 404].includes(response.status())).toBeTruthy();
}

test.describe("Backtests orchestration", () => {
  test.describe.configure({ timeout: 90_000 });

  test("valid builtin and character mentions complete successfully", async ({ page, request }) => {
    const timestamp = Date.now();
    const resources: {
      characters: number[];
      roles: number[];
      templates: number[];
      portfolios: number[];
      backtests: string[];
    } = {
      characters: [],
      roles: [],
      templates: [],
      portfolios: [],
      backtests: [],
    };

    try {
      const role = await createRole(request, {
        key: `orchestration_role_${timestamp}`,
        name: `Orchestration Role ${timestamp}`,
        description: "E2E orchestration success role",
        systemPrompt: "Review the current backtest context and summarize tradeoffs.",
      });
      resources.roles.push(role.id);

      const characterHandle = `analyst_e2e_${timestamp}`;
      const character = await createCharacter(request, {
        handle: characterHandle,
        displayName: `Analyst E2E ${timestamp}`,
        description: "Summarize the run from an analyst perspective.",
        promptAppend: "Highlight the main tradeoff clearly.",
        roleId: role.id,
        enabled: true,
      });
      resources.characters.push(character.id);

      const template = await createTemplate(request, {
        name: `E2E orchestration success ${timestamp}`,
        content: [
          "# Orchestration success template",
          "",
          "Ask @librarian to gather supporting context.",
          `Then have @${characterHandle} synthesize the tradeoff for the final note.`,
        ].join("\n"),
      });
      resources.templates.push(template.id);

      const portfolio = await createPortfolio(request, {
        name: `Orchestration Portfolio ${timestamp}`,
        slug: `orchestration_portfolio_${timestamp}`,
      });
      resources.portfolios.push(portfolio.id);
      await createBalance(request, portfolio.id, "25000");

      const backtestId = await launchBacktestFromConfig(page, {
        backtestName: `Orchestration Success ${timestamp}`,
        orchestrationPatternKey: "analyst_reviewer_v1",
        portfolioId: portfolio.id,
        portfolioName: portfolio.name,
        templateId: template.id,
        templateName: template.name,
      });
      resources.backtests.push(backtestId);

      await waitForBacktestStatus(request, backtestId, "COMPLETED");
      await page.reload();

      await expect(page.getByText(/total return/i)).toBeVisible();
      await expect(page.getByText(/langgraph decision summary/i)).toBeVisible();
      await expect(page.getByText(/execution failed/i)).toHaveCount(0);
    } finally {
      for (const backtestId of resources.backtests) {
        await cleanupResource(request, "DELETE", `/backtests/${backtestId}`);
      }
      for (const templateId of resources.templates) {
        await cleanupResource(request, "DELETE", `/templates/${templateId}`);
      }
      for (const portfolioId of resources.portfolios) {
        await cleanupResource(request, "DELETE", `/portfolios/${portfolioId}`);
      }
      for (const characterId of resources.characters) {
        await cleanupResource(request, "DELETE", `/orchestration/characters/${characterId}`);
      }
      for (const roleId of resources.roles) {
        await cleanupResource(request, "DELETE", `/orchestration/roles/${roleId}`);
      }
    }
  });

  test("unknown or disabled mentions fail clearly", async ({ page, request }) => {
    const timestamp = Date.now();
    const resources: {
      characters: number[];
      roles: number[];
      templates: number[];
      portfolios: number[];
      backtests: string[];
    } = {
      characters: [],
      roles: [],
      templates: [],
      portfolios: [],
      backtests: [],
    };

    try {
      const role = await createRole(request, {
        key: `orchestration_failure_role_${timestamp}`,
        name: `Orchestration Failure Role ${timestamp}`,
        description: "E2E orchestration failure role",
        systemPrompt: "Review the current backtest context and explain the risk.",
      });
      resources.roles.push(role.id);

      const disabledHandle = `disabled_e2e_${timestamp}`;
      const disabledCharacter = await createCharacter(request, {
        handle: disabledHandle,
        displayName: `Disabled E2E ${timestamp}`,
        description: "A disabled mention target for orchestration failure coverage.",
        roleId: role.id,
        enabled: false,
      });
      resources.characters.push(disabledCharacter.id);

      const unknownHandle = `ghost_e2e_${timestamp}`;
      const unknownTemplate = await createTemplate(request, {
        name: `E2E orchestration unknown ${timestamp}`,
        content: `# Unknown mention\n\nAsk @${unknownHandle} to review this run.`,
      });
      resources.templates.push(unknownTemplate.id);

      const portfolio = await createPortfolio(request, {
        name: `Orchestration Failure Portfolio ${timestamp}`,
        slug: `orchestration_failure_portfolio_${timestamp}`,
      });
      resources.portfolios.push(portfolio.id);
      await createBalance(request, portfolio.id, "25000");

      const unknownBacktestId = await launchBacktestFromConfig(page, {
        backtestName: `Orchestration Unknown ${timestamp}`,
        orchestrationPatternKey: "analyst_reviewer_v1",
        portfolioId: portfolio.id,
        portfolioName: portfolio.name,
        templateId: unknownTemplate.id,
        templateName: unknownTemplate.name,
      });
      resources.backtests.push(unknownBacktestId);

      await waitForBacktestStatus(request, unknownBacktestId, "FAILED");
      await page.reload();
      await expect(page.getByText("Execution failed")).toBeVisible();
      await expect(page.getByText(`Mention target @${unknownHandle} was not found`)).toBeVisible();

      const disabledTemplate = await createTemplate(request, {
        name: `E2E orchestration disabled ${timestamp}`,
        content: `# Disabled mention\n\nAsk @${disabledHandle} to review this run.`,
      });
      resources.templates.push(disabledTemplate.id);

      const disabledBacktestId = await launchBacktestFromConfig(page, {
        backtestName: `Orchestration Disabled ${timestamp}`,
        orchestrationPatternKey: "analyst_reviewer_v1",
        portfolioId: portfolio.id,
        portfolioName: portfolio.name,
        templateId: disabledTemplate.id,
        templateName: disabledTemplate.name,
      });
      resources.backtests.push(disabledBacktestId);

      await waitForBacktestStatus(request, disabledBacktestId, "FAILED");
      await page.reload();
      await expect(page.getByText("Execution failed")).toBeVisible();
      await expect(page.getByText(`Mention target @${disabledHandle} is disabled`)).toBeVisible();
    } finally {
      for (const backtestId of resources.backtests) {
        await cleanupResource(request, "DELETE", `/backtests/${backtestId}`);
      }
      for (const templateId of resources.templates) {
        await cleanupResource(request, "DELETE", `/templates/${templateId}`);
      }
      for (const portfolioId of resources.portfolios) {
        await cleanupResource(request, "DELETE", `/portfolios/${portfolioId}`);
      }
      for (const characterId of resources.characters) {
        await cleanupResource(request, "DELETE", `/orchestration/characters/${characterId}`);
      }
      for (const roleId of resources.roles) {
        await cleanupResource(request, "DELETE", `/orchestration/roles/${roleId}`);
      }
    }
  });
});
