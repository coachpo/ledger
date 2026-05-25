import {
  Boxes,
  Braces,
  Cable,
  Code2,
  Download,
  KeyRound,
  ShieldCheck,
  Workflow,
} from "lucide-react";

import {
  diagnosticToEditorTarget,
  type WorkflowPackageEditorIssue,
} from "@/lib/platform-authoring/workflow-packages/manifest";
import type { ModelConnectionKind } from "@/lib/types/model-connection";
import type {
  WorkflowPackageManifestRead,
  WorkflowPackageRead,
} from "@/lib/types/workflow-package";

export type WorkflowPackageEditorTab =
  | "overview"
  | "agents"
  | "output-schemas"
  | "capability-profiles"
  | "private-mcp"
  | "workflow-yaml"
  | "secret-bindings"
  | "exports";

export type WorkflowPackageEditorTabDefinition = {
  description: string;
  icon: typeof Workflow;
  label: string;
  value: WorkflowPackageEditorTab;
};

export type DiagnosticTarget = {
  field: string;
  tab: WorkflowPackageEditorTab;
} | null;

export function diagnosticToAuthoringTarget(
  path: string,
): Exclude<DiagnosticTarget, null> {
  const target = diagnosticToEditorTarget(path);
  switch (target.tab) {
    case "agents":
    case "capability-profiles":
    case "exports":
    case "overview":
    case "output-schemas":
    case "private-mcp":
    case "secret-bindings":
    case "workflow-yaml":
      return { field: target.field, tab: target.tab };
    case "launch":
    case "preflight":
      return { field: target.field, tab: "overview" };
  }
}

export const editorTabs: WorkflowPackageEditorTabDefinition[] = [
  {
    description:
      "Package metadata, manifest identity, current hashes, and local edit state.",
    icon: Workflow,
    label: "Overview",
    value: "overview",
  },
  {
    description:
      "Package-private agent definitions stay local to this package shell.",
    icon: Boxes,
    label: "Agents",
    value: "agents",
  },
  {
    description:
      "Local output contracts are authored inside the package boundary.",
    icon: Braces,
    label: "Output Schemas",
    value: "output-schemas",
  },
  {
    description:
      "Capability profiles collect server-declared tool keys for local agents.",
    icon: ShieldCheck,
    label: "Capability Profiles",
    value: "capability-profiles",
  },
  {
    description:
      "Private MCP server bindings stay portable and secret-reference driven.",
    icon: Cable,
    label: "Private MCP",
    value: "private-mcp",
  },
  {
    description:
      "Author workflow graphs as raw YAML, including kind:http operation nodes.",
    icon: Code2,
    label: "Workflow YAML",
    value: "workflow-yaml",
  },
  {
    description:
      "Bind package-local secret references without exposing stored values.",
    icon: KeyRound,
    label: "Secret Bindings",
    value: "secret-bindings",
  },
  {
    description:
      "Import or export clean package YAML without database ids or secret values.",
    icon: Download,
    label: "Import / Export",
    value: "exports",
  },
];

export function getEditorTabDefinition(tab: WorkflowPackageEditorTab) {
  return (
    editorTabs.find((definition) => definition.value === tab) ?? editorTabs[0]
  );
}

export function packageTitle(
  workflowPackage: WorkflowPackageRead | undefined,
  isNew: boolean,
) {
  return workflowPackage
    ? workflowPackage.name
    : isNew
      ? "New Workflow Package"
      : "Workflow Package";
}

export function packageSubtitle(
  workflowPackage: WorkflowPackageRead | undefined,
  isNew: boolean,
) {
  if (workflowPackage) {
    return workflowPackage.key;
  }
  return isNew ? "Draft manifest shell" : "Loading package identity";
}

export function manifestIdentity(manifest: WorkflowPackageManifestRead) {
  return `package:${manifest.packageId}:${manifest.manifestHash}`;
}

const CONNECTION_KIND_LABELS: Record<ModelConnectionKind, string> = {
  deterministic_smoke: "Deterministic smoke",
  provider: "Provider-backed",
};

export function connectionKindLabel(
  value: ModelConnectionKind | null | undefined,
): string {
  return CONNECTION_KIND_LABELS[value ?? "provider"];
}

export function collectSecretReferenceKeys(value: unknown): string[] {
  const matches = JSON.stringify(value).matchAll(
    /\$\{\{\s*secrets\.([a-z][a-z0-9_]*)\s*}}/g,
  );
  return [
    ...new Set([...matches].map((match) => match[1]).filter(Boolean)),
  ].sort((left, right) => left.localeCompare(right));
}

export function issueMessagesForPrefix(
  issues: readonly WorkflowPackageEditorIssue[],
  prefix: string,
) {
  return issues.filter(
    (issue) =>
      issue.field === prefix ||
      issue.field.startsWith(`${prefix}.`) ||
      issue.field.startsWith(`${prefix}[`),
  );
}
