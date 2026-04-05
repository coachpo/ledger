import type { PortfolioRead, PortfolioWriteInput, PortfolioUpdateInput } from "../types/portfolio";
import { type IdParam, portfolioPath, request } from "../api-client";

export function listPortfolios(signal?: AbortSignal): Promise<PortfolioRead[]> {
  return request<PortfolioRead[]>("/portfolios", { signal });
}

export function createPortfolio(
  input: PortfolioWriteInput,
  signal?: AbortSignal,
): Promise<PortfolioRead> {
  return request<PortfolioRead>("/portfolios", {
    body: input,
    method: "POST",
    signal,
  });
}

export function getPortfolio(
  portfolioId: IdParam,
  signal?: AbortSignal,
): Promise<PortfolioRead> {
  return request<PortfolioRead>(portfolioPath(portfolioId), { signal });
}

export function updatePortfolio(
  portfolioId: IdParam,
  input: PortfolioUpdateInput,
  signal?: AbortSignal,
): Promise<PortfolioRead> {
  return request<PortfolioRead>(portfolioPath(portfolioId), {
    body: input,
    method: "PATCH",
    signal,
  });
}

export function deletePortfolio(portfolioId: IdParam, signal?: AbortSignal): Promise<void> {
  return request<void>(portfolioPath(portfolioId), {
    method: "DELETE",
    signal,
  });
}

export const portfoliosApi = {
  create: createPortfolio,
  delete: deletePortfolio,
  get: getPortfolio,
  list: listPortfolios,
  update: updatePortfolio,
} as const;
