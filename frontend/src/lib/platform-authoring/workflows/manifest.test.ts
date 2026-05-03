import { describe, expect, it } from "vitest";

import {
  createWorkflowManifestScaffold,
  extractWorkflowManifestOutline,
  formatWorkflowManifestYaml,
  mapWorkflowManifestDiagnosticsForEditor,
  parseWorkflowManifestLocallyForEditor,
} from "./manifest";

const WORKFLOW_MANIFEST_SOURCE_MAX_LENGTH = 262_144;

const twoStepManifest = `apiVersion: ledger.workflow/v1
kind: Workflow
metadata:
  key: market_review
  name: Market Review
  description: Runs research before producing the final slot output.
inputSchema:
  type: object
  properties:
    ticker:
      type: string
    horizon_days:
      type: integer
  required:
    - ticker
  additionalProperties: false
steps:
  - id: research
    agents:
      - slot: analysis
        uses: research_agent@7
        with:
          ticker: \${{ inputs.ticker }}
          horizon_days: \${{ inputs.horizon_days }}
      - slot: context
        uses: context_agent@3
        optional: true
        with:
          ticker: \${{ inputs.ticker }}
  - id: decision
    agents:
      - slot: final
        uses: decision_agent@2
        with:
          analysis: \${{ steps.research.outputs.analysis.summary }}
output:
  from: \${{ steps.decision.outputs.final }}
`;

describe("workflow manifest helpers", () => {
  it("creates starter YAML that the local editor parser can read", () => {
    const source = createWorkflowManifestScaffold({
      description: "Screens a ticker before writing an analysis slot.",
      key: "ticker_review",
      name: "Ticker Review",
    });

    const parsed = parseWorkflowManifestLocallyForEditor(source);
    const outline = extractWorkflowManifestOutline(source);

    expect(parsed.diagnostics).toEqual([]);
    expect(parsed.value).toMatchObject({
      apiVersion: "ledger.workflow/v1",
      kind: "Workflow",
      metadata: {
        key: "ticker_review",
        name: "Ticker Review",
      },
    });
    expect(outline.diagnostics).toEqual([]);
    expect(outline.outline.steps).toHaveLength(1);
    expect(outline.outline.steps[0]).toMatchObject({
      id: "research",
      agentSlots: [{ optional: false, slot: "analysis", uses: "research_agent@1" }],
    });
  });

  it("extracts sections, ordered step ids, and ordered agent slots from a two-step manifest", () => {
    const result = extractWorkflowManifestOutline(twoStepManifest);

    expect(result.diagnostics).toEqual([]);
    expect(result.outline.sections.map((section) => [section.id, section.present])).toEqual([
      ["apiVersion", true],
      ["kind", true],
      ["metadata", true],
      ["inputSchema", true],
      ["steps", true],
      ["flow", false],
      ["output", true],
      ["postRunMemory", false],
    ]);
    expect(result.outline.sections[0]?.line).toBe(1);
    expect(result.outline.steps.map((step) => step.id)).toEqual(["research", "decision"]);
    expect(result.outline.steps[0]?.agentSlots.map((agent) => agent.slot)).toEqual(["analysis", "context"]);
    expect(result.outline.steps[0]?.agentSlots[1]).toMatchObject({
      optional: true,
      path: "steps[0].agents[1]",
      uses: "context_agent@3",
    });
  });

  it("accepts v2 flow locally without requiring v1 steps and warns for unbounded loops", () => {
    const source = `apiVersion: ledger.workflow/v2
kind: Workflow
metadata:
  key: graph_review
  name: Graph Review
  description: Browser-previewable v2 workflow.
inputSchema:
  type: object
  properties:
    ticker:
      type: string
flow:
  kind: loop
  id: review_loop
  sequence:
    kind: sequence
    id: review_sequence
    nodes:
      - kind: step
        id: risk_review
        slot: risk
        uses: risk_agent@1
        with:
          ticker: \${{ inputs.ticker }}
output:
  from: \${{ nodes.review_loop.outputs.risk }}
`;

    const parsed = parseWorkflowManifestLocallyForEditor(source);
    const outline = extractWorkflowManifestOutline(source);

    expect(parsed.isValidYaml).toBe(true);
    expect(parsed.diagnostics).toHaveLength(1);
    expect(parsed.diagnostics[0]).toMatchObject({
      origin: "local",
      path: "flow.maxIterations",
      severity: "warning",
    });
    expect(parsed.diagnostics[0]?.message).toContain("maxIterations");
    expect(outline.outline.sections.find((section) => section.id === "flow")).toMatchObject({ present: true });
    expect(outline.outline.sections.find((section) => section.id === "steps")).toMatchObject({ present: false });
    expect(outline.outline.steps[0]).toMatchObject({ id: "risk_review" });
  });

  it("returns lightweight local diagnostics for malformed YAML without claiming backend authority", () => {
    const result = parseWorkflowManifestLocallyForEditor(`apiVersion: ledger.workflow/v1
kind: Workflow
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

  it("short-circuits oversized sources before parsing and returns local diagnostics", () => {
    const oversizedSource = `${"a".repeat(WORKFLOW_MANIFEST_SOURCE_MAX_LENGTH + 1)}`;

    const parsed = parseWorkflowManifestLocallyForEditor(oversizedSource);
    const outline = extractWorkflowManifestOutline(oversizedSource);
    const formatted = formatWorkflowManifestYaml(oversizedSource);

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
    expect(outline.outline.sections).toHaveLength(8);
    expect(outline.outline.sections.every((section) => section.present === false)).toBe(true);
    expect(outline.outline.steps).toEqual([]);
    expect(outline.diagnostics[0]).toMatchObject({
      origin: "local",
      path: "$",
      severity: "error",
      line: null,
      column: null,
    });

    expect(formatted.formatted).toBeNull();
    expect(formatted.diagnostics).toHaveLength(1);
    expect(formatted.diagnostics[0]).toMatchObject({
      origin: "local",
      path: "$",
      severity: "error",
      line: null,
      column: null,
    });
  });

  it("maps backend diagnostics to editor panel items and fills line numbers from manifest paths", () => {
    const diagnostics = mapWorkflowManifestDiagnosticsForEditor(
      [
        {
          column: null,
          line: null,
          message: "Backend validation remains authoritative for saved agents.",
          path: "steps[1].agents[0].uses",
          severity: "error",
        },
      ],
      { manifestSource: twoStepManifest, origin: "backend" },
    );

    expect(diagnostics).toHaveLength(1);
    expect(diagnostics[0]).toMatchObject({
      canJump: true,
      locationLabel: expect.stringContaining("Line"),
      origin: "backend",
      path: "steps[1].agents[0].uses",
    });
    expect(diagnostics[0]?.line).toBeGreaterThan(0);
    expect(diagnostics[0]?.column).toBeGreaterThan(0);
  });

  it("formats valid YAML into stable manifest order and returns diagnostics for invalid YAML", () => {
    const result = formatWorkflowManifestYaml(`kind: Workflow
apiVersion: ledger.workflow/v1
output:
  from: \${{ steps.research.outputs.analysis }}
steps:
  - agents:
      - uses: research_agent@1
        slot: analysis
    id: research
inputSchema:
  description: Inputs used to launch the market review.
  required: [ticker]
  additionalProperties: false
  title: Market Review Input
  properties:
    ticker:
      description: Symbol to research.
      title: Ticker Symbol
      type: string
  type: object
metadata:
  name: Market Review
  description: Runs research.
  key: market_review
`);

    expect(result.diagnostics).toEqual([]);
    expect(result.formatted).toBe(`apiVersion: ledger.workflow/v1
kind: Workflow
metadata:
  key: market_review
  name: Market Review
  description: Runs research.
inputSchema:
  type: object
  title: Market Review Input
  description: Inputs used to launch the market review.
  properties:
    ticker:
      type: string
      title: Ticker Symbol
      description: Symbol to research.
  required:
    - ticker
  additionalProperties: false
steps:
  - id: research
    agents:
      - slot: analysis
        uses: research_agent@1
output:
  from: \${{ steps.research.outputs.analysis }}
`);

    const invalid = formatWorkflowManifestYaml("apiVersion: [broken");

    expect(invalid.formatted).toBeNull();
    expect(invalid.diagnostics[0]).toMatchObject({ origin: "local", severity: "error" });
  });
});
