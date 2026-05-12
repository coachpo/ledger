export type ModelConnectionReasoningEffort = string;
export type ModelConnectionApiStyle = "responses" | "chat_completions";
export type ModelConnectionKind = "provider" | "deterministic_smoke";

export interface ModelConnectionCreateInput {
  key: string;
  name: string;
  description?: string;
  connectionKind?: ModelConnectionKind;
  baseUrl: string;
  modelId: string;
  reasoningEffort?: ModelConnectionReasoningEffort | null;
  timeoutSeconds?: number;
  apiStyle?: ModelConnectionApiStyle;
  apiKey?: string;
}

export interface ModelConnectionUpdateInput {
  name?: string;
  description?: string | null;
  connectionKind?: ModelConnectionKind;
  baseUrl?: string;
  modelId?: string;
  reasoningEffort?: ModelConnectionReasoningEffort | null;
  timeoutSeconds?: number;
  apiStyle?: ModelConnectionApiStyle;
  apiKey?: string;
}

export interface ModelConnectionListItemRead {
  id: number;
  key: string;
  name: string;
  description: string;
  connectionKind: ModelConnectionKind;
  baseUrl: string;
  modelId: string;
  reasoningEffort: ModelConnectionReasoningEffort | null;
  timeoutSeconds: number;
  apiStyle: ModelConnectionApiStyle;
  lastTestedAt?: string | null;
  lastTestOk?: boolean | null;
  lastTestMessage?: string | null;
}

export interface ModelConnectionRead extends ModelConnectionListItemRead {
  createdAt: string;
  updatedAt: string;
}

export interface ModelConnectionListRead {
  items: ModelConnectionListItemRead[];
}

export type ModelConnectionListParams = Record<string, never>;

export interface ModelConnectionConnectionTestRead {
  modelConnectionId: number;
  ok: boolean;
  message: string;
  lastTestedAt: string;
}
