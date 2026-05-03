import type { UnknownRecord } from "./common";

export type WorkflowStatus = "draft" | "published" | "deprecated" | "archived";
export type WorkflowManifestApiVersion = "ledger.workflow/v1" | "ledger.workflow/v2";
export type WorkflowManifestDiagnosticSeverity = "error" | "warning";
export type WorkflowCompiledGraphNodeKind = "step" | "sequence" | "fanout" | "loop";

export interface WorkflowCompiledGraphRef {
  compiledSlot?: string;
  nodeId?: string;
  path?: string;
  slot?: string;
  source: "inputs" | "nodes";
  sourceNodeId?: string;
  sourceSlot?: string;
  stepIndex?: number;
}

export interface WorkflowCompiledGraphNode {
  agentKey?: string;
  agentVersion?: number;
  branchId?: string;
  branchIds?: string[];
  childNodeIds?: string[];
  fanoutId?: string;
  id: string;
  kind: WorkflowCompiledGraphNodeKind;
  loopId?: string;
  loopIteration?: number;
  maxIterations?: number;
  mode?: string;
  nodeId: string;
  optional?: boolean;
  refs?: Record<string, WorkflowCompiledGraphRef>;
  sequenceNodeId?: string;
  slot?: string;
  sourceRefs?: unknown;
  stateRefs?: Record<string, WorkflowCompiledGraphRef>;
  stepIndex?: number;
}

export interface WorkflowCompiledGraph {
  apiVersion: WorkflowManifestApiVersion;
  nodes: WorkflowCompiledGraphNode[];
  output?: WorkflowCompiledGraphRef;
  postRunMemory?: {
    enabled?: boolean;
    sourceRefs?: Record<string, WorkflowCompiledGraphRef>;
    benchmarkSymbol?: WorkflowCompiledGraphRef;
  };
  rootNodeId: string;
  validation?: Record<string, unknown>;
}

export interface WorkflowWireSource {
  from: "input" | "step";
  path?: string | null;
  stepIndex?: number | null;
  slot?: string | null;
}

export interface WorkflowStepAgentWrite {
  agentKey: string;
  agentVersion?: number | null;
  slot: string;
  wiring?: Record<string, WorkflowWireSource>;
  optional?: boolean;
}

export interface WorkflowStepWrite {
  index: number;
  agents: WorkflowStepAgentWrite[];
}

export interface WorkflowOutputSlotWrite {
  kind: "slot";
  stepIndex: number;
  slot: string;
  path?: string | null;
}

export type WorkflowOutputSpecWrite = WorkflowOutputSlotWrite;

export interface WorkflowStepAgentRead {
  agentId: number;
  agentKey: string;
  agentVersion: number;
  outputSchemaId: number;
  outputSchemaVersion: number;
  slot: string;
  wiring: Record<string, WorkflowWireSource>;
  optional: boolean;
  budgetUsd: string;
}

export interface WorkflowStepRead {
  index: number;
  agents: WorkflowStepAgentRead[];
}

export interface WorkflowOutputSlotRead {
  kind: "slot";
  stepIndex: number;
  slot: string;
  path?: string | null;
  agentId: number;
  agentKey: string;
  agentVersion: number;
  outputSchemaId: number;
  outputSchemaVersion: number;
}

export type WorkflowOutputSpecRead = WorkflowOutputSlotRead;

export interface WorkflowCompiledCreateInput {
  key: string;
  name: string;
  description?: string;
  inputSchema: UnknownRecord;
  steps: WorkflowStepWrite[];
  outputSpec: WorkflowOutputSpecWrite;
}

export type WorkflowCompiledUpdateInput = Omit<WorkflowCompiledCreateInput, "key">;

export interface WorkflowManifestWriteInput {
  manifestSource: string;
}

export type WorkflowManifestCreateInput = WorkflowManifestWriteInput;
export type WorkflowManifestUpdateInput = WorkflowManifestWriteInput;

export type WorkflowCreateInput = Partial<WorkflowCompiledCreateInput> & Partial<WorkflowManifestWriteInput>;

export type WorkflowUpdateInput = Partial<WorkflowCompiledUpdateInput> & Partial<WorkflowManifestWriteInput>;

export type WorkflowRunCreateInput = UnknownRecord;

export interface WorkflowManifestDiagnostic {
  severity: WorkflowManifestDiagnosticSeverity;
  message: string;
  path: string;
  line: number | null;
  column: number | null;
}

export interface WorkflowManifestValidationMetadata {
  apiVersion: WorkflowManifestApiVersion;
  key: string;
  name: string;
  description: string;
}

export type WorkflowManifestValidationInput = WorkflowManifestWriteInput;

export interface WorkflowManifestValidationRead {
  diagnostics: WorkflowManifestDiagnostic[];
  metadata: WorkflowManifestValidationMetadata | null;
  compiledPayload: WorkflowCompiledCreateInput | null;
  compiledGraph?: WorkflowCompiledGraph | null;
  runInputSchema: UnknownRecord | null;
}

export interface WorkflowRead {
  id: number;
  key: string;
  version: number;
  status: WorkflowStatus;
  name: string;
  description: string;
  manifestApiVersion: WorkflowManifestApiVersion;
  manifestSource: string;
  inputSchema: UnknownRecord;
  steps: WorkflowStepRead[];
  outputSpec: WorkflowOutputSpecRead;
  compiledGraph?: WorkflowCompiledGraph | null;
  aggregateBudgetUsd: string;
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowListRead {
  items: WorkflowRead[];
}

export interface WorkflowListParams {
  status?: WorkflowStatus;
}
