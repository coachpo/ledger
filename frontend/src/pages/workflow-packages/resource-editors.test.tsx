import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkflowPackageRead } from "@/lib/types/workflow-package";

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
  useCreateWorkflowPackageLaunch: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useImportWorkflowPackage: () => ({ isPending: false, mutateAsync: vi.fn() }),
  usePreflightWorkflowPackage: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useTools: () => useToolsMock(),
  useUpdateWorkflowPackage: () => useUpdateWorkflowPackageMock(),
  useValidateWorkflowPackageManifest: () => useValidateWorkflowPackageManifestMock(),
  useWorkflowPackage: (...args: unknown[]) => useWorkflowPackageMock(...args),
  useWorkflowPackageLaunch: () => ({ data: undefined, error: null, isError: false, isPending: false }),
  useWorkflowPackageVersions: () => ({ data: { items: [] }, error: null, isError: false, isPending: false }),
}));

const packageRead: WorkflowPackageRead = {
  archivedAt: null,
  compiledHash: "compiled-hash-123",
  createdAt: "2026-05-01T10:00:00Z",
  description: "Private package for multi-agent market review.",
  id: 42,
  key: "market_review_package",
  latestVersion: 7,
  latestVersionId: 70,
  manifestHash: "manifest-hash-123",
  name: "Market Review Package",
  status: "active",
  updatedAt: "2026-05-05T10:00:00Z",
  warnings: [],
};

function renderEditor(initialEntry = "/workflow-packages/42") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/workflow-packages/:packageId" element={<WorkflowPackageEditorPage />} />
        <Route path="/workflow-packages/new" element={<WorkflowPackageEditorPage />} />
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
    useWorkflowPackageMock.mockReturnValue({ data: packageRead, error: null, isError: false, isPending: false });
    useCreateWorkflowPackageMock.mockReturnValue({ isPending: false, mutateAsync: createPackageMock });
    useUpdateWorkflowPackageMock.mockReturnValue({ isPending: false, mutateAsync: updatePackageMock });
    useValidateWorkflowPackageManifestMock.mockReturnValue({ isPending: false, mutateAsync: validateManifestMock });
    useModelConnectionsMock.mockReturnValue({
      data: { items: [{ id: 1, key: "primary_model", status: "active", name: "Primary Model", description: "OpenAI", baseUrl: "https://api.openai.com/v1", modelId: "gpt-5.5", reasoningEffort: null, timeoutSeconds: 60, apiStyle: "responses" }] },
      error: null,
      isError: false,
      isPending: false,
    });
    useToolsMock.mockReturnValue({
      data: { items: [{ key: "ledger.reports.lookup", displayName: "Report Lookup", description: "Read reports", module: "ledger.reports" }] },
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
    expect(screen.getByTestId(/package-output-schema-card-/)).toHaveTextContent("Output schema root");

    clickTab("Capability Profiles");
    fireEvent.click(screen.getByRole("button", { name: "Add Profile" }));
    expect(screen.getByTestId("capability-tool-command")).toHaveTextContent("Report Lookup");

    clickTab("Private MCP");
    fireEvent.click(screen.getByRole("button", { name: "Add Private MCP" }));
    expect(screen.getByTestId(/package-private-mcp-card-/)).toHaveTextContent("Required secret binding names");
  });

  it("saves local resource changes through workflow package update without secret values", async () => {
    renderEditor();

    clickTab("Private MCP");
    fireEvent.click(screen.getByRole("button", { name: "Add Private MCP" }));
    fireEvent.change(screen.getByLabelText("Private MCP 1 local key"), { target: { value: "market_mcp" } });
    fireEvent.change(screen.getByLabelText("Private MCP 1 name"), { target: { value: "Market MCP" } });
    fireEvent.change(screen.getByLabelText("Private MCP 1 command"), { target: { value: "market-mcp" } });
    fireEvent.change(screen.getByLabelText("Private MCP 1 args"), { target: { value: '["--token", "${MARKET_DATA_API_KEY}"]' } });
    fireEvent.click(screen.getByRole("button", { name: "Add Binding" }));
    fireEvent.change(screen.getByLabelText("Required secret binding 1"), { target: { value: "MARKET_DATA_API_KEY" } });

    fireEvent.click(screen.getByRole("button", { name: "Save package draft" }));

    expect(updatePackageMock).toHaveBeenCalledWith({
      packageId: "42",
      payload: expect.objectContaining({ manifestSource: expect.stringContaining("MARKET_DATA_API_KEY_SECRET") }),
    });
    const payload = updatePackageMock.mock.calls[0][0].payload.manifestSource as string;
    expect(payload).not.toContain("sk-");
    expect(payload).not.toContain("apiKey:");
    expect(createPackageMock).not.toHaveBeenCalled();
  });

  it("opens the matching agent sheet and focuses the diagnostic field", async () => {
    validateManifestMock.mockResolvedValueOnce({
      compiledHash: null,
      compiledPlan: null,
      diagnostics: [{ column: null, line: null, message: "Missing model connection", path: "spec.agents[1].modelConnection", severity: "error" }],
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

    fireEvent.click(screen.getByRole("button", { name: "Run package preflight" }));

    expect(await screen.findByRole("tab", { name: "Agents tab" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByTestId("package-agent-sheet-1")).toHaveTextContent("Missing model connection");
    await waitFor(() => expect(document.activeElement).toHaveAttribute("data-field", "spec.agents[1].modelConnection"));
    expect(screen.getByTestId("agents-validation-feedback")).toHaveTextContent("spec.agents[1].modelConnection");
  });

  it("focuses output schema diagnostics on the exact indexed field", async () => {
    validateManifestMock.mockResolvedValueOnce({
      compiledHash: null,
      compiledPlan: null,
      diagnostics: [{ column: null, line: null, message: "Schema key is invalid", path: "spec.outputSchemas[1].key", severity: "error" }],
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

    fireEvent.click(screen.getByRole("button", { name: "Run package preflight" }));

    expect(await screen.findByRole("tab", { name: "Output Schemas tab" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("Schema key is invalid")).toBeVisible();
    await waitFor(() => expect(document.activeElement).toHaveAttribute("data-field", "spec.outputSchemas[1].key"));
  });

  it("focuses capability profile and private MCP diagnostics by exact resource index", async () => {
    validateManifestMock.mockResolvedValueOnce({
      compiledHash: null,
      compiledPlan: null,
      diagnostics: [{ column: null, line: null, message: "Select at least one tool", path: "spec.capabilityProfiles[1].toolKeys[0]", severity: "error" }],
      manifestHash: null,
      metadata: null,
      packageDefinition: null,
      warnings: [],
    }).mockResolvedValueOnce({
      compiledHash: null,
      compiledPlan: null,
      diagnostics: [{ column: null, line: null, message: "Binding name is required", path: "spec.mcpServers[1].requiredBindings[0]", severity: "error" }],
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
    fireEvent.click(screen.getByRole("button", { name: "Run package preflight" }));

    expect(await screen.findByRole("tab", { name: "Capability Profiles tab" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("Select at least one tool")).toBeVisible();
    await waitFor(() => expect(document.activeElement).toHaveAttribute("data-field", "spec.capabilityProfiles[1].toolKeys[0]"));

    clickTab("Private MCP");
    fireEvent.click(screen.getByRole("button", { name: "Add Private MCP" }));
    fireEvent.click(screen.getByRole("button", { name: "Add Private MCP" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Add Binding" })[1]);
    clickTab("Overview");
    fireEvent.click(screen.getByRole("button", { name: "Run package preflight" }));

    expect(await screen.findByRole("tab", { name: "Private MCP tab" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("Binding name is required")).toBeVisible();
    await waitFor(() => expect(document.activeElement).toHaveAttribute("data-field", "spec.mcpServers[1].requiredBindings[0]"));
  });

  it("does not import retired global authoring API clients", async () => {
    const { readFile } = await import("node:fs/promises");
    const source = await readFile(`${process.cwd()}/src/pages/workflow-packages/editor.tsx`, "utf8");
    const forbidden = [
      ["agents", "Api"].join(""),
      ["capabilities", "Api"].join(""),
      ["output", "Schemas", "Api"].join(""),
      ["mcp", "Servers", "Api"].join(""),
      ["@/hooks/use", "-agents"].join(""),
      ["@/hooks/use", "-capabilities"].join(""),
      ["@/hooks/use", "-output-schemas"].join(""),
      ["@/hooks/use", "-mcp-servers"].join(""),
    ];
    for (const token of forbidden) {
      expect(source).not.toContain(token);
    }
  });
});
