export type CapabilityStatus = "draft" | "published" | "deprecated" | "archived";

export interface CapabilityToolGrantWrite {
  tool: string;
}

export interface CapabilityToolGrantRead extends CapabilityToolGrantWrite {
  displayName: string;
  description: string;
}

export interface CapabilityCreateInput {
  key: string;
  name: string;
  description?: string;
  toolGrants: CapabilityToolGrantWrite[];
}

export interface CapabilityUpdateInput {
  name?: string;
  description?: string;
  toolGrants?: CapabilityToolGrantWrite[];
}

export interface CapabilityRead {
  id: number;
  key: string;
  version: number;
  status: CapabilityStatus;
  name: string;
  description: string;
  toolGrants: CapabilityToolGrantRead[];
  createdAt: string;
  updatedAt: string;
}

export interface CapabilityListRead {
  items: CapabilityRead[];
}

export interface CapabilityListParams {
  status?: CapabilityStatus;
}
