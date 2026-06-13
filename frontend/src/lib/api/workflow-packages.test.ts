import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkflowPackageMetadataRead } from "../types/workflow-package";

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

function getLastFetchCall(fetchMock: ReturnType<typeof createFetchMock>) {
  const call = fetchMock.mock.calls.at(-1);
  if (!call) {
    throw new Error("Expected fetch to be called");
  }
  const [input, init] = call;
  return { init, url: new URL(String(input)) };
}

async function loadWorkflowPackagesApi(baseUrl: string = "") {
  vi.resetModules();
  Reflect.set(import.meta.env, "VITE_API_BASE_URL", baseUrl);
  return import("./workflow-packages");
}

const manifestSource = `apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: research_package
  name: Research Package
spec:
  workflows: []`;

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

describe("workflow packages api", () => {
  it("lists workflow packages from the unversioned platform endpoint", async () => {
    const { listWorkflowPackages } = await loadWorkflowPackagesApi("https://signaldeck.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [] }, 200));

    await expect(listWorkflowPackages()).resolves.toEqual({ items: [] });

    const { init, url } = getLastFetchCall(fetchMock);
    expect(`${url.origin}${url.pathname}`).toBe("https://signaldeck.example.com/api/workflow-packages");
    expect(url.searchParams.toString()).toBe("");
    expect(init?.method).toBe("GET");
  });

  it("deletes workflow packages without expecting a response body", async () => {
    const { deleteWorkflowPackage } = await loadWorkflowPackagesApi("https://signaldeck.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));

    await expect(deleteWorkflowPackage(17)).resolves.toBeUndefined();

    const { init, url } = getLastFetchCall(fetchMock);
    expect(`${url.origin}${url.pathname}`).toBe("https://signaldeck.example.com/api/workflow-packages/17");
    expect(init?.method).toBe("DELETE");
  });

  it("posts manifest validation and create requests with manifestSource", async () => {
    const { createWorkflowPackage, validateWorkflowPackageManifest } = await loadWorkflowPackagesApi(
      "https://signaldeck.example.com/api/v1/",
    );
    const validationRead = {
      diagnostics: [],
      warnings: [],
      metadata: {
        apiVersion: "signaldeck.workflowPackage/v1",
        key: "research_package",
        name: "Research Package",
        description: "",
      } satisfies WorkflowPackageMetadataRead,
      packageDefinition: { metadata: { key: "research_package" } },
      compiledPlan: { packageKey: "research_package" },
      manifestHash: "abc",
      compiledHash: "def",
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(validationRead, 200));
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 11, key: "research_package" }, 201));

    await expect(validateWorkflowPackageManifest({ manifestSource })).resolves.toEqual(validationRead);
    expect(getLastFetchCall(fetchMock).init?.body).toBe(JSON.stringify({ manifestSource }));

    await expect(createWorkflowPackage({ manifestSource })).resolves.toEqual({ id: 11, key: "research_package" });
    const { init, url } = getLastFetchCall(fetchMock);
    expect(`${url.origin}${url.pathname}`).toBe("https://signaldeck.example.com/api/workflow-packages");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ manifestSource }));
  });

  it("uses PATCH for package updates and POST for current package imports", async () => {
    const { importWorkflowPackage, updateWorkflowPackage } = await loadWorkflowPackagesApi("https://signaldeck.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 12 }, 200));
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 12 }, 201));

    await updateWorkflowPackage(12, { manifestSource });
    let lastCall = getLastFetchCall(fetchMock);
    expect(`${lastCall.url.origin}${lastCall.url.pathname}`).toBe("https://signaldeck.example.com/api/workflow-packages/12");
    expect(lastCall.init?.method).toBe("PATCH");
    expect(lastCall.init?.body).toBe(JSON.stringify({ manifestSource }));

    await importWorkflowPackage({ manifestSource });
    lastCall = getLastFetchCall(fetchMock);
    expect(`${lastCall.url.origin}${lastCall.url.pathname}`).toBe("https://signaldeck.example.com/api/workflow-packages/import");
    expect(lastCall.init?.method).toBe("POST");
    expect(lastCall.init?.body).toBe(JSON.stringify({ manifestSource }));
  });

  it("builds current export URLs without fetching", async () => {
    const { exportWorkflowPackageUrl } = await loadWorkflowPackagesApi("https://signaldeck.example.com/api/v1/");

    expect(exportWorkflowPackageUrl(12)).toBe("https://signaldeck.example.com/api/workflow-packages/12/export");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts preflight bodies and reads launch metadata with workflowKey query params", async () => {
    const { getWorkflowPackageLaunch, preflightWorkflowPackage } = await loadWorkflowPackagesApi(
      "https://signaldeck.example.com/api/v1/",
    );
    fetchMock.mockResolvedValueOnce(jsonResponse({ packageId: 12, ready: true }, 200));
    fetchMock.mockResolvedValueOnce(jsonResponse({ packageId: 12, ready: true }, 200));

    await preflightWorkflowPackage(12, {
      parameters: { ticker: "MSFT" },
      workflowKey: "summarize",
    });
    let lastCall = getLastFetchCall(fetchMock);
    expect(`${lastCall.url.origin}${lastCall.url.pathname}`).toBe("https://signaldeck.example.com/api/workflow-packages/12/preflight");
    expect(Object.fromEntries(lastCall.url.searchParams.entries())).toEqual({});
    expect(lastCall.init?.method).toBe("POST");
    expect(JSON.parse(String(lastCall.init?.body))).toEqual({
      parameters: { ticker: "MSFT" },
      workflowKey: "summarize",
    });

    await getWorkflowPackageLaunch(12, { workflowKey: "summarize" });
    lastCall = getLastFetchCall(fetchMock);
    expect(`${lastCall.url.origin}${lastCall.url.pathname}`).toBe("https://signaldeck.example.com/api/workflow-packages/12/launch");
    expect(Object.fromEntries(lastCall.url.searchParams.entries())).toEqual({ workflowKey: "summarize" });
    expect(lastCall.init?.method).toBe("GET");
  });

  it("creates launches with package workflow metadata", async () => {
    const { createWorkflowPackageLaunch } = await loadWorkflowPackagesApi("https://signaldeck.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 99, status: "queued" }, 201));

    await expect(
      createWorkflowPackageLaunch(12, {
        workflowKey: "summarize",
        parameters: { ticker: "MSFT" },
      }),
    ).resolves.toEqual({ id: 99, status: "queued" });

    const { init, url } = getLastFetchCall(fetchMock);
    expect(`${url.origin}${url.pathname}`).toBe("https://signaldeck.example.com/api/workflow-packages/12/launches");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ workflowKey: "summarize", parameters: { ticker: "MSFT" } }));
  });

  it("reads and mutates workflow-scoped runtime input registry preset entries", async () => {
    const {
      createWorkflowPackageRuntimeInputPresetEntry,
      deleteWorkflowPackageRuntimeInputPresetEntry,
      getWorkflowPackageRuntimeInputRegistry,
      updateWorkflowPackageRuntimeInputPresetEntry,
    } = await loadWorkflowPackagesApi("https://signaldeck.example.com/api/v1/");
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          packageId: 12,
          packageKey: "research_package",
          workflowKey: "summarize",
          currentMetadata: null,
          presets: [],
          history: [],
        },
        200,
      ),
    );
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 7, slot: "preset" }, 201));
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 7, slot: "preset" }, 200));
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));

    await getWorkflowPackageRuntimeInputRegistry(12, { workflowKey: "summarize" });
    let lastCall = getLastFetchCall(fetchMock);
    expect(`${lastCall.url.origin}${lastCall.url.pathname}`).toBe(
      "https://signaldeck.example.com/api/workflow-packages/12/runtime-input-registry",
    );
    expect(Object.fromEntries(lastCall.url.searchParams.entries())).toEqual({ workflowKey: "summarize" });
    expect(lastCall.init?.method).toBe("GET");

    await createWorkflowPackageRuntimeInputPresetEntry(
      12,
      { name: "Morning", payload: { ticker: "MSFT" } },
      { workflowKey: "summarize" },
    );
    lastCall = getLastFetchCall(fetchMock);
    expect(`${lastCall.url.origin}${lastCall.url.pathname}`).toBe(
      "https://signaldeck.example.com/api/workflow-packages/12/runtime-input-registry/presets",
    );
    expect(Object.fromEntries(lastCall.url.searchParams.entries())).toEqual({ workflowKey: "summarize" });
    expect(lastCall.init?.method).toBe("POST");
    expect(lastCall.init?.body).toBe(JSON.stringify({ name: "Morning", payload: { ticker: "MSFT" } }));

    await updateWorkflowPackageRuntimeInputPresetEntry(
      12,
      7,
      { payload: { ticker: "AVGO" } },
      { workflowKey: "summarize" },
    );
    lastCall = getLastFetchCall(fetchMock);
    expect(`${lastCall.url.origin}${lastCall.url.pathname}`).toBe(
      "https://signaldeck.example.com/api/workflow-packages/12/runtime-input-registry/presets/7",
    );
    expect(Object.fromEntries(lastCall.url.searchParams.entries())).toEqual({ workflowKey: "summarize" });
    expect(lastCall.init?.method).toBe("PATCH");
    expect(lastCall.init?.body).toBe(JSON.stringify({ payload: { ticker: "AVGO" } }));

    await expect(
      deleteWorkflowPackageRuntimeInputPresetEntry(12, 7, { workflowKey: "summarize" }),
    ).resolves.toBeUndefined();
    lastCall = getLastFetchCall(fetchMock);
    expect(`${lastCall.url.origin}${lastCall.url.pathname}`).toBe(
      "https://signaldeck.example.com/api/workflow-packages/12/runtime-input-registry/presets/7",
    );
    expect(Object.fromEntries(lastCall.url.searchParams.entries())).toEqual({ workflowKey: "summarize" });
    expect(lastCall.init?.method).toBe("DELETE");
  });
});
;
