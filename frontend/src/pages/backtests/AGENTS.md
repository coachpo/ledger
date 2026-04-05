# FRONTEND BACKTEST PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/backtests/` contains the routed backtest list, configuration, and detail pages. These routes launch historical simulations, collect webhook settings, poll active callback states, and render result and report follow-up UI.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Inventory management | `list.tsx` | newest-first list, running progress bars, terminal delete, completed summary text |
| Simulation configuration | `config.tsx` | existing/new portfolio mode, optional default template creation, benchmark selection, and webhook URL/timeout settings |
| Detail orchestration | `detail.tsx` | 5s polling while active, recent activity, charts, trade log, report links |
| Query hooks | `../../hooks/use-backtests.ts` | list/detail queries plus create/cancel/delete mutations |
| Validation rules | `../../components/shared/form-schemas.ts` | `backtestCreateFormSchema` and the page-local validation summary |
| Result widgets | `../../components/backtests/AGENTS.md` | status badge, KPI cards, equity curve, drawdown, trade log |
| E2E coverage | `../../../e2e/backtests.spec.ts` | launch flow, polling until completion, result rendering, delete cleanup |

## CONVENTIONS
- `detail.tsx` relies on `useBacktest()` polling every 5 seconds for `PENDING`, `RUNNING`, `AWAITING_CALLBACK`, and `PROCESSING_CALLBACK` rows instead of manual timers in the page.
- `config.tsx` can create a new portfolio plus an initial `DEPOSIT` balance before calling `createBacktest`, so the route owns the cross-feature launch orchestration.
- `config.tsx` owns the webhook settings (`webhookUrl`, `webhookTimeout`) and pairs them with benchmark, commission, and template choices before submit.
- Completed runs derive report links from `results.trades[*].reportSlug`; navigation to `/reports/:slug` stays page-level.
- Validation is intentionally duplicated in two layers: `backtestCreateFormSchema` enforces structural rules, and `buildValidationMessages()` keeps the inline summary readable before submit.

## ANTI-PATTERNS
- Do not hand-roll backtest polling in the page body; keep that policy in `use-backtests.ts`.
- Do not bypass `ConfirmDeleteDialog` for terminal deletes or inline destructive buttons without confirmation.
- Do not hardcode alternative benchmark lists or result-link routes in child components when `config.tsx` and `detail.tsx` already define the live behavior.
- Do not move backtest launch logic into generic shared components; it depends on portfolio, template, and backtest route state.

## VALIDATION
```bash
cd frontend
pnpm test:run src/pages/backtests/list.test.tsx src/pages/backtests/config.test.tsx src/pages/backtests/detail.test.tsx
pnpm test:e2e --grep Backtests
```

## NOTES
- `list.tsx` shows delete only for `COMPLETED`, `FAILED`, and `CANCELLED` rows, matching the backend terminal-state contract.
- `detail.tsx` shows progress and recent activity while active, including explicit copy for `AWAITING_CALLBACK` vs `PROCESSING_CALLBACK`, then switches to charts and trade history once `results` are available.
