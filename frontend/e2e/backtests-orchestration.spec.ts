import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API_BASE = "http://127.0.0.1:8001/api/v1";

type LaunchBacktestOptions = {
  backtestName: string;
  orchestrationPatternKey: "seeded_internal_backtest_v1" | "analyst_reviewer_v1";
  templateId: number;
};

type CreatedTemplate = { id: number; name: string };
type CreatedRole = { id: number };
type CreatedCharacter = { id: number };

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

async function configureBacktestForm(
  page: Page,
  { backtestName, orchestrationPatternKey, templateId }: LaunchBacktestOptions,
) {
  const timestamp = Date.now();

  await expect(page.locator("#backtest-name")).toBeVisible();
  await page.locator("#backtest-name").fill(backtestName);
  await page.locator("#orchestration-pattern").selectOption(orchestrationPatternKey);
  await page.getByRole("radio", { name: /create new/i }).click();
  await expect(page.getByRole("radio", { name: /create new/i })).toBeChecked();
  await page.locator("#new-portfolio-name").fill(`Orchestration Portfolio ${timestamp}`);
  await page.locator("#new-portfolio-slug").fill(`orchestration_portfolio_${timestamp}`);
  await page.locator("#new-portfolio-initial-cash").fill("25000");
  await page.locator("#template-id").selectOption(String(templateId));
  await page.locator("#frequency").selectOption("MONTHLY");
  await page.locator("#start-date").fill("2024-01-02");
  await page.locator("#end-date").fill("2024-03-29");
  await page.getByRole("button", { name: /legacy callback settings/i }).click();
  await page.locator("#webhook-url").fill("http://localhost:5678/webhook/test");
  await page.locator("#webhook-timeout").fill("600");
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

  await Promise.all([
    page.waitForURL(/\/backtests\/\d+$/, { timeout: 30_000 }),
    launchButton.click(),
  ]);

  const backtestId = page.url().split("/backtests/")[1];
  expect(backtestId).toMatch(/^\d+$/);
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
    const resources: { characters: number[]; roles: number[]; templates: number[]; backtests: string[] } = {
      characters: [],
      roles: [],
      templates: [],
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

      const backtestId = await launchBacktestFromConfig(page, {
        backtestName: `Orchestration Success ${timestamp}`,
        orchestrationPatternKey: "analyst_reviewer_v1",
        templateId: template.id,
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
    const resources: { characters: number[]; roles: number[]; templates: number[]; backtests: string[] } = {
      characters: [],
      roles: [],
      templates: [],
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

      const unknownBacktestId = await launchBacktestFromConfig(page, {
        backtestName: `Orchestration Unknown ${timestamp}`,
        orchestrationPatternKey: "analyst_reviewer_v1",
        templateId: unknownTemplate.id,
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
        templateId: disabledTemplate.id,
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
      for (const characterId of resources.characters) {
        await cleanupResource(request, "DELETE", `/orchestration/characters/${characterId}`);
      }
      for (const roleId of resources.roles) {
        await cleanupResource(request, "DELETE", `/orchestration/roles/${roleId}`);
      }
    }
  });
});
