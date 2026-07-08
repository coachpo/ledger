import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError } from "@/lib/api-client";
import type {
  WorkflowPackageLaunchRead,
  WorkflowPackageManifestRead,
  WorkflowPackageRead,
} from "@/lib/types/workflow-package";

import { WorkflowPackageLaunchPage } from "./launch";

const {
  createLaunchMock,
  navigateMock,
  preflightPackageMock,
  useCreateLaunchMock,
  usePreflightPackageMock,
  useWorkflowPackageLaunchMock,
  useWorkflowPackageManifestMock,
  useWorkflowPackageMock,
} = vi.hoisted(() => ({
  createLaunchMock: vi.fn(),
  navigateMock: vi.fn(),
  preflightPackageMock: vi.fn(),
  useCreateLaunchMock: vi.fn(),
  usePreflightPackageMock: vi.fn(),
  useWorkflowPackageLaunchMock: vi.fn(),
  useWorkflowPackageManifestMock: vi.fn(),
  useWorkflowPackageMock: vi.fn(),
}));

vi.mock("react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router")>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("@/hooks/use-workflow-packages", () => ({
  useCreateWorkflowPackageLaunch: () => useCreateLaunchMock(),
  usePreflightWorkflowPackage: () => usePreflightPackageMock(),
  useWorkflowPackage: (...args: unknown[]) => useWorkflowPackageMock(...args),
  useWorkflowPackageLaunch: (...args: unknown[]) => useWorkflowPackageLaunchMock(...args),
  useWorkflowPackageManifest: (...args: unknown[]) => useWorkflowPackageManifestMock(...args),
}));

const packageRead: WorkflowPackageRead = {
  compiledHash: "compiled-hash-123",
  createdAt: "2026-05-01T10:00:00Z",
  description: "Package for neutral research workflows.",
  id: 42,
  key: "market_review_package",
  manifestHash: "manifest-hash-123",
  name: "Market Review Package",
  updatedAt: "2026-05-05T10:00:00Z",
};

const marketReviewWorkflow = {
  description: "Run market review",
  inputSchema: {
    properties: {
      ticker: { description: "Ticker symbol", title: "Ticker", type: "string" },
    },
    required: ["ticker"],
    type: "object",
  },
  key: "market_review",
  name: "Market Review",
};

const manifestRead: WorkflowPackageManifestRead = {
  compiledHash: "compiled-hash-123",
  manifestHash: "manifest-hash-123",
  manifestSource: "apiVersion: signaldeck.workflowPackage/v1",
  packageDefinition: {
    spec: {
      workflows: [marketReviewWorkflow],
    },
  },
  packageId: 42,
  packageKey: "market_review_package",
};

const launchRead: WorkflowPackageLaunchRead = {
  blockingErrors: [],
  description: "Run market review",
  inputSchema: {
    properties: {
      ticker: { description: "Ticker symbol", title: "Ticker", type: "string" },
    },
    required: ["ticker"],
    type: "object",
  },
  manifestHash: "manifest-hash-123",
  name: "Market Review",
  packageId: 42,
  packageKey: "market_review_package",
  ready: true,
  resolvedModelConnections: [],
  warnings: [],
  workflowKey: "market_review",
};

function renderLaunchPage(initialEntry = "/workflow-packages/42/run") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/workflow-packages/:packageId/run" element={<WorkflowPackageLaunchPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function chooseWorkflow(name = "Market Review") {
  const selector = screen.getByRole("combobox", { name: /workflow/i });
  selector.focus();
  fireEvent.keyDown(selector, { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name }));
  await waitFor(() => expect(selector).toHaveTextContent(name));
}

async function completeReadyPreflight() {
  fireEvent.click(screen.getByRole("button", { name: /run preflight/i }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: /launch run/i })).not.toBeDisabled(),
  );
}

async function enterTickerViaForm(value: string) {
  const schemaForm = await screen.findByTestId("runtime-input-schema-form");
  fireEvent.change(within(schemaForm).getByRole("textbox", { name: "Ticker" }), {
    target: { value },
  });
}

describe("WorkflowPackageLaunchPage", () => {
  beforeEach(() => {
    createLaunchMock.mockReset();
    navigateMock.mockReset();
    preflightPackageMock.mockReset();
    useWorkflowPackageMock.mockReset();
    useWorkflowPackageLaunchMock.mockReset();
    useWorkflowPackageManifestMock.mockReset();

    preflightPackageMock.mockResolvedValue(launchRead);
    createLaunchMock.mockResolvedValue({
      createdAt: "2026-05-08T10:00:00Z",
      id: 99,
      status: "queued",
      workflowKey: "market_review",
      workflowPackageId: 42,
      workflowPackageKey: "market_review_package",
    });

    useWorkflowPackageMock.mockReturnValue({
      data: packageRead,
      error: null,
      isError: false,
      isPending: false,
    });
    useWorkflowPackageManifestMock.mockReturnValue({
      data: manifestRead,
      error: null,
      isError: false,
      isPending: false,
    });
    useWorkflowPackageLaunchMock.mockReturnValue({
      data: launchRead,
      error: null,
      isError: false,
      isPending: false,
    });
    usePreflightPackageMock.mockReturnValue({
      isPending: false,
      mutateAsync: preflightPackageMock,
    });
    useCreateLaunchMock.mockReturnValue({
      isPending: false,
      mutateAsync: createLaunchMock,
    });
  });

  it("renders without the removed saved inputs helper", async () => {
    renderLaunchPage();

    expect(screen.getByTestId("workflow-package-launch-page")).toBeVisible();
    expect(screen.queryByTestId("runtime-input-saved-inputs-helper")).not.toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(useWorkflowPackageLaunchMock).toHaveBeenLastCalledWith("42", undefined),
    );
  });

  it("renders an invalid route state for non-numeric package ids", () => {
    renderLaunchPage("/workflow-packages/new/run");
    expect(screen.getByText("Invalid workflow package launch route")).toBeVisible();
  });

  it("launches a package run after preflight and navigates to run detail", async () => {
    renderLaunchPage();

    await chooseWorkflow();
    await enterTickerViaForm("AAPL");
    await completeReadyPreflight();
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    await waitFor(() =>
      expect(preflightPackageMock).toHaveBeenCalledWith({
        packageId: "42",
        payload: { parameters: { ticker: "AAPL" }, workflowKey: "market_review" },
      }),
    );
    expect(createLaunchMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: { parameters: { ticker: "AAPL" }, workflowKey: "market_review" },
    });
    expect(navigateMock).toHaveBeenCalledWith("/runs/99");
  });

  it("blocks create-launch when preflight returns blocking diagnostics", async () => {
    preflightPackageMock.mockResolvedValueOnce({
      ...launchRead,
      blockingErrors: [{ field: "spec.agents[0].modelConnection", issue: "Missing model connection primary_model" }],
      ready: false,
    });
    renderLaunchPage();

    await chooseWorkflow();
    await enterTickerViaForm("AAPL");
    fireEvent.click(screen.getByRole("button", { name: /run preflight/i }));

    expect(await screen.findByText(/Missing model connection primary_model/i)).toBeVisible();
    expect(screen.getByRole("button", { name: /launch run/i })).toBeDisabled();
    expect(createLaunchMock).not.toHaveBeenCalled();
  });

  it("prevents preflight and launch when advanced JSON is invalid", async () => {
    renderLaunchPage();

    await chooseWorkflow();
    await completeReadyPreflight();
    preflightPackageMock.mockClear();
    fireEvent.click(screen.getByRole("radio", { name: "JSON" }));
    fireEvent.change(screen.getByLabelText("Runtime inputs JSON"), {
      target: { value: '{"ticker":' },
    });

    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));
    const feedback = await screen.findByTestId("runtime-input-validation-feedback");
    expect(feedback).toHaveTextContent("Runtime inputs JSON");
    expect(preflightPackageMock).not.toHaveBeenCalled();
    expect(createLaunchMock).not.toHaveBeenCalled();
  });

  it("rejects non-object advanced JSON locally", async () => {
    renderLaunchPage();

    await chooseWorkflow();
    fireEvent.click(screen.getByRole("radio", { name: "JSON" }));
    fireEvent.change(screen.getByLabelText("Runtime inputs JSON"), {
      target: { value: "[]" },
    });
    fireEvent.click(screen.getByRole("button", { name: /run preflight/i }));

    const feedback = await screen.findByTestId("runtime-input-validation-feedback");
    expect(feedback).toHaveTextContent("Runtime inputs JSON must be a valid object.");
    expect(preflightPackageMock).not.toHaveBeenCalled();
    expect(createLaunchMock).not.toHaveBeenCalled();
  });

  it("shows backend path-specific launch validation details inline", async () => {
    createLaunchMock.mockRejectedValueOnce(new ApiRequestError({
      code: "validation_error",
      details: [{ field: "parameters.ticker", issue: "Ticker is required." }],
      message: "Workflow package launch validation failed",
      status: 422,
    }));
    renderLaunchPage();

    await chooseWorkflow();
    await enterTickerViaForm("AAPL");
    await completeReadyPreflight();
    fireEvent.click(screen.getByRole("button", { name: /launch run/i }));

    const feedback = await screen.findByTestId("runtime-input-validation-feedback");
    expect(feedback).toHaveTextContent("parameters.ticker");
    expect(feedback).toHaveTextContent("Ticker is required.");
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("keeps raw JSON fallback for unsupported workflow input schemas", async () => {
    const unsupportedInputSchema = {
      patternProperties: { "^x-": { type: "string" } },
      properties: {},
      type: "object",
    };
    const unsupportedManifest: WorkflowPackageManifestRead = {
      ...manifestRead,
      packageDefinition: {
        spec: {
          workflows: [
            {
              ...marketReviewWorkflow,
              inputSchema: unsupportedInputSchema,
            },
          ],
        },
      },
    };
    useWorkflowPackageManifestMock.mockReturnValue({
      data: unsupportedManifest,
      error: null,
      isError: false,
      isPending: false,
    });
    useWorkflowPackageLaunchMock.mockReturnValue({
      data: { ...launchRead, inputSchema: unsupportedInputSchema },
      error: null,
      isError: false,
      isPending: false,
    });
    renderLaunchPage();

    await chooseWorkflow();
    expect(screen.getByTestId("runtime-input-schema-template-warning")).toBeVisible();
    expect(screen.queryByRole("radio", { name: "Form" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Runtime inputs JSON"), {
      target: { value: '{"x-note":"raw"}' },
    });
    fireEvent.click(screen.getByRole("button", { name: /run preflight/i }));

    await waitFor(() =>
      expect(preflightPackageMock).toHaveBeenCalledWith({
        packageId: "42",
        payload: { parameters: { "x-note": "raw" }, workflowKey: "market_review" },
      }),
    );
  });

  it("resets runtime JSON state when switching workflows", async () => {
    const newsSchema = {
      properties: {
        query: { title: "Query", type: "string" },
      },
      required: ["query"],
      type: "object",
    };
    const multiWorkflowManifest: WorkflowPackageManifestRead = {
      ...manifestRead,
      packageDefinition: {
        spec: {
          workflows: [
            marketReviewWorkflow,
            {
              description: "Run news review",
              inputSchema: newsSchema,
              key: "news_research",
              name: "News Research",
            },
          ],
        },
      },
    };
    useWorkflowPackageManifestMock.mockReturnValue({
      data: multiWorkflowManifest,
      error: null,
      isError: false,
      isPending: false,
    });
    useWorkflowPackageLaunchMock.mockImplementation((_packageId, workflowKey) => ({
      data: workflowKey === "news_research"
        ? {
            ...launchRead,
            description: "Run news review",
            inputSchema: newsSchema,
            name: "News Research",
            workflowKey: "news_research",
          }
        : launchRead,
      error: null,
      isError: false,
      isPending: false,
    }));
    renderLaunchPage();

    await chooseWorkflow();
    fireEvent.click(screen.getByRole("radio", { name: "JSON" }));
    fireEvent.change(screen.getByLabelText("Runtime inputs JSON"), {
      target: { value: '{"ticker":"AAPL"}' },
    });

    await chooseWorkflow("News Research");

    expect(screen.getByLabelText("Runtime inputs JSON")).toHaveValue(
      JSON.stringify({ query: "" }, null, 2),
    );
    expect(screen.queryByTestId("runtime-input-validation-feedback")).not.toBeInTheDocument();
  });

  it("applies valid advanced JSON back to the launch form", async () => {
    renderLaunchPage();

    await chooseWorkflow();
    fireEvent.click(screen.getByRole("radio", { name: "JSON" }));
    const runtimeJson = screen.getByLabelText("Runtime inputs JSON");
    fireEvent.change(runtimeJson, { target: { value: '{"ticker":"NVDA"}' } });
    fireEvent.click(screen.getByRole("button", { name: "Apply JSON to form" }));

    const schemaForm = await screen.findByTestId("runtime-input-schema-form");
    expect(within(schemaForm).getByRole("textbox", { name: "Ticker" })).toHaveValue("NVDA");
    expect(runtimeJson).toHaveValue(JSON.stringify({ ticker: "NVDA" }, null, 2));
  });
});
