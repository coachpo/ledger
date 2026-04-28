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

export type TemplateRuntimeInputs = Record<string, string>;

export interface TextTemplateInlineCompileInput {
  content: string;
  inputs?: TemplateRuntimeInputs;
}

export interface TextTemplateStoredCompileInput {
  inputs?: TemplateRuntimeInputs;
}

export interface TextTemplateCompileRead {
  id: number;
  name: string;
  compiled: string;
}

export interface TextTemplateInlineCompileRead {
  compiled: string;
}

export interface PlaceholderPosition {
  symbol: string;
  name: string | null;
}

export interface PlaceholderPortfolio {
  slug: string;
  name: string;
  baseCurrency: string;
  positions: PlaceholderPosition[];
}

export interface PlaceholderReport {
  name: string;
  createdAt: string;
}

export interface PlaceholderTree {
  portfolios: PlaceholderPortfolio[];
  reports: PlaceholderReport[];
}
