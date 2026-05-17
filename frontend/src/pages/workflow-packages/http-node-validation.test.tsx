import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkflowPackageManifestRead, WorkflowPackageRead } from "@/lib/types/workflow-package";

import { WorkflowPackageEditorPage } from "./editor";

const {
  navigateMock,
  useWorkflowPackageManifestMock,
  useWorkflowPackageMock,
  validatePackageMock,
} = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  useWorkflowPackageManifestMock: vi.fn(),
  useWorkflowPackageMock: vi.fn(),
  validatePackageMock: vi.fn(),
}));

vi.mock("react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router")>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("@/hooks/use-model-connections", () => ({
  useModelConnections: () => ({ data: { items: [] }, error: null, isError: false, isPending: false }),
}));

vi.mock("@/hooks/use-workflow-packages", () => ({
  useCreateWorkflowPackage: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useCreateWorkflowPackageLaunch: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useDeleteWorkflowPackageSecretBinding: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useImportWorkflowPackage: () => ({ isPending: false, mutateAsync: vi.fn() }),
  usePreflightWorkflowPackage: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useTools: () => ({ data: { items: [] }, error: null, isError: false, isPending: false }),
  useUpdateWorkflowPackage: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useUpsertWorkflowPackageSecretBinding: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useValidateWorkflowPackageManifest: () => ({ isPending: false, mutateAsync: validatePackageMock }),
  useWorkflowPackage: (...args: unknown[]) => useWorkflowPackageMock(...args),
  useWorkflowPackageLaunch: () => ({ data: undefined, error: null, isError: false, isPending: false }),
  useWorkflowPackageManifest: (...args: unknown[]) => useWorkflowPackageManifestMock(...args),
  useWorkflowPackageSecretBindings: () => ({ data: { items: [] }, error: null, isError: false, isPending: false }),
  useWorkflowPackageVersions: () => ({ data: { items: [] }, error: null, isError: false, isPending: false }),
}));

const packageRead: WorkflowPackageRead = {
  compiledHash: "compiled-hash-123",
  createdAt: "2026-05-01T10:00:00Z",
  description: "HTTP callback package.",
  id: 42,
  key: "http_callbacks",
  latestVersion: 7,
  latestVersionId: 70,
  manifestHash: "manifest-hash-123",
  name: "HTTP Callback Package",
  status: "active",
  updatedAt: "2026-05-05T10:00:00Z",
  warnings: [],
};

const httpManifestSource = `apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: http_callbacks
  name: HTTP Callback Package
  description: Package with a non-agent HTTP callback.
spec:
  inputs:
    type: object
    properties:
      webhookUrl:
        type: string
      ticker:
        type: string
  outputSchemas:
    - key: webhook_response
      name: Webhook Response
      jsonSchema:
        type: object
  workflows:
    - key: notify
      name: Notify
      inputSchema:
        type: object
      flow:
        kind: http
        id: notify_slack
        slot: webhook_result
        method: PATCH
        url: \${{ inputs.webhookUrl }}
        headers:
          Authorization: \${{ secrets.slack_webhook_token }}
        body:
          ticker: \${{ inputs.ticker }}
        response:
          outputSchema: webhook_response
      output:
        from: \${{ nodes.notify_slack.outputs.webhook_result }}
`;

const manifestRead: WorkflowPackageManifestRead = {
  compiledHash: "compiled-hash-123",
  manifestHash: "manifest-hash-123",
  manifestSource: httpManifestSource,
  packageDefinition: {},
  packageId: 42,
  packageKey: "http_callbacks",
  version: 7,
};

function renderEditor() {
  return render(
    <MemoryRouter initialEntries={["/workflow-packages/42"]}>
      <Routes>
        <Route path="/workflow-packages/:packageId" element={<WorkflowPackageEditorPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("WorkflowPackageEditorPage HTTP node validation", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    validatePackageMock.mockReset();
    validatePackageMock.mockResolvedValue({
      compiledHash: null,
      compiledPlan: null,
      diagnostics: [
        {
          column: null,
          line: null,
          message: "HTTP method PATCH is not supported; use GET or POST.",
          path: "spec.workflows[0].flow.method",
          severity: "error",
        },
      ],
      manifestHash: null,
      metadata: null,
      packageDefinition: null,
      warnings: [],
    });
    useWorkflowPackageMock.mockReturnValue({ data: packageRead, error: null, isError: false, isPending: false, refetch: vi.fn() });
    useWorkflowPackageManifestMock.mockReturnValue({
      data: manifestRead,
      error: null,
      isError: false,
      isFetching: false,
      isPending: false,
      refetch: vi.fn(),
    });
  });

  it("keeps HTTP nodes in YAML and validates them through the manifest flow", async () => {
    renderEditor();

    fireEvent.click(screen.getByRole("tab", { name: "Workflow YAML tab" }));
    expect((screen.getByRole("textbox", { name: "Workflow YAML" }) as HTMLTextAreaElement).value).toContain("kind: http");
    fireEvent.click(screen.getByRole("button", { name: "Run package preflight" }));

    await waitFor(() => expect(validatePackageMock).toHaveBeenCalledTimes(1));
    const payload = validatePackageMock.mock.calls[0][0].manifestSource as string;
    expect(payload).toContain("kind: http");
    expect(payload).toContain("method: PATCH");
    expect(payload).toContain("Authorization: ${{ secrets.slack_webhook_token }}");
    expect(await screen.findByRole("tab", { name: "Workflow YAML tab" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText(/HTTP method PATCH is not supported/i)).toBeVisible();
    expect(screen.getByTestId("workflow-yaml-validation-feedback")).toHaveTextContent("spec.workflows[0].flow.method");
  });
});
