import { parseDocument, stringify } from "yaml";

import { schemaBuilderToJsonSchema, parseSchemaJsonText } from "../schema/codec";
import { createDefaultSchemaNode } from "../schema/factories";
import type { SchemaIRNode } from "../schema/types";
import type { UnknownRecord } from "@/lib/types/common";
import type { WorkflowPackageManifestDiagnostic } from "@/lib/types/workflow-package";

export type PackageMcpTransport = "stdio" | "http-sse";

export type PackageAgentDraft = {
  budgetUsd: string;
  capabilityProfiles: string[];
  description: string;
  inputSchema: SchemaIRNode;
  key: string;
  mcpServers: string[];
  modelConnection: string;
  name: string;
  outputSchema: string;
  systemPrompt: string;
  timeoutSeconds: string;
};

export type PackageOutputSchemaDraft = {
  description: string;
  jsonSchema: SchemaIRNode;
  key: string;
  name: string;
};

export type PackageCapabilityProfileDraft = {
  description: string;
  key: string;
  name: string;
  toolKeys: string[];
};

export type PackageMcpServerDraft = {
  argsText: string;
  command: string;
  description: string;
  env: Record<string, string>;
  headers: Record<string, string>;
  key: string;
  name: string;
  query: Record<string, string>;
  toolKeys: string[];
  transport: PackageMcpTransport;
  url: string;
};

export type WorkflowPackageDraft = {
  apiVersion: "ledger.workflowPackage/v1";
  kind: "WorkflowPackage";
  metadata: {
    description: string;
    key: string;
    name: string;
  };
  spec: {
    agents: PackageAgentDraft[];
    capabilityProfiles: PackageCapabilityProfileDraft[];
    inputs: SchemaIRNode;
    mcpServers: PackageMcpServerDraft[];
    outputSchemas: PackageOutputSchemaDraft[];
    workflows: UnknownRecord[];
  };
};

export type WorkflowPackageEditorIssue = {
  field: string;
  issue: string;
  resourceKey?: string;
  tab: WorkflowPackageEditorTab;
};

export type WorkflowPackageEditorTab =
  | "overview"
  | "agents"
  | "output-schemas"
  | "capability-profiles"
  | "private-mcp"
  | "preflight"
  | "launch"
  | "exports";

let nextDraftId = 0;

function createLocalKey(prefix: string) {
  nextDraftId += 1;
  return `${prefix}_${nextDraftId}`;
}

export function createPackageAgentDraft(overrides: Partial<PackageAgentDraft> = {}): PackageAgentDraft {
  return {
    budgetUsd: "0",
    capabilityProfiles: [],
    description: "",
    inputSchema: createDefaultSchemaNode("object"),
    key: createLocalKey("agent"),
    mcpServers: [],
    modelConnection: "",
    name: "New Agent",
    outputSchema: "",
    systemPrompt: "You are a concise Ledger package agent.",
    timeoutSeconds: "60",
    ...overrides,
  };
}

export function createPackageOutputSchemaDraft(overrides: Partial<PackageOutputSchemaDraft> = {}): PackageOutputSchemaDraft {
  return {
    description: "",
    jsonSchema: createDefaultSchemaNode("object"),
    key: createLocalKey("output_schema"),
    name: "New Output Schema",
    ...overrides,
  };
}

export function createPackageCapabilityProfileDraft(overrides: Partial<PackageCapabilityProfileDraft> = {}): PackageCapabilityProfileDraft {
  return {
    description: "",
    key: createLocalKey("profile"),
    name: "New Capability Profile",
    toolKeys: [],
    ...overrides,
  };
}

export function createPackageMcpServerDraft(overrides: Partial<PackageMcpServerDraft> = {}): PackageMcpServerDraft {
  return {
    argsText: "[]",
    command: "",
    description: "",
    env: {},
    headers: {},
    key: createLocalKey("private-mcp"),
    name: "New Private MCP",
    query: {},
    toolKeys: [],
    transport: "stdio",
    url: "",
    ...overrides,
  };
}

export function createWorkflowPackageDraft(overrides: Partial<WorkflowPackageDraft> = {}): WorkflowPackageDraft {
  return {
    apiVersion: "ledger.workflowPackage/v1",
    kind: "WorkflowPackage",
    metadata: {
      description: "",
      key: "new_workflow_package",
      name: "New Workflow Package",
    },
    spec: {
      agents: [],
      capabilityProfiles: [],
      inputs: createDefaultSchemaNode("object"),
      mcpServers: [],
      outputSchemas: [],
      workflows: [],
    },
    ...overrides,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function readString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function readStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function parseSchema(value: unknown): SchemaIRNode {
  const parsed = parseSchemaJsonText(JSON.stringify(isRecord(value) ? value : { additionalProperties: false, properties: {}, type: "object" }, null, 2));
  return parsed.builder ?? createDefaultSchemaNode("object");
}

function parseArgsText(value: unknown) {
  return JSON.stringify(Array.isArray(value) ? value.filter((item) => typeof item === "string") : [], null, 2);
}

function parseAgent(value: unknown, index: number): PackageAgentDraft {
  const record = isRecord(value) ? value : {};
  return createPackageAgentDraft({
    budgetUsd: readString(record.budgetUsd, "0"),
    capabilityProfiles: readStringArray(record.capabilityProfiles),
    description: readString(record.description),
    inputSchema: parseSchema(record.inputSchema),
    key: readString(record.key, `agent_${index + 1}`),
    mcpServers: readStringArray(record.mcpServers),
    modelConnection: readString(record.modelConnection),
    name: readString(record.name, `Agent ${index + 1}`),
    outputSchema: readString(record.outputSchema),
    systemPrompt: readString(record.systemPrompt),
    timeoutSeconds: readString(record.timeoutSeconds, "60"),
  });
}

function parseOutputSchema(value: unknown, index: number): PackageOutputSchemaDraft {
  const record = isRecord(value) ? value : {};
  return createPackageOutputSchemaDraft({
    description: readString(record.description),
    jsonSchema: parseSchema(record.jsonSchema),
    key: readString(record.key, `output_schema_${index + 1}`),
    name: readString(record.name, `Output Schema ${index + 1}`),
  });
}

function parseCapabilityProfile(value: unknown, index: number): PackageCapabilityProfileDraft {
  const record = isRecord(value) ? value : {};
  return createPackageCapabilityProfileDraft({
    description: readString(record.description),
    key: readString(record.key, `profile_${index + 1}`),
    name: readString(record.name, `Capability Profile ${index + 1}`),
    toolKeys: readStringArray(record.toolKeys),
  });
}

function normalizeStringMap(value: unknown): Record<string, string> {
  if (!isRecord(value)) {
    return {};
  }
  const entries = Object.entries(value)
    .map(([key, entry]) => [key.trim(), readString(entry).trim()] as const)
    .filter(([key, entryValue]) => Boolean(key) && Boolean(entryValue));
  return Object.fromEntries(entries);
}

function parseMcpServer(value: unknown, index: number): PackageMcpServerDraft {
  const record = isRecord(value) ? value : {};
  const transport = record.transport === "http-sse" ? "http-sse" : "stdio";
  return createPackageMcpServerDraft({
    argsText: parseArgsText(record.args),
    command: readString(record.command),
    description: readString(record.description),
    env: normalizeStringMap(record.env),
    headers: normalizeStringMap(record.headers),
    key: readString(record.key, `private-mcp-${index + 1}`),
    name: readString(record.name, `Private MCP ${index + 1}`),
    query: normalizeStringMap(record.query),
    toolKeys: readStringArray(record.toolKeys),
    transport,
    url: readString(record.url),
  });
}

export function packageDraftFromManifestSource(source: string): { draft: WorkflowPackageDraft; errors: string[] } {
  try {
    const document = parseDocument(source, { prettyErrors: false, uniqueKeys: false });
    const value = document.toJS() as unknown;
    if (!isRecord(value)) {
      return { draft: createWorkflowPackageDraft(), errors: ["Manifest root must be an object."] };
    }
    const metadata = isRecord(value.metadata) ? value.metadata : {};
    const spec = isRecord(value.spec) ? value.spec : {};
    return {
      draft: createWorkflowPackageDraft({
        apiVersion: "ledger.workflowPackage/v1",
        kind: "WorkflowPackage",
        metadata: {
          description: readString(metadata.description),
          key: readString(metadata.key, "new_workflow_package"),
          name: readString(metadata.name, "New Workflow Package"),
        },
        spec: {
          agents: Array.isArray(spec.agents) ? spec.agents.map(parseAgent) : [],
          capabilityProfiles: Array.isArray(spec.capabilityProfiles) ? spec.capabilityProfiles.map(parseCapabilityProfile) : [],
          inputs: parseSchema(spec.inputs),
          mcpServers: Array.isArray(spec.mcpServers) ? spec.mcpServers.map(parseMcpServer) : [],
          outputSchemas: Array.isArray(spec.outputSchemas) ? spec.outputSchemas.map(parseOutputSchema) : [],
          workflows: Array.isArray(spec.workflows) ? (spec.workflows.filter(isRecord) as UnknownRecord[]) : [],
        },
      }),
      errors: document.errors.map((error) => error.message),
    };
  } catch (error) {
    return { draft: createWorkflowPackageDraft(), errors: [error instanceof Error ? error.message : "Unable to parse package manifest."] };
  }
}

function parseMcpArgs(argsText: string): string[] {
  try {
    const parsed = JSON.parse(argsText || "[]") as unknown;
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

export function workflowPackageDraftToManifestObject(draft: WorkflowPackageDraft): UnknownRecord {
  return {
    apiVersion: "ledger.workflowPackage/v1",
    kind: "WorkflowPackage",
    metadata: {
      description: draft.metadata.description.trim(),
      key: draft.metadata.key.trim().toLowerCase(),
      name: draft.metadata.name.trim(),
    },
    spec: {
      agents: draft.spec.agents.map((agent) => ({
        budgetUsd: agent.budgetUsd.trim() || "0",
        capabilityProfiles: [...agent.capabilityProfiles].sort((left, right) => left.localeCompare(right)),
        description: agent.description.trim(),
        inputSchema: schemaBuilderToJsonSchema(agent.inputSchema),
        key: agent.key.trim().toLowerCase(),
        mcpServers: [...agent.mcpServers].sort((left, right) => left.localeCompare(right)),
        modelConnection: agent.modelConnection.trim(),
        name: agent.name.trim(),
        outputSchema: agent.outputSchema.trim(),
        systemPrompt: agent.systemPrompt,
      })),
      capabilityProfiles: draft.spec.capabilityProfiles.map((profile) => ({
        description: profile.description.trim(),
        key: profile.key.trim().toLowerCase(),
        name: profile.name.trim(),
        toolKeys: [...profile.toolKeys].sort((left, right) => left.localeCompare(right)),
      })),
      inputs: schemaBuilderToJsonSchema(draft.spec.inputs),
      mcpServers: draft.spec.mcpServers.map((server) => {
        const common = {
          description: server.description.trim(),
          key: server.key.trim().toLowerCase(),
          name: server.name.trim(),
          toolKeys: [...server.toolKeys].sort((left, right) => left.localeCompare(right)),
          transport: server.transport,
        };
        return server.transport === "stdio"
          ? {
              ...common,
              args: parseMcpArgs(server.argsText),
              command: server.command.trim(),
              env: normalizeStringMap(server.env),
            }
          : {
              ...common,
              headers: normalizeStringMap(server.headers),
              query: normalizeStringMap(server.query),
              url: server.url.trim(),
            };
      }),
      outputSchemas: draft.spec.outputSchemas.map((schema) => ({
        description: schema.description.trim(),
        jsonSchema: schemaBuilderToJsonSchema(schema.jsonSchema),
        key: schema.key.trim().toLowerCase(),
        name: schema.name.trim(),
      })),
      workflows: draft.spec.workflows,
    },
  };
}

export function workflowPackageDraftToManifestSource(draft: WorkflowPackageDraft): string {
  return stringify(workflowPackageDraftToManifestObject(draft), { lineWidth: 110 });
}

function required(value: string, field: string, issue: string, tab: WorkflowPackageEditorTab, resourceKey?: string): WorkflowPackageEditorIssue[] {
  return value.trim() ? [] : [{ field, issue, resourceKey, tab }];
}

function duplicateIssues(keys: readonly string[], fieldPrefix: string, tab: WorkflowPackageEditorTab): WorkflowPackageEditorIssue[] {
  const seen = new Set<string>();
  return keys.flatMap((key, index) => {
    const normalized = key.trim().toLowerCase();
    if (!normalized || !seen.has(normalized)) {
      seen.add(normalized);
      return [];
    }
    return [{ field: `${fieldPrefix}[${index}].key`, issue: `Duplicate local key: ${normalized}`, resourceKey: key, tab }];
  });
}

export function validateWorkflowPackageDraft(draft: WorkflowPackageDraft): WorkflowPackageEditorIssue[] {
  const outputSchemaKeys = new Set(draft.spec.outputSchemas.map((schema) => schema.key.trim()).filter(Boolean));
  const capabilityProfileKeys = new Set(draft.spec.capabilityProfiles.map((profile) => profile.key.trim()).filter(Boolean));
  const mcpServerKeys = new Set(draft.spec.mcpServers.map((server) => server.key.trim()).filter(Boolean));
  return [
    ...required(draft.metadata.key, "metadata.key", "Package key is required.", "overview"),
    ...required(draft.metadata.name, "metadata.name", "Package name is required.", "overview"),
    ...duplicateIssues(draft.spec.outputSchemas.map((schema) => schema.key), "spec.outputSchemas", "output-schemas"),
    ...duplicateIssues(draft.spec.capabilityProfiles.map((profile) => profile.key), "spec.capabilityProfiles", "capability-profiles"),
    ...duplicateIssues(draft.spec.mcpServers.map((server) => server.key), "spec.mcpServers", "private-mcp"),
    ...duplicateIssues(draft.spec.agents.map((agent) => agent.key), "spec.agents", "agents"),
    ...draft.spec.agents.flatMap((agent, index) => [
      ...required(agent.key, `spec.agents[${index}].key`, "Agent key is required.", "agents", agent.key),
      ...required(agent.name, `spec.agents[${index}].name`, "Agent name is required.", "agents", agent.key),
      ...required(agent.modelConnection, `spec.agents[${index}].modelConnection`, "Model connection key is required.", "agents", agent.key),
      ...required(agent.outputSchema, `spec.agents[${index}].outputSchema`, "Output schema key is required.", "agents", agent.key),
      ...(agent.outputSchema && !outputSchemaKeys.has(agent.outputSchema) ? [{ field: `spec.agents[${index}].outputSchema`, issue: "Select a package-local output schema.", resourceKey: agent.key, tab: "agents" as const }] : []),
      ...agent.capabilityProfiles.flatMap((key, refIndex) => capabilityProfileKeys.has(key) ? [] : [{ field: `spec.agents[${index}].capabilityProfiles[${refIndex}]`, issue: "Select a package-local capability profile.", resourceKey: agent.key, tab: "agents" as const }]),
      ...agent.mcpServers.flatMap((key, refIndex) => mcpServerKeys.has(key) ? [] : [{ field: `spec.agents[${index}].mcpServers[${refIndex}]`, issue: "Select a package-local private MCP server.", resourceKey: agent.key, tab: "agents" as const }]),
    ]),
  ];
}

export function diagnosticToEditorTarget(path: string): { field: string; tab: WorkflowPackageEditorTab } {
  if (path.startsWith("spec.agents")) {
    return { field: path, tab: "agents" };
  }
  if (path.startsWith("spec.outputSchemas")) {
    return { field: path, tab: "output-schemas" };
  }
  if (path.startsWith("spec.capabilityProfiles")) {
    return { field: path, tab: "capability-profiles" };
  }
  if (path.startsWith("spec.mcpServers")) {
    return { field: path, tab: "private-mcp" };
  }
  if (path.startsWith("spec.workflows")) {
    return { field: path, tab: "preflight" };
  }
  return { field: path, tab: "overview" };
}

export function mapBackendDiagnostics(diagnostics: readonly WorkflowPackageManifestDiagnostic[]): WorkflowPackageEditorIssue[] {
  return diagnostics.map((diagnostic) => ({
    field: diagnostic.path,
    issue: diagnostic.message,
    tab: diagnosticToEditorTarget(diagnostic.path).tab,
  }));
}
