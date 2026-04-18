import { expect, test, type APIRequestContext } from "@playwright/test";

const API_V2 = "http://127.0.0.1:8001/api/v2";

type CreatedAgentSpec = {
  id: number;
  key: string;
  name: string;
};

async function createAgentSpec(
  request: APIRequestContext,
  data: { key: string; name: string },
): Promise<CreatedAgentSpec> {
  const createResponse = await request.post(`${API_V2}/agent-specs`, {
    data: {
      defaultCapabilityBundleKeys: [],
      defaultPersonaProfileKeys: [],
      finalOutputContract: null,
      instructions: "Summarize the request clearly and keep the response compact.",
      key: data.key,
      modelPolicy: {},
      name: data.name,
    },
  });

  expect(createResponse.ok()).toBeTruthy();
  const created = (await createResponse.json()) as CreatedAgentSpec;

  const activateResponse = await request.post(`${API_V2}/agent-specs/${created.id}/activate`);
  expect(activateResponse.ok()).toBeTruthy();

  return created;
}

test.describe("Studio and Tryout", () => {
  test.describe.configure({ timeout: 60_000 });

  test("persisted tryout runs are inspectable in Studio and leave orchestration isolated", async ({
    page,
    request,
  }) => {
    const timestamp = Date.now();
    const agent = await createAgentSpec(request, {
      key: `e2e_tryout_agent_${timestamp}`,
      name: `E2E Tryout Agent ${timestamp}`,
    });

    await page.goto("/");
    await page.getByTestId("nav-studio").click();
    await expect(page).toHaveURL(/\/studio$/);
    await expect(page.getByTestId("studio-index-page")).toBeVisible();

    await page.getByTestId("studio-index-agents-link").click();
    await expect(page).toHaveURL(/\/studio\/agents$/);
    await expect(page.getByTestId("studio-agents-list")).toBeVisible();
    await expect(page.getByTestId(`studio-agents-row-${agent.key}`)).toBeVisible();

    await page.getByTestId(`studio-agents-open-${agent.key}`).click();
    await expect(page).toHaveURL(new RegExp(`/studio/agents/${agent.key}/edit$`));
    await expect(page.getByTestId("studio-agents-editor")).toBeVisible();
    await expect(page.getByLabel("Agent Name")).toHaveValue(agent.name);
    await expect(page.getByLabel("Agent Instructions")).toHaveValue(
      /summarize the request clearly/i,
    );

    await page.goto("/studio/workflows");
    await expect(page).toHaveURL(/\/studio\/workflows$/);
    await expect(page.getByTestId("studio-workflows-list")).toBeVisible();

    await page.getByTestId("nav-tryout").click();
    await expect(page).toHaveURL(/\/tryout$/);
    await expect(page.getByTestId("tryout-page")).toBeVisible();
    await expect(page.getByText(/execute one workflow spec or one single-agent spec/i)).toBeVisible();

    await page.getByLabel(/^single-agent spec$/i).check();
    await expect(page.getByTestId("tryout-agent-select")).toContainText(agent.name);
    await page.getByTestId("tryout-agent-select").selectOption(String(agent.id));
    await page.getByRole("button", { name: /add input/i }).click();
    await page.getByPlaceholder("ticker").fill("ticker");
    await page.getByPlaceholder("AAPL").fill("AAPL");

    await page.getByTestId("tryout-execute-button").click();

    const activeRunBadge = page.getByText(/^Active run #\d+$/);
    await expect(activeRunBadge).toBeVisible();
    const activeRunText = await activeRunBadge.textContent();
    const runId = Number(activeRunText?.match(/\d+/)?.[0]);
    expect(runId).toBeGreaterThan(0);

    await expect(page.getByText(`Active run #${runId}`)).toBeVisible();
    await expect(page.getByTestId("tryout-status-panel")).toContainText(`Run #${runId}`);
    await expect(page.getByTestId("tryout-status-panel")).toContainText(/single_agent/i);

    await page.getByTestId("tryout-persist-button").click();

    await expect(page.getByTestId("tryout-status-panel")).toContainText(/expires: not scheduled/i);
    await expect(page.getByTestId("tryout-final-output")).toContainText(/single_agent/i);
    await expect(page.getByTestId("tryout-final-output")).toContainText(agent.key);

    await page.goto(`/studio/runs/${runId}`);
    await expect(page).toHaveURL(new RegExp(`/studio/runs/${runId}$`));
    await expect(page.getByTestId("studio-run-detail")).toBeVisible();
    await expect(page.getByText(`Studio Run #${runId}`)).toBeVisible();
    await expect(page.getByTestId("studio-run-summary-card")).toContainText(/caller type: tryout/i);
    await expect(page.getByTestId("studio-run-summary-card")).toContainText(
      /execution kind: single_agent/i,
    );
    await expect(page.getByTestId("studio-run-trace-summary-card")).toContainText(/events: 4/i);

    await page.getByTestId("nav-orchestration").click();
    await expect(page).toHaveURL(/\/orchestration$/);
    await expect(page.getByRole("heading", { name: "Orchestration" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Manage Roles" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Manage Characters" })).toBeVisible();
    await expect(page.getByTestId("studio-run-detail")).toHaveCount(0);
    await expect(page.getByTestId("tryout-page")).toHaveCount(0);
    await expect(page.getByText(agent.key)).toHaveCount(0);
  });
});
