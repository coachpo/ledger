import type { RuntimeInputMap } from "../runtime-inputs";

export interface TextTemplateRead {
  id: number;
  name: string;
  content: string;
  createdAt: string;
  updatedAt: string;
}

export interface TextTemplateWriteInput {
  name: string;
  content: string;
}

export interface TextTemplateUpdateInput {
  name?: string;
  content?: string;
}

export interface TextTemplateInlineCompileInput {
  content: string;
  inputs?: RuntimeInputMap;
}

export interface TextTemplateInlineCompileRead {
  compiled: string;
}

interface PlaceholderReport {
  name: string;
  createdAt: string;
}

export interface PlaceholderTree {
  reports: PlaceholderReport[];
}
