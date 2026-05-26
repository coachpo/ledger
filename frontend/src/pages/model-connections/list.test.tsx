import type { ComponentProps } from "react";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ModelConnectionsListPage } from "./list";
import { createDefaultCapabilities } from "./model-connection-ui";

const {
  deleteModelConnectionMock,
  deleteModelConnectionsMock,
  navigateMock,
  toastErrorMock,
  toastSuccessMock,
  useDeleteModelConnectionsMock,
  useModelConnectionsMock,
} = vi.hoisted(() => ({
  deleteModelConnectionMock: vi.fn(),
  deleteModelConnectionsMock: vi.fn(),
  navigateMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  useDeleteModelConnectionsMock: vi.fn(),
  useModelConnectionsMock: vi.fn(),
}));

vi.mock("react-router", () => ({
  Link: ({ children, to, ...props }: ComponentProps<"a"> & { to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
  useNavigate: () => navigateMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}));

vi.mock("@/hooks/use-model-connections", () => ({
  useDeleteModelConnection: () => ({
    isPending: false,
    mutateAsync: deleteModelConnectionMock,
  }),
  useDeleteModelConnections: () => useDeleteModelConnectionsMock(),
  useModelConnections: () => useModelConnectionsMock(),
}));

describe("ModelConnectionsListPage", () => {
  beforeEach(() => {
    deleteModelConnectionMock.mockReset();
    deleteModelConnectionsMock.mockReset();
    navigateMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    useDeleteModelConnectionsMock.mockReset();
    useDeleteModelConnectionsMock.mockReturnValue({
      isPending: false,
      mutate: deleteModelConnectionsMock,
    });
    useModelConnectionsMock.mockReturnValue({
      data: {
        items: [
          {
            baseUrl: "https://api.openai.com/v1",
            capabilities: {
              ...createDefaultCapabilities("openai_responses"),
              strictJsonSchemaOutput: {
                detail: null,
                lastProbedAt: null,
                status: "supported",
              },
            },
            connectionKind: "provider",
            description: "Production traffic",
            id: 9,
            key: "primary_compatible",
            lastProbedAt: "2026-04-22T07:45:00Z",
            lastTestMessage: "Connection OK",
            lastTestOk: true,
            lastTestedAt: "2026-04-22T08:00:00Z",
            modelId: "gpt-4.1",
            name: "Primary Compatible",
            outputStrategyPolicy: "prefer_strict_schema",
            parallelToolCallsPolicy: "serialize",
            probeCacheTtlSeconds: 900,
            protocolProfile: "openai_responses",
            reasoningEffort: null,
            reasoningPolicy: "allow",
            streamingPolicy: "allow",
            timeoutSeconds: 90,
          },
          {
            baseUrl: "https://backup.openai.com/v1",
            capabilities: {
              ...createDefaultCapabilities("openai_chat_completions"),
              nativeToolCalls: {
                detail: "Tool calls rejected by fixture.",
                lastProbedAt: "2026-04-21T07:30:00Z",
                status: "unsupported",
              },
            },
            connectionKind: "deterministic_smoke",
            description: "Fallback traffic",
            id: 4,
            key: "legacy_backup",
            lastProbedAt: "2026-04-21T07:30:00Z",
            lastTestMessage: "Key rejected",
            lastTestOk: false,
            lastTestedAt: "2026-04-21T08:00:00Z",
            modelId: "gpt-4o-mini",
            name: "Legacy Backup",
            outputStrategyPolicy: "allow_json_object_validation",
            parallelToolCallsPolicy: "forbid",
            probeCacheTtlSeconds: 300,
            protocolProfile: "openai_chat_completions",
            reasoningEffort: "xhigh",
            reasoningPolicy: "forbid",
            streamingPolicy: "forbid",
            timeoutSeconds: 45,
          },
          {
            baseUrl: "https://literal.openai.com/v1",
            capabilities: createDefaultCapabilities("openai_responses"),
            connectionKind: "provider",
            description: "Literal none reasoning value",
            id: 12,
            key: "literal_none",
            lastProbedAt: null,
            lastTestMessage: null,
            lastTestOk: null,
            lastTestedAt: null,
            modelId: "gpt-none-literal",
            name: "Literal None",
            outputStrategyPolicy: "allow_plain_text",
            parallelToolCallsPolicy: "allow",
            probeCacheTtlSeconds: 1200,
            protocolProfile: "openai_responses",
            reasoningEffort: "none",
            reasoningPolicy: "allow",
            streamingPolicy: "allow",
            timeoutSeconds: 30,
          },
          {
            baseUrl: "https://reasoning-blocked.openai.com/v1",
            capabilities: {
              ...createDefaultCapabilities("openai_chat_completions"),
              reasoningHints: {
                detail: "Reasoning hints are unsupported by this fixture.",
                lastProbedAt: "2026-04-20T07:30:00Z",
                status: "unsupported",
              },
              usageReporting: {
                detail: "Usage metadata was not reported.",
                lastProbedAt: "2026-04-20T07:31:00Z",
                status: "unsupported",
              },
            },
            connectionKind: "provider",
            description: "Unsupported reasoning and usage metadata",
            id: 18,
            key: "reasoning_blocked",
            lastProbedAt: "2026-04-20T07:31:00Z",
            lastTestMessage: "Reasoning hints rejected",
            lastTestOk: false,
            lastTestedAt: "2026-04-20T07:35:00Z",
            modelId: "gpt-blocked-reasoning",
            name: "Reasoning Blocked",
            outputStrategyPolicy: "prefer_strict_schema",
            parallelToolCallsPolicy: "serialize",
            probeCacheTtlSeconds: 900,
            protocolProfile: "openai_chat_completions",
            reasoningEffort: "high",
            reasoningPolicy: "allow",
            streamingPolicy: "allow",
            timeoutSeconds: 60,
          },
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });
  });

  it("renders compact inventory empty and error states", () => {
    useModelConnectionsMock.mockReturnValue({
      data: { items: [] },
      error: null,
      isError: false,
      isPending: false,
    });
    const { rerender } = render(<ModelConnectionsListPage />);

    expect(screen.getByText("No model connections exist yet.")).toBeVisible();
    expect(
      screen.getByText(
        /create a saved endpoint before launching workflow packages/i,
      ),
    ).toBeVisible();

    useModelConnectionsMock.mockReturnValue({
      data: undefined,
      error: new Error("Model API unavailable"),
      isError: true,
      isPending: false,
    });
    rerender(<ModelConnectionsListPage />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Model API unavailable",
    );
  });

  it("renders table rows, confirms deletes, and exposes create and edit routes", async () => {
    deleteModelConnectionMock.mockResolvedValue(undefined);

    render(<ModelConnectionsListPage />);

    expect(
      screen.getByText(/backend-derived compatibility evidence/i),
    ).toBeVisible();
    expect(screen.getByTestId("model-connections-row-9")).toBeVisible();
    expect(screen.getByTestId("model-connections-row-4")).toBeVisible();
    expect(screen.getByTestId("model-connections-row-12")).toBeVisible();
    const primaryRow = within(screen.getByTestId("model-connections-row-9"));
    expect(primaryRow.getByText("primary_compatible")).toBeVisible();
    expect(primaryRow.getByText("gpt-4.1")).toBeVisible();
    expect(primaryRow.getByText("Protocol profile")).toBeVisible();
    expect(primaryRow.getByText("Responses-compatible")).toBeVisible();
    expect(primaryRow.getByText("Test state")).toBeVisible();
    expect(primaryRow.getByText(/^passed$/i)).toBeVisible();
    expect(primaryRow.getByText("Reachability")).toBeVisible();
    expect(
      primaryRow.getByText("3 supported · 0 unsupported · 7 unknown"),
    ).toBeVisible();
    expect(primaryRow.getByText(/Prefer strict schema/)).toBeVisible();
    expect(screen.queryByText("Provider-backed")).not.toBeInTheDocument();
    expect(screen.queryByText("Deterministic smoke")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("model-connections-delete-9"));
    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      "Delete Primary Compatible?",
    );
    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      "Deletion is blocked while current workflow packages reference its stable key.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete connection" }));
    await waitFor(() =>
      expect(deleteModelConnectionMock).toHaveBeenCalledWith(9),
    );
    expect(toastSuccessMock).toHaveBeenCalledWith("Model connection deleted");

    expect(screen.getByTestId("model-connections-new")).toHaveAttribute(
      "href",
      "/model-connections/new",
    );
    expect(screen.getByTestId("model-connections-open-9")).toHaveAttribute(
      "href",
      "/model-connections/9/edit",
    );
  });

  it("renders search and table controls by default while keeping cards browse-only", () => {
    render(<ModelConnectionsListPage />);

    expect(
      screen.getByRole("textbox", { name: "Search model connections" }),
    ).toHaveAttribute(
      "placeholder",
      "Search by name, key, model, protocol, or compatibility evidence...",
    );
    expect(screen.getByLabelText("Table view")).toHaveAttribute(
      "data-state",
      "on",
    );
    expect(screen.getByRole("table").parentElement).toHaveClass(
      "min-w-0",
      "overflow-x-auto",
    );
    expect(
      screen.getAllByRole("checkbox", {
        name: "Select all shown model connections",
      }),
    ).toHaveLength(1);
    expect(
      within(screen.getByTestId("model-connections-row-9")).getByRole(
        "checkbox",
        { name: "Select model connection Primary Compatible" },
      ),
    ).toBeVisible();

    for (const column of [
      "Name",
      "Stable key",
      "Model ID",
      "Protocol profile",
      "Capability summary",
      "Test state",
      "Runtime policy",
      "Actions",
    ]) {
      expect(screen.getByRole("columnheader", { name: column })).toBeVisible();
    }
    for (const removedColumn of [
      "Model",
      "Base URL",
      "Protocol Profile",
      "Compatibility Evidence",
      "Runtime Policy Evidence",
      "Reachability Test",
      "Credential State",
    ]) {
      expect(
        screen.queryByRole("columnheader", { name: removedColumn }),
      ).not.toBeInTheDocument();
    }

    expect(screen.getByTestId("model-connections-open-9")).toHaveAttribute(
      "href",
      "/model-connections/9/edit",
    );
    fireEvent.click(screen.getByTestId("model-connections-delete-9"));
    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      "Delete Primary Compatible?",
    );
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    fireEvent.click(screen.getByLabelText("Cards view"));
    expect(screen.getByLabelText("Cards view")).toHaveAttribute(
      "data-state",
      "on",
    );
    expect(
      screen.queryByRole("checkbox", {
        name: "Select all shown model connections",
      }),
    ).not.toBeInTheDocument();
    const primaryCard = within(screen.getByTestId("model-connections-row-9"));
    expect(
      primaryCard.queryByRole("checkbox", {
        name: "Select model connection Primary Compatible",
      }),
    ).not.toBeInTheDocument();
    expect(primaryCard.getByLabelText("Stable key: primary_compatible")).toBeVisible();
    expect(primaryCard.getByText("Credential state")).toBeVisible();
    expect(primaryCard.getByText("Write-only secret")).toBeVisible();
  });

  it("filters the sorted model connection inventory locally", () => {
    render(<ModelConnectionsListPage />);

    fireEvent.change(
      screen.getByRole("textbox", { name: "Search model connections" }),
      { target: { value: "responses-compatible" } },
    );

    expect(
      screen.getByTestId("model-connections-row-9"),
    ).toBeVisible();
    expect(
      screen.getByTestId("model-connections-row-12"),
    ).toBeVisible();
    expect(
      screen.queryByTestId("model-connections-row-4"),
    ).not.toBeInTheDocument();

    fireEvent.change(
      screen.getByRole("textbox", { name: "Search model connections" }),
      { target: { value: "literal" } },
    );

    expect(
      screen.queryByTestId("model-connections-row-9"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("model-connections-row-4"),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("model-connections-row-12")).toBeVisible();

    fireEvent.change(
      screen.getByRole("textbox", { name: "Search model connections" }),
      { target: { value: "missing" } },
    );
    expect(
      screen.getByText("No model connections match this search."),
    ).toBeVisible();
  });

  it("scopes table selection to filtered rows and batch deletes", async () => {
    deleteModelConnectionsMock.mockImplementation(
      (_ids: unknown, options: { onSuccess: () => void }) =>
        options.onSuccess(),
    );

    render(<ModelConnectionsListPage />);

    fireEvent.click(screen.getByLabelText("Table view"));
    fireEvent.click(
      within(screen.getByTestId("model-connections-row-9")).getByRole(
        "checkbox",
        { name: "Select model connection Primary Compatible" },
      ),
    );
    expect(screen.getByText("1 of 4 model connections selected")).toBeVisible();
    const bulkActions = screen.getByTestId("model-connections-bulk-actions");
    expect(bulkActions).toBeVisible();
    expect(screen.getByRole("table").compareDocumentPosition(bulkActions)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );

    fireEvent.change(
      screen.getByRole("textbox", { name: "Search model connections" }),
      { target: { value: "legacy" } },
    );
    expect(
      screen.queryByTestId("model-connections-bulk-actions"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Delete selected" }),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Select all shown model connections",
      }),
    );
    expect(screen.getByText("1 of 1 model connections selected")).toBeVisible();
    expect(screen.getByTestId("model-connections-row-4")).toHaveAttribute(
      "data-state",
      "selected",
    );
    expect(screen.getByRole("button", { name: "Clear" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Delete selected" }));

    await waitFor(() =>
      expect(deleteModelConnectionsMock).toHaveBeenCalledWith(
        [4],
        expect.objectContaining({
          onError: expect.any(Function),
          onSuccess: expect.any(Function),
        }),
      ),
    );
    expect(toastSuccessMock).toHaveBeenCalledWith("1 model connection deleted");
  });

  it("clears table selection when switching back to cards", () => {
    render(<ModelConnectionsListPage />);

    fireEvent.click(screen.getByLabelText("Table view"));
    fireEvent.click(
      within(screen.getByTestId("model-connections-row-9")).getByRole(
        "checkbox",
        { name: "Select model connection Primary Compatible" },
      ),
    );
    expect(screen.getByText("1 of 4 model connections selected")).toBeVisible();

    fireEvent.click(screen.getByLabelText("Cards view"));

    expect(
      screen.queryByText("1 of 4 model connections selected"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("checkbox", {
        name: "Select all shown model connections",
      }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Table view"));
    expect(
      within(screen.getByTestId("model-connections-row-9")).getByRole(
        "checkbox",
        { name: "Select model connection Primary Compatible" },
      ),
    ).toHaveAttribute("aria-checked", "false");
    expect(
      screen.queryByRole("button", { name: "Delete selected" }),
    ).not.toBeInTheDocument();
  });

  it("shows blocked delete backend messages without rendering secret payloads", async () => {
    const blockedError = Object.assign(
      new Error(
        "Model connection is used by workflow packages and cannot be deleted.",
      ),
      {
        details: [{ field: "apiKey", issue: "sk-live-secret" }],
        ["secret" + "Payload"]: { apiKey: "sk-live-secret" },
      },
    );
    deleteModelConnectionMock.mockRejectedValue(blockedError);

    render(<ModelConnectionsListPage />);
    fireEvent.click(screen.getByTestId("model-connections-delete-9"));
    fireEvent.click(screen.getByRole("button", { name: "Delete connection" }));

    await waitFor(() =>
      expect(toastErrorMock).toHaveBeenCalledWith(
        "Model connection is used by workflow packages and cannot be deleted.",
      ),
    );
    expect(toastErrorMock).not.toHaveBeenCalledWith(
      expect.stringContaining("sk-live-secret"),
    );
    expect(screen.queryByText(/sk-live-secret/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret payload/i)).not.toBeInTheDocument();
  });
});
