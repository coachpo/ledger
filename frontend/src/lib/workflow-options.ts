import type { UnknownRecord } from "./types/common";
import type { WorkflowPackageManifestRead } from "./types/workflow-package";

export type WorkflowOption = {
  description: string;
  inputSchema: UnknownRecord;
  key: string;
  label: string;
};

type WorkflowDefinition = {
  description?: unknown;
  inputSchema?: unknown;
  key?: unknown;
  label?: unknown;
  name?: unknown;
};

type WorkflowPackageDefinition = {
  spec?: {
    workflows?: unknown;
  };
};

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function readString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function readInputSchema(value: unknown): UnknownRecord {
  return isRecord(value) ? value : {};
}

function toWorkflowOption(workflow: WorkflowDefinition): WorkflowOption | null {
  const key = readString(workflow.key).trim();
  if (!key) {
    return null;
  }

  const label = readString(workflow.label).trim() || readString(workflow.name).trim() || key;

  return {
    description: readString(workflow.description),
    inputSchema: readInputSchema(workflow.inputSchema),
    key,
    label,
  };
}

function readWorkflowDefinitions(manifest: WorkflowPackageManifestRead): WorkflowDefinition[] {
  const packageDefinition = manifest.packageDefinition as WorkflowPackageDefinition | undefined;
  const workflows = packageDefinition?.spec?.workflows;
  return Array.isArray(workflows) ? (workflows.filter(isRecord) as WorkflowDefinition[]) : [];
}

export function getWorkflowOptions(
  manifest: WorkflowPackageManifestRead,
  selectedWorkflowKey?: string | null,
): WorkflowOption[] {
  const options = readWorkflowDefinitions(manifest)
    .map(toWorkflowOption)
    .filter((option): option is WorkflowOption => Boolean(option));

  const normalizedSelectedWorkflowKey = selectedWorkflowKey?.trim() ?? "";
  if (
    !normalizedSelectedWorkflowKey ||
    options.some((option) => option.key === normalizedSelectedWorkflowKey)
  ) {
    return options;
  }

  return [
    ...options,
    {
      description: "Missing manifest workflow",
      inputSchema: {},
      key: normalizedSelectedWorkflowKey,
      label: `Unknown workflow: ${normalizedSelectedWorkflowKey}`,
    },
  ];
}
