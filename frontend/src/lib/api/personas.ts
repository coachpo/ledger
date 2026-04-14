import { type IdParam, type RequestQueryValue, requestV2, toPathSegment } from "../api-client";
import type {
  PersonaProfileDraftCreateInput,
  PersonaProfileDraftUpdateInput,
  PersonaProfileListParams,
  PersonaProfileListRead,
  PersonaProfileRead,
  StudioVersionHistoryRead,
} from "../types/studio";

function personasPath(): string {
  return "/studio/persona-profiles";
}

function personaPath(personaKey: IdParam): string {
  return `${personasPath()}/${toPathSegment(personaKey)}`;
}

function personaVersionsPath(personaKey: IdParam): string {
  return `${personaPath(personaKey)}/versions`;
}

function personaVersionPath(personaKey: IdParam, version: number | string): string {
  return `${personaVersionsPath(personaKey)}/${toPathSegment(version)}`;
}

function toQueryRecord<T extends object>(
  params?: T,
): Record<string, RequestQueryValue> | undefined {
  return params as Record<string, RequestQueryValue> | undefined;
}

export function listPersonas(
  params?: PersonaProfileListParams,
  signal?: AbortSignal,
): Promise<PersonaProfileListRead> {
  return requestV2<PersonaProfileListRead>(personasPath(), {
    query: toQueryRecord(params),
    signal,
  });
}

export function getPersona(personaKey: IdParam, signal?: AbortSignal): Promise<PersonaProfileRead> {
  return requestV2<PersonaProfileRead>(personaPath(personaKey), { signal });
}

export function createPersona(payload: PersonaProfileDraftCreateInput): Promise<PersonaProfileRead> {
  return requestV2<PersonaProfileRead>(personasPath(), {
    body: payload,
    method: "POST",
  });
}

export function listPersonaVersions(
  personaKey: IdParam,
  signal?: AbortSignal,
): Promise<StudioVersionHistoryRead> {
  return requestV2<StudioVersionHistoryRead>(personaVersionsPath(personaKey), { signal });
}

export function getPersonaVersion(
  personaKey: IdParam,
  version: number | string,
  signal?: AbortSignal,
): Promise<PersonaProfileRead> {
  return requestV2<PersonaProfileRead>(personaVersionPath(personaKey, version), { signal });
}

export function updatePersonaVersion(
  personaKey: IdParam,
  version: number | string,
  payload: PersonaProfileDraftUpdateInput,
): Promise<PersonaProfileRead> {
  return requestV2<PersonaProfileRead>(personaVersionPath(personaKey, version), {
    body: payload,
    method: "PATCH",
  });
}

export function activatePersonaVersion(
  personaKey: IdParam,
  version: number | string,
): Promise<PersonaProfileRead> {
  return requestV2<PersonaProfileRead>(`${personaVersionPath(personaKey, version)}/activate`, {
    method: "POST",
  });
}

export function deprecatePersonaVersion(
  personaKey: IdParam,
  version: number | string,
): Promise<PersonaProfileRead> {
  return requestV2<PersonaProfileRead>(`${personaVersionPath(personaKey, version)}/deprecate`, {
    method: "POST",
  });
}

export function archivePersonaVersion(
  personaKey: IdParam,
  version: number | string,
): Promise<PersonaProfileRead> {
  return requestV2<PersonaProfileRead>(`${personaVersionPath(personaKey, version)}/archive`, {
    method: "POST",
  });
}

export const personasApi = {
  activate: activatePersonaVersion,
  archive: archivePersonaVersion,
  create: createPersona,
  deprecate: deprecatePersonaVersion,
  get: getPersona,
  getVersion: getPersonaVersion,
  list: listPersonas,
  listVersions: listPersonaVersions,
  updateVersion: updatePersonaVersion,
} as const;
