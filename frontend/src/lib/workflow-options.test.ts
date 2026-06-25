import { describe, expect, it } from "vitest";
import { getWorkflowOptions } from "./workflow-options";
import type { WorkflowPackageManifestRead } from "./types/workflow-package";

function buildManifest(overrides: Partial<WorkflowPackageManifestRead> = {}): WorkflowPackageManifestRead {
  return {
    packageId: 1,
    packageKey: "trading_package",
    manifestSource: "manifest-yaml",
    packageDefinition: {
      spec: {
        workflows: [],
      },
    },
    manifestHash: "manifest-hash",
    compiledHash: "compiled-hash",
    ...overrides,
  };
}

describe("getWorkflowOptions", () => {
  it("preserves manifest order and maps workflow fields to options", () => {
    const manifest = buildManifest({
      packageDefinition: {
        spec: {
          workflows: [
            {
              description: "First workflow",
              inputSchema: { type: "object" },
              key: "first",
              label: "First label",
            },
            {
              description: "Second workflow",
              inputSchema: { type: "object", properties: { amount: { type: "number" } } },
              key: "second",
              name: "Second name",
            },
          ],
        },
      },
    });

    expect(getWorkflowOptions(manifest)).toEqual([
      {
        description: "First workflow",
        inputSchema: { type: "object" },
        key: "first",
        label: "First label",
      },
      {
        description: "Second workflow",
        inputSchema: { type: "object", properties: { amount: { type: "number" } } },
        key: "second",
        label: "Second name",
      },
    ]);
  });

  it("appends a visible stale option for the selected workflow key", () => {
    const manifest = buildManifest({
      packageDefinition: {
        spec: {
          workflows: [
            {
              description: "Known workflow",
              inputSchema: { type: "object" },
              key: "known",
              name: "Known workflow",
            },
          ],
        },
      },
    });

    expect(getWorkflowOptions(manifest, "stale-key")).toEqual([
      {
        description: "Known workflow",
        inputSchema: { type: "object" },
        key: "known",
        label: "Known workflow",
      },
      {
        description: "Missing manifest workflow",
        inputSchema: {},
        key: "stale-key",
        label: "Unknown workflow: stale-key",
      },
    ]);
  });
});
