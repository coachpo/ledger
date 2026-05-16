# FRONTEND SHARED COMPONENTS GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/components/AGENTS.md`.

## OVERVIEW
`src/components/shared/` holds reusable components and helper schemas used across multiple feature areas. This folder is where cross-feature UI belongs once it has real reuse beyond a single route.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are retired/archive context, not live acceptance paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Error containment | `error-boundary.tsx`, `error-boundary-fallback.tsx` | route-safe fallback UI |
| Generic tables | `data-table.tsx`, `data-table-column-header.tsx` | reusable TanStack table wrappers |
| Summary metrics | `metric-card.tsx` | consistent KPI card layout |
| Shared field logic | `form-schemas.ts` | reusable Zod validation snippets for portfolio, balance, position, and trading forms |
| Search/select UI | `searchable-select.tsx` | command-style picker used by feature forms |
| Row-card inventory UI | `resource-row-card.tsx` | compact inventory cards used by portfolio, template, and run lists |

## CONVENTIONS
- Keep components generic enough to serve multiple features; pass feature-specific labels, callbacks, and columns from callers.
- Shared validation snippets belong in `form-schemas.ts` when they are reused across preserved product forms or dialogs.
- Error-boundary components stay UI-focused; logging or recovery policy belongs in higher-level app code.
- Keep shared helpers presentational; request logic and route ownership stay in pages, hooks, or feature folders.

## ANTI-PATTERNS
- Do not embed portfolio-only, template-only, report-only, or agent-platform request logic in this folder.
- Do not turn a one-off route widget into a shared component before a second real use case exists.
- Do not hard-code API types or query keys inside reusable table/search wrappers.
- Do not duplicate form validation that already exists in `form-schemas.ts`.

## NOTES
- Shared schemas here are the canonical place for cross-route validation rules that are still reused after the cutover.
- This folder no longer owns retired orchestration, Studio, Tryout, or runtime-v2 helper surfaces.
