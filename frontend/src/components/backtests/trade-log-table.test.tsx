import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TradeLogTable } from "./trade-log-table";

describe("TradeLogTable", () => {
  it("sorts rows when the symbol header is clicked", () => {
    render(
      <TradeLogTable
        trades={[
          {
            cycleDate: "2024-01-15",
            symbol: "MSFT",
            side: "BUY",
            quantity: "1",
            requestedPrice: "100.00",
            executedPrice: "100.00",
            executed: true,
            reportSlug: null,
          },
          {
            cycleDate: "2024-01-16",
            symbol: "AAPL",
            side: "BUY",
            quantity: "1",
            requestedPrice: "90.00",
            executedPrice: "90.00",
            executed: true,
            reportSlug: null,
          },
        ]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /symbol/i }));

    const rows = screen.getAllByRole("row");
    expect(rows[1]).toHaveTextContent("AAPL");
    expect(rows[2]).toHaveTextContent("MSFT");
  });
});
