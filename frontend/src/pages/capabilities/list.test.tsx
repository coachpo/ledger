import type { ComponentProps } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CapabilitiesListPage } from "./list";

const {
  archiveCapabilityMock,
  navigateMock,
  toastErrorMock,
  toastSuccessMock,
  useCapabilitiesMock,
} = vi.hoisted(() => ({
  archiveCapabilityMock: vi.fn(),
  navigateMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  useCapabilitiesMock: vi.fn(),
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

vi.mock("@/hooks/use-capabilities", () => ({
  useArchiveCapability: () => ({ isPending: false, mutateAsync: archiveCapabilityMock }),
  useCapabilities: () => useCapabilitiesMock(),
}));

describe("CapabilitiesListPage", () => {
  beforeEach(() => {
    archiveCapabilityMock.mockReset();
    navigateMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    useCapabilitiesMock.mockReturnValue({
      data: {
        items: [
          {
            createdAt: "2026-04-20T10:00:00Z",
            description: "Condenses results.",
            id: 3,
            key: "summarize_capability",
            name: "Summarize Capability",
            status: "draft",
            toolKeys: ["search_docs", "answer_user"],
            tools: [
              {
                key: "search_docs",
                displayName: "Search Docs",
                description: "Search indexed documents.",
              },
              {
                key: "answer_user",
                displayName: "Answer User",
                description: "Generate a final answer.",
              },
            ],
            updatedAt: "2026-04-20T10:00:00Z",
            version: 2,
          },
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });
  });

  it("renders rows, archives, and navigates to create/edit routes", async () => {
    archiveCapabilityMock.mockResolvedValue({ id: 3 });

    render(<CapabilitiesListPage />);

    expect(screen.getByTestId("capabilities-row-summarize_capability")).toBeVisible();
    expect(screen.getByText(/2 tool\(s\)/i)).toBeVisible();

    fireEvent.click(screen.getByTestId("capabilities-archive-summarize_capability"));
    await waitFor(() => expect(archiveCapabilityMock).toHaveBeenCalledWith(3));
    expect(toastSuccessMock).toHaveBeenCalledWith("Capability archived");

    fireEvent.click(screen.getByTestId("capabilities-new"));
    expect(navigateMock).toHaveBeenCalledWith("/capabilities/new");

    fireEvent.click(screen.getByTestId("capabilities-open-summarize_capability"));
    expect(navigateMock).toHaveBeenCalledWith("/capabilities/3/edit");
  });

  it("archives a capability from the list", async () => {
    archiveCapabilityMock.mockResolvedValue({ id: 3 });

    render(<CapabilitiesListPage />);

    fireEvent.click(screen.getByTestId("capabilities-archive-summarize_capability"));

    await waitFor(() => expect(archiveCapabilityMock).toHaveBeenCalledWith(3));
    expect(toastSuccessMock).toHaveBeenCalledWith("Capability archived");
  });
});
