import type { ApiErrorDetail, ApiErrorResponse } from "./types/common";

export type RequestMethod = "DELETE" | "GET" | "PATCH" | "POST";
export type RequestQueryValue = boolean | number | string | null | undefined;

export interface RequestOptions {
  body?: FormData | object | null;
  headers?: HeadersInit;
  method?: RequestMethod;
  query?: Record<string, RequestQueryValue>;
  signal?: AbortSignal;
}

export interface ApiRequestErrorOptions {
  code: string;
  details?: ApiErrorDetail[];
  message: string;
  status: number;
}

export type IdParam = number | string;

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000/api/v1";
const API_BASE_URL = normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL);

export class ApiRequestError extends Error {
  readonly code: string;
  readonly details: ApiErrorDetail[];
  readonly status: number;

  constructor({ status, code, message, details = [] }: ApiRequestErrorOptions) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
    this.details = details;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

function normalizeApiBaseUrl(value: string | undefined): string {
  const normalized = value?.trim();

  if (!normalized) {
    return DEFAULT_API_BASE_URL;
  }

  return normalized.endsWith("/") ? normalized.slice(0, -1) : normalized;
}

export function toPathSegment(value: IdParam): string {
  return encodeURIComponent(String(value));
}

export function buildApiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}

function buildQueryString(query?: Record<string, RequestQueryValue>): string {
  if (!query) {
    return "";
  }

  const searchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null) {
      continue;
    }

    searchParams.set(key, String(value));
  }

  return searchParams.toString();
}

function buildUrl(path: string, query?: Record<string, RequestQueryValue>): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const queryString = buildQueryString(query);

  if (!queryString) {
    return `${API_BASE_URL}${normalizedPath}`;
  }

  return `${API_BASE_URL}${normalizedPath}?${queryString}`;
}

function isApiErrorDetail(value: unknown): value is ApiErrorDetail {
  if (!value || typeof value !== "object") {
    return false;
  }

  return (
    typeof Reflect.get(value, "field") === "string" &&
    typeof Reflect.get(value, "issue") === "string"
  );
}

async function toApiRequestError(response: Response): Promise<ApiRequestError> {
  const defaultMessage = `Request failed with status ${response.status}`;
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    const payload = (await response.json()) as
      | (Partial<ApiErrorResponse> & { detail?: unknown })
      | null;

    return new ApiRequestError({
      status: response.status,
      code: typeof payload?.code === "string" ? payload.code : "request_failed",
      message:
        typeof payload?.message === "string"
          ? payload.message
          : typeof payload?.detail === "string"
            ? payload.detail
            : defaultMessage,
      details: Array.isArray(payload?.details)
        ? payload.details.filter(isApiErrorDetail)
        : [],
    });
  }

  const text = await response.text();

  return new ApiRequestError({
    status: response.status,
    code: "request_failed",
    message: text || defaultMessage,
  });
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const method = options.method ?? "GET";
  let body: BodyInit | undefined;

  if (options.body instanceof FormData) {
    body = options.body;
  } else if (options.body !== undefined && options.body !== null) {
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    body = JSON.stringify(options.body);
  }

  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }

  const response = await fetch(buildUrl(path, options.query), {
    body,
    headers,
    method,
    signal: options.signal,
  });

  if (!response.ok) {
    throw await toApiRequestError(response);
  }

  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }

  const text = await response.text();

  if (!text) {
    return undefined as T;
  }

  return JSON.parse(text) as T;
}

export function createCsvFormData(file: File): FormData {
  const formData = new FormData();
  formData.append("file", file, file.name);
  return formData;
}

export function serializeSymbols(symbols: readonly string[]): string {
  return symbols
    .map((symbol) => symbol.trim())
    .filter((symbol) => symbol.length > 0)
    .join(",");
}

export function portfolioPath(portfolioId: IdParam): string {
  return `/portfolios/${toPathSegment(portfolioId)}`;
}
