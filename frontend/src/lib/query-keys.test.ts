import { describe, expect, it } from "vitest";

import { queryKeys } from "./query-keys";

describe("query keys", () => {
  it("normalizes string and numeric ids to the same key", () => {
    expect(queryKeys.portfolios.detail("1")).toEqual(queryKeys.portfolios.detail(1));
    expect(queryKeys.balances.list("1")).toEqual(queryKeys.balances.list(1));
    expect(queryKeys.positions.detail("1", "7")).toEqual(
      queryKeys.positions.detail(1, 7),
    );
  });

  it("normalizes symbol filters inside history params", () => {
    expect(
      queryKeys.marketHistory.series("1", {
        range: "3mo",
        symbols: ["MSFT", "AAPL", "MSFT"],
      }),
    ).toEqual(
      queryKeys.marketHistory.series(1, {
        range: "3mo",
        symbols: ["AAPL", "MSFT"],
      }),
    );
  });

  it("normalizes position lookup symbols inside query keys", () => {
    expect(queryKeys.positions.lookup("1", " aapl ")).toEqual(
      queryKeys.positions.lookup(1, "AAPL"),
    );
  });

  it("keeps existing v1 query key shapes stable", () => {
    expect(queryKeys.portfolios.list()).toEqual(["api", "portfolios", "list"]);
    expect(queryKeys.reports.list()).toEqual(["api", "reports", "list"]);
  });

  it("adds an isolated unversioned platform namespace", () => {
    expect(queryKeys.platform.agents.detail("7")).toEqual(queryKeys.platform.agents.detail(7));
    expect(queryKeys.platform.agents.list({ status: "published" })).toEqual([
      "api",
      "platform",
      "agents",
      "list",
      { status: "published" },
    ]);

    expect(queryKeys.platform.capabilities.detail("7")).toEqual(queryKeys.platform.capabilities.detail(7));
    expect(queryKeys.platform.capabilities.list({ status: "published" })).toEqual([
      "api",
      "platform",
      "capabilities",
      "list",
      { status: "published" },
    ]);

    expect(queryKeys.platform.workflows.detail("9", 2)).toEqual(
      queryKeys.platform.workflows.detail(9, 2),
    );
    expect(queryKeys.platform.workflows.detail(9, 2)).toEqual([
      "api",
      "platform",
      "workflows",
      "detail",
      "9",
      { version: 2 },
    ]);

    expect(
      queryKeys.platform.runs.list({
        offset: 0,
        status: "succeeded",
        targetKey: " report_lookup_reference ",
        targetKind: "workflow",
      }),
    ).toEqual([
      "api",
      "platform",
      "runs",
      "list",
      {
        offset: 0,
        status: "succeeded",
        targetKey: "report_lookup_reference",
        targetKind: "workflow",
      },
    ]);
    expect(queryKeys.platform.workflows.launch("9", 2)).toEqual(
      queryKeys.platform.workflows.launch(9, 2),
    );
    expect(queryKeys.platform.workflows.launch(9, 2)).toEqual([
      "api",
      "platform",
      "workflows",
      "launch",
      "9",
      { version: 2 },
    ]);
    expect(queryKeys.platform.workflows.versions("9")).toEqual(queryKeys.platform.workflows.versions(9));
    expect(queryKeys.platform.workflows.versions(9)).toEqual([
      "api",
      "platform",
      "workflows",
      "versions",
      "9",
    ]);

    expect(queryKeys.platform.runs.rerunDraft("42")).toEqual(
      queryKeys.platform.runs.rerunDraft(42),
    );
    expect(queryKeys.platform.runs.rerunDraft(42)).toEqual([
      "api",
      "platform",
      "runs",
      "rerunDraft",
      "42",
    ]);
    expect(queryKeys.platform.runs.stepReplayDraft("42", 2)).toEqual(
      queryKeys.platform.runs.stepReplayDraft(42, 2),
    );
    expect(queryKeys.platform.runs.stepReplayDraft(42, 2)).toEqual([
      "api",
      "platform",
      "runs",
      "stepReplayDraft",
      "42",
      { stepIndex: 2 },
    ]);
  });

  it("keeps platform keys separate from preserved v1 resources", () => {
    expect(queryKeys.platform.runs.detail(42)).not.toEqual(queryKeys.reports.detail(42));
    expect(queryKeys.platform.agents.all).not.toEqual(queryKeys.portfolios.all);
    expect(queryKeys.platform.runs.all).not.toEqual(queryKeys.templates.all);
    expect(queryKeys.platform.capabilities.tools()).toEqual([
      "api",
      "platform",
      "capabilities",
      "tools",
    ]);
    expect(queryKeys.platform.capabilities.tools()).not.toEqual(queryKeys.platform.capabilities.list());
  });
});
