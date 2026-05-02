import { describe, expect, it } from "vitest";

import {
  createAgentManifestScaffold,
  extractAgentManifestOutline,
  formatAgentManifestYaml,
  locateAgentManifestPath,
  mapAgentManifestDiagnosticsForEditor,
  parseAgentManifestLocallyForEditor,
} from "./manifest";

const AGENT_MANIFEST_SOURCE_MAX_LENGTH = 262_144;

const fullAgentManifest = `apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: macro_agent
  name: Macro Agent
  description: Tracks macro context.
spec:
  modelConnection: primary_openai
  systemPrompt: Analyze carefully.
  inputSchema:
    type: object
    properties:
      ticker:
        type: string
    required:
      - ticker
    additionalProperties: false
  outputSchema: summary_schema@5
  capabilities:
    - summarize_capability@3
    - filings_capability@2
  mcpServers:
    - quotes-mcp@2
  budgetUsd: "2.50"
`;

describe("agent manifest helpers", () => {
  it("creates starter YAML that the local editor parser can read", () => {
    const source = createAgentManifestScaffold({
      key: "ticker_agent",
      modelConnection: "primary_openai",
      name: "Ticker Agent",
      outputSchema: "summary_schema@1",
    });

    const parsed = parseAgentManifestLocallyForEditor(source);
    const outline = extractAgentManifestOutline(source);

    expect(parsed.diagnostics).toEqual([]);
    expect(parsed.value).toMatchObject({
      apiVersion: "ledger.agent/v1",
      kind: "Agent",
      metadata: {
        key: "ticker_agent",
        name: "Ticker Agent",
      },
      spec: {
        modelConnection: "primary_openai",
        outputSchema: "summary_schema@1",
      },
    });
    expect(outline.diagnostics).toEqual([]);
    expect(outline.outline.refs.map((ref) => [ref.kind, ref.ref])).toEqual([
      ["modelConnection", "primary_openai"],
      ["outputSchema", "summary_schema@1"],
    ]);
  });

  it("extracts sections and ordered refs from a complete agent manifest", () => {
    const result = extractAgentManifestOutline(fullAgentManifest);

    expect(result.diagnostics).toEqual([]);
    expect(result.outline.sections.map((section) => [section.id, section.present])).toEqual([
      ["apiVersion", true],
      ["kind", true],
      ["metadata", true],
      ["spec", true],
    ]);
    expect(result.outline.sections[0]?.line).toBe(1);
    expect(result.outline.sections.map((section) => [section.id, section.path, section.line])).toEqual([
      ["apiVersion", "apiVersion", 1],
      ["kind", "kind", 2],
      ["metadata", "metadata", 3],
      ["spec", "spec", 7],
    ]);
    expect(result.outline.refs.map((ref) => [ref.kind, ref.path, ref.ref])).toEqual([
      ["modelConnection", "spec.modelConnection", "primary_openai"],
      ["outputSchema", "spec.outputSchema", "summary_schema@5"],
      ["capability", "spec.capabilities[0]", "summarize_capability@3"],
      ["capability", "spec.capabilities[1]", "filings_capability@2"],
      ["mcpServer", "spec.mcpServers[0]", "quotes-mcp@2"],
    ]);
    expect(result.outline.refs.every((ref) => ref.line !== null)).toBe(true);
  });

  it("rejects legacy spec.skills instead of exposing compatibility refs", () => {
    const legacyManifest = fullAgentManifest.replace(
      "capabilities:\n    - summarize_capability@3\n    - filings_capability@2",
      "skills:\n    - summarize_skill@3",
    );

    const parsed = parseAgentManifestLocallyForEditor(legacyManifest);
    const outline = extractAgentManifestOutline(legacyManifest);

    expect(parsed.isValidYaml).toBe(false);
    expect(parsed.value).toBeNull();
    expect(parsed.diagnostics).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          message: "Use spec.capabilities; legacy spec.skills is not supported",
          origin: "local",
          path: "spec.skills",
          severity: "error",
        }),
      ]),
    );
    expect(outline.outline.refs).toEqual([]);
  });

  it("rejects manifests that mix spec.capabilities with legacy spec.skills", () => {
    const mixedManifest = fullAgentManifest.replace(
      "  mcpServers:",
      "  skills:\n    - summarize_skill@3\n  mcpServers:",
    );

    const parsed = parseAgentManifestLocallyForEditor(mixedManifest);

    expect(parsed.isValidYaml).toBe(false);
    expect(parsed.diagnostics).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          path: "spec.skills",
          severity: "error",
        }),
      ]),
    );
  });

  it("returns lightweight local diagnostics for malformed YAML without claiming backend authority", () => {
    const result = parseAgentManifestLocallyForEditor(`apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: [broken
`);

    expect(result.value).toBeNull();
    expect(result.isValidYaml).toBe(false);
    expect(result.diagnostics).toHaveLength(1);
    expect(result.diagnostics[0]).toMatchObject({
      origin: "local",
      path: "$",
      severity: "error",
    });
    expect(result.diagnostics[0]?.line).toEqual(expect.any(Number));
    expect(result.diagnostics[0]?.column).toEqual(expect.any(Number));
    expect(result.diagnostics[0]?.message).toContain("Malformed YAML");
  });

  it("diagnoses unsupported YAML features and raw model connection ids", () => {
    const result = parseAgentManifestLocallyForEditor(`apiVersion: ledger.agent/v1
kind: Agent
metadata: &agent_metadata
  key: macro_agent
  name: Macro Agent
spec:
  modelConnectionId: 44
  modelConnection: primary_openai
  systemPrompt: !secret Analyze carefully.
  inputSchema:
    type: object
  outputSchema: summary_schema@5
  capabilities:
    - &capability summarize_capability@3
    - *capability
  <<: {}
`);

    expect(result.isValidYaml).toBe(false);
    expect(result.diagnostics.map((diagnostic) => diagnostic.message)).toEqual(
      expect.arrayContaining([
        expect.stringContaining("YAML anchors are not supported"),
        expect.stringContaining("YAML aliases are not supported"),
        expect.stringContaining("YAML merge keys are not supported"),
        expect.stringContaining("raw modelConnectionId is not supported"),
      ]),
    );
    expect(result.diagnostics.some((diagnostic) => diagnostic.message.includes("YAML tag"))).toBe(true);
    expect(result.diagnostics).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          message: expect.stringContaining("raw modelConnectionId is not supported"),
          path: "spec.modelConnectionId",
        }),
      ]),
    );
  });

  it("short-circuits oversized sources before parsing and returns local diagnostics", () => {
    const oversizedSource = `${"a".repeat(AGENT_MANIFEST_SOURCE_MAX_LENGTH + 1)}`;

    const parsed = parseAgentManifestLocallyForEditor(oversizedSource);
    const outline = extractAgentManifestOutline(oversizedSource);
    const formatted = formatAgentManifestYaml(oversizedSource);

    expect(parsed).toMatchObject({
      isValidYaml: false,
      value: null,
    });
    expect(parsed.diagnostics).toHaveLength(1);
    expect(parsed.diagnostics[0]).toMatchObject({
      origin: "local",
      path: "$",
      severity: "error",
      line: null,
      column: null,
    });
    expect(parsed.diagnostics[0]?.message).toContain("at most 262144 characters");

    expect(outline.diagnostics).toHaveLength(1);
    expect(outline.outline.sections).toHaveLength(4);
    expect(outline.outline.sections.every((section) => section.present === false)).toBe(true);
    expect(outline.outline.refs).toEqual([]);

    expect(formatted.formatted).toBeNull();
    expect(formatted.diagnostics[0]).toMatchObject({ origin: "local", severity: "error" });
  });

  it("maps backend diagnostics to editor panel items and fills line numbers from manifest paths", () => {
    const diagnostics = mapAgentManifestDiagnosticsForEditor(
      [
        {
          column: null,
          line: null,
          message: "Capability version was not found.",
          path: "spec.capabilities[1]",
          severity: "error",
        },
      ],
      { manifestSource: fullAgentManifest, origin: "backend" },
    );

    expect(diagnostics).toHaveLength(1);
    expect(diagnostics[0]).toMatchObject({
      canJump: true,
      locationLabel: expect.stringContaining("Line"),
      origin: "backend",
      path: "spec.capabilities[1]",
    });
    expect(diagnostics[0]?.line).toBeGreaterThan(0);
    expect(diagnostics[0]?.column).toBeGreaterThan(0);
  });

  it("locates manifest paths for section and ref diagnostics and leaves malformed sources non-actionable", () => {
    expect(locateAgentManifestPath(fullAgentManifest, "metadata")).toMatchObject({
      column: 3,
      line: 4,
    });
    expect(locateAgentManifestPath(fullAgentManifest, "spec.modelConnection")).toMatchObject({
      column: 20,
      line: 8,
    });

    const diagnostics = mapAgentManifestDiagnosticsForEditor(
      [
        {
          column: null,
          line: null,
          message: "Metadata has a backend issue.",
          path: "metadata",
          severity: "error",
        },
        {
          column: null,
          line: null,
          message: "Unknown path cannot be located.",
          path: "spec.notThere[4]",
          severity: "error",
        },
      ],
      { manifestSource: fullAgentManifest, origin: "backend" },
    );

    expect(diagnostics[0]).toMatchObject({ canJump: true, line: 4, path: "metadata" });
    expect(diagnostics[1]).toMatchObject({ canJump: true, line: 8, path: "spec.notThere[4]" });

    const malformedDiagnostics = mapAgentManifestDiagnosticsForEditor(
      [
        {
          column: null,
          line: null,
          message: "Cannot locate inside malformed YAML.",
          path: "spec.outputSchema",
          severity: "error",
        },
      ],
      { manifestSource: "apiVersion: [broken", origin: "backend" },
    );

    expect(malformedDiagnostics[0]).toMatchObject({ canJump: false, line: null });
  });

  it("formats valid YAML into stable manifest order and returns diagnostics for invalid YAML", () => {
    const result = formatAgentManifestYaml(`kind: Agent
apiVersion: ledger.agent/v1
spec:
  budgetUsd: "2.50"
  mcpServers: [quotes-mcp@2]
  capabilities: [summarize_capability@3]
  outputSchema: summary_schema@5
  inputSchema:
    description: Inputs for macro analysis runs.
    required: [ticker]
    additionalProperties: false
    title: Macro Agent Input
    properties:
      ticker:
        description: Symbol to analyze.
        title: Ticker Symbol
        type: string
    type: object
  systemPrompt: Analyze carefully.
  modelConnection: primary_openai
metadata:
  name: Macro Agent
  description: Tracks macro context.
  key: macro_agent
`);

    expect(result.diagnostics).toEqual([]);
    expect(result.formatted).toBe(`apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: macro_agent
  name: Macro Agent
  description: Tracks macro context.
spec:
  modelConnection: primary_openai
  systemPrompt: Analyze carefully.
  inputSchema:
    type: object
    title: Macro Agent Input
    description: Inputs for macro analysis runs.
    properties:
      ticker:
        type: string
        title: Ticker Symbol
        description: Symbol to analyze.
    required:
      - ticker
    additionalProperties: false
  outputSchema: summary_schema@5
  capabilities:
    - summarize_capability@3
  mcpServers:
    - quotes-mcp@2
  budgetUsd: "2.50"
`);

    const invalid = formatAgentManifestYaml("apiVersion: [broken");

    expect(invalid.formatted).toBeNull();
    expect(invalid.diagnostics[0]).toMatchObject({ origin: "local", severity: "error" });
  });
});
