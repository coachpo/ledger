export type CapabilityStatus = "draft" | "published" | "deprecated";

export interface CapabilityToolRead {
  key: string;
  displayName: string;
  description: string;
}

export interface CapabilityToolListRead {
  items: CapabilityToolRead[];
}

export interface CapabilityCreateInput {
  key: string;
  name: string;
  description?: string;
  toolKeys: string[];
}

export interface CapabilityUpdateInput {
  name?: string;
  description?: string;
  toolKeys?: string[];
}

export interface CapabilityRead {
  id: number;
  key: string;
  version: number;
  status: CapabilityStatus;
  name: string;
  description: string;
  toolKeys: string[];
  tools: CapabilityToolRead[];
  createdAt: string;
  updatedAt: string;
}

export interface CapabilityListRead {
  items: CapabilityRead[];
}

export interface CapabilityListParams {
  status?: CapabilityStatus;
}
