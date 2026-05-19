import {
  buildPlatformApiUrl,
  requestPlatform,
  toPathSegment,
  toQueryRecord,
  type IdParam,
} from "../api-client";
import type {
  WorkflowPackageImportRequest,
  WorkflowPackageLaunchCreateRequest,
  WorkflowPackageLaunchCreateResponse,
  WorkflowPackageLaunchRead,
  WorkflowPackageListRead,
  WorkflowPackageManifestRead,
  WorkflowPackageManifestRequest,
  WorkflowPackageRead,
  WorkflowPackageSecretBindingListRead,
  WorkflowPackageSecretBindingRead,
  WorkflowPackageSecretBindingUpdateRequest,
  WorkflowPackageUpdateRequest,
  WorkflowPackageValidationRead,
} from "../types/workflow-package";

function workflowPackagePath(packageId: IdParam): string {
  return `/workflow-packages/${toPathSegment(packageId)}`;
}

function workflowPackageSecretBindingPath(packageId: IdParam, key: IdParam): string {
  return `${workflowPackagePath(packageId)}/secret-bindings/${toPathSegment(key)}`;
}

type WorkflowPackageWorkflowOptions = {
  signal?: AbortSignal;
  workflowKey?: string | null;
};

function workflowKeyQuery(options: WorkflowPackageWorkflowOptions = {}) {
  return toQueryRecord({
    workflowKey: options.workflowKey,
  });
}

export function listWorkflowPackages(signal?: AbortSignal): Promise<WorkflowPackageListRead> {
  return requestPlatform<WorkflowPackageListRead>("/workflow-packages", {
    signal,
  });
}

export function getWorkflowPackage(
  packageId: IdParam,
  signal?: AbortSignal,
): Promise<WorkflowPackageRead> {
  return requestPlatform<WorkflowPackageRead>(workflowPackagePath(packageId), { signal });
}

export function getWorkflowPackageManifest(
  packageId: IdParam,
  signal?: AbortSignal,
): Promise<WorkflowPackageManifestRead> {
  return requestPlatform<WorkflowPackageManifestRead>(`${workflowPackagePath(packageId)}/manifest`, {
    signal,
  });
}

export function validateWorkflowPackageManifest(
  payload: WorkflowPackageManifestRequest,
  signal?: AbortSignal,
): Promise<WorkflowPackageValidationRead> {
  return requestPlatform<WorkflowPackageValidationRead>("/workflow-packages/validate-manifest", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function createWorkflowPackage(
  payload: WorkflowPackageManifestRequest,
  signal?: AbortSignal,
): Promise<WorkflowPackageRead> {
  return requestPlatform<WorkflowPackageRead>("/workflow-packages", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function updateWorkflowPackage(
  packageId: IdParam,
  payload: WorkflowPackageUpdateRequest,
  signal?: AbortSignal,
): Promise<WorkflowPackageRead> {
  return requestPlatform<WorkflowPackageRead>(workflowPackagePath(packageId), {
    body: payload,
    method: "PATCH",
    signal,
  });
}

export function deleteWorkflowPackage(
  packageId: IdParam,
  signal?: AbortSignal,
): Promise<void> {
  return requestPlatform<void>(workflowPackagePath(packageId), {
    method: "DELETE",
    signal,
  });
}

export function listWorkflowPackageSecretBindings(
  packageId: IdParam,
  signal?: AbortSignal,
): Promise<WorkflowPackageSecretBindingListRead> {
  return requestPlatform<WorkflowPackageSecretBindingListRead>(`${workflowPackagePath(packageId)}/secret-bindings`, {
    signal,
  });
}

export function upsertWorkflowPackageSecretBinding(
  packageId: IdParam,
  key: IdParam,
  payload: WorkflowPackageSecretBindingUpdateRequest,
  signal?: AbortSignal,
): Promise<WorkflowPackageSecretBindingRead> {
  return requestPlatform<WorkflowPackageSecretBindingRead>(workflowPackageSecretBindingPath(packageId, key), {
    body: payload,
    method: "PUT",
    signal,
  });
}

export function deleteWorkflowPackageSecretBinding(
  packageId: IdParam,
  key: IdParam,
  signal?: AbortSignal,
): Promise<void> {
  return requestPlatform<void>(workflowPackageSecretBindingPath(packageId, key), {
    method: "DELETE",
    signal,
  });
}

export function importWorkflowPackage(
  payload: WorkflowPackageImportRequest,
  signal?: AbortSignal,
): Promise<WorkflowPackageRead> {
  return requestPlatform<WorkflowPackageRead>("/workflow-packages/import", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function exportWorkflowPackageUrl(packageId: IdParam): string {
  return buildPlatformApiUrl(`${workflowPackagePath(packageId)}/export`);
}

export function preflightWorkflowPackage(
  packageId: IdParam,
  options: WorkflowPackageWorkflowOptions = {},
): Promise<WorkflowPackageLaunchRead> {
  return requestPlatform<WorkflowPackageLaunchRead>(`${workflowPackagePath(packageId)}/preflight`, {
    method: "POST",
    query: workflowKeyQuery(options),
    signal: options.signal,
  });
}

export function getWorkflowPackageLaunch(
  packageId: IdParam,
  options: WorkflowPackageWorkflowOptions = {},
): Promise<WorkflowPackageLaunchRead> {
  return requestPlatform<WorkflowPackageLaunchRead>(`${workflowPackagePath(packageId)}/launch`, {
    query: workflowKeyQuery(options),
    signal: options.signal,
  });
}

export function createWorkflowPackageLaunch(
  packageId: IdParam,
  payload: WorkflowPackageLaunchCreateRequest,
  signal?: AbortSignal,
): Promise<WorkflowPackageLaunchCreateResponse> {
  return requestPlatform<WorkflowPackageLaunchCreateResponse>(`${workflowPackagePath(packageId)}/launches`, {
    body: payload,
    method: "POST",
    signal,
  });
}

export const workflowPackagesApi = {
  delete: deleteWorkflowPackage,
  deleteSecretBinding: deleteWorkflowPackageSecretBinding,
  create: createWorkflowPackage,
  createLaunch: createWorkflowPackageLaunch,
  exportUrl: exportWorkflowPackageUrl,
  get: getWorkflowPackage,
  getLaunch: getWorkflowPackageLaunch,
  getManifest: getWorkflowPackageManifest,
  import: importWorkflowPackage,
  list: listWorkflowPackages,
  listSecretBindings: listWorkflowPackageSecretBindings,
  preflight: preflightWorkflowPackage,
  update: updateWorkflowPackage,
  upsertSecretBinding: upsertWorkflowPackageSecretBinding,
  validateManifest: validateWorkflowPackageManifest,
} as const;
