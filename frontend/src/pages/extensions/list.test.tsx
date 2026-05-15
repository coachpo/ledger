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
    contributionCategories: ["backend_api_routes", "frontend_routes"],
    contributions: [
      {
        category: "backend_api_routes",
        dependencies: [],
        extensionKey: "ledger.finance",
        ownerExtensionKey: "ledger.finance",
        summary: "Preserved finance API routes",
        surface: "/api/v1/portfolios",
      },
      {
        category: "frontend_routes",
        dependencies: [],
        extensionKey: "ledger.finance",
        ownerExtensionKey: "ledger.finance",
        summary: "Portfolio and report workspace routes",
        surface: "/portfolios",
      },
    ],
    createdAt: "2026-05-15T12:00:00Z",
    defaultEnabled: true,
    dependencies: [],
    disabledAt: null,
    disabledReason: null,
    enabled: true,
    enabledAt: "2026-05-15T12:00:00Z",
    key: "ledger.finance",
    label: "Finance Workspace",
    phase: "phase_1_bundled_first_party",
    stateVersion: 1,
    updatedAt: "2026-05-15T12:00:00Z",
    versioningRule: "Follows the backend package version.",
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
    toggleExtensionMock.mockResolvedValue(
      extensionFixture({ enabled: false, stateVersion: 2 }),
    );
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

  it("renders bundled extension state and phase-1 lifecycle copy", () => {
    render(<ExtensionsListPage />);

    expect(screen.getByTestId("extensions-list-page")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Extensions" })).toBeVisible();
    expect(
      screen.getByText(
        /install and remove actions are not supported in phase 1/i,
      ),
    ).toBeVisible();

    const row = screen.getByTestId("extension-row-ledger-finance");
    expect(row).toHaveTextContent("Finance Workspace");
    expect(row).toHaveTextContent("ledger.finance");
    expect(row).toHaveTextContent("Current state: Enabled");
    expect(row).toHaveTextContent("Contributions: 2");
    expect(row).toHaveTextContent("State version: 1");
    expect(
      within(row).getByTestId("extension-toggle-ledger-finance"),
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

    fireEvent.click(
      screen.getByTestId("extension-toggle-ledger-finance"),
    );

    await waitFor(() =>
      expect(toggleExtensionMock).toHaveBeenCalledWith({
        extensionKey: "ledger.finance",
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
            disabledAt: "2026-05-15T13:00:00Z",
            disabledReason: "matrix maintenance",
            enabled: false,
            enabledAt: null,
            stateVersion: 2,
          }),
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });
    toggleExtensionMock.mockResolvedValue(
      extensionFixture({ enabled: true, stateVersion: 3 }),
    );
    render(<ExtensionsListPage />);

    const row = screen.getByTestId("extension-row-ledger-finance");
    expect(row).toHaveTextContent("Current state: Disabled");
    fireEvent.click(
      within(row).getByTestId("extension-toggle-ledger-finance"),
    );

    await waitFor(() =>
      expect(toggleExtensionMock).toHaveBeenCalledWith({
        extensionKey: "ledger.finance",
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

    fireEvent.click(
      screen.getByTestId("extension-toggle-ledger-finance"),
    );

    await waitFor(() =>
      expect(toastErrorMock).toHaveBeenCalledWith("Extension API unavailable"),
    );
    expect(
      screen.getByTestId("extension-row-ledger-finance"),
    ).toHaveTextContent("Current state: Enabled");
  });
});
