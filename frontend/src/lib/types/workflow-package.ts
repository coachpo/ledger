import type { UnknownRecord } from "./common";
import type { RunStatus } from "./run";

export type WorkflowPackageStatus = "draft" | "active" | "archived";
export type WorkflowPackageImportMode = "create" | "createVersion";
export type WorkflowPackageManifestApiVersion = "ledger.workflowPackage/v1";
export type WorkflowPackageManifestDiagnosticSeverity = "error" | "warning";

export interface WorkflowPackageManifestRequest {
  manifestSource: string;
}

export interface WorkflowPackageUpdateRequest {
  manifestSource?: string | null;
  status?: WorkflowPackageStatus | null;
}

export interface WorkflowPackageImportRequest extends WorkflowPackageManifestRequest {
  mode?: WorkflowPackageImportMode;
}

export interface WorkflowPackageMetadataRead {
  apiVersion: WorkflowPackageManifestApiVersion | string;
  key: string;
  name: string;
  description: string;
}

export interface WorkflowPackageManifestDiagnostic {
  severity: WorkflowPackageManifestDiagnosticSeverity;
  message: string;
  path: string;
  line: number | null;
  column: number | null;
}

export interface WorkflowPackageValidationRead {
  diagnostics: WorkflowPackageManifestDiagnostic[];
  warnings: UnknownRecord[];
  metadata: WorkflowPackageMetadataRead | null;
  packageDefinition: UnknownRecord | null;
  compiledPlan: UnknownRecord | null;
  manifestHash: string | null;
  compiledHash: string | null;
}

export interface WorkflowPackageRead {
  id: number;
  key: string;
  name: string;
  description: string;
  status: WorkflowPackageStatus;
  latestVersion: number | null;
  latestVersionId: number | null;
  manifestHash: string | null;
  compiledHash: string | null;
  warnings: UnknownRecord[];
  createdAt: string;
  updatedAt: string;
  archivedAt: string | null;
}

export interface WorkflowPackageListRead {
  items: WorkflowPackageRead[];
}

export interface WorkflowPackageVersionRead {
  id: number;
  packageId: number;
  version: number;
  manifestHash: string;
  compiledHash: string;
  validationSummary: UnknownRecord;
  warnings: UnknownRecord[];
  createdAt: string;
  launchedAt: string | null;
}

export interface WorkflowPackageVersionListRead {
  items: WorkflowPackageVersionRead[];
}

export interface WorkflowPackageLaunchRead {
  packageId: number;
  packageKey: string;
  packageVersion: number;
  manifestHash: string;
  workflowKey: string;
  name: string;
  description: string;
  inputSchema: UnknownRecord;
  ready: boolean;
  blockingErrors: UnknownRecord[];
  warnings: UnknownRecord[];
}
export interface WorkflowPackageLaunchCreateRequest {
  version?: number | null;
  workflowKey?: string | null;
  parameters?: UnknownRecord;
}

export interface WorkflowPackageLaunchCreateResponse {
  id: number;
  status: RunStatus;
  workflowPackageId: number;
  workflowPackageKey: string;
  workflowPackageVersion: number;
  workflowKey: string;
  createdAt: string;
}

export interface WorkflowPackageListParams {
  status?: WorkflowPackageStatus;
  includeArchived?: boolean;
}

export interface WorkflowPackageVersionedRequestOptions {
  signal?: AbortSignal;
  version?: number;
  workflowKey?: string;
}
