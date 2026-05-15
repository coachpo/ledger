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
  WorkflowPackageListParams,
  WorkflowPackageListRead,
  WorkflowPackageManifestRead,
  WorkflowPackageManifestReadOptions,
  WorkflowPackageManifestRequest,
  WorkflowPackageRead,
  WorkflowPackageSecretBindingListRead,
  WorkflowPackageSecretBindingRead,
  WorkflowPackageSecretBindingUpdateRequest,
  WorkflowPackageUpdateRequest,
  WorkflowPackageValidationRead,
  WorkflowPackageVersionedRequestOptions,
  WorkflowPackageVersionListRead,
} from "../types/workflow-package";

function workflowPackagePath(packageId: IdParam): string {
  return `/workflow-packages/${toPathSegment(packageId)}`;
}

function workflowPackageSecretBindingPath(packageId: IdParam, key: IdParam): string {
  return `${workflowPackagePath(packageId)}/secret-bindings/${toPathSegment(key)}`;
}

function normalizeManifestVersion(version: number | string | null | undefined) {
  return version === undefined || version === null || version === "" ? undefined : version;
}

function manifestReadQuery(options: WorkflowPackageManifestReadOptions = {}) {
  return toQueryRecord({
    version: normalizeManifestVersion(options.version),
  });
}

function versionedWorkflowQuery(options: WorkflowPackageVersionedRequestOptions = {}) {
  return toQueryRecord({
    version: options.version,
    workflowKey: options.workflowKey,
  });
}

export function listWorkflowPackages(
  params: WorkflowPackageListParams = {},
  signal?: AbortSignal,
): Promise<WorkflowPackageListRead> {
  return requestPlatform<WorkflowPackageListRead>("/workflow-packages", {
    query: toQueryRecord(params),
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
  options: WorkflowPackageManifestReadOptions = {},
): Promise<WorkflowPackageManifestRead> {
  return requestPlatform<WorkflowPackageManifestRead>(`${workflowPackagePath(packageId)}/manifest`, {
    query: manifestReadQuery(options),
    signal: options.signal,
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

export function listWorkflowPackageVersions(
  packageId: IdParam,
  signal?: AbortSignal,
): Promise<WorkflowPackageVersionListRead> {
  return requestPlatform<WorkflowPackageVersionListRead>(`${workflowPackagePath(packageId)}/versions`, {
    signal,
  });
}

export function createWorkflowPackageVersion(
  packageId: IdParam,
  payload: WorkflowPackageManifestRequest,
  signal?: AbortSignal,
): Promise<WorkflowPackageRead> {
  return requestPlatform<WorkflowPackageRead>(`${workflowPackagePath(packageId)}/versions`, {
    body: payload,
    method: "POST",
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

export function exportWorkflowPackageUrl(
  packageId: IdParam,
  version?: number,
): string {
  const url = new URL(buildPlatformApiUrl(`${workflowPackagePath(packageId)}/export`));
  if (version !== undefined) {
    url.searchParams.set("version", String(version));
  }
  return url.toString();
}

export function preflightWorkflowPackage(
  packageId: IdParam,
  options: WorkflowPackageVersionedRequestOptions = {},
): Promise<WorkflowPackageLaunchRead> {
  return requestPlatform<WorkflowPackageLaunchRead>(`${workflowPackagePath(packageId)}/preflight`, {
    method: "POST",
    query: versionedWorkflowQuery(options),
    signal: options.signal,
  });
}

export function getWorkflowPackageLaunch(
  packageId: IdParam,
  options: WorkflowPackageVersionedRequestOptions = {},
): Promise<WorkflowPackageLaunchRead> {
  return requestPlatform<WorkflowPackageLaunchRead>(`${workflowPackagePath(packageId)}/launch`, {
    query: versionedWorkflowQuery(options),
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
  createVersion: createWorkflowPackageVersion,
  exportUrl: exportWorkflowPackageUrl,
  get: getWorkflowPackage,
  getLaunch: getWorkflowPackageLaunch,
  getManifest: getWorkflowPackageManifest,
  import: importWorkflowPackage,
  list: listWorkflowPackages,
  listSecretBindings: listWorkflowPackageSecretBindings,
  listVersions: listWorkflowPackageVersions,
  preflight: preflightWorkflowPackage,
  update: updateWorkflowPackage,
  upsertSecretBinding: upsertWorkflowPackageSecretBinding,
  validateManifest: validateWorkflowPackageManifest,
} as const;
