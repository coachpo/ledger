import type { UnknownRecord } from "@/lib/types/common";
import type {
  WorkflowCreateInput,
  WorkflowListParams,
  WorkflowListRead,
  WorkflowOutputSpecRead,
  WorkflowOutputSpecWrite,
  WorkflowRead,
  WorkflowStatus,
  WorkflowStepAgentRead,
  WorkflowStepAgentWrite,
  WorkflowStepRead,
  WorkflowStepWrite,
  WorkflowWireSource,
} from "@/lib/types/workflow";
import type { PlatformAuthoringIssue } from "../common/issues";

export type WorkflowBindingPathToken = string;
export type WorkflowBindingPath = WorkflowBindingPathToken[];
export type WorkflowBindingSourceKind = "none" | WorkflowWireSource["from"];

export interface WireBinding {
  source: WorkflowBindingSourceKind;
  stepIndex: number | null;
  slot: string | null;
  pathTokens: WorkflowBindingPath;
}

export interface WorkflowDraftAgent {
  agentKey: string;
  agentVersion: string;
  optional: boolean;
  slot: string;
  wiring: Record<string, WireBinding>;
}

export interface WorkflowDraftStep {
  agents: WorkflowDraftAgent[];
  id: string;
}

export interface WorkflowDraftOutput {
  kind: "slot";
  pathTokens: WorkflowBindingPath;
  slot: string;
  stepIndex: string;
}

export interface WorkflowDraft {
  description: string;
  inputSchemaText: string;
  key: string;
  name: string;
  output: WorkflowDraftOutput;
  steps: WorkflowDraftStep[];
}

export type WorkflowValidationIssue = PlatformAuthoringIssue;
export type WorkflowJsonSchema = UnknownRecord;
export type WorkflowDraftModel = WorkflowDraft;
export type WorkflowSection = "input" | "steps" | "output" | "review";

export type WorkflowReadModel = WorkflowRead;
export type WorkflowListReadModel = WorkflowListRead;
export type WorkflowListParamsModel = WorkflowListParams;
export type WorkflowStatusModel = WorkflowStatus;
export type WorkflowStepAgentReadModel = WorkflowStepAgentRead;
export type WorkflowStepAgentWriteModel = WorkflowStepAgentWrite;
export type WorkflowStepReadModel = WorkflowStepRead;
export type WorkflowStepWriteModel = WorkflowStepWrite;
export type WorkflowOutputSpecReadModel = WorkflowOutputSpecRead;
export type WorkflowOutputSpecWriteModel = WorkflowOutputSpecWrite;
export type WorkflowCreateInputModel = WorkflowCreateInput;
