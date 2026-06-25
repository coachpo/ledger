import { expect, test, type APIRequestContext } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const PLATFORM_API_BASE = "http://127.0.0.1:8001/api";
const FAKE_PROVIDER_BASE_URL =
  process.env.SIGNALDECK_FAKE_PROVIDER_BASE_URL ?? "http://127.0.0.1:18081/v1";
const FIXTURE_PATH = resolve(
  process.cwd(),
  "..",
  "backend",
  "tests",
  "fixtures",
  "workflow_packages",
  "tradingagents_advisory_research.yaml",
);

const LAUNCH_PARAMETERS = {
  ticker: "AAPL",
  asOfDate: "2026-05-08",
  portfolioId: "tradingagents_demo",
  horizonDays: 30,
  benchmarkSymbol: "SPY",
};

function fixtureSource() {
  return readFileSync(FIXTURE_PATH, "utf8");
}

async function seedTradingAgentsModel(request: APIRequestContext) {
  const list = await request.get(`${PLATFORM_API_BASE}/model-connections`, {
    params: { status: "active" },
  });
  expect(list.ok()).toBeTruthy();
  const existing = (await list.json()).items.find(
    (item: { id: number; key: string }) => item.key === "tradingagents_primary_model",
  );
  const payload = {
    key: "tradingagents_primary_model",
    name: "TradingAgents Primary Model",
    description: "Fake provider model binding for workflow-package E2E.",
    baseUrl: FAKE_PROVIDER_BASE_URL,
    modelId: "fake-strict-schema",
    reasoningEffort: "low",
    protocolProfile: "openai_responses",
    timeoutSeconds: 5,
    apiKey: "sk-e2e-tradingagents-fake-provider",
  };
  let connectionId: number;
  if (existing) {
    const { key: _key, ...updatePayload } = payload;
    const response = await request.patch(`${PLATFORM_API_BASE}/model-connections/${existing.id}`, { data: updatePayload });
    expect(response.ok()).toBeTruthy();
    connectionId = existing.id;
  } else {
    const response = await request.post(`${PLATFORM_API_BASE}/model-connections`, { data: payload });
    expect(response.ok()).toBeTruthy();
    connectionId = Number((await response.json()).id);
  }

  const probe = await request.post(
    `${PLATFORM_API_BASE}/model-connections/${connectionId}/capability-probe`,
    { data: { capabilityKeys: ["nativeToolCalls", "strictJsonSchemaOutput"], refresh: true } },
  );
  expect(probe.ok()).toBeTruthy();
}

async function createOrUpdatePackage(request: APIRequestContext, manifestSource: string) {
  const create = await request.post(`${PLATFORM_API_BASE}/workflow-packages`, { data: { manifestSource } });
  if (create.status() === 201) {
    return create.json();
  }
  const createBody = await create.text();
  if (create.status() !== 409) {
    throw new Error(`Unexpected workflow package create status ${create.status()}: ${createBody}`);
  }
  const list = await request.get(`${PLATFORM_API_BASE}/workflow-packages`);
  expect(list.ok()).toBeTruthy();
  const existing = (await list.json()).items.find(
    (item: { id: number; key: string }) => item.key === "tradingagents_advisory_research",
  );
  expect(existing).toBeTruthy();
  const updated = await request.patch(`${PLATFORM_API_BASE}/workflow-packages/${existing.id}`, {
    data: { manifestSource },
  });
  expect(updated.ok()).toBeTruthy();
  return updated.json();
}

async function waitForRun(request: APIRequestContext, runId: number) {
  const startedAt = Date.now();
  let latest: Record<string, unknown> | null = null;
  while (Date.now() - startedAt < 30_000) {
    const response = await request.get(`${PLATFORM_API_BASE}/runs/${runId}`);
    expect(response.ok()).toBeTruthy();
    const body = (await response.json()) as Record<string, unknown>;
    latest = body;
    if (!["queued", "running"].includes(String(body.status))) {
      return body;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Run ${runId} did not finish: ${JSON.stringify(latest)}`);
}

function workflowStepCount(detail: Record<string, unknown>) {
  const steps = Array.isArray(detail.steps) ? detail.steps : [];
  return new Set(
    steps
      .filter((step): step is { index: unknown } => typeof step === "object" && step !== null && "index" in step)
      .map((step) => Number(step.index)),
  ).size;
}

test.describe("TradingAgents workflow-package smoke", () => {
  test("launches the ordinary package fixture with fake provider output", async ({ request }) => {
    await seedTradingAgentsModel(request);
    const workflowPackage = await createOrUpdatePackage(request, fixtureSource());

    const preflight = await request.post(`${PLATFORM_API_BASE}/workflow-packages/${workflowPackage.id}/preflight`, {
      data: { workflowKey: "advisory_research", parameters: LAUNCH_PARAMETERS },
    });
    expect(preflight.ok()).toBeTruthy();
    expect(await preflight.json()).toMatchObject({ ready: true, workflowKey: "advisory_research" });

    const launch = await request.post(`${PLATFORM_API_BASE}/workflow-packages/${workflowPackage.id}/launches`, {
      data: { workflowKey: "advisory_research", parameters: LAUNCH_PARAMETERS },
    });
    expect(launch.status()).toBe(201);
    const launched = await launch.json();
    const detail = await waitForRun(request, Number(launched.id));

    expect(detail.status).toBe("succeeded");
    expect(detail.targetKind).toBe("workflowPackage");
    expect(detail.packageProvenance).toMatchObject({
      workflowPackageKey: "tradingagents_advisory_research",
      workflowKey: "advisory_research",
    });
    expect(workflowStepCount(detail)).toBeGreaterThanOrEqual(14);
    expect(detail.finalOutput).toMatchObject({ posture: "fake provider posture" });
  });

  test("reports missing model binding through launch readiness validation", async ({ request }) => {
    const suffix = Date.now();
    const missingModelKey = `missing_tradingagents_model_${suffix}`;
    const manifestSource = fixtureSource()
      .replace("key: tradingagents_advisory_research", `key: e2e_missing_model_${suffix}`)
      .replace(
        /modelConnection: tradingagents_primary_model/g,
        `modelConnection: ${missingModelKey}`,
      );

    const create = await request.post(`${PLATFORM_API_BASE}/workflow-packages`, {
      data: { manifestSource },
    });
    expect(create.status()).toBe(201);
    const created = await create.json();

    const launch = await request.post(
      `${PLATFORM_API_BASE}/workflow-packages/${created.id}/launches`,
      {
        data: { workflowKey: "advisory_research", parameters: LAUNCH_PARAMETERS },
      },
    );
    expect(launch.status()).toBe(422);
    const body = await launch.json();

    expect(body).toMatchObject({
      code: "validation_error",
      message: "Workflow package launch validation failed",
    });
    expect(body.details).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          field: "spec.agents[0].modelConnection",
          issue: `Model connection '${missingModelKey}' was not found`,
        }),
      ]),
    );
  });
});
