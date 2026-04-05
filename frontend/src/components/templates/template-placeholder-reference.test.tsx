import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TemplatePlaceholderReference } from "./template-placeholder-reference";

describe("TemplatePlaceholderReference", () => {
  it("renders static guidance and inserts a selected placeholder", () => {
    const onInsert = vi.fn();

    render(
      <TemplatePlaceholderReference
        open
        isLoading={false}
        onClose={() => {}}
        onInsert={onInsert}
        placeholderTree={{
          portfolios: [
            {
              slug: "growth",
              name: "Growth",
              baseCurrency: "USD",
              positions: [{ symbol: "AAPL", name: "Apple Inc." }],
            },
          ],
          reports: [{ name: "latest_report", createdAt: "2026-03-18T21:04:55Z" }],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /dynamic report selectors/i }));
    fireEvent.click(screen.getByText('reports.latest("AAPL").content'));

    expect(onInsert).toHaveBeenCalledWith('reports.latest("AAPL").content');
    expect(screen.getByRole("button", { name: /growth/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /latest_report/i })).toBeInTheDocument();
  });
});
