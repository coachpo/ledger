# FRONTEND API MODULES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/lib/AGENTS.md`.

## OVERVIEW
`src/lib/api/` contains resource-specific request helpers layered on top of `api-client.ts`. These modules are the only frontend code that should know endpoint paths, multipart upload details, and download URL construction.

## STRUCTURE
```text
src/lib/api/
├── portfolios.ts          # portfolio CRUD
├── balances.ts            # portfolio-scoped balance CRUD
├── positions.ts           # position CRUD, lookup, CSV preview/commit
├── trading-operations.ts  # BUY/SELL/DIVIDEND/SPLIT requests
├── market-data.ts         # quotes and history requests
├── templates.ts           # template CRUD, compile, placeholder tree
├── reports.ts             # list/detail, compile, upload, download URL
└── backtests.ts           # list/detail, create, cancel, delete
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Shared fetch/error behavior | `../api-client.ts` | base URL, error envelope parsing, query encoding |
| Template contract | `templates.ts` | stored CRUD, inline compile, placeholder tree |
| Report contract | `reports.ts` | slug-based reads, compile, upload, download helper |
| Backtest contract | `backtests.ts` | id-based lifecycle endpoints for historical simulations |
| CSV import endpoints | `positions.ts` | preview/commit upload helpers |
| Market data endpoints | `market-data.ts` | quotes/history query serialization |

## CONVENTIONS
- One module per backend resource family; keep path helpers and request bodies close to that resource.
- Always route network calls through `request()` or `buildUrl()` from `api-client.ts`.
- Keep upload/download specifics here: multipart report upload, CSV preview/commit, and markdown download URLs should not leak into hooks or pages.
- Keep backtest lifecycle semantics here as well: `POST /backtests`, `POST /backtests/{id}/cancel`, and `DELETE /backtests/{id}` should not be hand-built in hooks or pages.
- Match backend casing exactly; request/response types come from `../types/*` rather than inline object literals.

## ANTI-PATTERNS
- Do not call `fetch` directly from hooks or pages when a helper belongs here.
- Do not mix multiple resource domains into one helper file just because the UI screen uses them together.
- Do not put toasts, navigation, or React state in this directory.
- Do not hand-build download paths outside `reports.ts`; keep absolute URL generation centralized.
