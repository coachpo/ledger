import type {
  ApprovalSummary,
  PersonaProfileRef,
  RuntimeRunStatus,
  TerminalError,
  TraceSummary,
} from "./runtime";

export interface TryoutExecuteInput {
  workflowSpecKey?: string | null;
  workflowSpecVersion?: number | null;
  agentSpecKey?: string | null;
  agentSpecVersion?: number | null;
  inputs?: Record<string, string>;
  personaProfileRefs?: PersonaProfileRef[];
  persistRun?: boolean;
}

export interface TryoutRead {
  runId: number;
  status: RuntimeRunStatus;
  finalOutput: unknown | null;
  reportMarkdown: string | null;
  traceSummary: TraceSummary;
  approvalSummary: ApprovalSummary;
  expiresAt: string | null;
  terminalError: TerminalError | null;
}

export type TryoutPersistRead = TryoutRead;
