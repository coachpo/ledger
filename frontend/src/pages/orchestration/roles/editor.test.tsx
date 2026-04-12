import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OrchestrationRoleEditorPage } from "./editor";

const navigateMock = vi.fn();
const paramsMock: { roleId?: string } = {};
const createRoleMock = vi.fn();
const updateRoleMock = vi.fn();
const existingRole = {
  id: 1,
  key: "macro_research_role",
  name: "Librarian",
  description: "Investigates macro drivers.",
  systemPrompt: "Research and summarize.",
   capabilityBundleKeys: ["research.context_bundle", "reports.latest_bundle"],
  enabled: false,
  version: 3,
  createdAt: "2026-04-01T10:00:00Z",
  updatedAt: "2026-04-01T10:00:00Z",
};

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
  useParams: () => paramsMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/hooks/use-orchestration", () => ({
  useOrchestrationRole: () =>
    paramsMock.roleId
      ? {
          data: existingRole,
          isPending: false,
          isError: false,
          error: null,
        }
      : {
          data: undefined,
          isPending: false,
          isError: false,
          error: null,
        },
  useCreateOrchestrationRole: () => ({
    isPending: false,
    mutateAsync: createRoleMock,
  }),
  useUpdateOrchestrationRole: () => ({
    isPending: false,
    mutateAsync: updateRoleMock,
  }),
}));

describe("OrchestrationRoleEditorPage", () => {
  beforeEach(() => {
    paramsMock.roleId = undefined;
    navigateMock.mockReset();
    createRoleMock.mockReset();
    updateRoleMock.mockReset();
  });

  it("defaults enabled on create and sends the toggle value through the create hook", async () => {
    createRoleMock.mockResolvedValue({ id: 12 });

    render(<OrchestrationRoleEditorPage />);

    const enabledSwitch = screen.getByRole("switch", { name: /enabled/i });
    expect(enabledSwitch).toBeChecked();

    fireEvent.click(enabledSwitch);
    fireEvent.change(screen.getByLabelText(/key/i), {
      target: { value: "macro_research_role" },
    });
    fireEvent.change(screen.getByLabelText(/name/i), {
      target: { value: "Macro Research" },
    });
    fireEvent.change(screen.getByLabelText(/system prompt/i), {
      target: { value: "Research and summarize." },
    });
    fireEvent.change(screen.getByLabelText(/capability bundle refs/i), {
      target: { value: "research.context_bundle\nreports.latest_bundle" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save role/i }));

    await waitFor(() => expect(createRoleMock).toHaveBeenCalledTimes(1));
    expect(createRoleMock).toHaveBeenCalledWith({
      key: "macro_research_role",
      name: "Macro Research",
      description: null,
      systemPrompt: "Research and summarize.",
      capabilityBundleKeys: ["research.context_bundle", "reports.latest_bundle"],
      enabled: false,
    });
  });

  it("hydrates enabled from the existing role and sends updates through the update hook", async () => {
    paramsMock.roleId = "1";
    updateRoleMock.mockResolvedValue({ id: 1 });

    render(<OrchestrationRoleEditorPage />);

    const enabledSwitch = screen.getByRole("switch", { name: /enabled/i });
    expect(screen.getByLabelText(/key/i)).toBeDisabled();
    expect(screen.getByLabelText(/capability bundle refs/i)).toHaveValue(
      "research.context_bundle\nreports.latest_bundle",
    );
    expect(enabledSwitch).not.toBeChecked();

    fireEvent.click(enabledSwitch);
    fireEvent.click(screen.getByRole("button", { name: /save role/i }));

    await waitFor(() => expect(updateRoleMock).toHaveBeenCalledTimes(1));
    expect(updateRoleMock).toHaveBeenCalledWith({
      roleId: "1",
      payload: {
        name: "Librarian",
        description: "Investigates macro drivers.",
        systemPrompt: "Research and summarize.",
        capabilityBundleKeys: ["research.context_bundle", "reports.latest_bundle"],
        enabled: true,
      },
    });
  });
});
