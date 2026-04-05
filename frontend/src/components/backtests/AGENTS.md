# FRONTEND BACKTEST COMPONENTS GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/components/AGENTS.md`.

## OVERVIEW
`src/components/backtests/` contains the result widgets for the backtest workspace. These components stay presentational and consume the shared backtest wire contract from `src/lib/types/backtest.ts`.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Status badges | `backtest-status-badge.tsx` | maps all seven lifecycle states, including callback waits, to badge styles |
| KPI cards | `metrics-summary.tsx` | renders portfolio return, drawdown, sharpe, trade count, win rate, and commission |
| Equity curve | `equity-curve-chart.tsx` | normalizes the portfolio line, overlays benchmark curves, toggles benchmark visibility |
| Drawdown chart | `drawdown-chart.tsx` | renders drawdown points with the shared chart container |
| Trade history | `trade-log-table.tsx` | sortable table for cycle date, symbol, side, quantity, price, and execution status |
| Shared dependencies | `../shared/metric-card.tsx`, `../ui/chart.tsx`, `../ui/table.tsx`, `../../lib/format.ts` | layout, chart chrome, table primitives, and wire-string formatting |

## CONVENTIONS
- Components accept already-fetched backtest data and do not own query, mutation, or route state.
- `metrics-summary.tsx` formats wire-string numbers through `lib/format` instead of coercing them at the type layer.
- `equity-curve-chart.tsx` normalizes the portfolio curve to the starting value and keeps benchmark visibility in local UI state only.
- `trade-log-table.tsx` sorts client-side and uses the shared `ui/table` primitives instead of bespoke table markup.
- `backtest-status-badge.tsx` is the single source of truth for the full status palette: `PENDING`, `RUNNING`, `AWAITING_CALLBACK`, `PROCESSING_CALLBACK`, `COMPLETED`, `FAILED`, and `CANCELLED`.

## ANTI-PATTERNS
- Do not move backtest-specific chart math or sort behavior into `src/components/ui/`; these widgets are domain components.
- Do not redefine backtest status colors outside `backtest-status-badge.tsx`.
- Do not bypass `src/lib/types/backtest.ts` with ad-hoc prop types in result widgets.
- Do not promote these widgets into `shared/` until another feature truly reuses the same result contract.

## VALIDATION
```bash
cd frontend
pnpm test:run src/components/backtests/equity-curve-chart.test.tsx src/components/backtests/trade-log-table.test.tsx
```

## NOTES
- `equity-curve-chart.tsx` uses `ChartTooltipContent` for multi-series hover state and sanitizes benchmark symbols into CSS variable keys.
- `trade-log-table.tsx` sorts by date, symbol, action, quantity, price, and execution status without mutating the original trade array.
