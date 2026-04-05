export type CsvImportMode = "upsert";

export interface CsvAcceptedRow {
  row: number;
  symbol: string;
  quantity: string;
  averageCost: string;
  name: string | null;
}

export interface CsvRowError {
  row: number;
  field: string;
  issue: string;
}

export interface CsvPreviewRead {
  fileName: string;
  mode: CsvImportMode;
  acceptedRows: CsvAcceptedRow[];
  errors: CsvRowError[];
}

export interface CsvCommitRead {
  fileName: string;
  mode: CsvImportMode;
  inserted: number;
  updated: number;
  unchanged: number;
  errors: CsvRowError[];
}
