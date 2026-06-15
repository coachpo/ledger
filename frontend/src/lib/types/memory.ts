import type { UnknownRecord } from "./common";


export type MemoryRevisionAction = "created" | "reused" | "superseded";

export type MemoryAdminSort = "updatedAtDesc" | "createdAtDesc";

export type MemoryScopeType =
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

export interface MemoryRuntimeProvenance {
  runId: number;
  agentKey: string;
  workflowKey?: string | null;
  stepId?: string | null;
  slot?: string | null;
}

export interface MemoryProvenance extends MemoryRuntimeProvenance {
  agentName?: string | null;
  agentVersion: number;
  createdByType?: "agent" | "operator";
  workflowVersion?: number | null;
  traceId?: string | null;
}

export interface MemoryRetrievalScore {
  rank?: number | null;
  score?: number | null;
  sources?: "lexical"[];
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
  provenance: MemoryRuntimeProvenance;
  createdAt: string;
  retrievalScore?: MemoryRetrievalScore | null;
}

export interface MemoryRevisionRead {
  revisionId: string;
  version: number;
  contentHash: string;
  createdAt: string;
  supersedesRevisionId?: string | null;
}

export interface MemoryOutcome {
  summary: string;
  observedAt: string;
}

export interface MemoryReflection {
  summary: string;
  content: string;
  reflectedAt: string;
  source?: string | null;
  reflection: string;
}

export interface MemoryApiRevisionRead {
  revisionId: string;
  version: number;
  visibleToWorkflow: boolean;
  revisionAction: MemoryRevisionAction;
  summary: string;
  content: string;
  contentHash: string;
  subjectRefs: MemorySubjectRef[];
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
  visibleToWorkflow: boolean;
  kind: string;
  summary: string;
  content: string;
  subjectRefs: MemorySubjectRef[];
  scope: MemoryScope;
  provenance: MemoryRuntimeProvenance;
  revision: MemoryRevisionRead;
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

export interface MemoryAdminListParams {
  packageKey?: string | null;
  workflowKey?: string | null;
  agentKey?: string | null;
  runId?: number | null;
  scopeType?: MemoryScopeType | null;
  kind?: string | null;
  visibleToWorkflow?: boolean | null;
  query?: string | null;
  limit?: number;
  offset?: number;
  sort?: MemoryAdminSort;
}

export interface MemoryAdminHistoryParams {
  limit?: number;
  offset?: number;
}

export interface MemoryAdminListItemRead {
  memoryId: string;
  revisionId: string;
  visibleToWorkflow: boolean;
  kind: string;
  summary: string;
  excerpt: string;
  subjectRefs: MemorySubjectRef[];
  scope: MemoryScope;
  provenance: MemoryRuntimeProvenance;
  createdAt: string;
  updatedAt?: string | null;
  lastEventType?: string | null;
}

export interface MemoryAdminListRead {
  items: MemoryAdminListItemRead[];
  total: number;
  limit: number;
  offset: number;
  sort: MemoryAdminSort;
}

export interface MemoryAdminEntryRead {
  memoryId: string;
  revisionId: string;
  visibleToWorkflow: boolean;
  kind: string;
  summary: string;
  content: string;
  subjectRefs: MemorySubjectRef[];
  scope: MemoryScope;
  provenance: MemoryRuntimeProvenance;
  revision: MemoryRevisionRead;
  createdAt: string;
  updatedAt?: string | null;
  outcome?: MemoryOutcome | null;
  reflections: MemoryReflection[];
}

export interface MemoryAdminCreateRequest {
  kind?: string;
  summary?: string;
  content?: string;
  subjectRefs?: MemorySubjectRef[];
  scope: MemoryScope;
  provenance: MemoryProvenance;
  visibleToWorkflow?: boolean;
  idempotencyKey?: string | null;
}

export interface MemoryAdminRevisionCreateRequest {
  summary: string;
  content: string;
  subjectRefs?: MemorySubjectRef[];
  provenance: MemoryProvenance;
}

export interface MemoryAdminWorkflowVisibilityUpdateRequest {
  visibleToWorkflow: boolean;
  summary?: string;
  observedAt?: string;
}

export type MemoryAdminRevisionListRead = MemoryApiRevisionListRead;

export type MemoryAdminEventListRead = MemoryApiEventListRead;
