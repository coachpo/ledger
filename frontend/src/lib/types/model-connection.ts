export type ModelConnectionStatus = "active" | "archived";
export type ModelConnectionReasoningEffort = string;
export type ModelConnectionApiStyle = "responses" | "chat_completions";

export interface ModelConnectionCreateInput {
  key: string;
  name: string;
  description?: string;
  baseUrl: string;
  organization?: string | null;
  project?: string | null;
  modelId: string;
  reasoningEffort?: ModelConnectionReasoningEffort | null;
  timeoutSeconds?: number;
  apiStyle?: ModelConnectionApiStyle;
  apiKey?: string;
}

export interface ModelConnectionUpdateInput {
  name?: string;
  description?: string | null;
  baseUrl?: string;
  organization?: string | null;
  project?: string | null;
  modelId?: string;
  reasoningEffort?: ModelConnectionReasoningEffort | null;
  timeoutSeconds?: number;
  apiStyle?: ModelConnectionApiStyle;
  apiKey?: string;
}

export interface ModelConnectionListItemRead {
  id: number;
  key: string;
  status: ModelConnectionStatus;
  name: string;
  description: string;
  baseUrl: string;
  organization?: string | null;
  project?: string | null;
  modelId: string;
  reasoningEffort: ModelConnectionReasoningEffort | null;
  timeoutSeconds: number;
  apiStyle: ModelConnectionApiStyle;
  hasApiKey: boolean;
  apiKeyLast4?: string | null;
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

export interface ModelConnectionListParams {
  status?: ModelConnectionStatus;
}

export interface ModelConnectionConnectionTestRead {
  modelConnectionId: number;
  ok: boolean;
  message: string;
  lastTestedAt: string;
}
