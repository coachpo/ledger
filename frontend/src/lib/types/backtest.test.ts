import { describe, expect, it } from "vitest";

import type { BacktestRead } from "./backtest";

describe("BacktestRead webhook contract", () => {
  it("accepts webhook fields instead of LLM fields", () => {
    const valid = {
      id: 1,
      portfolioId: 1,
      portfolioName: "Core Portfolio",
      templateId: 1,
      depositBalanceId: 1,
      name: "Backtest",
      status: "COMPLETED",
      frequency: "DAILY",
      startDate: "2024-01-02",
      endDate: "2024-03-29",
      currentCycleDate: null,
      totalCycles: 1,
      completedCycles: 1,
      webhookUrl: "http://test.example.com/webhook",
      webhookTimeout: 600,
      currentCycleStatus: null,
      priceMode: "CLOSING_PRICE",
      commissionMode: "ZERO",
      commissionValue: "0",
      benchmarkSymbols: ["^GSPC"],
      recentActivity: null,
      results: null,
      errorMessage: null,
      createdAt: "2024-01-02T00:00:00Z",
      updatedAt: "2024-01-02T00:00:00Z",
    } satisfies BacktestRead;

    expect(valid.webhookUrl).toBe("http://test.example.com/webhook");
    expect(valid.webhookTimeout).toBe(600);
  });
});
