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

async function loadAgentsApi(baseUrl: string = "") {
  vi.resetModules();
  Reflect.set(import.meta.env, "VITE_API_BASE_URL", baseUrl);
  return import("./agents");
}

const manifestSource = `apiVersion: signaldeck.agent/v1
kind: Agent
metadata:
  key: manifest_api_agent
  name: Manifest API Agent
spec:
  modelConnection: primary_openai
  systemPrompt: Analyze carefully.
  inputSchema:
    type: object
  outputSchema: summary_schema@1
  capabilities: []
  mcpServers: []
  budgetUsd: "0"`;

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

describe("agents api", () => {
  it("posts manifest validation requests to the platform validation endpoint", async () => {
    const { validateAgentManifest } = await loadAgentsApi("https://signaldeck.example.com/api/v1/");
    const validationResult = {
      diagnostics: [],
      metadata: {
        apiVersion: "signaldeck.agent/v1",
        key: "manifest_api_agent",
        name: "Manifest API Agent",
        description: "",
      },
      compiledPayload: {
        key: "manifest_api_agent",
        name: "Manifest API Agent",
        modelConnectionId: 7,
        systemPrompt: "Analyze carefully.",
        inputSchema: { type: "object" },
        outputSchemaKey: "summary_schema",
        outputSchemaVersion: 1,
        capabilities: [],
        mcpServers: [],
        budgetUsd: "0",
      },
      runInputSchema: { type: "object", additionalProperties: false },
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(validationResult, 200));

    await expect(validateAgentManifest({ manifestSource })).resolves.toEqual(validationResult);

    const { init, url } = getLastFetchCall(fetchMock);
    expect(`${url.origin}${url.pathname}`).toBe(
      "https://signaldeck.example.com/api/agents/validate-manifest",
    );
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ manifestSource }));
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
  });

  it("sends manifestSource-only payloads when creating agents from YAML", async () => {
    const { createAgent } = await loadAgentsApi("https://signaldeck.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 11 }, 201));

    await createAgent({
      budgetUsd: "99",
      inputSchema: { type: "object" },
      key: "legacy_agent",
      manifestSource,
      modelConnectionId: 99,
      name: "Legacy Agent",
      outputSchemaKey: "legacy_schema",
      systemPrompt: "Legacy prompt",
    } as never);

    const { init, url } = getLastFetchCall(fetchMock);
    expect(`${url.origin}${url.pathname}`).toBe("https://signaldeck.example.com/api/agents");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ manifestSource }));
  });

  it("sends manifestSource-only payloads when updating agents from YAML", async () => {
    const { updateAgent } = await loadAgentsApi("https://signaldeck.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 12 }, 200));

    await updateAgent(12, {
      budgetUsd: "99",
      inputSchema: { type: "object" },
      manifestSource,
      modelConnectionId: 99,
      name: "Legacy Agent",
      outputSchemaKey: "legacy_schema",
      systemPrompt: "Legacy prompt",
    } as never);

    const { init, url } = getLastFetchCall(fetchMock);
    expect(`${url.origin}${url.pathname}`).toBe("https://signaldeck.example.com/api/agents/12");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ manifestSource }));
  });
});
