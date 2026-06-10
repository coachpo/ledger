import type { ComponentProps } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TemplateListPage } from "./list";

const deleteTemplateMutateMock = vi.fn();
const deleteTemplatesMutateMock = vi.fn();
const useTemplatesListMock = vi.fn();

vi.mock("react-router", () => ({
  Link: ({ children, to, ...props }: ComponentProps<"a"> & { to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/hooks/use-templates", () => ({
  useTemplates: () => useTemplatesListMock(),
  useDeleteTemplate: () => ({
    isPending: false,
    mutate: deleteTemplateMutateMock,
  }),
  useDeleteTemplates: () => ({
    isPending: false,
    mutate: deleteTemplatesMutateMock,
  }),
}));

function queryResult<T>(data: T) {
  return {
    data,
    error: null,
    isError: false,
    isPending: false,
  };
}

function templateShellRegions() {
  return Array.from(
    screen
      .getByTestId("templates-list-page")
      .querySelectorAll("[data-inventory-shell-region]"),
  ).map((region) => region.getAttribute("data-inventory-shell-region"));
}

const quarterlyTemplate = {
  id: 7,
  name: "Quarterly Review",
  content: "Portfolio summary {{inputs.ticker}}",
  createdAt: "2026-05-01T10:00:00Z",
  updatedAt: "2026-05-02T10:00:00Z",
};

describe("TemplateListPage", () => {
  beforeEach(() => {
    deleteTemplateMutateMock.mockReset();
    deleteTemplatesMutateMock.mockReset();
    useTemplatesListMock.mockReset();
    useTemplatesListMock.mockReturnValue(queryResult([]));
  });

  it("keeps loading copy in the inventory content while route-owned toolbar controls stay visible", () => {
    useTemplatesListMock.mockReturnValue({
      data: undefined,
      error: null,
      isError: false,
      isPending: true,
    });

    render(<TemplateListPage />);

    expect(templateShellRegions()).toEqual(["context", "toolbar", "content"]);
    expect(screen.getByRole("link", { name: /new template/i })).toHaveAttribute(
      "href",
      "/templates/new",
    );
    expect(screen.getByLabelText("Search templates")).toBeVisible();
    expect(screen.queryByRole("radio", { name: /cards view/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /table view/i })).not.toBeInTheDocument();
    expect(screen.getByText("No templates loaded")).toBeVisible();

    const inventory = screen.getByTestId("templates-inventory");
    expect(within(inventory).getByText("Loading templates...")).toBeVisible();
    expect(within(inventory).queryByText("No templates yet.")).not.toBeInTheDocument();
  });

  it("keeps error copy in the inventory content while route-owned toolbar controls stay visible", () => {
    useTemplatesListMock.mockReturnValue({
      data: undefined,
      error: new Error("Templates API unavailable"),
      isError: true,
      isPending: false,
    });

    render(<TemplateListPage />);

    expect(templateShellRegions()).toEqual(["context", "toolbar", "content"]);
    expect(screen.getByRole("link", { name: /new template/i })).toHaveAttribute(
      "href",
      "/templates/new",
    );
    expect(screen.getByLabelText("Search templates")).toBeVisible();
    expect(screen.getByText("No templates loaded")).toBeVisible();

    const inventory = screen.getByTestId("templates-inventory");
    expect(within(inventory).getByRole("alert")).toHaveTextContent(
      "Templates API unavailable",
    );
    expect(within(inventory).queryByText("Loading templates...")).not.toBeInTheDocument();
  });

  it("keeps compact route controls and the new-template entry visible in the empty state", () => {
    render(<TemplateListPage />);

    const shellRegions = Array.from(
      screen
        .getByTestId("templates-list-page")
        .querySelectorAll("[data-inventory-shell-region]"),
    ).map((region) => region.getAttribute("data-inventory-shell-region"));
    expect(shellRegions).toEqual(["context", "toolbar", "content"]);
    expect(screen.queryByRole("radio", { name: /cards view/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /table view/i })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Templates" })).toBeVisible();
    const newTemplateLink = screen.getByRole("link", {
      name: /new template/i,
    });
    expect(newTemplateLink).toBeVisible();
    expect(newTemplateLink).toHaveAttribute("href", "/templates/new");
    expect(screen.getByLabelText("Search templates")).toBeVisible();
    expect(screen.queryByRole("radio", { name: /cards view/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /table view/i })).not.toBeInTheDocument();

    const inventory = screen.getByTestId("templates-inventory");
    expect(within(inventory).getByText("No templates yet.")).toBeVisible();
    expect(within(inventory).getByTestId("templates-empty-state")).toHaveTextContent(
      "No templates yet.",
    );
    expect(
      within(inventory).getByText(/Create a reusable markdown template/i),
    ).toBeVisible();
  });

  it("keeps filtered-empty deterministic while preserving search and new-template controls", () => {
    useTemplatesListMock.mockReturnValue(
      queryResult({ items: [quarterlyTemplate] }),
    );

    render(<TemplateListPage />);

    fireEvent.change(screen.getByLabelText("Search templates"), {
      target: { value: "missing" },
    });

    expect(screen.getByLabelText("Search templates")).toBeVisible();
    expect(screen.getByRole("link", { name: /new template/i })).toBeVisible();
    expect(screen.getByTestId("templates-active-filters")).toHaveTextContent(
      "missing",
    );
    expect(screen.getByText("No templates match your search.")).toBeVisible();
    expect(screen.getByTestId("templates-filtered-empty-state")).toHaveTextContent(
      "No templates match your search.",
    );
    expect(screen.getByText("Showing 0 templates of 1 template")).toBeVisible();
    expect(screen.queryByText("No templates yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("Quarterly Review")).not.toBeInTheDocument();

    fireEvent.click(
      within(screen.getByTestId("templates-active-filters")).getByRole("button", {
        name: "Clear filters",
      }),
    );

    expect(screen.queryByTestId("templates-active-filters")).not.toBeInTheDocument();
    expect(screen.getByText("Quarterly Review")).toBeVisible();
  });

});
