export type ApiErrorDetailValue = string | number | boolean | null;

export type ApiErrorDetail = {
  field?: string;
  issue?: string;
  [key: string]: ApiErrorDetailValue | undefined;
};

export interface ApiErrorResponse {
  code: string;
  message: string;
  details: ApiErrorDetail[];
}

export type UnknownRecord = Record<string, unknown>;
