export interface PortfolioRead {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  baseCurrency: string;
  positionCount: number;
  balanceCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface PortfolioWriteInput {
  name: string;
  slug: string;
  description?: string | null;
  baseCurrency: string;
}

export interface PortfolioUpdateInput {
  name?: string;
  description?: string | null;
}
