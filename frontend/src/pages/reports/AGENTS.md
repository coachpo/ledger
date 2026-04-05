# FRONTEND REPORTS GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`. This file only covers `src/pages/reports/`.

## OVERVIEW
`src/pages/reports/` owns the routed report inventory and report detail experience: generate from template, upload markdown, group/search/sort the inventory, render/edit content, download files, and delete snapshots.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Report inventory | `list.tsx` | list query, generate/upload dialogs, source badges, delete flow, dropdown actions |
| Report detail | `detail.tsx` | markdown read mode, local textarea edit mode, download button |
| Report grouping logic | `../../lib/report-grouping.ts` | search, group-by, and sort helpers for the inventory |
| Shared generation dialog | `../../components/forms/generate-report-dialog.tsx` | template selection plus optional runtime inputs |
| Report hooks | `../../hooks/use-reports.ts` | list/detail queries plus compile/upload/update/delete mutations |
| Template-driven generation | `../templates/editor.tsx` | saved templates can generate reports directly from the editor |
| Report API contract | `../../lib/api/reports.ts`, `../../lib/types/report.ts` | slug-based endpoints, metadata, download URL helper |
| E2E coverage | `../../../e2e/reports.spec.ts` | sidebar nav, generate, edit, download, delete, editor shortcut |

## CONVENTIONS
- Route params use report `slug`, not numeric ids.
- `list.tsx` owns search text, group-by mode, cards/table mode, collapsed groups, and sort state; grouping stays a page concern backed by `report-grouping.ts` helpers.
- `list.tsx` combines `useReports()` with `useTemplates()` so report generation can stay template-driven without duplicating compile logic.
- Report generation from the list uses `GenerateReportDialog`, so optional runtime inputs flow through the same row helpers as the template editor.
- Markdown uploads send `multipart/form-data` with `.md` file content plus optional `author`, `description`, and comma-separated `tags` metadata.
- `detail.tsx` renders markdown with `react-markdown` + `remark-gfm` in read mode and switches to a plain textarea for direct content edits.
- Native markdown downloads always use `downloadReportUrl()` from the API layer instead of hand-built links.
- Report pages own toasts and route navigation; hooks only manage server-state mutation/query behavior.
- `list.tsx` surfaces three live report sources (`compiled`, `uploaded`, `external`) with source badges; upload slug autofill is only a suggestion and the backend remains authoritative on normalization and uniqueness.

## ANTI-PATTERNS
- Do not navigate or fetch reports by numeric id; the routed surface is slug-based.
- Do not reimplement compile, upload, or delete requests inside the pages when `use-reports.ts` already wraps them.
- Do not fork report inventory grouping/search logic into ad-hoc inline utilities when `report-grouping.ts` already models the view rules.
- Do not treat compiled reports as live templates; edits change stored markdown content only.
- Do not hard-code report download paths or upload validation rules in the pages.
- Do not move report placeholder or template-editor behavior into this folder; that contract belongs to templates, hooks, and the backend compiler.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm build
pnpm test:e2e --grep Reports
```

## NOTES
- `list.tsx` auto-suggests an upload slug from the selected filename but the backend remains the authority on slug validity and uniqueness.
- `detail.tsx` keeps edit mode local and invalidates both report list/detail queries after a successful save.
- `reports.spec.ts` is the high-signal regression file for this folder because it covers sidebar navigation, generation, detail editing, download headers, and delete cleanup.
