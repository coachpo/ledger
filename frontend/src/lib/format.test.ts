import { describe, expect, it } from "vitest";

import {
  formatCompactNumber,
  formatCurrency,
  formatDate,
  formatDateTime,
  formatDecimal,
  formatPercent,
} from "./format";

function expectedCurrency(value: number, currency: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function expectedDate(isoString: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(isoString));
}

function expectedDateTime(isoString: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(new Date(isoString));
}

describe("format", () => {
  it("formats currency, decimals, and percentages across common inputs", () => {
    expect(formatCurrency(1234.5)).toBe(expectedCurrency(1234.5, "USD"));
    expect(formatCurrency("9876.5", "EUR")).toBe(expectedCurrency(9876.5, "EUR"));
    expect(formatCurrency(0, "JPY")).toBe(expectedCurrency(0, "JPY"));

    expect(formatDecimal("1234.5678")).toBe("1234.57");
    expect(formatDecimal(12.34567, 4)).toBe("12.3457");
    expect(formatDecimal(0, 4)).toBe("0.0000");

    expect(formatPercent("0.1234")).toBe("12.34%");
    expect(formatPercent(-0.0567, 1)).toBe("-5.7%");
    expect(formatPercent(0)).toBe("0.00%");
  });

  it("formats ISO date and datetime strings", () => {
    const isoString = "2024-03-15T12:34:56Z";

    expect(formatDate(isoString)).toBe(expectedDate(isoString));
    expect(formatDateTime(isoString)).toBe(expectedDateTime(isoString));
  });

  it("formats compact numbers and preserves sign", () => {
    expect(formatCompactNumber(123)).toBe("123.00");
    expect(formatCompactNumber(1234)).toBe("1.23K");
    expect(formatCompactNumber(1234567)).toBe("1.23M");
    expect(formatCompactNumber(-7654)).toBe("-7.65K");
  });

  it("returns safe fallbacks for invalid numeric input", () => {
    expect(formatCurrency("not-a-number")).toBe("$0.00");
    expect(formatDecimal("not-a-number")).toBe("0.00");
    expect(formatPercent("not-a-number")).toBe("0.00%");
    expect(formatCompactNumber("not-a-number")).toBe("0");
  });
});
