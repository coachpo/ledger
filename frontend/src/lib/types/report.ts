import type { TemplateRuntimeInputs } from "./text-template";

export interface ReportAnalysisMetadata {
  ticker?: string | null;
  portfolioSlug?: string | null;
  reviewType?: string | null;
  trigger?: string | null;
  reviewDate?: string | null;
  versionGroup?: string | null;
  [key: string]: unknown;
}

export interface ReportMetadata {
  author: string | null;
  description: string | null;
  tags: string[];
  analysis?: ReportAnalysisMetadata;
  [key: string]: unknown;
}

export interface ReportRead {
  id: number;
  name: string;
  slug: string;
  source: "compiled" | "uploaded" | "external";
  content: string;
  metadata: ReportMetadata;
  createdAt: string;
  updatedAt: string;
}

export interface ReportUpdateInput {
  content?: string;
}

export interface ReportCompileInput {
  inputs?: TemplateRuntimeInputs;
}
