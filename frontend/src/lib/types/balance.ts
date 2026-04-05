export interface BalanceRead {
  id: number;
  portfolioId: number;
  label: string;
  amount: string;
  currency: string;
  operationType: "DEPOSIT" | "WITHDRAWAL";
  hasTradingOperations: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface BalanceWriteInput {
  label: string;
  amount: string;
  operationType: "DEPOSIT" | "WITHDRAWAL";
}

export interface BalanceUpdateInput {
  label?: string;
  amount?: string;
  operationType?: "DEPOSIT" | "WITHDRAWAL";
}

export interface BalanceCompactRead {
  id: number;
  label: string;
  amount: string;
  currency: string;
}
