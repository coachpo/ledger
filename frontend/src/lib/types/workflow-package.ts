import type { UnknownRecord } from "./common";
import type { ModelConnectionKind } from "./model-connection";
import type { RunStatus } from "./run";

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
  manifestHash: string | null;
  compiledHash: string | null;
  createdAt: string;
  updatedAt: string;
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

export type WorkflowPackageRuntimeInputSlot = "history" | "personal";

export interface WorkflowPackageRuntimeInputStaleReason {
  field: string;
  issue: string;
  stored: string | null;
  current: string | null;
}

export interface WorkflowPackageRuntimeInputStaleRead {
  stale: boolean;
  reasons: WorkflowPackageRuntimeInputStaleReason[];
}

export interface WorkflowPackageRuntimeInputCurrentMetadataRead {
  workflowKey: string;
  manifestHash: string;
  compiledHash: string;
  schemaFingerprint: string;
  inputSchema: UnknownRecord;
}

export interface WorkflowPackageRuntimeInputEntryRead {
  id: number;
  packageId: number;
  workflowKey: string;
  slot: WorkflowPackageRuntimeInputSlot;
  name: string | null;
  payload: UnknownRecord;
  sourceKind: string;
  manifestHash: string;
  compiledHash: string;
  schemaFingerprint: string;
  inputSchemaSnapshot: UnknownRecord | null;
  sourceRunId: number | null;
  stale: WorkflowPackageRuntimeInputStaleRead;
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowPackageRuntimeInputRegistryRead {
  packageId: number;
  packageKey: string;
  workflowKey: string;
  currentMetadata: WorkflowPackageRuntimeInputCurrentMetadataRead | null;
  personal: WorkflowPackageRuntimeInputEntryRead[];
  history: WorkflowPackageRuntimeInputEntryRead[];
}

export interface WorkflowPackageRuntimeInputPersonalEntryCreateRequest {
  name?: string | null;
  payload: UnknownRecord;
}

export interface WorkflowPackageRuntimeInputPersonalEntryUpdateRequest {
  name?: string | null;
  payload?: UnknownRecord;
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

