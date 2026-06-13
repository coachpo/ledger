import { toast } from "sonner";

import type {
  MemoryAdminCreateRequest,
  MemoryAdminListItemRead,
  MemoryAdminListParams,
  MemoryAdminRevisionCreateRequest,
  MemoryAdminStatusUpdateRequest,
  MemoryLifecycleStatus,
  MemoryProvenance,
  MemoryRevisionAction,
  MemoryScope,
  MemoryScopeType,
  MemorySubjectRef,
} from "@/lib/types/memory";

export const DEFAULT_OPERATOR_AGENT_KEY = "local-instance-operator";
export const ALL_SCOPES_FILTER = "__all_scopes__";
export const ALL_STATUSES_FILTER = "__all_statuses__";
export const STATUS_VALUES: readonly MemoryLifecycleStatus[] = [
  "pending",
  "approved",
  "archived",
];
export const SCOPE_TYPE_VALUES: readonly MemoryScopeType[] = [
  "package",
  "workflow",
  "run",
  "agent",
  "namespace",
];
export const RUNTIME_IMPACT_COPY =
  "Approved memory in a matching scope may appear in future workflow lookup; pending or archived memory remains visible here for operators but is excluded from default runtime lookup.";

export type JsonObject = Record<string, unknown>;
export type MemoryDetailTab = "detail" | "revisions" | "events";

export type CreateDraft = {
  agentKey: string;
  attributesJson: string;
  content: string;
  kind: string;
  packageKey: string;
  runId: string;
  scopeKey: string;
  scopeType: MemoryScopeType;
  status: MemoryLifecycleStatus;
  subjectId: string;
  subjectKind: string;
  subjectLabel: string;
  summary: string;
  workflowKey: string;
};

export type RevisionDraft = {
  attributesJson: string;
  content: string;
  summary: string;
};

export type StatusDraft = {
  attributesJson: string;
  status: MemoryLifecycleStatus;
  summary: string;
};

export type AdminRevisionVariables = {
  memoryId: string;
  payload: MemoryAdminRevisionCreateRequest;
};

export type AdminStatusVariables = {
  memoryId: string;
  payload: MemoryAdminStatusUpdateRequest;
};

export type AdminListFilterState = {
  agentKey: string;
  kind: string;
  packageKey: string;
  query: string;
  runId: string;
  scopeType: string;
  status: string;
  workflowKey: string;
};

export function optionalText(value: string): string | undefined {
  const normalized = value.trim();
  return normalized ? normalized : undefined;
}

export function optionalRunId(value: string): number | undefined {
  const normalized = value.trim();
  if (!normalized) {
    return undefined;
  }
  const parsed = Number(normalized);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

export function parseRequiredRunId(value: string): number | null {
  return optionalRunId(value) ?? null;
}

export function parseJsonObject(
  value: string,
  label: string,
): JsonObject | null {
  const normalized = value.trim();
  if (!normalized) {
    return {};
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(normalized) as unknown;
  } catch (error) {
    const suffix = error instanceof Error ? ` ${error.message}` : "";
    toast.error(`${label} must be a JSON object.${suffix}`);
    return null;
  }

  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    return parsed as JsonObject;
  }

  toast.error(`${label} must be a JSON object.`);
  return null;
}

export function titleCase(value: string): string {
  return value
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

export function statusTone(status: MemoryLifecycleStatus) {
  if (status === "approved") {
    return "success" as const;
  }
  if (status === "pending") {
    return "warning" as const;
  }
  return "muted" as const;
}

export function revisionTone(action: MemoryRevisionAction) {
  return action === "created"
    ? "success"
    : action === "superseded"
      ? "muted"
      : "neutral";
}

export function formatScope(scope: MemoryScope): string {
  return scope.scopeType === "namespace"
    ? `Namespace ${scope.scopeKey}`
    : `${titleCase(scope.scopeType)} ${scope.scopeKey}`;
}

export function formatProvenance(provenance: MemoryProvenance): string {
  const workflow = provenance.workflowKey ? ` · ${provenance.workflowKey}` : "";
  const creator = provenance.createdByType
    ? `${provenance.createdByType} · `
    : "";
  return `${creator}${provenance.agentKey}@${provenance.agentVersion}${workflow} · run #${provenance.runId}`;
}

export function subjectRefSummary(
  item: Pick<MemoryAdminListItemRead, "subjectRefs">,
): string {
  if (item.subjectRefs.length === 0) {
    return "No subject refs";
  }
  return item.subjectRefs
    .map((subject) => `${subject.kind}:${subject.id}`)
    .join(" · ");
}

export function buildSubjectRefs(draft: CreateDraft): MemorySubjectRef[] {
  const subjectKind = optionalText(draft.subjectKind);
  const subjectId = optionalText(draft.subjectId);
  if (!subjectKind || !subjectId) {
    return [];
  }
  return [
    {
      id: subjectId,
      kind: subjectKind,
      label: optionalText(draft.subjectLabel) ?? null,
    },
  ];
}

export function buildOperatorProvenance({
  agentKey,
  runId,
  workflowKey,
}: {
  agentKey: string;
  runId: number;
  workflowKey?: string;
}): MemoryProvenance {
  return {
    agentKey: optionalText(agentKey) ?? DEFAULT_OPERATOR_AGENT_KEY,
    agentVersion: 1,
    createdByType: "operator",
    runId,
    ...(workflowKey ? { workflowKey } : {}),
  };
}

export function buildAdminListParams(
  filters: AdminListFilterState,
): MemoryAdminListParams {
  const params: MemoryAdminListParams = {};
  const normalizedPackageKey = optionalText(filters.packageKey);
  const normalizedWorkflowKey = optionalText(filters.workflowKey);
  const normalizedAgentKey = optionalText(filters.agentKey);
  const normalizedKind = optionalText(filters.kind);
  const normalizedQuery = optionalText(filters.query);
  const parsedRunId = optionalRunId(filters.runId);

  if (normalizedPackageKey) params.packageKey = normalizedPackageKey;
  if (normalizedWorkflowKey) params.workflowKey = normalizedWorkflowKey;
  if (normalizedAgentKey) params.agentKey = normalizedAgentKey;
  if (parsedRunId) params.runId = parsedRunId;
  if (filters.scopeType !== ALL_SCOPES_FILTER)
    params.scopeType = filters.scopeType as MemoryScopeType;
  if (normalizedKind) params.kind = normalizedKind;
  if (filters.status !== ALL_STATUSES_FILTER)
    params.status = filters.status as MemoryLifecycleStatus;
  if (normalizedQuery) params.query = normalizedQuery;

  return params;
}

export function createInitialDraft(): CreateDraft {
  return {
    agentKey: DEFAULT_OPERATOR_AGENT_KEY,
    attributesJson: "{}",
    content: "",
    kind: "note",
    packageKey: "",
    runId: "",
    scopeKey: "",
    scopeType: "package",
    status: "approved",
    subjectId: "",
    subjectKind: "",
    subjectLabel: "",
    summary: "",
    workflowKey: "",
  };
}

export function createRevisionDraft(): RevisionDraft {
  return { attributesJson: "{}", content: "", summary: "" };
}

export function createStatusDraft(
  status: MemoryLifecycleStatus = "approved",
): StatusDraft {
  return { attributesJson: "{}", status, summary: "" };
}

export function createMemoryPayloadFromDraft(
  draft: CreateDraft,
): MemoryAdminCreateRequest | null {
  const scopeKey = optionalText(draft.scopeKey);
  const runId = parseRequiredRunId(draft.runId);
  const attributes = parseJsonObject(draft.attributesJson, "Create attributes");
  if (!scopeKey || !runId || !attributes) {
    toast.error("Create memory needs run id, scope key, and valid attributes.");
    return null;
  }

  return {
    attributes,
    content: draft.content,
    kind: optionalText(draft.kind) ?? "note",
    provenance: buildOperatorProvenance({
      agentKey: draft.agentKey,
      runId,
      workflowKey: optionalText(draft.workflowKey),
    }),
    scope: { scopeKey, scopeType: draft.scopeType },
    status: draft.status,
    subjectRefs: buildSubjectRefs(draft),
    summary: draft.summary,
  };
}
