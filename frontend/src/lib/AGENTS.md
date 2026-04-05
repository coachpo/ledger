# FRONTEND LIB GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This file only covers `src/lib/`.

## OVERVIEW
`src/lib/` owns the frontend API contract, query-key naming, derived portfolio analytics, formatting helpers, markdown formatting, report grouping helpers, runtime-input row helpers, and shared type definitions for portfolio, market-data, CSV, template, report, and backtest flows.

## CHILD DOCS
- `api/AGENTS.md` — resource request helpers and upload/download boundaries
- `types/AGENTS.md` — shared TypeScript wire contracts and enum-like unions

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| HTTP wrapper / error mapping | `api-client.ts` | `request()`, `ApiRequestError`, `buildUrl()`, CSV form-data helpers |
| API endpoint functions | `api/*.ts` | domain-specific modules for portfolios, balances, positions, trading operations, market data, templates, reports, and backtests |
| Shared wire types | `types/*.ts` | domain-specific type definitions, including text-template and report types |
| Backtest contracts | `api/backtests.ts`, `types/backtest.ts` | lifecycle endpoints plus webhook fields, callback-aware statuses, result, trade, and curve wire shapes |
| Query key factory | `query-keys.ts` | hierarchical keys, param normalization, template/report keys, `invalidatePortfolioScope()` |
| Portfolio analytics | `portfolio-analytics.ts` | quote enrichment, market value, PnL, allocation |
| Display formatting | `format.ts` | currency, decimal, percent, date/datetime, compact numbers |
| Markdown formatting | `markdown-format.ts` | Prettier-backed markdown normalization for the template editor |
| Runtime input helpers | `runtime-inputs.ts` | row ids, row-to-map conversion, shared editor/report-generation helpers |
| Report grouping | `report-grouping.ts` | report list filtering, grouping, and sort helpers |
| Unit coverage | `api.test.ts`, `query-keys.test.ts`, `portfolio-analytics.test.ts`, `format.test.ts`, `markdown-format.test.ts` | contract and helper regressions |

## CONVENTIONS
- `api-client.ts` is the only place that should know the base URL, query-string encoding, and error-envelope parsing.
- `api-client.ts` falls back to `http://127.0.0.1:8000/api/v1` only when `VITE_API_BASE_URL` is absent; `start.sh` and Playwright override that value for real runs.
- Domain-specific API functions live in `api/*.ts` modules, organized by resource type.
- Wire decimals remain strings until shared format/analytics helpers convert them for display math.
- `query-keys.ts` normalizes ids as strings, symbol lists as trimmed uppercase sets, and history params so cache keys stay stable across callers.
- `invalidatePortfolioScope()` is the default invalidation path for portfolio-scoped mutations; templates use their own `queryKeys.templates.*` namespace.
- Report flows use `queryKeys.reports.*`; `downloadReportUrl()` stays in the API layer because it builds the absolute file URL from the configured API base.
- `runtime-inputs.ts` is the shared translator between editable key/value rows and trimmed `TemplateRuntimeInputs` maps for preview and report generation.
- `report-grouping.ts` is frontend-only derived-view logic; backend report endpoints stay flat while grouping/search/sort are composed locally.
- Backtest flows use `queryKeys.backtests.list()` and `.detail(id)` only; polling policy lives in hooks, but the cache-key contract lives here.
- Frontend API helpers only call the CRUD backtest endpoints; callback endpoints under `/backtests/{id}/cycles/*` are backend-to-webhook integration surfaces, not browser-facing requests.
- Report detail queries are slug-scoped, not numeric-id scoped, even though some shared helper signatures still use generic `IdParam` naming.

## ANTI-PATTERNS
- Do not hard-code endpoint paths or duplicate `request()` behavior in hooks/components.
- Do not bypass `api-client.ts` and call `fetch` directly.
- Do not create API functions outside the `api/*.ts` domain modules.
- Do not invent new query-key shapes outside `query-keys.ts`.
- Do not duplicate backend contract types when `types/*.ts` already exposes them.
- Do not change template, CSV, or error-envelope shapes here without updating the backend contract and the calling hooks/pages.
- Do not change report, upload-metadata, or placeholder-tree shapes here without updating the backend contract and the calling hooks/pages.
- Do not change backtest request or result shapes here without updating `backend/app/schemas/backtest.py`, hooks, pages, and tests together.
- Do not change `api/` helpers or `types/` contracts in isolation; keep request helpers and wire shapes in sync.
- Do not mix presentation-only formatting into API wrapper code.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
pnpm build
```

## NOTES
- Route code should import direct modules from `api/*` and `types/*` instead of relying on barrel re-exports.
- `markdown-format.ts` centralizes Prettier-based markdown cleanup so the template editor does not embed formatter setup inline.
- `runtime-inputs.ts` is shared by `TemplateEditorPage` and `GenerateReportDialog`; keep those flows aligned when changing row semantics.
- Current unit tests in this folder are helper/API focused; routed and feature-heavy behavior is covered primarily by Playwright flows.
- `portfolio-analytics.ts` is where quote-enriched position math belongs, not in routed screens.
