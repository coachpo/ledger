import type {
  PositionRead,
  PositionSymbolLookupRead,
  PositionWriteInput,
  PositionUpdateInput,
} from "../types/position";
import type { CsvPreviewRead, CsvCommitRead } from "../types/csv";
import { type IdParam, createCsvFormData, portfolioPath, request, toPathSegment } from "../api-client";

export function listPositions(
  portfolioId: IdParam,
  signal?: AbortSignal,
): Promise<PositionRead[]> {
  return request<PositionRead[]>(`${portfolioPath(portfolioId)}/positions`, {
    signal,
  });
}

export function createPosition(
  portfolioId: IdParam,
  input: PositionWriteInput,
  signal?: AbortSignal,
): Promise<PositionRead> {
  return request<PositionRead>(`${portfolioPath(portfolioId)}/positions`, {
    body: input,
    method: "POST",
    signal,
  });
}

export function getPositionSymbolLookup(
  portfolioId: IdParam,
  symbol: string,
  signal?: AbortSignal,
): Promise<PositionSymbolLookupRead> {
  return request<PositionSymbolLookupRead>(`${portfolioPath(portfolioId)}/positions/lookup`, {
    query: { symbol },
    signal,
  });
}

export function updatePosition(
  portfolioId: IdParam,
  positionId: IdParam,
  input: PositionUpdateInput,
  signal?: AbortSignal,
): Promise<PositionRead> {
  return request<PositionRead>(
    `${portfolioPath(portfolioId)}/positions/${toPathSegment(positionId)}`,
    {
      body: input,
      method: "PATCH",
      signal,
    },
  );
}

export function deletePosition(
  portfolioId: IdParam,
  positionId: IdParam,
  signal?: AbortSignal,
): Promise<void> {
  return request<void>(`${portfolioPath(portfolioId)}/positions/${toPathSegment(positionId)}`, {
    method: "DELETE",
    signal,
  });
}

export function previewPositionImport(
  portfolioId: IdParam,
  file: File,
  signal?: AbortSignal,
): Promise<CsvPreviewRead> {
  return request<CsvPreviewRead>(`${portfolioPath(portfolioId)}/positions/imports/preview`, {
    body: createCsvFormData(file),
    method: "POST",
    signal,
  });
}

export function commitPositionImport(
  portfolioId: IdParam,
  file: File,
  signal?: AbortSignal,
): Promise<CsvCommitRead> {
  return request<CsvCommitRead>(`${portfolioPath(portfolioId)}/positions/imports/commit`, {
    body: createCsvFormData(file),
    method: "POST",
    signal,
  });
}

export const positionsApi = {
  commitImport: commitPositionImport,
  create: createPosition,
  delete: deletePosition,
  list: listPositions,
  lookup: getPositionSymbolLookup,
  previewImport: previewPositionImport,
  update: updatePosition,
} as const;
