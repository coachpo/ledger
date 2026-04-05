# FRONTEND SHARED COMPONENTS GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/components/AGENTS.md`.

## OVERVIEW
`src/components/shared/` holds reusable components and helper schemas used across multiple feature areas. This folder is where cross-feature UI belongs once it has real reuse beyond a single route.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Error containment | `error-boundary.tsx`, `error-boundary-fallback.tsx` | route-safe fallback UI |
| Generic tables | `data-table.tsx`, `data-table-column-header.tsx` | reusable TanStack table wrappers |
| Summary metrics | `metric-card.tsx` | consistent KPI card layout |
| Shared field logic | `form-schemas.ts` | reusable Zod validation snippets, including backtest configuration rules |
| Search/select UI | `searchable-select.tsx` | command-style picker used by feature forms |

## CONVENTIONS
- Keep components generic enough to serve multiple features; pass feature-specific labels, callbacks, and columns from callers.
- Shared validation snippets belong in `form-schemas.ts` when they are reused across dialogs or routes; `backtestCreateFormSchema` is the current multi-section example and now validates `webhookUrl`, `webhookTimeout`, benchmark selection, plus the shared text/slug/numeric patterns from this file.
- Error-boundary components stay UI-focused; logging or recovery policy belongs in higher-level app code.

## ANTI-PATTERNS
- Do not embed portfolio-only, template-only, or report-only request logic in this folder.
- Do not turn a one-off route widget into a shared component before a second real use case exists.
- Do not hard-code API types or query keys inside reusable table/search wrappers.
