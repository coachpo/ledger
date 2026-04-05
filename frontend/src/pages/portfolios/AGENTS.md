# FRONTEND PORTFOLIO PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/portfolios/` contains the routed portfolio list and portfolio detail workspace. These pages orchestrate CRUD flows, quote enrichment, section dialogs, and portfolio-scoped invalidation.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Portfolio inventory | `list.tsx` | create/edit/delete flows and route entry into a workspace |
| Portfolio workspace | `detail.tsx` | balances, positions, trades, quote-enriched metrics |
| Portfolio UI sections | `../../components/portfolios/AGENTS.md` | tables, dialogs, trading forms |
| Shared analytics | `../../lib/portfolio-analytics.ts` | market value, PnL, allocation, signed balances |
| Mutation invalidation | `../../lib/query-keys.ts`, `../../hooks/use-*.ts` | `invalidatePortfolioScope()` behavior |

## CONVENTIONS
- `detail.tsx` is the orchestration hub: it loads portfolio data, balances, positions, trades, and market data, then enriches positions with shared analytics helpers.
- Quote fetching is portfolio-scoped and derives its symbol set from current positions; missing quotes degrade gracefully instead of blocking the page.
- Dialog state stays local to the page while request/mutation logic stays in hooks and feature components.

## ANTI-PATTERNS
- Do not duplicate analytics math in the page body when `portfolio-analytics.ts` already owns it.
- Do not issue one market-data request per position; keep the bulk quote/history flow intact.
- Do not bypass `invalidatePortfolioScope()` after portfolio-scoped writes.
