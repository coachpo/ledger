import type { ComponentProps } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { stringifyJson } from "@/lib/platform-authoring/common/serialization";

import { TemplateEditorPage } from "./editor";
import { TemplateListPage } from "./list";

const paramsMock: { templateId?: string } = {};
const navigateMock = vi.fn();
const compileInlineMock = vi.fn();
const compileReportMutateMock = vi.fn();
const deleteTemplateMutateMock = vi.fn();
const deleteTemplatesMutateMock = vi.fn();
const useTemplateMock = vi.fn();
const useTemplatesListMock = vi.fn();

vi.mock("react-router", () => ({
  Link: ({ children, to, ...props }: ComponentProps<"a"> & { to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
  useNavigate: () => navigateMock,
  useParams: () => paramsMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/hooks/use-debounce", () => ({
  useDebounce: <T,>(value: T) => value,
}));

vi.mock("@/lib/markdown-format", () => ({
  formatMarkdown: vi.fn(),
}));

vi.mock("@/hooks/use-templates", () => ({
  useTemplate: (templateId?: string) => useTemplateMock(templateId),
  useTemplates: () => useTemplatesListMock(),
  useCreateTemplate: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useUpdateTemplate: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useDeleteTemplate: () => ({
    isPending: false,
    mutate: deleteTemplateMutateMock,
  }),
  useDeleteTemplates: () => ({
    isPending: false,
    mutate: deleteTemplatesMutateMock,
  }),
  useCompileInline: () => ({
    mutate: compileInlineMock,
    data: undefined,
    error: null,
    isPending: false,
  }),
  usePlaceholders: () => ({
    data: {
      portfolios: [
        {
          slug: "growth",
          name: "Growth",
          baseCurrency: "USD",
          positions: [{ symbol: "AAPL", name: "Apple Inc." }],
        },
      ],
      reports: [
        {
          name: "latest_report_20260318_210455",
          createdAt: "2026-03-18T21:04:55Z",
        },
      ],
    },
    isLoading: false,
  }),
}));

vi.mock("@/hooks/use-reports", () => ({
  useCompileReport: () => ({
    isPending: false,
    mutate: compileReportMutateMock,
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

describe("TemplateEditorPage", () => {
  beforeEach(() => {
    paramsMock.templateId = undefined;
    navigateMock.mockReset();
    compileInlineMock.mockReset();
    compileReportMutateMock.mockReset();
    deleteTemplateMutateMock.mockReset();
    deleteTemplatesMutateMock.mockReset();
    useTemplateMock.mockReset();
    const savedTemplate = {
      id: 42,
      name: "Saved Template",
      content: "Existing content",
      createdAt: "2026-05-01T10:00:00Z",
      updatedAt: "2026-05-02T10:00:00Z",
    };
    useTemplateMock.mockImplementation((templateId?: string) => ({
      data: templateId ? savedTemplate : undefined,
      error: null,
      isError: false,
      isLoading: false,
    }));
    useTemplatesListMock.mockReset();
    useTemplatesListMock.mockReturnValue(queryResult([]));
  });

  it("renders a full-height semantic editor shell with labeled core controls", () => {
    render(<TemplateEditorPage />);

    const shell = screen.getByTestId("template-editor-shell");
    expect(shell).toHaveClass("h-full", "min-h-0", "min-w-0");
    expect(shell).toHaveAttribute("aria-labelledby", "template-editor-title");
    expect(screen.queryByRole("main")).not.toBeInTheDocument();
    expect(screen.getByTestId("template-editor-header")).toHaveClass(
      "sticky",
      "top-0",
      "z-20",
    );
    expect(screen.getByTestId("template-authoring-context")).toHaveClass(
      "grid",
      "shrink-0",
    );
    expect(screen.getByTestId("template-editor-split")).toHaveClass(
      "min-h-0",
      "flex-1",
      "rounded-xl",
    );
    expect(
      screen.getByRole("heading", { name: "Create Template" }),
    ).toBeVisible();
    expect(screen.getByLabelText(/^Template name$/i)).toHaveAttribute(
      "placeholder",
      "Name this template...",
    );
    expect(
      screen.getByRole("textbox", { name: /^Template content$/i }),
    ).toHaveAttribute("placeholder", "Enter template content…");
    expect(screen.getByRole("button", { name: "Close editor" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    expect(screen.getByText("Unsaved draft")).toBeVisible();
    expect(screen.getByText("Exact Runtime Input JSON")).toBeVisible();
    expect(screen.getByText("Runtime Inputs")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Generate Report" }),
    ).toBeDisabled();
  });

  it("renders a deterministic not-found state for missing saved templates", () => {
    paramsMock.templateId = "42";
    useTemplateMock.mockReturnValue({
      data: undefined,
      error: new Error("Template not found."),
      isError: true,
      isLoading: false,
    });

    render(<TemplateEditorPage />);

    expect(screen.getByText("Template not found.")).toBeVisible();
    expect(
      screen.queryByTestId("template-editor-shell"),
    ).not.toBeInTheDocument();
  });

  it("shows dynamic report selector guidance and inserts a selector example", () => {
    render(<TemplateEditorPage />);

    fireEvent.click(
      screen.getByRole("button", { name: /dynamic report selectors/i }),
    );

    expect(
      screen.getByText(/Latest and tagged report selectors\./i),
    ).toBeInTheDocument();
    expect(
      screen.getByText('reports.latest("AAPL").content'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('reports.by_tag("weekly_review").latest.content'),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByText('reports.latest("AAPL").content'));

    expect(screen.getByPlaceholderText("Enter template content…")).toHaveValue(
      '{{reports.latest("AAPL").content}}',
    );
  });

  it("passes runtime inputs through preview compile and report generation", () => {
    paramsMock.templateId = "42";

    render(<TemplateEditorPage />);

    fireEvent.click(screen.getByRole("button", { name: /show/i }));
    fireEvent.click(screen.getByRole("button", { name: /add input/i }));

    const keyInputs = screen.getAllByPlaceholderText("ticker");
    const valueInputs = screen.getAllByPlaceholderText("AAPL");

    fireEvent.change(keyInputs[0], { target: { value: "ticker" } });
    fireEvent.change(valueInputs[0], { target: { value: "MSFT" } });
    fireEvent.change(screen.getByPlaceholderText("Enter template content…"), {
      target: { value: "Ticker {{inputs.ticker}}" },
    });

    const rawRuntimeInputPreview = screen.getByLabelText(
      /exact raw runtime input json/i,
    );

    expect(rawRuntimeInputPreview).toHaveValue(
      stringifyJson({ ticker: "MSFT" }),
    );
    expect(rawRuntimeInputPreview).toHaveAttribute("readonly");

    expect(compileInlineMock).toHaveBeenLastCalledWith({
      content: "Ticker {{inputs.ticker}}",
      inputs: { ticker: "MSFT" },
    });

    fireEvent.click(screen.getByRole("button", { name: /generate report/i }));
    const dialog = screen.getByRole("dialog");

    expect(within(dialog).getByDisplayValue("ticker")).toBeInTheDocument();
    expect(within(dialog).getByDisplayValue("MSFT")).toBeInTheDocument();
    fireEvent.click(
      within(dialog).getByRole("button", { name: /^generate$/i }),
    );

    expect(compileReportMutateMock).toHaveBeenCalledWith(
      {
        templateId: "42",
        input: { inputs: { ticker: "MSFT" } },
      },
      expect.any(Object),
    );
  });

  it("removes orchestration mention assistance while keeping the placeholder reference", () => {
    render(<TemplateEditorPage />);

    expect(
      screen.queryByRole("button", { name: /mention assistance/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /inputs/i })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /dynamic report selectors/i }),
    ).toBeInTheDocument();
  });

  it("labels template inventory controls and distinguishes filtered-empty from empty", () => {
    useTemplatesListMock.mockReturnValue(
      queryResult({
        items: [
          {
            id: 7,
            name: "Quarterly Review",
            content: "Portfolio summary",
            createdAt: "2026-05-01T10:00:00Z",
            updatedAt: "2026-05-02T10:00:00Z",
          },
        ],
      }),
    );

    render(<TemplateListPage />);

    expect(screen.getByLabelText("Search templates")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Search templates"), {
      target: { value: "missing" },
    });

    expect(screen.getByText("No templates match your search.")).toBeVisible();
    expect(screen.queryByText("No templates yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("Quarterly Review")).not.toBeInTheDocument();
  });

  it("renders template table navigation as explicit links with confirmed row deletes", () => {
    useTemplatesListMock.mockReturnValue(
      queryResult({
        items: [
          {
            id: 7,
            name: "Quarterly Review",
            content: "Portfolio summary",
            createdAt: "2026-05-01T10:00:00Z",
            updatedAt: "2026-05-02T10:00:00Z",
          },
        ],
      }),
    );

    render(<TemplateListPage />);

    fireEvent.click(screen.getByRole("radio", { name: /table view/i }));

    const table = screen.getByRole("table");
    expect(table.parentElement?.parentElement).toHaveClass(
      "min-w-0",
      "max-w-full",
      "rounded-md",
      "border",
    );
    const editorLink = within(table).getByRole("link", {
      name: "Open editor for Quarterly Review",
    });
    const actionsButton = within(table).getByRole("button", {
      name: "Open actions for Quarterly Review",
    });
    expect(editorLink).toHaveAttribute("href", "/templates/7/edit");
    expect(
      editorLink.compareDocumentPosition(actionsButton) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);

    fireEvent.keyDown(
      within(table).getByRole("button", {
        name: "Open actions for Quarterly Review",
      }),
      { key: "Enter" },
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));

    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      "Delete Quarterly Review?",
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(deleteTemplateMutateMock).toHaveBeenCalledWith(
      7,
      expect.any(Object),
    );
  });

  it("supports table-only template selection, scoped bulk delete, and clear", () => {
    useTemplatesListMock.mockReturnValue(
      queryResult({
        items: [
          {
            id: 7,
            name: "Quarterly Review",
            content: "Portfolio summary",
            createdAt: "2026-05-01T10:00:00Z",
            updatedAt: "2026-05-02T10:00:00Z",
          },
          {
            id: 8,
            name: "Monthly Snapshot",
            content: "Risk summary",
            createdAt: "2026-05-03T10:00:00Z",
            updatedAt: "2026-05-04T10:00:00Z",
          },
        ],
      }),
    );

    render(<TemplateListPage />);

    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /table view/i }));
    fireEvent.click(
      screen.getByRole("checkbox", { name: /select all shown templates/i }),
    );

    expect(
      within(screen.getByTestId("templates-bulk-actions")).getByText(
        "2 of 2 templates selected",
      ),
    ).toBeVisible();

    fireEvent.change(screen.getByLabelText("Search templates"), {
      target: { value: "Monthly" },
    });

    const bulkActions = screen.getByTestId("templates-bulk-actions");
    expect(
      within(bulkActions).getByText("1 of 1 templates selected"),
    ).toBeVisible();
    fireEvent.click(
      within(bulkActions).getByRole("button", { name: /delete selected/i }),
    );

    expect(deleteTemplatesMutateMock).toHaveBeenCalledWith(
      [8],
      expect.any(Object),
    );
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();

    fireEvent.click(within(bulkActions).getByRole("button", { name: "Clear" }));
    expect(
      screen.queryByTestId("templates-bulk-actions"),
    ).not.toBeInTheDocument();
  });

  it("clears template selection when switching back to cards", () => {
    useTemplatesListMock.mockReturnValue(
      queryResult({
        items: [
          {
            id: 7,
            name: "Quarterly Review",
            content: "Portfolio summary",
            createdAt: "2026-05-01T10:00:00Z",
            updatedAt: "2026-05-02T10:00:00Z",
          },
        ],
      }),
    );

    render(<TemplateListPage />);

    fireEvent.click(screen.getByRole("radio", { name: /table view/i }));
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /select template quarterly review/i,
      }),
    );
    expect(screen.getByTestId("templates-bulk-actions")).toBeVisible();

    fireEvent.click(screen.getByRole("radio", { name: /cards view/i }));
    expect(
      screen.queryByTestId("templates-bulk-actions"),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: /table view/i }));
    expect(
      screen.getByRole("checkbox", {
        name: /select template quarterly review/i,
      }),
    ).toHaveAttribute("aria-checked", "false");
  });
});
