import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  WorkflowPackageManifestRead,
  WorkflowPackageRead,
} from "@/lib/types/workflow-package";

import { WorkflowPackageEditorPage } from "./editor";

const {
  createPackageMock,
  navigateMock,
  updatePackageMock,
  useCreateWorkflowPackageMock,
  useModelConnectionsMock,
  useToolsMock,
  useUpdateWorkflowPackageMock,
  useValidateWorkflowPackageManifestMock,
  useWorkflowPackageManifestMock,
  useWorkflowPackageMock,
  validateManifestMock,
} = vi.hoisted(() => ({
  createPackageMock: vi.fn(),
  navigateMock: vi.fn(),
  updatePackageMock: vi.fn(),
  useCreateWorkflowPackageMock: vi.fn(),
  useModelConnectionsMock: vi.fn(),
  useToolsMock: vi.fn(),
  useUpdateWorkflowPackageMock: vi.fn(),
  useValidateWorkflowPackageManifestMock: vi.fn(),
  useWorkflowPackageManifestMock: vi.fn(),
  useWorkflowPackageMock: vi.fn(),
  validateManifestMock: vi.fn(),
}));

vi.mock("react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router")>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("@/hooks/use-model-connections", () => ({
  useModelConnections: (...args: unknown[]) => useModelConnectionsMock(...args),
}));

vi.mock("@/hooks/use-workflow-packages", () => ({
  useCreateWorkflowPackage: () => useCreateWorkflowPackageMock(),
  useCreateWorkflowPackageLaunch: () => ({
    isPending: false,
    mutateAsync: vi.fn(),
  }),
  useDeleteWorkflowPackageSecretBinding: () => ({
    isPending: false,
    mutateAsync: vi.fn(),
  }),
  useImportWorkflowPackage: () => ({ isPending: false, mutateAsync: vi.fn() }),
  usePreflightWorkflowPackage: () => ({
    isPending: false,
    mutateAsync: vi.fn(),
  }),
  useTools: () => useToolsMock(),
  useUpdateWorkflowPackage: () => useUpdateWorkflowPackageMock(),
  useUpsertWorkflowPackageSecretBinding: () => ({
    isPending: false,
    mutateAsync: vi.fn(),
  }),
  useValidateWorkflowPackageManifest: () =>
    useValidateWorkflowPackageManifestMock(),
  useWorkflowPackage: (...args: unknown[]) => useWorkflowPackageMock(...args),
  useWorkflowPackageLaunch: () => ({
    data: undefined,
    error: null,
    isError: false,
    isPending: false,
  }),
  useWorkflowPackageManifest: (...args: unknown[]) =>
    useWorkflowPackageManifestMock(...args),
  useWorkflowPackageSecretBindings: () => ({
    data: { items: [] },
    error: null,
    isError: false,
    isPending: false,
  }),
}));

const packageRead: WorkflowPackageRead = {
  compiledHash: "compiled-hash-123",
  createdAt: "2026-05-01T10:00:00Z",
  description: "Private package for multi-agent market review.",
  id: 42,
  key: "market_review_package",
  lastLaunchedAt: "2026-05-05T11:00:00Z",
  manifestHash: "manifest-hash-123",
  name: "Market Review Package",
  status: "active",
  updatedAt: "2026-05-05T10:00:00Z",
  warnings: [],
};

const manifestRead: WorkflowPackageManifestRead = {
  compiledHash: "compiled-hash-123",
  manifestHash: "manifest-hash-123",
  manifestSource: `apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: hydrated_market_review
  name: Hydrated Market Review
  description: Manifest source description
spec:
  inputs:
    type: object
`,
  packageDefinition: {},
  packageId: 42,
  packageKey: "market_review_package",
};

function renderEditor(initialEntry = "/workflow-packages/42") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/workflow-packages/:packageId"
          element={<WorkflowPackageEditorPage />}
        />
        <Route
          path="/workflow-packages/new"
          element={<WorkflowPackageEditorPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

function clickTab(name: string) {
  fireEvent.click(screen.getByRole("tab", { name: `${name} tab` }));
}

describe("WorkflowPackageEditorPage resource editors", () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
    navigateMock.mockReset();
    createPackageMock.mockReset();
    updatePackageMock.mockReset();
    validateManifestMock.mockReset();
    createPackageMock.mockResolvedValue({ ...packageRead, id: 99 });
    updatePackageMock.mockResolvedValue(packageRead);
    validateManifestMock.mockResolvedValue({
      compiledHash: "compiled",
      compiledPlan: {},
      diagnostics: [],
      manifestHash: "manifest",
      metadata: null,
      packageDefinition: {},
      warnings: [],
    });
    useWorkflowPackageMock.mockReturnValue({
      data: packageRead,
      error: null,
      isError: false,
      isPending: false,
      refetch: vi.fn(),
    });
    useWorkflowPackageManifestMock.mockReturnValue({
      data: manifestRead,
      error: null,
      isError: false,
      isFetching: false,
      isPending: false,
      refetch: vi.fn(),
    });
    useCreateWorkflowPackageMock.mockReturnValue({
      isPending: false,
      mutateAsync: createPackageMock,
    });
    useUpdateWorkflowPackageMock.mockReturnValue({
      isPending: false,
      mutateAsync: updatePackageMock,
    });
    useValidateWorkflowPackageManifestMock.mockReturnValue({
      isPending: false,
      mutateAsync: validateManifestMock,
    });
    useModelConnectionsMock.mockReturnValue({
      data: {
        items: [
          {
            id: 1,
            key: "primary_model",
            status: "active",
            name: "Primary Model",
            description: "OpenAI",
            baseUrl: "https://api.openai.com/v1",
            modelId: "gpt-5.5",
            reasoningEffort: null,
            timeoutSeconds: 60,
            apiStyle: "responses",
          },
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });
    useToolsMock.mockReturnValue({
      data: {
        items: [
          {
            key: "signaldeck.reports.lookup",
            displayName: "Report Lookup",
            description: "Read reports",
          },
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });
  });

  it("opens package-local resource tabs and renders accessible editor controls", () => {
    renderEditor();

    clickTab("Agents");
    expect(screen.getByTestId("workflow-package-agents-tab")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Add Agent" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("Agent editor");
    expect(screen.getByLabelText("Agent local key")).toBeVisible();
    expect(screen.getByText("Select global model connection")).toBeVisible();
    expect(screen.getByLabelText("System prompt")).toBeVisible();
    expect(screen.getByLabelText("Budget USD")).toBeVisible();
    expect(screen.getByLabelText("Timeout seconds")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Close agent editor" }));

    clickTab("Output Schemas");
    fireEvent.click(screen.getByRole("button", { name: "Add Schema" }));
    expect(screen.getByTestId(/package-output-schema-card-/)).toHaveTextContent(
      "Output schema root",
    );

    clickTab("Capability Profiles");
    fireEvent.click(screen.getByRole("button", { name: "Add Profile" }));
    expect(screen.getByTestId("capability-tool-command")).toHaveTextContent(
      "Report Lookup",
    );

    clickTab("Private MCP");
    fireEvent.click(screen.getByRole("button", { name: "Add Private MCP" }));
    expect(screen.getByTestId(/package-private-mcp-card-/)).toHaveTextContent(
      "Environment values",
    );
    expect(
      screen.getByText(
        "Configure package-local MCP transport values inline for the selected transport.",
      ),
    ).toBeVisible();
  });

  it("hides disabled finance tools from authoring discovery and restores them", () => {
    useToolsMock.mockReturnValue({
      data: { items: [] },
      error: null,
      isError: false,
      isPending: false,
    });
    const disabledView = renderEditor();
    clickTab("Capability Profiles");
    fireEvent.click(screen.getByRole("button", { name: "Add Profile" }));
    expect(screen.getByTestId("capability-tool-command")).not.toHaveTextContent(
      "Report Lookup",
    );
    disabledView.unmount();

    useToolsMock.mockReturnValue({
      data: {
        items: [
          {
            key: "signaldeck.reports.lookup",
            displayName: "Report Lookup",
            description: "Read reports",
          },
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });
    renderEditor();
    clickTab("Capability Profiles");
    fireEvent.click(screen.getByRole("button", { name: "Add Profile" }));
    expect(screen.getByTestId("capability-tool-command")).toHaveTextContent(
      "Report Lookup",
    );
  });

  it("saves stdio private MCP inline env values through workflow package update", async () => {
    renderEditor();

    clickTab("Private MCP");
    fireEvent.click(screen.getByRole("button", { name: "Add Private MCP" }));
    fireEvent.change(screen.getByLabelText("Private MCP 1 local key"), {
      target: { value: "market_mcp" },
    });
    fireEvent.change(screen.getByLabelText("Private MCP 1 name"), {
      target: { value: "Market MCP" },
    });
    fireEvent.change(screen.getByLabelText("Private MCP 1 command"), {
      target: { value: "market-mcp" },
    });
    fireEvent.change(screen.getByLabelText("Private MCP 1 args"), {
      target: { value: '["--token", "${MARKET_DATA_API_KEY}"]' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add Env" }));
    fireEvent.change(screen.getByLabelText("Private MCP 1 env key 1"), {
      target: { value: "MARKET_DATA_API_KEY" },
    });
    fireEvent.change(screen.getByLabelText("Private MCP 1 env value 1"), {
      target: { value: "${MARKET_DATA_API_KEY}" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Save package draft" }));

    expect(updatePackageMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: expect.objectContaining({
        manifestSource: expect.stringContaining("env:"),
      }),
    });
    const payload = updatePackageMock.mock.calls[0][0].payload
      .manifestSource as string;
    expect(payload).toContain("env:");
    expect(payload).toContain("MARKET_DATA_API_KEY: ${MARKET_DATA_API_KEY}");
    expect(payload).toContain("command: market-mcp");
    expect(payload).toContain("args:");
    expect(createPackageMock).not.toHaveBeenCalled();
  });

  it("renders transport-specific inline value editors for private MCP servers", () => {
    useWorkflowPackageManifestMock.mockReturnValue({
      data: {
        ...manifestRead,
        manifestSource: `apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: hydrated_market_review
  name: Hydrated Market Review
  description: Manifest source description
spec:
  inputs:
    type: object
  mcpServers:
    - key: stdio_market
      name: Stdio Market
      transport: stdio
      command: market-mcp
      args: []
      env:
        MARKET_DATA_API_KEY: \${MARKET_DATA_API_KEY}
      toolKeys: []
    - key: http_market
      name: HTTP Market
      transport: http-sse
      url: https://example.com/mcp
      headers:
        Authorization: Bearer \${MARKET_DATA_API_KEY}
      query:
        apiKey: \${MARKET_DATA_API_KEY}
      toolKeys: []
`,
      },
      error: null,
      isError: false,
      isFetching: false,
      isPending: false,
      refetch: vi.fn(),
    });

    renderEditor();

    clickTab("Private MCP");
    expect(screen.getByLabelText("Private MCP 1 env key 1")).toHaveValue(
      "MARKET_DATA_API_KEY",
    );
    expect(
      screen.queryByLabelText("Private MCP 1 header key 1"),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("Private MCP 2 header key 1")).toHaveValue(
      "Authorization",
    );
    expect(screen.getByLabelText("Private MCP 2 query key 1")).toHaveValue(
      "apiKey",
    );
    expect(
      screen.queryByLabelText("Private MCP 2 env key 1"),
    ).not.toBeInTheDocument();
  });

  it("preserves workflow subtrees when saving unrelated tabs", async () => {
    renderEditor();

    clickTab("Output Schemas");
    fireEvent.click(screen.getByRole("button", { name: "Add Schema" }));
    fireEvent.click(screen.getByRole("button", { name: "Save package draft" }));

    const payload = updatePackageMock.mock.calls.at(-1)?.[0].payload
      .manifestSource as string;
    expect(payload).toContain("agents:");
    expect(payload).toContain("outputSchemas:");
    expect(payload).toContain("mcpServers:");
    expect(payload).toContain("outputSchemas:");
  });

  it("opens the matching agent sheet and focuses the diagnostic field", async () => {
    validateManifestMock.mockResolvedValueOnce({
      compiledHash: null,
      compiledPlan: null,
      diagnostics: [
        {
          column: null,
          line: null,
          message: "Missing model connection",
          path: "spec.agents[1].modelConnection",
          severity: "error",
        },
      ],
      manifestHash: null,
      metadata: null,
      packageDefinition: null,
      warnings: [],
    });
    renderEditor();

    clickTab("Agents");
    fireEvent.click(screen.getByRole("button", { name: "Add Agent" }));
    fireEvent.click(screen.getByRole("button", { name: "Close agent editor" }));
    fireEvent.click(screen.getByRole("button", { name: "Add Agent" }));
    fireEvent.click(screen.getByRole("button", { name: "Close agent editor" }));
    clickTab("Overview");

    fireEvent.click(
      screen.getByRole("button", { name: "Run package preflight" }),
    );

    expect(
      await screen.findByRole("tab", { name: "Agents tab" }),
    ).toHaveAttribute("aria-selected", "true");
    expect(
      await screen.findByTestId("package-agent-sheet-1"),
    ).toHaveTextContent("Missing model connection");
    await waitFor(() =>
      expect(document.activeElement).toHaveAttribute(
        "data-field",
        "spec.agents[1].modelConnection",
      ),
    );
    expect(screen.getByTestId("agents-validation-feedback")).toHaveTextContent(
      "spec.agents[1].modelConnection",
    );
  });

  it("focuses output schema diagnostics on the exact indexed field", async () => {
    validateManifestMock.mockResolvedValueOnce({
      compiledHash: null,
      compiledPlan: null,
      diagnostics: [
        {
          column: null,
          line: null,
          message: "Schema key is invalid",
          path: "spec.outputSchemas[1].key",
          severity: "error",
        },
      ],
      manifestHash: null,
      metadata: null,
      packageDefinition: null,
      warnings: [],
    });
    renderEditor();

    clickTab("Output Schemas");
    fireEvent.click(screen.getByRole("button", { name: "Add Schema" }));
    fireEvent.click(screen.getByRole("button", { name: "Add Schema" }));
    clickTab("Overview");

    fireEvent.click(
      screen.getByRole("button", { name: "Run package preflight" }),
    );

    expect(
      await screen.findByRole("tab", { name: "Output Schemas tab" }),
    ).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("Schema key is invalid")).toBeVisible();
    await waitFor(() =>
      expect(document.activeElement).toHaveAttribute(
        "data-field",
        "spec.outputSchemas[1].key",
      ),
    );
  });

  it("focuses capability profile and private MCP diagnostics by exact resource index", async () => {
    validateManifestMock
      .mockResolvedValueOnce({
        compiledHash: null,
        compiledPlan: null,
        diagnostics: [
          {
            column: null,
            line: null,
            message: "Select at least one tool",
            path: "spec.capabilityProfiles[1].toolKeys[0]",
            severity: "error",
          },
        ],
        manifestHash: null,
        metadata: null,
        packageDefinition: null,
        warnings: [],
      })
      .mockResolvedValueOnce({
        compiledHash: null,
        compiledPlan: null,
        diagnostics: [
          {
            column: null,
            line: null,
            message: "Environment value is required",
            path: "spec.mcpServers[1].env.MARKET_DATA_API_KEY",
            severity: "error",
          },
        ],
        manifestHash: null,
        metadata: null,
        packageDefinition: null,
        warnings: [],
      });
    renderEditor();

    clickTab("Capability Profiles");
    fireEvent.click(screen.getByRole("button", { name: "Add Profile" }));
    fireEvent.click(screen.getByRole("button", { name: "Add Profile" }));
    clickTab("Overview");
    fireEvent.click(
      screen.getByRole("button", { name: "Run package preflight" }),
    );

    expect(
      await screen.findByRole("tab", { name: "Capability Profiles tab" }),
    ).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("Select at least one tool")).toBeVisible();
    await waitFor(() =>
      expect(document.activeElement).toHaveAttribute(
        "data-field",
        "spec.capabilityProfiles[1].toolKeys[0]",
      ),
    );

    clickTab("Private MCP");
    fireEvent.click(screen.getByRole("button", { name: "Add Private MCP" }));
    fireEvent.click(screen.getByRole("button", { name: "Add Private MCP" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Add Env" })[1]);
    fireEvent.change(screen.getByLabelText("Private MCP 2 env key 1"), {
      target: { value: "MARKET_DATA_API_KEY" },
    });
    clickTab("Overview");
    fireEvent.click(
      screen.getByRole("button", { name: "Run package preflight" }),
    );

    expect(
      await screen.findByRole("tab", { name: "Private MCP tab" }),
    ).toHaveAttribute("aria-selected", "true");
    expect(
      await screen.findByText("Environment value is required"),
    ).toBeVisible();
    await waitFor(() =>
      expect(document.activeElement).toHaveAttribute(
        "data-field",
        "spec.mcpServers[1].env.MARKET_DATA_API_KEY",
      ),
    );
  });

});
