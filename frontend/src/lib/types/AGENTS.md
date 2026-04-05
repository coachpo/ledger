# FRONTEND SHARED TYPES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/lib/AGENTS.md`.

## OVERVIEW
`src/lib/types/` mirrors the backend wire contracts for portfolios, balances, positions, market data, templates, reports, CSV import, trading operations, and backtests. Treat these files as the shared schema boundary between frontend UI and backend API.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Portfolio/balance/position types | `portfolio.ts`, `balance.ts`, `position.ts` | CRUD payloads plus read models |
| Trading payload unions | `trading.ts` | BUY/SELL/DIVIDEND/SPLIT request shapes |
| Backtest contracts | `backtest.ts` | status/frequency enums, webhook fields, current-cycle status, recent activity, curves, trade log, and results |
| Market data types | `market-data.ts` | quote/history payloads and warnings |
| Template contract | `text-template.ts` | template CRUD, compile, runtime-input maps, placeholder tree |
| Report contract | `report.ts` | slug-based report reads, metadata, update input |
| Shared helpers | `common.ts`, `csv.ts` | common ids/timestamps and CSV preview shapes |

## CONVENTIONS
- Keep frontend field names aligned with backend camelCase aliases; do not reintroduce snake_case here.
- Money, quantities, market values, and similar numeric payloads stay as strings on the wire; conversion belongs in shared formatting/analytics helpers, not in the type layer.
- Model enum-like values as exact string unions so invalid report sources, trading sides, or operation types fail at compile time.
- Use these files for API shapes only; derive view models separately when the UI needs extra formatting or enrichment.
- Unknown report metadata keys are allowed by the backend; preserve extensibility in `report.ts` instead of narrowing metadata too aggressively.
- Backtest wire contracts must mirror the backend callback lifecycle exactly, including `AWAITING_CALLBACK` and `PROCESSING_CALLBACK`, plus `webhookUrl`, `webhookTimeout`, and `currentCycleStatus` on reads.
- Backtest result types intentionally omit backend-only `_run_state` bookkeeping; frontend `results` should model final user-facing output only.

## ANTI-PATTERNS
- Do not declare ad-hoc wire types inside hooks or page components.
- Do not collapse backend distinctions such as slug-based report lookup vs numeric portfolio ids.
- Do not collapse the distinction between slug-based report routes and numeric backtest ids when building shared route contracts.
- Do not collapse callback-aware backtest statuses into a generic `RUNNING` type; polling and status-badge logic depend on the explicit union values.
- Do not convert decimal strings to numbers at the type layer.
- Do not change template/report placeholder tree shapes without coordinating backend schemas, hooks, and tests.
- Do not expose backend-only `_run_state` internals in frontend result contracts.
