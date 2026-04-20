export type SkillStatus = "draft" | "published" | "deprecated" | "archived";

export interface SkillToolDefinitionWrite {
  tool: string;
}

export interface SkillToolDefinitionRead extends SkillToolDefinitionWrite {
  displayName: string;
  description: string;
}

export interface SkillCreateInput {
  key: string;
  name: string;
  description?: string;
  toolDefinitions: SkillToolDefinitionWrite[];
}

export interface SkillUpdateInput {
  name?: string;
  description?: string;
  toolDefinitions?: SkillToolDefinitionWrite[];
}

export interface SkillRead {
  id: number;
  key: string;
  version: number;
  status: SkillStatus;
  name: string;
  description: string;
  toolDefinitions: SkillToolDefinitionRead[];
  createdAt: string;
  updatedAt: string;
}

export interface SkillListRead {
  items: SkillRead[];
}

export interface SkillListParams {
  status?: SkillStatus;
}
