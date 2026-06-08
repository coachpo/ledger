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
    expect(queryKeys.platform.workflowPackages.list()).toEqual([
      "api",
      "platform",
      "workflowPackages",
      "list",
    ]);
    expect(queryKeys.platform.workflowPackages.manifest("9")).toEqual(
      queryKeys.platform.workflowPackages.manifest(9),
    );
    expect(queryKeys.platform.workflowPackages.launch("9", " review ")).toEqual(
      queryKeys.platform.workflowPackages.launch(9, "review"),
    );
    expect(queryKeys.platform.workflowPackages.launch(9, "review")).toEqual([
      "api",
      "platform",
      "workflowPackages",
      "launch",
      "9",
      { workflowKey: "review" },
    ]);
    expect(queryKeys.platform.workflowPackages.preflight(9)).toEqual([
      "api",
      "platform",
      "workflowPackages",
      "preflight",
      "9",
    ]);
    expect(queryKeys.platform.workflowPackages.launches()).toEqual([
      "api",
      "platform",
      "workflowPackages",
      "launch",
    ]);
    expect(queryKeys.platform.workflowPackages.preflights()).toEqual([
      "api",
      "platform",
      "workflowPackages",
      "preflight",
    ]);
    expect(queryKeys.platform.workflowPackages.runtimeInputRegistry("9", " review ")).toEqual(
      queryKeys.platform.workflowPackages.runtimeInputRegistry(9, "review"),
    );
    expect(queryKeys.platform.workflowPackages.runtimeInputRegistry(9, "review")).toEqual([
      "api",
      "platform",
      "workflowPackages",
      "runtimeInputRegistry",
      "9",
      { workflowKey: "review" },
    ]);
    expect(queryKeys.platform.workflowPackages.runtimeInputRegistryScope(9)).toEqual([
      "api",
      "platform",
      "workflowPackages",
      "runtimeInputRegistry",
      "9",
    ]);
  });

  it("keeps package-first platform keys separate from removed authoring namespaces", () => {
    expect(queryKeys.platform.modelConnections.detail("7")).toEqual(
      queryKeys.platform.modelConnections.detail(7),
    );
    expect(queryKeys.platform.runs.detail(42)).not.toEqual(queryKeys.reports.detail(42));
    expect(queryKeys.platform.workflowPackages.all).not.toEqual(queryKeys.portfolios.all);
    expect(queryKeys.platform.extensions.detail("signaldeck.finance")).toEqual([
      "api",
      "platform",
      "extensions",
      "detail",
      "signaldeck.finance",
    ]);

    expect(queryKeys.platform.memory.detail("memory_1")).toEqual([
      "api",
      "platform",
      "memory",
      "detail",
      "memory_1",
    ]);
    expect(
      queryKeys.platform.memory.list({
        scope: { scopeKey: "42", scopeType: "run" },
        visibility: "explicit-scope",
      }),
    ).toEqual([
      "api",
      "platform",
      "memory",
      "list",
      { scope: { scopeKey: "42", scopeType: "run" }, visibility: "explicit-scope" },
    ]);

    expect(Object.keys(queryKeys.platform)).toEqual([
      "all",
      "memory",
      "modelConnections",
      "extensions",
      "tools",
      "schedules",
      "runs",
      "workflowPackages",
    ]);
  });

  it("normalizes schedule list and fire-history filters", () => {
    expect(queryKeys.platform.schedules.detail("44")).toEqual(
      queryKeys.platform.schedules.detail(44),
    );
    expect(queryKeys.platform.schedules.lists()).toEqual([
      "api",
      "platform",
      "schedules",
      "list",
    ]);
    expect(
      queryKeys.platform.schedules.list({
        offset: 0,
        packageKey: " research_package ",
        status: "enabled",
        workflowKey: " daily_research ",
      }),
    ).toEqual([
      "api",
      "platform",
      "schedules",
      "list",
      {
        offset: 0,
        packageKey: "research_package",
        status: "enabled",
        workflowKey: "daily_research",
      },
    ]);
    expect(queryKeys.platform.schedules.fires("44", { limit: 50 })).toEqual(
      queryKeys.platform.schedules.fires(44, { limit: 50 }),
    );
    expect(queryKeys.platform.schedules.firesScope(44)).toEqual([
      "api",
      "platform",
      "schedules",
      "fires",
      "44",
    ]);
  });

  it("normalizes package run filters", () => {
    expect(queryKeys.platform.runs.lists()).toEqual([
      "api",
      "platform",
      "runs",
      "list",
    ]);
    expect(queryKeys.platform.runs.rerunDrafts()).toEqual([
      "api",
      "platform",
      "runs",
      "rerunDraft",
    ]);
    expect(queryKeys.platform.runs.forkDrafts()).toEqual([
      "api",
      "platform",
      "runs",
      "forkDraft",
    ]);
    expect(
      queryKeys.platform.runs.list({
        offset: 0,
        status: "succeeded",
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
        workflowKey: "summarize",
        workflowPackageKey: "research_package",
      },
    ]);
  });
});
