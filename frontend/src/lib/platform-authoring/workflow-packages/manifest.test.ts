import { describe, expect, it } from "vitest";

import {
  createPackageAgentDraft,
  createPackageCapabilityProfileDraft,
  createPackageMcpServerDraft,
  createPackageOutputSchemaDraft,
  createWorkflowPackageDraft,
  diagnosticToEditorTarget,
  packageDraftFromManifestSource,
  previewContainsSecretValue,
  validateWorkflowPackageDraft,
  workflowPackageDraftToManifestObject,
  workflowPackageDraftToManifestSource,
} from "./manifest";

describe("workflow package manifest helpers", () => {
  it("roundtrips package-local resources without database ids or secret values", () => {
    const draft = createWorkflowPackageDraft({
      metadata: { description: "Package", key: "research_package", name: "Research Package" },
    });
    draft.spec.outputSchemas = [createPackageOutputSchemaDraft({ key: "summary_schema", name: "Summary" })];
    draft.spec.capabilityProfiles = [createPackageCapabilityProfileDraft({ key: "research_tools", name: "Research tools", toolKeys: ["ledger.reports.lookup"] })];
    draft.spec.mcpServers = [createPackageMcpServerDraft({ argsText: '["--api-key", "${MARKET_DATA_API_KEY}"]', command: "market-mcp", key: "market-mcp", name: "Market MCP", requiredBindings: ["MARKET_DATA_API_KEY"] })];
    draft.spec.agents = [createPackageAgentDraft({ capabilityProfiles: ["research_tools"], key: "analyst", mcpServers: ["market-mcp"], modelConnection: "primary_model", name: "Analyst", outputSchema: "summary_schema" })];

    const source = workflowPackageDraftToManifestSource(draft);
    const object = workflowPackageDraftToManifestObject(draft);
    const parsed = packageDraftFromManifestSource(source);

    expect(parsed.errors).toEqual([]);
    expect(parsed.draft.spec.agents[0]).toMatchObject({ key: "analyst", outputSchema: "summary_schema" });
    expect(JSON.stringify(object)).not.toContain("modelConnectionId");
    expect(JSON.stringify(object)).not.toContain("apiKey");
    expect(JSON.stringify(object)).not.toContain("secretPayload");
    expect(JSON.stringify(object)).toContain("MARKET_DATA_API_KEY_SECRET");
  });

  it("validates local references and maps backend diagnostics to resource tabs", () => {
    const draft = createWorkflowPackageDraft();
    draft.spec.agents = [createPackageAgentDraft({ key: "analyst", modelConnection: "primary_model", outputSchema: "missing_schema" })];

    expect(validateWorkflowPackageDraft(draft)).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ field: "spec.agents[0].outputSchema", tab: "agents" }),
      ]),
    );

    expect(diagnosticToEditorTarget("spec.agents[0].modelConnection")).toEqual({ field: "spec.agents[0].modelConnection", tab: "agents" });
    expect(diagnosticToEditorTarget("spec.outputSchemas[0]")).toEqual({ field: "spec.outputSchemas[0]", tab: "output-schemas" });
    expect(diagnosticToEditorTarget("spec.capabilityProfiles.research.toolKeys[0]")).toEqual({ field: "spec.capabilityProfiles.research.toolKeys[0]", tab: "capability-profiles" });
    expect(diagnosticToEditorTarget("spec.mcpServers[0].requiredBindings[0]")).toEqual({ field: "spec.mcpServers[0].requiredBindings[0]", tab: "private-mcp" });
  });

  it("detects likely secret values but permits binding placeholders", () => {
    expect(previewContainsSecretValue("apiKey: sk-live-secret")).toBe(true);
    expect(previewContainsSecretValue("secretRefs:\n  apiKey:\n    - MARKET_DATA_API_KEY_SECRET")).toBe(false);
  });
});
