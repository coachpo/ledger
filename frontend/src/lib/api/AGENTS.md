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
├── simulations.ts           # list/detail, create, cancel, delete
└── orchestration.ts       # roles, characters, mention catalog
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Shared fetch/error behavior | `../api-client.ts` | base URL, error envelope parsing, query encoding |
| Template contract | `templates.ts` | stored CRUD, inline compile, placeholder tree |
| Report contract | `reports.ts` | slug-based reads, compile, upload, download helper |
| Simulation contract | `simulations.ts` | id-based lifecycle endpoints for historical simulations |
| Orchestration contract | `orchestration.ts` | role/character CRUD plus mention catalog |
| CSV import endpoints | `positions.ts` | preview/commit upload helpers |
| Market data endpoints | `market-data.ts` | quotes/history query serialization |

## CONVENTIONS
- One module per backend resource family; keep path helpers and request bodies close to that resource.
- Always route network calls through `request()` or `buildUrl()` from `api-client.ts`.
- Keep upload/download specifics here: multipart report upload, CSV preview/commit, and markdown download URLs should not leak into hooks or pages.
- Keep simulation lifecycle semantics here as well: `POST /simulations`, `POST /simulations/{id}/cancel`, and `DELETE /simulations/{id}` should not be hand-built in hooks or pages.
- `simulations.ts` mirrors the current backend contract as-is, including retained legacy webhook fields on create/read payloads even though normal execution is now internal LangGraph.
- `orchestration.ts` mirrors the current backend contract for roles, characters, and mention catalog access; keep hooks/pages thin around it.
- Match backend casing exactly; request/response types come from `../types/*` rather than inline object literals.

## ANTI-PATTERNS
- Do not call `fetch` directly from hooks or pages when a helper belongs here.
- Do not mix multiple resource domains into one helper file just because the UI screen uses them together.
- Do not put toasts, navigation, or React state in this directory.
- Do not hand-build download paths outside `reports.ts`; keep absolute URL generation centralized.
- Do not bypass `request()` for orchestration routes or mention-catalog requests.
