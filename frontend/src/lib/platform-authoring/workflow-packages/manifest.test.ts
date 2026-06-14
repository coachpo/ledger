import { describe, expect, it } from "vitest";

import {
  createPackageAgentDraft,
  createPackageCapabilityProfileDraft,
  createPackageMcpServerDraft,
  createPackageOutputSchemaDraft,
  createWorkflowPackageDraft,
  diagnosticToEditorTarget,
  packageDraftFromManifestSource,
  validateWorkflowPackageDraft,
  workflowPackageDraftToManifestObject,
  workflowPackageDraftToManifestSource,
} from "./manifest";

describe("workflow package manifest helpers", () => {
  it("roundtrips package-local resources and inline private MCP maps without synthetic binding refs", () => {
    const draft = createWorkflowPackageDraft({
      metadata: { description: "Package", key: "research_package", name: "Research Package" },
    });
    draft.spec.outputSchemas = [createPackageOutputSchemaDraft({ key: "summary_schema", name: "Summary" })];
    draft.spec.capabilityProfiles = [createPackageCapabilityProfileDraft({ key: "research_tools", name: "Research tools", toolKeys: ["signaldeck.finance.reports.lookup"] })];
    draft.spec.mcpServers = [
      createPackageMcpServerDraft({
        argsText: '["--api-key", "${MARKET_DATA_API_KEY}"]',
        command: "market-mcp",
        env: { MARKET_DATA_API_KEY: "${MARKET_DATA_API_KEY}" },
        key: "market-mcp",
        name: "Market MCP",
      }),
      createPackageMcpServerDraft({
        headers: { Authorization: "Bearer ${MARKET_DATA_API_KEY}" },
        key: "market-http",
        name: "Market HTTP MCP",
        query: { apiKey: "${MARKET_DATA_API_KEY}" },
        transport: "http-sse",
        url: "https://example.com/mcp",
      }),
    ];
    draft.spec.agents = [createPackageAgentDraft({ capabilityProfiles: ["research_tools"], key: "analyst", mcpServers: ["market-mcp", "market-http"], modelConnection: "primary_model", name: "Analyst", outputSchema: "summary_schema" })];

    const source = workflowPackageDraftToManifestSource(draft);
    const object = workflowPackageDraftToManifestObject(draft) as {
      spec: {
        mcpServers: Array<Record<string, unknown>>;
      };
    };
    const parsed = packageDraftFromManifestSource(source);

    expect(source).toContain("env:");
    expect(source).toContain("headers:");
    expect(source).toContain("query:");
    expect(source).toContain("MARKET_DATA_API_KEY: ${MARKET_DATA_API_KEY}");
    expect(source).toContain("Authorization: Bearer ${MARKET_DATA_API_KEY}");
    expect(source).toContain("apiKey: ${MARKET_DATA_API_KEY}");

    expect(object.spec.mcpServers).toEqual([
      {
        args: ["--api-key", "${MARKET_DATA_API_KEY}"],
        command: "market-mcp",
        description: "",
        env: { MARKET_DATA_API_KEY: "${MARKET_DATA_API_KEY}" },
        key: "market-mcp",
        name: "Market MCP",
        toolKeys: [],
        transport: "stdio",
      },
      {
        description: "",
        headers: { Authorization: "Bearer ${MARKET_DATA_API_KEY}" },
        key: "market-http",
        name: "Market HTTP MCP",
        query: { apiKey: "${MARKET_DATA_API_KEY}" },
        toolKeys: [],
        transport: "http-sse",
        url: "https://example.com/mcp",
      },
    ]);

    expect(parsed.errors).toEqual([]);
    expect(parsed.draft.spec.agents[0]).toMatchObject({ key: "analyst", outputSchema: "summary_schema" });
    expect(parsed.draft.spec.mcpServers).toMatchObject([
      { env: { MARKET_DATA_API_KEY: "${MARKET_DATA_API_KEY}" }, key: "market-mcp", transport: "stdio" },
      { headers: { Authorization: "Bearer ${MARKET_DATA_API_KEY}" }, key: "market-http", query: { apiKey: "${MARKET_DATA_API_KEY}" }, transport: "http-sse" },
    ]);
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
    expect(diagnosticToEditorTarget("spec.mcpServers[0].env.MARKET_DATA_API_KEY")).toEqual({ field: "spec.mcpServers[0].env.MARKET_DATA_API_KEY", tab: "private-mcp" });
  });
});
