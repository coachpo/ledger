export interface PositionRead {
  id: number;
  portfolioId: number;
  symbol: string;
  name: string | null;
  quantity: string;
  averageCost: string;
  currency: string;
  createdAt: string;
  updatedAt: string;
}

export interface PositionWriteInput {
  symbol: string;
  name?: string | null;
  quantity: string;
  averageCost: string;
}

export interface PositionSymbolLookupRead {
  symbol: string;
  name: string | null;
}

export interface PositionUpdateInput {
  name?: string | null;
  quantity?: string;
  averageCost?: string;
}

export interface PositionCompactRead {
  symbol: string;
  quantity: string;
  averageCost: string;
  currency: string;
}
