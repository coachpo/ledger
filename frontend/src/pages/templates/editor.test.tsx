import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TemplateEditorPage } from "./editor";

const paramsMock: { templateId?: string } = {};
const navigateMock = vi.fn();
const compileInlineMock = vi.fn();
const compileReportMutateMock = vi.fn();

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

vi.mock("@/hooks/use-debounce", () => ({
  useDebounce: (value: string) => value,
}));

vi.mock("@/lib/markdown-format", () => ({
  formatMarkdown: vi.fn(),
}));

vi.mock("@/hooks/use-templates", () => ({
  useTemplate: () => ({ data: undefined, isLoading: false }),
  useCreateTemplate: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useUpdateTemplate: () => ({ isPending: false, mutateAsync: vi.fn() }),
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

describe("TemplateEditorPage", () => {
  beforeEach(() => {
    paramsMock.templateId = undefined;
    navigateMock.mockReset();
    compileInlineMock.mockReset();
    compileReportMutateMock.mockReset();
  });

  it("shows dynamic report selector guidance and inserts a selector example", () => {
    render(<TemplateEditorPage />);

    fireEvent.click(screen.getByRole("button", { name: /dynamic report selectors/i }));

    expect(
      screen.getByText(
        /Use these when the latest matching report matters more than a fixed saved name\./i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/`reports\[0\]` is the newest report\./i)).toBeInTheDocument();
    expect(screen.getByText('reports.latest("AAPL").content')).toBeInTheDocument();
    expect(screen.getByText('reports.by_tag("weekly_review").latest.content')).toBeInTheDocument();

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

    expect(compileInlineMock).toHaveBeenLastCalledWith({
      content: "Ticker {{inputs.ticker}}",
      inputs: { ticker: "MSFT" },
    });

    fireEvent.click(screen.getByRole("button", { name: /generate report/i }));
    const dialog = screen.getByRole("dialog");

    expect(within(dialog).getByDisplayValue("ticker")).toBeInTheDocument();
    expect(within(dialog).getByDisplayValue("MSFT")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: /^generate$/i }));

    expect(compileReportMutateMock).toHaveBeenCalledWith(
      {
        templateId: "42",
        input: { inputs: { ticker: "MSFT" } },
      },
      expect.any(Object),
    );
  });
});
