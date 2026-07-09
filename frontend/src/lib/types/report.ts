import type { RuntimeInputMap } from "../runtime-inputs";

interface ReportAnalysisMetadata {
  ticker?: string | null;
  reviewType?: string | null;
  trigger?: string | null;
  reviewDate?: string | null;
  versionGroup?: string | null;
  [key: string]: unknown;
}

type ReportCreatedByType = "agent";

export interface ReportCreatedByMetadata {
  type: ReportCreatedByType;
  runId: number;
  agentKey: string;
  agentVersion: number;
  agentName?: string | null;
  workflowKey?: string | null;
  workflowVersion?: number | null;
  stepId?: string | null;
  slot?: string | null;
  traceId?: string | null;
}

interface ReportMetadata {
  author: string | null;
  description: string | null;
  tags: string[];
  analysis?: ReportAnalysisMetadata;
  createdBy?: ReportCreatedByMetadata;
  [key: string]: unknown;
}

export type ReportSource = "compiled" | "uploaded" | "external" | "agent";

export interface ReportRead {
  id: number;
  name: string;
  slug: string;
  source: ReportSource;
  content: string;
  metadata: ReportMetadata;
  createdAt: string;
  updatedAt: string;
}

export interface ReportUpdateInput {
  content?: string;
}

export interface ReportCompileInput {
  inputs?: RuntimeInputMap;
}
