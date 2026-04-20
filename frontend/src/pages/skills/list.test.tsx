import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SkillsListPage } from "./list";

const {
  archiveSkillMock,
  navigateMock,
  toastErrorMock,
  toastSuccessMock,
  useSkillsMock,
} = vi.hoisted(() => ({
  archiveSkillMock: vi.fn(),
  navigateMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  useSkillsMock: vi.fn(),
}));

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}));

vi.mock("@/hooks/use-skills", () => ({
  useArchiveSkill: () => ({ isPending: false, mutateAsync: archiveSkillMock }),
  useSkills: () => useSkillsMock(),
}));

describe("SkillsListPage", () => {
  beforeEach(() => {
    archiveSkillMock.mockReset();
    navigateMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    useSkillsMock.mockReturnValue({
      data: {
        items: [
          {
            id: 3,
            key: "summarize_skill",
            name: "Summarize Skill",
            description: "Condenses results.",
            toolDefinitions: [{ tool: "search_docs" }, { tool: "answer_user" }],
            status: "draft",
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
    archiveSkillMock.mockResolvedValue({ id: 3 });

    render(<SkillsListPage />);

    expect(screen.getByTestId("skills-row-summarize_skill")).toBeVisible();
    expect(screen.getByText(/2 tool definition/i)).toBeVisible();

    fireEvent.click(screen.getByTestId("skills-archive-summarize_skill"));
    await waitFor(() => expect(archiveSkillMock).toHaveBeenCalledWith(3));
    expect(toastSuccessMock).toHaveBeenCalledWith("Skill archived");

    fireEvent.click(screen.getByTestId("skills-new"));
    expect(navigateMock).toHaveBeenCalledWith("/skills/new");

    fireEvent.click(screen.getByTestId("skills-open-summarize_skill"));
    expect(navigateMock).toHaveBeenCalledWith("/skills/3/edit");
  });

  it("archives a skill from the list", async () => {
    archiveSkillMock.mockResolvedValue({ id: 3 });

    render(<SkillsListPage />);

    fireEvent.click(screen.getByTestId("skills-archive-summarize_skill"));

    await waitFor(() => expect(archiveSkillMock).toHaveBeenCalledWith(3));
    expect(toastSuccessMock).toHaveBeenCalledWith("Skill archived");
  });
});
