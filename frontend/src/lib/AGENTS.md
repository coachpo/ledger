# FRONTEND LIB GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This file only covers `src/lib/`.

## OVERVIEW
`src/lib/` owns the frontend API contract, query-key naming, derived portfolio analytics, formatting helpers, markdown formatting, report grouping helpers, runtime-input row helpers, and shared type definitions for portfolios, market data, templates, reports, extensions, Memory, and the current agent-platform domains.

Extension model: statically resident extension state.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

## CHILD DOCS
- `api/AGENTS.md` — resource request helpers and upload/download boundaries
- `types/AGENTS.md` — shared TypeScript wire contracts and enum-like unions
- `platform-authoring/AGENTS.md` — pure schema/value/ref/workflow/agent authoring helpers

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| HTTP wrapper / error mapping | `api-client.ts` | `request()`, `requestPlatform()`, `ApiRequestError`, URL helpers, CSV form-data helpers |
| API endpoint functions | `api/*.ts` | domain-specific modules for portfolios, balances, positions, trading operations, market data, templates, reports, extensions, Memory, and agent-platform resources |
| Shared wire types | `types/*.ts` | domain-specific type definitions for preserved product, extension state, Memory, and platform routes |
| Query key factory | `query-keys.ts` | hierarchical keys, param normalization, and preserved-product plus platform/extension cache namespaces |
| Portfolio analytics | `portfolio-analytics.ts` | quote enrichment, market value, PnL, allocation |
| Display formatting | `format.ts` | currency, decimal, percent, date/datetime, compact numbers |
| Markdown formatting | `markdown-format.ts` | Prettier-backed markdown normalization for the template editor |
| Runtime input helpers | `runtime-inputs.ts` | row ids, row-to-map conversion, shared editor/report-generation helpers |
| Platform authoring helpers | `platform-authoring/AGENTS.md` | schema/value/ref/workflow/agent IR, codecs, factories, validation |
| Report grouping | `report-grouping.ts` | report list filtering, grouping, and sort helpers |
| Unit coverage | `api.test.ts`, `query-keys.test.ts`, `portfolio-analytics.test.ts`, `format.test.ts`, `markdown-format.test.ts` | contract and helper regressions |

## CONVENTIONS
- `api-client.ts` is the only place that should know the base URL, query-string encoding, and error-envelope parsing.
- `api-client.ts` falls back to `http://127.0.0.1:8000/api/v1` only when `VITE_API_BASE_URL` is absent; `start.sh` and Playwright override that value for real runs.
- Domain-specific API functions live in `api/*.ts` modules, organized by resource type.
- Wire decimals remain strings until shared format/analytics helpers convert them for display math.
- `query-keys.ts` normalizes ids as strings, extension keys as strings, symbol lists as trimmed/deduplicated/sorted arrays where relevant, and history params so cache keys stay stable across callers.
- `invalidatePortfolioScope()` is the default invalidation path for portfolio-scoped mutations; reports, extension state, and platform resources use their own namespaces.
- Report flows use `queryKeys.reports.*`; `downloadReportUrl()` stays in the API layer because it builds the absolute file URL from the configured API base.
- `runtime-inputs.ts` is the shared translator between editable key/value rows and trimmed `TemplateRuntimeInputs` maps for preview and report generation.
- `report-grouping.ts` is frontend-only derived-view logic; backend report endpoints stay flat while grouping/search/sort are composed locally.
- Platform flows use `requestPlatform()`-backed helpers and `queryKeys.platform.*`; keep route-specific polling, Memory access gating, extension-state filtering, or mutation policy in hooks rather than embedding it in pages.
- Report detail queries are slug-scoped, not numeric-id scoped, even though some shared helper signatures still use generic `IdParam` naming.

## ANTI-PATTERNS
- Do not hard-code endpoint paths or duplicate `request()` / `requestPlatform()` behavior in hooks/components.
- Do not bypass `api-client.ts` and call `fetch` directly.
- Do not create API functions outside the `api/*.ts` domain modules.
- Do not invent new query-key shapes outside `query-keys.ts`.
- Do not duplicate backend contract types when `types/*.ts` already exposes them.
- Do not change template, CSV, error-envelope, report, extension, Memory, or platform contract shapes here without updating the backend contract and the calling hooks/pages.
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
- Current unit tests in this folder are helper/API focused; routed and feature-heavy behavior is covered primarily by Playwright and targeted page tests.
- `portfolio-analytics.ts` is where quote-enriched position math belongs, not in routed screens.
