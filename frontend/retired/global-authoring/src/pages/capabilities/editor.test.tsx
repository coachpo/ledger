import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { stringifyJson } from "@/lib/platform-authoring/common/serialization";

import { CapabilitiesEditorPage } from "./editor";

const navigateMock = vi.fn();
const paramsMock: { capabilityId?: string } = {};
const createCapabilityMock = vi.fn();
const updateCapabilityMock = vi.fn();
const activateCapabilityMock = vi.fn();
const toastErrorMock = vi.fn();
const toastSuccessMock = vi.fn();
const toolsQueryMock = vi.fn();

const catalogTools = [
  {
    key: "search_docs",
    displayName: "Search Docs",
    description: "Search indexed reports and documents.",
  },
  {
    key: "answer_user",
    displayName: "Answer User",
    description: "Generate a final answer for the user.",
  },
  {
    key: "signaldeck.reports.lookup",
    displayName: "Report Lookup",
    description: "Lookup saved SignalDeck reports.",
  },
];

const existingCapability = {
  createdAt: "2026-04-20T10:00:00Z",
  description: "Condenses results.",
  id: 3,
  key: "summarize_capability",
  name: "Summarize Capability",
  status: "draft",
  toolKeys: ["search_docs", "answer_user"],
  tools: [catalogTools[0], catalogTools[1]],
  updatedAt: "2026-04-20T10:00:00Z",
  version: 2,
};

let currentCapability = existingCapability;

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
  useParams: () => paramsMock,
}));
vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => toastErrorMock(...args),
    success: (...args: unknown[]) => toastSuccessMock(...args),
  },
}));

vi.mock("@/hooks/use-capabilities", () => ({
  useCapability: () =>
    paramsMock.capabilityId
      ? { data: currentCapability, error: null, isError: false, isPending: false }
      : { data: undefined, error: null, isError: false, isPending: false },
  useCapabilityTools: () => toolsQueryMock(),
  useCreateCapability: () => ({ isPending: false, mutateAsync: createCapabilityMock }),
  useUpdateCapability: () => ({ isPending: false, mutateAsync: updateCapabilityMock }),
  useActivateCapability: () => ({ isPending: false, mutateAsync: activateCapabilityMock }),
}));

describe("CapabilitiesEditorPage", () => {
  beforeEach(() => {
    paramsMock.capabilityId = undefined;
    currentCapability = existingCapability;
    navigateMock.mockReset();
    createCapabilityMock.mockReset();
    updateCapabilityMock.mockReset();
    activateCapabilityMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    toolsQueryMock.mockReset();
    toolsQueryMock.mockReturnValue({
      data: { items: catalogTools },
      error: null,
      isError: false,
      isPending: false,
    });
  });

  it("blocks invalid create saves when no catalog tool is selected", () => {
    render(<CapabilitiesEditorPage />);

    fireEvent.change(screen.getByLabelText(/^key$/i), { target: { value: "summarize_capability" } });
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "Summarize Capability" } });

    expect(screen.getByTestId("capability-empty-tool-selection")).toHaveTextContent("Select at least one catalog tool before saving.");
    expect(screen.getByRole("button", { name: /save capability/i })).toBeDisabled();
    expect(createCapabilityMock).not.toHaveBeenCalled();
    expect(toastErrorMock).not.toHaveBeenCalled();
  });

  it("saves selected catalog toolKeys through create without toolGrants", async () => {
    createCapabilityMock.mockResolvedValue({ id: 9 });

    render(<CapabilitiesEditorPage />);

    fireEvent.change(screen.getByLabelText(/^key$/i), { target: { value: "Summarize_Capability" } });
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "Summarize Capability" } });
    fireEvent.change(screen.getByLabelText(/^description$/i), { target: { value: "Condenses results." } });
    fireEvent.click(screen.getByRole("checkbox", { name: /select answer user/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /select search docs/i }));
    fireEvent.click(screen.getByRole("button", { name: /save capability/i }));

    await waitFor(() => expect(createCapabilityMock).toHaveBeenCalledTimes(1));
    expect(createCapabilityMock).toHaveBeenCalledWith({
      description: "Condenses results.",
      key: "summarize_capability",
      name: "Summarize Capability",
      toolKeys: ["search_docs", "answer_user"],
    });
    expect(createCapabilityMock.mock.calls[0]?.[0]).not.toHaveProperty("toolGrants");
    expect(navigateMock).toHaveBeenCalledWith("/capabilities/9/edit");
  });

  it("filters the catalog picker and shows display name, key, and description", () => {
    render(<CapabilitiesEditorPage />);

    fireEvent.change(screen.getByLabelText(/search catalog tools/i), { target: { value: "lookup saved" } });

    const catalog = within(screen.getByTestId("capability-tool-catalog"));
    expect(catalog.getByText("Report Lookup")).toBeVisible();
    expect(catalog.getByText("signaldeck.reports.lookup")).toBeVisible();
    expect(catalog.getByText("Lookup saved SignalDeck reports.")).toBeVisible();
    expect(screen.queryByText("Search Docs")).not.toBeInTheDocument();
  });
  it("hydrates edit state, saves toolKeys through the update hook, and navigates to the new version", async () => {
    paramsMock.capabilityId = "3";
    updateCapabilityMock.mockResolvedValue({ id: 8 });

    render(<CapabilitiesEditorPage />);

    expect(screen.getByLabelText(/^key$/i)).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: /select search docs/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /select answer user/i })).toBeChecked();
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "Updated Capability" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /select answer user/i }));
    fireEvent.click(screen.getByRole("button", { name: /save capability/i }));

    await waitFor(() => expect(updateCapabilityMock).toHaveBeenCalledTimes(1));
    expect(updateCapabilityMock).toHaveBeenCalledWith({
      payload: {
        description: "Condenses results.",
        name: "Updated Capability",
        toolKeys: ["search_docs"],
      },
      capabilityId: "3",
    });
    expect(updateCapabilityMock.mock.calls[0]?.[0].payload).not.toHaveProperty("toolGrants");
    expect(navigateMock).toHaveBeenCalledWith("/capabilities/8/edit");
  });
  it("shows a read-only exact JSON preview for the outgoing toolKeys payload", () => {
    render(<CapabilitiesEditorPage />);

    fireEvent.change(screen.getByLabelText(/^key$/i), { target: { value: "summarize_capability" } });
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "Summarize Capability" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /select answer user/i }));

    expect(screen.getByLabelText(/exact capability payload json/i)).toHaveValue(
      stringifyJson({
        description: undefined,
        key: "summarize_capability",
        name: "Summarize Capability",
        toolKeys: ["answer_user"],
      }),
    );
    expect(screen.getByLabelText(/exact capability payload json/i)).toHaveAttribute("readonly");
    expect(screen.queryByLabelText(/^tool grants$/i)).not.toBeInTheDocument();
  });

  it("blocks saves when the catalog query fails", () => {
    toolsQueryMock.mockReturnValue({
      data: undefined,
      error: new Error("catalog offline"),
      isError: true,
      isPending: false,
    });

    render(<CapabilitiesEditorPage />);

    expect(screen.getByTestId("capability-tool-catalog-error")).toHaveTextContent("catalog offline");
    expect(screen.getByRole("button", { name: /save capability/i })).toBeDisabled();
    expect(createCapabilityMock).not.toHaveBeenCalled();
    expect(updateCapabilityMock).not.toHaveBeenCalled();
  });

  it("blocks saves when edit mode contains stale toolKeys missing from the catalog", () => {
    paramsMock.capabilityId = "3";
    currentCapability = {
      ...existingCapability,
      toolKeys: ["search_docs", "retired_tool"],
      tools: [catalogTools[0]],
    };

    render(<CapabilitiesEditorPage />);

    const staleToolAlert = screen.getByTestId("capability-stale-tool-keys");
    expect(staleToolAlert).toHaveTextContent("retired_tool");
    expect(staleToolAlert).toHaveTextContent(/missing catalog key\(s\): retired_tool/i);
    expect(screen.getByRole("button", { name: /save capability/i })).toBeDisabled();
    expect(updateCapabilityMock).not.toHaveBeenCalled();
  });

  it("activates a draft capability", async () => {
    paramsMock.capabilityId = "3";
    activateCapabilityMock.mockResolvedValue({ id: 3 });

    render(<CapabilitiesEditorPage />);
    fireEvent.click(screen.getByTestId("capabilities-activate"));

    await waitFor(() => expect(activateCapabilityMock).toHaveBeenCalledWith("3"));
    expect(toastSuccessMock).toHaveBeenCalledWith("Capability activated");
  });
});
