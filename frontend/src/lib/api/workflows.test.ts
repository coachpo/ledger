import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ORIGINAL_API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const ORIGINAL_FETCH = globalThis.fetch;

function createFetchMock() {
  return vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>();
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function getLastFetchCall(fetchMock: ReturnType<typeof createFetchMock>): {
  init: RequestInit | undefined;
  url: URL;
} {
  const call = fetchMock.mock.calls.at(-1);

  if (!call) {
    throw new Error("Expected fetch to be called");
  }

  const [input, init] = call;
  return { init, url: new URL(String(input)) };
}

async function loadWorkflowsApi(baseUrl: string = "") {
  vi.resetModules();
  Reflect.set(import.meta.env, "VITE_API_BASE_URL", baseUrl);
  return import("./workflows");
}

const manifestSource = `apiVersion: ledger.workflow/v1
kind: Workflow
metadata:
  key: manifest_api_workflow
  name: Manifest API Workflow
inputSchema:
  type: object
steps:
  - id: research
    agents:
      - uses: manifest_api_agent@1
        slot: analysis
output:
  from: \${{ steps.research.outputs.analysis }}`;

let fetchMock = createFetchMock();

beforeEach(() => {
  fetchMock = createFetchMock();
  globalThis.fetch = fetchMock as typeof fetch;
  Reflect.set(import.meta.env, "VITE_API_BASE_URL", "");
});

afterEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = ORIGINAL_FETCH;
  Reflect.set(import.meta.env, "VITE_API_BASE_URL", ORIGINAL_API_BASE_URL);
});

describe("workflows api", () => {
  it("posts manifest validation requests to the platform validation endpoint", async () => {
    const { validateWorkflowManifest } = await loadWorkflowsApi("https://ledger.example.com/api/v1/");
    const validationResult = {
      diagnostics: [],
      metadata: {
        apiVersion: "ledger.workflow/v1",
        key: "manifest_api_workflow",
        name: "Manifest API Workflow",
        description: "",
      },
      compiledPayload: {
        key: "manifest_api_workflow",
        name: "Manifest API Workflow",
        inputSchema: { type: "object" },
        steps: [],
        outputSpec: { kind: "slot", stepIndex: 1, slot: "analysis" },
      },
      runInputSchema: { type: "object", additionalProperties: false },
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(validationResult, 200));

    await expect(validateWorkflowManifest({ manifestSource })).resolves.toEqual(validationResult);

    const { init, url } = getLastFetchCall(fetchMock);
    expect(`${url.origin}${url.pathname}`).toBe(
      "https://ledger.example.com/api/workflows/validate-manifest",
    );
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ manifestSource }));
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
  });

  it("reads workflow manifests from the platform detail endpoint", async () => {
    const { getWorkflow } = await loadWorkflowsApi("https://ledger.example.com/api/v1/");
    const workflowRead = {
      id: 12,
      aggregateBudgetUsd: "0.25000000",
      createdAt: "2026-04-20T10:00:00Z",
      description: "Manifest-backed read contract.",
      inputSchema: { type: "object" },
      key: "manifest_api_workflow",
      manifestApiVersion: "ledger.workflow/v1",
      manifestSource,
      name: "Manifest API Workflow",
      outputSpec: {
        agentId: 7,
        agentKey: "manifest_api_agent",
        agentVersion: 1,
        kind: "slot",
        outputSchemaId: 3,
        outputSchemaVersion: 1,
        slot: "analysis",
        stepIndex: 1,
      },
      status: "draft",
      steps: [],
      updatedAt: "2026-04-20T10:00:00Z",
      version: 2,
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(workflowRead, 200));

    await expect(getWorkflow(12, { version: 2 })).resolves.toEqual(workflowRead);

    const { init, url } = getLastFetchCall(fetchMock);
    expect(`${url.origin}${url.pathname}`).toBe("https://ledger.example.com/api/workflows/12");
    expect(url.searchParams.get("version")).toBe("2");
    expect(init?.method).toBe("GET");
  });

  it("sends manifestSource-only payloads when creating workflows from YAML", async () => {
    const { createWorkflow } = await loadWorkflowsApi("https://ledger.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 11 }, 201));

    await createWorkflow({ manifestSource });

    const { init, url } = getLastFetchCall(fetchMock);
    expect(`${url.origin}${url.pathname}`).toBe("https://ledger.example.com/api/workflows");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ manifestSource }));
  });

  it("sends manifestSource-only payloads when updating workflows from YAML", async () => {
    const { updateWorkflow } = await loadWorkflowsApi("https://ledger.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 12 }, 200));

    await updateWorkflow(12, { manifestSource });

    const { init, url } = getLastFetchCall(fetchMock);
    expect(`${url.origin}${url.pathname}`).toBe("https://ledger.example.com/api/workflows/12");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ manifestSource }));
  });
});
