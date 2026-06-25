import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  DIGITAL_ORACLE_EXTENSION_KEY,
  DIGITAL_ORACLE_LABEL,
  FINANCE_WORKSPACE_EXTENSION_KEY,
  FINANCE_WORKSPACE_LABEL,
} from "@/extensions";
import type { ExtensionRead } from "@/lib/types/extension";

import { ExtensionsListPage } from "./list";

const {
  toggleExtensionMock,
  toastErrorMock,
  toastSuccessMock,
  useExtensionsMock,
  useToggleExtensionMock,
} = vi.hoisted(() => ({
  toggleExtensionMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  useExtensionsMock: vi.fn(),
  useToggleExtensionMock: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}));

vi.mock("@/hooks/use-extensions", () => ({
  useExtensions: () => useExtensionsMock(),
  useToggleExtension: () => useToggleExtensionMock(),
}));

function extensionFixture(
  overrides: Partial<ExtensionRead> = {},
): ExtensionRead {
  return {
    enabled: true,
    key: FINANCE_WORKSPACE_EXTENSION_KEY,
    label: FINANCE_WORKSPACE_LABEL,
    ...overrides,
  };
}

describe("ExtensionsListPage", () => {
  beforeEach(() => {
    toggleExtensionMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    useExtensionsMock.mockReset();
    useToggleExtensionMock.mockReset();
    toggleExtensionMock.mockResolvedValue(extensionFixture({ enabled: false }));
    useToggleExtensionMock.mockReturnValue({
      isPending: false,
      mutateAsync: toggleExtensionMock,
    });
    useExtensionsMock.mockReturnValue({
      data: {
        items: [
          extensionFixture(),
          extensionFixture({
            key: DIGITAL_ORACLE_EXTENSION_KEY,
            label: DIGITAL_ORACLE_LABEL,
          }),
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });
  });

  it("renders bundled extension state", () => {
    render(<ExtensionsListPage />);

    const page = screen.getByTestId("extensions-list-page");
    expect(page).toBeVisible();
    expect(screen.getByRole("heading", { level: 1, name: "Extensions" })).toBeVisible();
    expect(screen.getByText("Manage bundled extensions.")).toBeVisible();
    const context = page.querySelector<HTMLElement>(
      '[data-inventory-shell-region="context"]',
    );

    if (!context) {
      throw new Error("Expected extensions context region.");
    }

    expect(context).toBeInTheDocument();
    expect(
      page.querySelector('[data-inventory-shell-region="toolbar"]'),
    ).not.toBeInTheDocument();
    expect(
      page.querySelector('[data-inventory-shell-region="filters"]'),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Cards view")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Table view")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(
      Array.from(
        page.querySelectorAll<HTMLElement>('[data-testid^="extension-row-"]'),
      ).map((row) => row.dataset.testid),
    ).toEqual([
      "extension-row-signaldeck-digital-oracle",
      "extension-row-signaldeck-finance",
    ]);
    const digitalOracleRow = screen.getByTestId(
      "extension-row-signaldeck-digital-oracle",
    );
    expect(digitalOracleRow).toHaveTextContent("Digital Oracle Runtime");
    expect(digitalOracleRow).toHaveTextContent("signaldeck.digital_oracle");
    expect(digitalOracleRow).toHaveTextContent("Enabled");
    expect(
      within(digitalOracleRow).getByRole("switch", {
        name: "Disable Digital Oracle Runtime extension",
      }),
    ).toHaveAttribute("data-state", "checked");
    expect(
      within(digitalOracleRow).getByTestId(
        "extension-toggle-signaldeck-digital-oracle",
      ),
    ).toHaveAttribute("data-state", "checked");

    const financeRow = screen.getByTestId("extension-row-signaldeck-finance");
    expect(financeRow).toHaveTextContent("Finance Workspace");
    expect(financeRow).toHaveTextContent("signaldeck.finance");
    expect(financeRow).toHaveTextContent("Enabled");
    expect(financeRow).not.toHaveTextContent(
      "Ownership: SignalDeck Core plus Finance Workspace extension",
    );
    expect(financeRow).not.toHaveTextContent("Blast radius");
    expect(financeRow).not.toHaveTextContent("Finance routes, nav, tools");
    expect(
      within(financeRow).getByRole("switch", {
        name: "Disable Finance Workspace extension",
      }),
    ).toHaveAttribute("data-state", "checked");
    expect(
      within(financeRow).getByTestId("extension-toggle-signaldeck-finance"),
    ).toHaveAttribute("data-state", "checked");
  });

  it("toggles extension enabled state through the backend mutation", async () => {
    render(<ExtensionsListPage />);

    fireEvent.click(screen.getByTestId("extension-toggle-signaldeck-finance"));

    await waitFor(() =>
      expect(toggleExtensionMock).toHaveBeenCalledWith({
        extensionKey: "signaldeck.finance",
        payload: { enabled: false },
      }),
    );
    expect(toastSuccessMock).toHaveBeenCalledWith("Finance Workspace disabled");
  });

  it("re-enables a disabled bundled extension through the same management control", async () => {
    useExtensionsMock.mockReturnValue({
      data: {
        items: [
          extensionFixture({
            enabled: false,
          }),
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });
    toggleExtensionMock.mockResolvedValue(extensionFixture({ enabled: true }));
    render(<ExtensionsListPage />);

    const row = screen.getByTestId("extension-row-signaldeck-finance");
    expect(row).toHaveTextContent("Disabled");
    fireEvent.click(
      within(row).getByTestId("extension-toggle-signaldeck-finance"),
    );

    await waitFor(() =>
      expect(toggleExtensionMock).toHaveBeenCalledWith({
        extensionKey: "signaldeck.finance",
        payload: { enabled: true },
      }),
    );
    expect(toastSuccessMock).toHaveBeenCalledWith("Finance Workspace enabled");
  });

  it("surfaces toggle failures without changing local state", async () => {
    toggleExtensionMock.mockRejectedValue(
      new Error("Extension API unavailable"),
    );
    render(<ExtensionsListPage />);

    fireEvent.click(screen.getByTestId("extension-toggle-signaldeck-finance"));

    await waitFor(() =>
      expect(toastErrorMock).toHaveBeenCalledWith("Extension API unavailable"),
    );
    expect(
      screen.getByTestId("extension-row-signaldeck-finance"),
    ).toHaveTextContent("Enabled");
  });

  it("uses a canonical route state panel while loading extension state", () => {
    useExtensionsMock.mockReturnValue({
      data: undefined,
      error: null,
      isError: false,
      isPending: true,
    });

    render(<ExtensionsListPage />);

    const loadingState = screen.getByTestId("extensions-loading-state");
    expect(loadingState).toHaveTextContent("Loading extension state");
    expect(loadingState).toHaveTextContent(
      "Loading the slim bundled-extension state before route gates and tool discovery update.",
    );
  });

  it("keeps sparse system-state copy for empty and error states", () => {
    useExtensionsMock.mockReturnValue({
      data: { items: [] },
      error: null,
      isError: false,
      isPending: false,
    });
    const { rerender } = render(<ExtensionsListPage />);

    const emptyState = screen.getByTestId("extensions-empty-state");
    expect(emptyState).toHaveTextContent("No bundled extensions are registered.");
    expect(
      screen.queryByRole("button", { name: /install/i }),
    ).not.toBeInTheDocument();

    useExtensionsMock.mockReturnValue({
      data: undefined,
      error: new Error("Extension API unavailable"),
      isError: true,
      isPending: false,
    });
    rerender(<ExtensionsListPage />);

    const errorState = screen.getByTestId("extensions-error-state");
    expect(errorState).toHaveTextContent("Unable to load extension state.");
    expect(errorState).toHaveTextContent("Extension API unavailable");
  });
});
