import { describe, expect, it } from "vitest";

import {
  RUN_DETAIL_TAB_LABELS,
  RUN_DETAIL_TAB_ORDER,
  inferRunDetailTabFromUrlHints,
  parseRunDetailTab,
  resolveRunDetailTab,
  withRunDetailTab,
} from "./detail-tabs";

describe("run detail tab contract", () => {
  it("keeps a stable tab order", () => {
    expect(RUN_DETAIL_TAB_ORDER).toEqual([
      "output",
      "execution",
      "overview",
      "input",
      "runtime",
      "usage",
      "memory",
      "lineage",
    ]);
  });

  it("keeps stable labels", () => {
    expect(RUN_DETAIL_TAB_LABELS).toEqual({
      output: "Output",
      execution: "Execution",
      overview: "Overview",
      input: "Input",
      runtime: "Runtime",
      usage: "Usage",
      memory: "Memory",
      lineage: "Lineage",
    });
  });

  it("parses only explicit top-level tab keys", () => {
    expect(parseRunDetailTab("overview")).toBe("overview");
    expect(parseRunDetailTab("execution")).toBe("execution");
    expect(parseRunDetailTab("output")).toBe("output");
    expect(parseRunDetailTab("input")).toBe("input");
    expect(parseRunDetailTab("runtime")).toBe("runtime");
    expect(parseRunDetailTab("usage")).toBe("usage");
    expect(parseRunDetailTab("memory")).toBe("memory");
    expect(parseRunDetailTab("lineage")).toBe("lineage");
    expect(parseRunDetailTab("summary")).toBeNull();
    expect(parseRunDetailTab("audit")).toBeNull();
    expect(parseRunDetailTab("diagnostics")).toBeNull();
    expect(parseRunDetailTab("outputs")).toBeNull();
    expect(parseRunDetailTab("inputs")).toBeNull();
    expect(parseRunDetailTab("tokens")).toBeNull();
    expect(parseRunDetailTab("unknown")).toBeNull();
  });

  it("prefers a valid raw tab over all other hints", () => {
    expect(
      resolveRunDetailTab({
        rawTab: "memory",
        rawMode: "summary",
        rawPane: "error",
        rawInspect: "step:1",
        rawHash: "#invocation-9",
      }),
    ).toBe("memory");
  });

  it("falls back from an invalid raw tab to hint inference", () => {
    expect(
      resolveRunDetailTab({
        rawTab: "not-a-tab",
        rawMode: "audit",
        rawPane: null,
        rawInspect: null,
        rawHash: null,
      }),
    ).toBe("overview");
  });

  it("returns null when no supported raw hints exist", () => {
    expect(
      inferRunDetailTabFromUrlHints({
        rawMode: null,
        rawPane: null,
        rawInspect: null,
        rawHash: null,
      }),
    ).toBeNull();
  });

  it("infers execution from inspect-only step, invocation, and operation targets", () => {
    expect(
      inferRunDetailTabFromUrlHints({
        rawMode: null,
        rawPane: null,
        rawInspect: "step:1",
        rawHash: null,
      }),
    ).toBe("execution");

    expect(
      inferRunDetailTabFromUrlHints({
        rawMode: null,
        rawPane: null,
        rawInspect: "invocation:1001",
        rawHash: null,
      }),
    ).toBe("execution");

    expect(
      inferRunDetailTabFromUrlHints({
        rawMode: null,
        rawPane: null,
        rawInspect: "operation:2001",
        rawHash: null,
      }),
    ).toBe("execution");
  });

  it("infers the tab from raw url hints only when present", () => {
    expect(
      inferRunDetailTabFromUrlHints({
        rawMode: "summary",
        rawPane: null,
        rawInspect: null,
        rawHash: null,
      }),
    ).toBe("overview");

    expect(
      inferRunDetailTabFromUrlHints({
        rawMode: "diagnostics",
        rawPane: null,
        rawInspect: null,
        rawHash: null,
      }),
    ).toBe("execution");

    expect(
      inferRunDetailTabFromUrlHints({
        rawMode: null,
        rawPane: "error",
        rawInspect: "step:1",
        rawHash: null,
      }),
    ).toBe("execution");

    expect(
      inferRunDetailTabFromUrlHints({
        rawMode: null,
        rawPane: "finalOutput",
        rawInspect: "run",
        rawHash: null,
      }),
    ).toBe("output");

    expect(
      inferRunDetailTabFromUrlHints({
        rawMode: null,
        rawPane: "details",
        rawInspect: "memory:abc",
        rawHash: null,
      }),
    ).toBeNull();

    expect(
      inferRunDetailTabFromUrlHints({
        rawMode: "tokens",
        rawPane: null,
        rawInspect: null,
        rawHash: null,
      }),
    ).toBe("usage");
  });

  it("ignores unsupported hashes for top-level tab inference", () => {
    expect(
      inferRunDetailTabFromUrlHints({
        rawMode: null,
        rawPane: null,
        rawInspect: null,
        rawHash: "#memory-abc",
      }),
    ).toBeNull();

    expect(
      inferRunDetailTabFromUrlHints({
        rawMode: null,
        rawPane: null,
        rawInspect: null,
        rawHash: "#run-context",
      }),
    ).toBeNull();
  });

  it("preserves unrelated query params when switching tabs", () => {
    const current = new URLSearchParams("foo=bar&tab=overview&pane=error&mode=summary");
    const next = withRunDetailTab(current, "lineage");

    expect(next.toString()).toBe("foo=bar&tab=lineage&pane=error&mode=summary");
    expect(current.toString()).toBe("foo=bar&tab=overview&pane=error&mode=summary");
  });
});
