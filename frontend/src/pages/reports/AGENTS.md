# FRONTEND REPORTS PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW

`src/pages/reports/` owns the report inventory and slug-addressed detail routes. The list page handles search, grouping, view mode, batch actions, upload, and template-driven generation, while the detail page handles markdown viewing, editing, and downloads for a single persisted report snapshot.

## WHERE TO LOOK

| Task                    | Location                                            | Notes                                                                                    |
| ----------------------- | --------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Report inventory        | `list.tsx`                                          | search, grouping, cards/table views, upload, generate, batch selection, and delete flows |
| Report detail           | `detail.tsx`                                        | slug-based lookup, markdown rendering, inline edit/save, and download action             |
| Query + mutation policy | `../../hooks/use-reports.ts`                        | list/detail invalidation, compile, upload, update, single delete, and batch delete       |
| Grouping/search helpers | `../../lib/report-grouping.ts`                      | source labels, filter/group/sort behavior, and table/card consistency                    |
| Shared generation UI    | `../../components/forms/generate-report-dialog.tsx` | template-driven report creation with runtime inputs                                      |
| Focused tests           | `source-label.test.tsx`                             | Agent/uploaded source labels, batch delete behavior, and slug-route detail checks        |

## CONVENTIONS

- Reports stay slug-addressed end to end. Route params, download links, and hook invalidation should all key off `slug`, not numeric ids.
- `list.tsx` owns search text, group/view state, collapsed groups, and selected slugs; request policy stays in `use-reports.ts`.
- Use `downloadReportUrl()` for downloads and `getReportSourceLabel()` for source badges instead of rebuilding either concern in the route.
- Upload, generate, single-delete, and batch-delete flows should all resolve back through list invalidation so cards and table views stay in sync.
- The detail page may edit only report content; immutable report identity stays in the route header and badges.
- Keep source badges aligned with the shared grouping helpers so list and detail surfaces agree on labels such as Agent and Uploaded.
- The report list is an extension-owned inventory route with `route-reports-list`, scroll shell, loading/ready/error/empty/filtered-empty/disabled-extension states, grouped cards/table views, labeled search, and explicit upload/generate actions.
- Report card and table navigation must stay as visible links. Sorting, selection, menus, upload, generate, edit, save, and delete remain buttons or form controls.
- Browser coverage must include a seeded report flow plus representative empty and API-error list states so finance inventory failures stay user-owned.

## ANTI-PATTERNS

- Do not derive report routes, batch actions, or downloads from numeric ids.
- Do not reimplement grouping, source-label, or selection logic outside the shared helpers and route state already here.
- Do not move upload/generate/delete request logic into child UI components when the route and hooks already own it.
- Do not add dedicated “proves not” tests for ordinary removal-only report UI changes; manual confirmation is enough unless the absence itself is a shipped contract.

## VALIDATION

```bash
cd frontend
pnpm test:run src/pages/reports/source-label.test.tsx
pnpm lint
pnpm typecheck
pnpm build
```
