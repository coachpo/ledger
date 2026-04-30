import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

const existingCapability = {
  id: 3,
  key: "summarize_capability",
  name: "Summarize Capability",
  description: "Condenses results.",
  toolGrants: [{ tool: "search_docs" }, { tool: "answer_user" }],
  status: "draft",
  version: 2,
};

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
      ? { data: existingCapability, error: null, isError: false, isPending: false }
      : { data: undefined, error: null, isError: false, isPending: false },
  useCreateCapability: () => ({ isPending: false, mutateAsync: createCapabilityMock }),
  useUpdateCapability: () => ({ isPending: false, mutateAsync: updateCapabilityMock }),
  useActivateCapability: () => ({ isPending: false, mutateAsync: activateCapabilityMock }),
}));

describe("CapabilitiesEditorPage", () => {
  beforeEach(() => {
    paramsMock.capabilityId = undefined;
    navigateMock.mockReset();
    createCapabilityMock.mockReset();
    updateCapabilityMock.mockReset();
    activateCapabilityMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
  });

  it("shows invalid-save feedback on create", async () => {
    render(<CapabilitiesEditorPage />);

    fireEvent.click(screen.getByRole("button", { name: /save capability/i }));

    await waitFor(() => expect(toastErrorMock).toHaveBeenCalledWith("At least one tool grant is required."));
    expect(createCapabilityMock).not.toHaveBeenCalled();
  });

  it("hydrates edit state, saves through the update hook, and navigates to the new version", async () => {
    paramsMock.capabilityId = "3";
    updateCapabilityMock.mockResolvedValue({ id: 8 });

    render(<CapabilitiesEditorPage />);

    expect(screen.getByLabelText(/key/i)).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "Updated Capability" } });
    fireEvent.click(screen.getByRole("button", { name: /save capability/i }));

    await waitFor(() => expect(updateCapabilityMock).toHaveBeenCalledTimes(1));
    expect(updateCapabilityMock).toHaveBeenCalledWith({
      payload: {
        description: "Condenses results.",
        name: "Updated Capability",
        toolGrants: [{ tool: "search_docs" }, { tool: "answer_user" }],
      },
      capabilityId: "3",
    });
    expect(navigateMock).toHaveBeenCalledWith("/capabilities/8/edit");
  });

  it("shows a read-only exact JSON preview for the current tool-grant lines", () => {
    render(<CapabilitiesEditorPage />);

    fireEvent.change(screen.getByLabelText(/^tool grants$/i), {
      target: { value: " search_docs \n\n answer_user " },
    });

    expect(screen.getByLabelText(/exact tool grants json/i)).toHaveValue(
      stringifyJson([{ tool: "search_docs" }, { tool: "answer_user" }]),
    );
    expect(screen.getByLabelText(/exact tool grants json/i)).toHaveAttribute("readonly");
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
