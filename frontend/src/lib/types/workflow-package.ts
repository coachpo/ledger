import type { UnknownRecord } from "./common";
import type { ModelConnectionKind } from "./model-connection";
import type { RunStatus } from "./run";

export type WorkflowPackageStatus = "draft" | "active";
export type WorkflowPackageManifestApiVersion = "signaldeck.workflowPackage/v1";
export type WorkflowPackageManifestDiagnosticSeverity = "error" | "warning";

export interface WorkflowPackageManifestRequest {
  manifestSource: string;
}

export interface WorkflowPackageManifestRead {
  packageId: number;
  packageKey: string;
  manifestSource: string;
  packageDefinition: UnknownRecord;
  manifestHash: string;
  compiledHash: string;
}

export interface WorkflowPackageUpdateRequest {
  manifestSource?: string | null;
  status?: WorkflowPackageStatus | null;
}

export interface WorkflowPackageSecretBindingRead {
  packageId: number;
  key: string;
  hasValue: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowPackageSecretBindingListRead {
  items: WorkflowPackageSecretBindingRead[];
}

export interface WorkflowPackageSecretBindingUpdateRequest {
  value: string;
}

export type WorkflowPackageImportRequest = WorkflowPackageManifestRequest;

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
  manifestHash: string | null;
  compiledHash: string | null;
  warnings: UnknownRecord[];
  createdAt: string;
  updatedAt: string;
  lastLaunchedAt: string | null;
}

export interface WorkflowPackageListRead {
  items: WorkflowPackageRead[];
}

export interface WorkflowPackageLaunchDiagnostic extends UnknownRecord {
  connectionKind?: ModelConnectionKind;
  field?: string;
  issue?: string;
  message?: string;
  path?: string;
  severity?: WorkflowPackageManifestDiagnosticSeverity | string;
}

export interface WorkflowPackageLaunchRead {
  packageId: number;
  packageKey: string;
  manifestHash: string;
  workflowKey: string;
  name: string;
  description: string;
  inputSchema: UnknownRecord;
  ready: boolean;
  blockingErrors: WorkflowPackageLaunchDiagnostic[];
  warnings: WorkflowPackageLaunchDiagnostic[];
}

export interface WorkflowPackageLaunchCreateRequest {
  workflowKey?: string | null;
  parameters?: UnknownRecord;
}

export interface WorkflowPackageLaunchCreateResponse {
  id: number;
  status: RunStatus;
  workflowPackageId: number;
  workflowPackageKey: string;
  workflowKey: string;
  createdAt: string;
}

export interface WorkflowPackageListParams {
  status?: WorkflowPackageStatus;
}
