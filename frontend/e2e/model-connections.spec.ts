import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const PLATFORM_API_BASE = "http://127.0.0.1:8001/api";
const DETERMINISTIC_MODEL_BASE_URL =
  "https://signaldeck-deterministic-model.local/v1";

type SeedModelConnectionPayload = {
  baseUrl: string;
  connectionKind: "provider" | "deterministic_smoke";
  description: string;
  key: string;
  modelId: string;
  name: string;
  protocolProfile: "openai_chat_completions" | "openai_responses";
  reasoningEffort: string | null;
  timeoutSeconds: number;
  apiKey?: string;
};

async function seedModelConnection(
  request: APIRequestContext,
  payload: SeedModelConnectionPayload,
) {
  const response = await request.post(`${PLATFORM_API_BASE}/model-connections`, {
    data: payload,
  });

  const responseText = await response.text();
  expect(response.status(), responseText).toBe(201);
  return JSON.parse(responseText) as { id: number; key: string; name: string };
}

async function seedTestedDeterministicConnection(
  request: APIRequestContext,
  suffix: number,
) {
  const connection = await seedModelConnection(request, {
    apiKey: "sk-e2e-redacted-model-connection",
    baseUrl: DETERMINISTIC_MODEL_BASE_URL,
    connectionKind: "deterministic_smoke",
    description: "Deterministic fixture for model connection inventory evidence.",
    key: `e2e_model_inventory_${suffix}`,
    modelId: "signaldeck-deterministic-json",
    name: `E2E Evidence Model ${suffix}`,
    protocolProfile: "openai_responses",
    reasoningEffort: null,
    timeoutSeconds: 5,
  });

  const testResponse = await request.post(
    `${PLATFORM_API_BASE}/model-connections/${connection.id}/connection-test`,
  );

  expect(testResponse.ok(), await testResponse.text()).toBeTruthy();
  return connection;
}

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

test.describe("model connections inventory", () => {
  test("renders evidence clusters and explicit edit actions for seeded connections", async ({
    page,
    request,
  }) => {
    const suffix = Date.now();
    const connection = await seedTestedDeterministicConnection(request, suffix);

    const listResponsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/model-connections") &&
        response.request().method() === "GET",
    );
    await page.goto("/model-connections");
    const listResponse = await listResponsePromise;
    const listResponseText = await listResponse.text();
    expect(listResponse.ok(), listResponseText).toBeTruthy();
    const listBody = JSON.parse(listResponseText) as { items: { id: number }[] };
    expect(listBody.items.some((item) => item.id === connection.id)).toBeTruthy();
    await expectSingleRouteMain(page, "route-model-connections-list", "scroll");
    await expect(page.getByTestId("platform-model-connections-page")).toBeVisible();

    await page
      .getByRole("textbox", { name: "Search model connections" })
      .fill(connection.key);

    const row = page.getByTestId(`model-connections-row-${connection.id}`);
    await expect(row).toBeVisible();
    await expect(row.getByLabel("Stable key: " + connection.key)).toBeVisible();

    for (const evidenceLabel of [
      "Protocol profile",
      "Test state",
      "Capability support",
      "Runtime policy",
      "Reachability",
      "Credential state",
    ]) {
      await expect(row.getByText(evidenceLabel)).toBeVisible();
    }

    await expect(row.getByText("Responses-compatible").first()).toBeVisible();
    await expect(row.getByText("Passed").first()).toBeVisible();
    await expect(row.getByText("API key optional")).toBeVisible();
    await expect(row.getByText("sk-e2e-redacted")).toHaveCount(0);

    const edit = row.getByRole("link", {
      name: `Edit model connection ${connection.name}`,
    });
    await expect(edit).toBeVisible();
    await expect(edit).toHaveAttribute(
      "href",
      `/model-connections/${connection.id}/edit`,
    );
  });
});
