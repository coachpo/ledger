import type { UnknownRecord } from "./common";

export type MemoryLifecycleStatus = "pending" | "resolved" | "expired";

export type MemoryRevisionAction = "created" | "reused" | "superseded";

export type MemoryScopeType =
  | "workspace"
  | "package"
  | "workflow"
  | "run"
  | "agent"
  | "namespace";

export type MemoryApiVisibility = "explicit-scope";

export interface MemoryScope {
  scopeType: MemoryScopeType;
  scopeKey: string;
}

export interface MemorySubjectRef {
  kind: string;
  id: string;
  label?: string | null;
}

export interface MemoryProvenance {
  runId: number;
  agentKey: string;
  agentName?: string | null;
  agentVersion: number;
  workflowKey?: string | null;
  workflowVersion?: number | null;
  stepId?: string | null;
  slot?: string | null;
  traceId?: string | null;
}

export interface MemoryRetrievalScore {
  rank?: number | null;
  score?: number | null;
  sources?: string[];
}

export interface MemoryApiAccessContext {
  runId?: number | null;
  packageKey: string;
  workflowKey?: string | null;
  agentKey?: string | null;
}

export interface MemoryApiAccessRequest {
  accessContext: MemoryApiAccessContext;
}

export interface MemoryApiListRequest extends MemoryApiAccessRequest {
  visibility?: MemoryApiVisibility;
  scope: MemoryScope;
  query?: string | null;
  subjectRefs?: MemorySubjectRef[];
  kind?: string | null;
  status?: MemoryLifecycleStatus | null;
  tags?: string[];
  limit?: number;
  offset?: number;
  maxCharacters?: number;
}

export interface MemoryApiListItemRead {
  memoryId: string;
  revisionId: string;
  kind: string;
  summary: string;
  content: string;
  subjectRefs: MemorySubjectRef[];
  scope: MemoryScope;
  provenance: MemoryProvenance;
  createdAt: string;
  retrievalScore?: MemoryRetrievalScore | null;
}

export interface MemoryApiRevisionRead {
  revisionId: string;
  version: number;
  status: MemoryLifecycleStatus;
  revisionAction: MemoryRevisionAction;
  summary: string;
  content: string;
  contentHash: string;
  subjectRefs: MemorySubjectRef[];
  attributes: UnknownRecord;
  supersedesRevisionId?: string | null;
  sourceRunId: number;
  sourceAgentKey: string;
  sourceStepId?: string | null;
  sourceSlot?: string | null;
  traceSpanId?: string | null;
  createdAt: string;
}

export interface MemoryApiEntryRead {
  memoryId: string;
  revisionId: string;
  status: MemoryLifecycleStatus;
  kind: string;
  summary: string;
  content: string;
  subjectRefs: MemorySubjectRef[];
  attributes: UnknownRecord;
  scope: MemoryScope;
  provenance: MemoryProvenance;
  revision: MemoryApiRevisionRead;
  createdAt: string;
  updatedAt?: string | null;
}

export interface MemoryApiListRead {
  items: MemoryApiListItemRead[];
  count: number;
  limit: number;
  offset: number;
  visibility: MemoryApiVisibility;
  scope: MemoryScope;
}

export interface MemoryApiRevisionListRead {
  items: MemoryApiRevisionRead[];
  count: number;
  limit: number;
  offset: number;
}

export interface MemoryApiEventRead {
  eventId: number;
  runId: number;
  eventType: string;
  memoryId?: string | null;
  revisionId?: string | null;
  retrievalMode?: string | null;
  filters: UnknownRecord;
  budget: UnknownRecord;
  excerpt?: string | null;
  injectedText?: string | null;
  resultSnapshot: UnknownRecord;
  statusSnapshot: UnknownRecord;
  stepId?: string | null;
  invocationId?: string | null;
  traceSpanId?: string | null;
  createdAt: string;
}

export interface MemoryApiEventListRead {
  items: MemoryApiEventRead[];
  count: number;
  limit: number;
  offset: number;
}
