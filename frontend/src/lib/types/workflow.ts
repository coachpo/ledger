import type { UnknownRecord } from "./common";

export type WorkflowStatus = "draft" | "published" | "deprecated" | "archived";

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

export interface WorkflowOutputAgentWrite {
  kind: "agent";
  agentKey: string;
  agentVersion?: number | null;
  wiring?: Record<string, WorkflowWireSource>;
}

export type WorkflowOutputSpecWrite = WorkflowOutputSlotWrite | WorkflowOutputAgentWrite;

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

export interface WorkflowOutputAgentRead {
  kind: "agent";
  agentId: number;
  agentKey: string;
  agentVersion: number;
  outputSchemaId: number;
  outputSchemaVersion: number;
  wiring: Record<string, WorkflowWireSource>;
}

export type WorkflowOutputSpecRead = WorkflowOutputSlotRead | WorkflowOutputAgentRead;

export interface WorkflowCreateInput {
  key: string;
  name: string;
  description?: string;
  inputSchema: UnknownRecord;
  steps: WorkflowStepWrite[];
  outputSpec: WorkflowOutputSpecWrite;
}

export type WorkflowUpdateInput = Omit<WorkflowCreateInput, "key">;
export type WorkflowRunCreateInput = UnknownRecord;

export interface WorkflowRead {
  id: number;
  key: string;
  version: number;
  status: WorkflowStatus;
  name: string;
  description: string;
  inputSchema: UnknownRecord;
  steps: WorkflowStepRead[];
  outputSpec: WorkflowOutputSpecRead;
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
