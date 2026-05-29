import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
    key: "signaldeck.finance",
    label: "Finance Workspace",
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
      data: { items: [extensionFixture()] },
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
    expect(context).not.toHaveTextContent("Surface");
    expect(context).not.toHaveTextContent("system state");
    expect(context).not.toHaveTextContent("Backend");
    expect(context).not.toHaveTextContent("slim contract");
    expect(context).not.toHaveTextContent(/Bundled\s*1/);
    expect(context).not.toHaveTextContent(/Enabled\s*1/);
    expect(context).not.toHaveTextContent("1 bundled extension returned");
    expect(
      page.querySelector('[data-inventory-shell-region="toolbar"]'),
    ).not.toBeInTheDocument();
    expect(
      page.querySelector('[data-inventory-shell-region="filters"]'),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Cards view")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Table view")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    const row = screen.getByTestId("extension-row-signaldeck-finance");
    expect(row).toHaveTextContent("Finance Workspace");
    expect(row).toHaveTextContent("signaldeck.finance");
    expect(row).toHaveTextContent("Enabled");
    expect(row).not.toHaveTextContent(
      "Ownership: SignalDeck Core plus Finance Workspace extension",
    );
    expect(row).not.toHaveTextContent("Blast radius");
    expect(row).not.toHaveTextContent("Finance routes, nav, tools");
    expect(screen.queryByText(/marketplace/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/install/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/remove/i)).not.toBeInTheDocument();
    expect(
      within(row).getByRole("switch", {
        name: "Disable Finance Workspace extension",
      }),
    ).toHaveAttribute("data-state", "checked");
    expect(
      within(row).getByTestId("extension-toggle-signaldeck-finance"),
    ).toHaveAttribute("data-state", "checked");
    expect(
      within(row).queryByRole("button", { name: /install/i }),
    ).not.toBeInTheDocument();
    expect(
      within(row).queryByRole("button", { name: /remove/i }),
    ).not.toBeInTheDocument();
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

  it("keeps sparse system-state copy for empty and error states", () => {
    useExtensionsMock.mockReturnValue({
      data: { items: [] },
      error: null,
      isError: false,
      isPending: false,
    });
    const { rerender } = render(<ExtensionsListPage />);

    expect(
      screen.getByText("No bundled extensions are registered."),
    ).toBeVisible();
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

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Unable to load extension state.");
    expect(alert).toHaveTextContent("Extension API unavailable");
  });
});
