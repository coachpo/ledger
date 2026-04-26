import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { stringifyJson } from "@/lib/platform-authoring/common/serialization";

import { SkillsEditorPage } from "./editor";

const navigateMock = vi.fn();
const paramsMock: { skillId?: string } = {};
const createSkillMock = vi.fn();
const updateSkillMock = vi.fn();
const activateSkillMock = vi.fn();
const toastErrorMock = vi.fn();
const toastSuccessMock = vi.fn();

const existingSkill = {
  id: 3,
  key: "summarize_skill",
  name: "Summarize Skill",
  description: "Condenses results.",
  toolDefinitions: [{ tool: "search_docs" }, { tool: "answer_user" }],
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

vi.mock("@/hooks/use-skills", () => ({
  useSkill: () =>
    paramsMock.skillId
      ? { data: existingSkill, error: null, isError: false, isPending: false }
      : { data: undefined, error: null, isError: false, isPending: false },
  useCreateSkill: () => ({ isPending: false, mutateAsync: createSkillMock }),
  useUpdateSkill: () => ({ isPending: false, mutateAsync: updateSkillMock }),
  useActivateSkill: () => ({ isPending: false, mutateAsync: activateSkillMock }),
}));

describe("SkillsEditorPage", () => {
  beforeEach(() => {
    paramsMock.skillId = undefined;
    navigateMock.mockReset();
    createSkillMock.mockReset();
    updateSkillMock.mockReset();
    activateSkillMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
  });

  it("shows invalid-save feedback on create", async () => {
    render(<SkillsEditorPage />);

    fireEvent.click(screen.getByRole("button", { name: /save skill/i }));

    await waitFor(() => expect(toastErrorMock).toHaveBeenCalledWith("At least one tool definition is required."));
    expect(createSkillMock).not.toHaveBeenCalled();
  });

  it("hydrates edit state, saves through the update hook, and navigates to the new version", async () => {
    paramsMock.skillId = "3";
    updateSkillMock.mockResolvedValue({ id: 8 });

    render(<SkillsEditorPage />);

    expect(screen.getByLabelText(/key/i)).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "Updated Skill" } });
    fireEvent.click(screen.getByRole("button", { name: /save skill/i }));

    await waitFor(() => expect(updateSkillMock).toHaveBeenCalledTimes(1));
    expect(updateSkillMock).toHaveBeenCalledWith({
      payload: {
        description: "Condenses results.",
        name: "Updated Skill",
        toolDefinitions: [{ tool: "search_docs" }, { tool: "answer_user" }],
      },
      skillId: "3",
    });
    expect(navigateMock).toHaveBeenCalledWith("/skills/8/edit");
  });

  it("shows a read-only exact JSON preview for the current tool-definition lines", () => {
    render(<SkillsEditorPage />);

    fireEvent.change(screen.getByLabelText(/^tool definitions$/i), {
      target: { value: " search_docs \n\n answer_user " },
    });

    expect(screen.getByLabelText(/exact tool definitions json/i)).toHaveValue(
      stringifyJson([{ tool: "search_docs" }, { tool: "answer_user" }]),
    );
    expect(screen.getByLabelText(/exact tool definitions json/i)).toHaveAttribute("readonly");
  });

  it("activates a draft skill", async () => {
    paramsMock.skillId = "3";
    activateSkillMock.mockResolvedValue({ id: 3 });

    render(<SkillsEditorPage />);
    fireEvent.click(screen.getByTestId("skills-activate"));

    await waitFor(() => expect(activateSkillMock).toHaveBeenCalledWith("3"));
    expect(toastSuccessMock).toHaveBeenCalledWith("Skill activated");
  });
});
