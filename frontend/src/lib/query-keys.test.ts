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

  it("adds workflow package keys under the platform namespace", () => {
    expect(queryKeys.platform.workflowPackages.detail("7")).toEqual(
      queryKeys.platform.workflowPackages.detail(7),
    );
    expect(queryKeys.platform.workflowPackages.list({ status: "active" })).toEqual([
      "api",
      "platform",
      "workflowPackages",
      "list",
      { status: "active" },
    ]);
    expect(queryKeys.platform.workflowPackages.versions("9")).toEqual(
      queryKeys.platform.workflowPackages.versions(9),
    );
    expect(queryKeys.platform.workflowPackages.versions(9)).toEqual([
      "api",
      "platform",
      "workflowPackages",
      "versions",
      "9",
    ]);
    expect(queryKeys.platform.workflowPackages.launch("9", "2", " review ")).toEqual(
      queryKeys.platform.workflowPackages.launch(9, 2, "review"),
    );
    expect(queryKeys.platform.workflowPackages.launch(9, 2, "review")).toEqual([
      "api",
      "platform",
      "workflowPackages",
      "launch",
      "9",
      { version: 2, workflowKey: "review" },
    ]);
    expect(queryKeys.platform.workflowPackages.preflight(9, 2)).toEqual([
      "api",
      "platform",
      "workflowPackages",
      "preflight",
      "9",
      { version: 2 },
    ]);
  });

  it("keeps package-first platform keys separate from removed authoring namespaces", () => {
    expect(queryKeys.platform.modelConnections.detail("7")).toEqual(
      queryKeys.platform.modelConnections.detail(7),
    );
    expect(queryKeys.platform.runs.detail(42)).not.toEqual(queryKeys.reports.detail(42));
    expect(queryKeys.platform.workflowPackages.all).not.toEqual(queryKeys.portfolios.all);
    expect(queryKeys.platform.extensions.detail("ledger.finance")).toEqual([
      "api",
      "platform",
      "extensions",
      "detail",
      "ledger.finance",
    ]);

    expect(Object.keys(queryKeys.platform)).toEqual([
      "all",
      "modelConnections",
      "extensions",
      "tools",
      "runs",
      "workflowPackages",
    ]);
    expect(Reflect.has(queryKeys.platform, "agents")).toBe(false);
    expect(Reflect.has(queryKeys.platform, "capabilities")).toBe(false);
    expect(Reflect.has(queryKeys.platform, "mcpServers")).toBe(false);
    expect(Reflect.has(queryKeys.platform, "outputSchemas")).toBe(false);
    expect(Reflect.has(queryKeys.platform, "workflows")).toBe(false);
  });

  it("normalizes package run filters", () => {
    expect(
      queryKeys.platform.runs.list({
        offset: 0,
        status: "succeeded",
        targetKind: "workflowPackage",
        workflowKey: " summarize ",
        workflowPackageKey: " research_package ",
      }),
    ).toEqual([
      "api",
      "platform",
      "runs",
      "list",
      {
        offset: 0,
        status: "succeeded",
        targetKind: "workflowPackage",
        workflowKey: "summarize",
        workflowPackageKey: "research_package",
      },
    ]);
  });
});
