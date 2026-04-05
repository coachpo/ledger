# FRONTEND PORTFOLIOS GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/components/AGENTS.md`. This file only covers `src/components/portfolios/`.

## OVERVIEW
`src/components/portfolios/` owns the portfolio workspace sections, dialogs, tables, and trading forms that support the routed list/detail pages. It also contains a couple of generic dialogs that other features reuse.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Portfolio list route | `../../pages/portfolios/list.tsx` | portfolio creation, navigation, overview cards |
| Portfolio workspace route | `../../pages/portfolios/detail.tsx` | orchestrates hooks, quotes, analytics, tabs, dialogs |
| Balances section | `portfolio-balances-section.tsx`, `balance-form-dialog.tsx` | balance table + create/edit dialog |
| Positions section | `portfolio-positions-section.tsx`, `position-form-dialog.tsx` | position table, quote warnings, create/edit dialog |
| Trading operations | `portfolio-trades-section.tsx`, `record-trading-operation-dialog.tsx`, `trading-operation-form.tsx` | operation history + BUY/SELL/DIVIDEND/SPLIT flows |
| Shared dialogs | `../forms/portfolio-form-dialog.tsx`, `confirm-delete-dialog.tsx` | create/edit/delete flows reused across routes |
| Focused tests | `*.test.tsx` | portfolio form, positions, trades, trading-operation dialog/form |

## CONVENTIONS
- Page components orchestrate hooks, analytics helpers, and local dialog state; section/dialog components keep narrower responsibilities.
- Quote-enriched position metrics come from `src/lib/portfolio-analytics.ts`, not inline page math.
- Use `formatCurrency()` and `formatDateTime()` for display consistency.
- Quote warnings are informational; show them without blocking the rest of the workspace.
- Mutation success/error feedback uses toasts close to the routed page or section that initiated the action.
- `ConfirmDeleteDialog` stays presentation-oriented so template pages can reuse it without importing portfolio-specific data logic.

## ANTI-PATTERNS
- Do not scatter decimal parsing across portfolio components; prefer shared analytics/format helpers and keep any current page-level aggregate parsing localized.
- Do not bypass section/dialog components by stuffing every portfolio action into the detail page.
- Do not treat quote-warning states as fatal for balances, positions, or trade history.
- Do not change CSV import, trade, or balance contract assumptions without coordinating with backend tests, `src/lib/api/positions.ts`, and `src/hooks/use-positions.ts`.
- Do not move request or mutation logic into table-only helpers just because the UI is tabular.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
pnpm build
```

## NOTES
- `../../pages/portfolios/detail.tsx` is the main orchestration hub: it combines portfolio, balance, position, trade, and quote hooks in one workspace.
- `../../pages/portfolios/detail.tsx` still computes the cash aggregate locally from balance strings; keep similar exceptions isolated rather than spreading parse logic through sections/dialogs.
