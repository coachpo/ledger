import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkflowPackageManifestRead, WorkflowPackageRead } from "@/lib/types/workflow-package";

import { WorkflowPackageEditorPage } from "./editor";

const {
  deleteSecretBindingMock,
  navigateMock,
  upsertSecretBindingMock,
  useWorkflowPackageManifestMock,
  useWorkflowPackageMock,
} = vi.hoisted(() => ({
  deleteSecretBindingMock: vi.fn(),
  navigateMock: vi.fn(),
  upsertSecretBindingMock: vi.fn(),
  useWorkflowPackageManifestMock: vi.fn(),
  useWorkflowPackageMock: vi.fn(),
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
  useDeleteWorkflowPackageSecretBinding: () => ({ isPending: false, mutateAsync: deleteSecretBindingMock }),
  useImportWorkflowPackage: () => ({ isPending: false, mutateAsync: vi.fn() }),
  usePreflightWorkflowPackage: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useTools: () => ({ data: { items: [] }, error: null, isError: false, isPending: false }),
  useUpdateWorkflowPackage: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useUpsertWorkflowPackageSecretBinding: () => ({ isPending: false, mutateAsync: upsertSecretBindingMock }),
  useValidateWorkflowPackageManifest: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useWorkflowPackage: (...args: unknown[]) => useWorkflowPackageMock(...args),
  useWorkflowPackageLaunch: () => ({ data: undefined, error: null, isError: false, isPending: false }),
  useWorkflowPackageManifest: (...args: unknown[]) => useWorkflowPackageManifestMock(...args),
  useWorkflowPackageSecretBindings: () => ({
    data: { items: [{ createdAt: "2026-05-15T08:00:00Z", hasValue: true, key: "slack_webhook_token", packageId: 42, updatedAt: "2026-05-15T08:00:00Z" }] },
    error: null,
    isError: false,
    isPending: false,
  }),
}));

const packageRead: WorkflowPackageRead = {
  compiledHash: "compiled-hash-123",
  createdAt: "2026-05-01T10:00:00Z",
  description: "HTTP callback package.",
  id: 42,
  key: "http_callbacks",
  lastLaunchedAt: "2026-05-05T11:00:00Z",
  manifestHash: "manifest-hash-123",
  name: "HTTP Callback Package",
  status: "active",
  updatedAt: "2026-05-05T10:00:00Z",
  warnings: [],
};

const manifestSource = `apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: http_callbacks
  name: HTTP Callback Package
spec:
  inputs:
    type: object
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
        method: POST
        url: https://example.test/hook
        headers:
          Authorization: \${{ secrets.slack_webhook_token }}
        body:
          token: \${{ secrets.body_token }}
        response:
          outputSchema: webhook_response
      output:
        from: \${{ nodes.notify_slack.outputs.webhook_result }}
`;

const manifestRead: WorkflowPackageManifestRead = {
  compiledHash: "compiled-hash-123",
  manifestHash: "manifest-hash-123",
  manifestSource,
  packageDefinition: {},
  packageId: 42,
  packageKey: "http_callbacks",
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

describe("WorkflowPackageEditorPage secret bindings", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    upsertSecretBindingMock.mockReset();
    deleteSecretBindingMock.mockReset();
    upsertSecretBindingMock.mockResolvedValue({ createdAt: "2026-05-15T08:05:00Z", hasValue: true, key: "body_token", packageId: 42, updatedAt: "2026-05-15T08:05:00Z" });
    deleteSecretBindingMock.mockResolvedValue(undefined);
    useWorkflowPackageMock.mockReturnValue({ data: packageRead, error: null, isError: false, isPending: false, refetch: vi.fn() });
    useWorkflowPackageManifestMock.mockReturnValue({ data: manifestRead, error: null, isError: false, isFetching: false, isPending: false, refetch: vi.fn() });
  });

  it("edits package secret bindings without echoing stored secret values", async () => {
    renderEditor();

    fireEvent.click(screen.getByRole("tab", { name: "Secret Bindings tab" }));
    const tab = screen.getByTestId("workflow-package-secret-bindings-tab");
    expect(tab).toHaveTextContent("slack_webhook_token");
    expect(tab).toHaveTextContent("body_token");
    expect(tab).toHaveTextContent(/stored value redacted/i);
    expect(screen.queryByText("slack-secret-value")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Secret binding key"), { target: { value: "body_token" } });
    fireEvent.change(screen.getByLabelText("Secret binding value"), { target: { value: "body-secret-value" } });
    fireEvent.click(screen.getByRole("button", { name: "Save secret binding" }));

    await waitFor(() => expect(upsertSecretBindingMock).toHaveBeenCalledWith({
      key: "body_token",
      packageId: "42",
      payload: { value: "body-secret-value" },
    }));
    expect(screen.getByLabelText("Secret binding value")).toHaveValue("");
    expect(screen.queryByText("body-secret-value")).not.toBeInTheDocument();

    fireEvent.click(within(tab).getByRole("button", { name: "Delete secret binding slack_webhook_token" }));
    await waitFor(() => expect(deleteSecretBindingMock).toHaveBeenCalledWith({ key: "slack_webhook_token", packageId: "42" }));
  });
});
