export interface ApiErrorDetail {
  field: string;
  issue: string;
}

export interface ApiErrorResponse {
  code: string;
  message: string;
  details: ApiErrorDetail[];
}

export type UnknownRecord = Record<string, unknown>;
